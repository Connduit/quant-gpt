"""Bounded Optuna/MLflow futures research using the existing experiment supervisor."""

import fcntl
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import optuna
import polars as pl
import yaml

from quantlab.discovery.common import code_version, fingerprint, read_json, write_json
from quantlab.discovery.config import Resources, distribution
from quantlab.discovery.engine import ExperimentEngine
from quantlab.futures.contracts import contract_from_dict
from quantlab.futures.features import FEATURE_GROUPS, build_futures_dataset, intraday_features
from quantlab.futures.storage import FuturesStore
from quantlab.research.config import strict
from quantlab.statistical.holdout import HoldoutVault
from quantlab.statistical.statistics import deflated_sharpe, fdr_adjust, sharpe_probability


def load_futures_research(path):
    path = Path(path).resolve()
    doc = yaml.safe_load(path.read_text())
    strict(
        doc,
        (
            "study",
            "data",
            "search",
            "validation",
            "strategy",
            "execution",
            "risk",
            "resources",
            "initial_cash",
            "overnight",
        ),
        "futures research",
    )
    strict(doc["study"], ("name", "seed", "max_trials", "max_wall_seconds"), "futures study")
    strict(doc["data"], ("store", "snapshots", "holdout_start", "holdout_end"), "futures data")
    strict(
        doc["search"],
        (
            "models",
            "feature_sets",
            "targets",
            "horizons",
            "decision_minutes",
            "strategy",
            "thresholds",
            "instruments",
        ),
        "futures search",
    )
    trials = doc["study"].get("max_trials", 4)
    wall = doc["study"].get("max_wall_seconds", 900)
    if type(trials) is not int or not 1 <= trials <= 100 or not 10 <= wall <= 86400:
        raise ValueError("Bound futures trial/wall budgets")
    if not doc["search"]["feature_sets"] or not doc["search"]["targets"]:
        raise ValueError("Nonempty feature sets and targets required")
    for groups in doc["search"]["feature_sets"].values():
        if not groups or set(groups) - set(FEATURE_GROUPS):
            raise ValueError("Unknown feature group")
    if set(doc["search"]["targets"]) - {
        "forward_return",
        "direction",
        "volatility_adjusted",
        "breakout_continuation",
    }:
        raise ValueError("Unknown futures target")
    if not doc["search"]["horizons"] or set(doc["search"]["horizons"]) - {5, 15, 60}:
        raise ValueError("Unsupported minute horizon")
    if not doc["search"].get("decision_minutes") or set(doc["search"]["decision_minutes"]) - {
        1,
        5,
        15,
    }:
        raise ValueError("Unsupported decision timeframe")
    if not doc["search"]["models"] or set(doc["search"]["models"]) - {
        "ridge",
        "logistic",
        "random_forest",
        "lightgbm",
        "xgboost",
    }:
        raise ValueError("Unsupported CPU model")
    for params in doc["search"]["models"].values():
        if set(params) & {"n_jobs", "random_state", "device", "seed", "nthread", "num_threads"}:
            raise ValueError("CPU/seed overrides prohibited")
        for space in params.values():
            distribution(space)
    allowed = {
        "threshold",
        "contracts_per_trade",
        "maximum_holding_minutes",
        "stop_loss",
        "take_profit",
        "regime",
        "position_sizing",
        "roll_method",
        "roll_days",
    }
    strict(doc.get("strategy", {}), allowed, "futures strategy")
    strict(doc["search"].get("strategy", {}), allowed, "futures strategy spaces")
    for space in doc["search"].get("strategy", {}).values():
        distribution(space)
    for space in doc["search"].get("thresholds", {}).values():
        distribution(space)
    strict(
        doc.get("validation", {}),
        (
            "training_sessions",
            "validation_sessions",
            "test_sessions",
            "expanding",
            "embargo_minutes",
            "gap_minutes",
        ),
        "futures validation",
    )
    cutoff = datetime.fromisoformat(str(doc["data"]["holdout_start"]))
    if cutoff.tzinfo is None:
        raise ValueError("Aware futures holdout timestamp required")
    doc["data"]["store"] = str((path.parent / doc["data"]["store"]).resolve())
    Resources(**doc.get("resources", {}))
    return doc


def _space(trial, name, spec):
    if spec["type"] == "categorical":
        return trial.suggest_categorical(name, spec["choices"])
    kwargs = {k: spec[k] for k in ("step", "log") if k in spec}
    return (trial.suggest_int if spec["type"] == "int" else trial.suggest_float)(
        name, spec["low"], spec["high"], **kwargs
    )


def prepare_futures(doc, root, *, holdout_vault_path=None):
    from quantlab.futures.evaluation import sealed_data

    root = Path(root)
    version = code_version()
    store = FuturesStore(doc["data"]["store"])
    frames = []
    metadata = {}
    contracts = {}
    for identifier in doc["data"]["snapshots"]:
        m = store.manifest(identifier)
        if m["quality"]["minutes"] != 1:
            raise ValueError(
                "Research uses canonical one-minute bars; decision cadences are separate"
            )
        c = contract_from_dict(m["contract"])
        contracts[c.identifier] = c
        metadata[identifier] = m
        observed = store.read(identifier)
        from quantlab.futures.calendar import calendar_from_dict

        calendar = calendar_from_dict(
            m["quality"].get("calendar_definition", {"mode": m["quality"]["session_mode"]})
        )
        for session in observed["session_date"].unique():
            expected = {stamp for stamp in calendar.expected(session) if stamp < c.last_trade}
            actual = set(observed.filter(pl.col("session_date") == session)["timestamp"].to_list())
            if actual != expected:
                raise ValueError(
                    "Statistical futures research requires complete configured contract sessions"
                )
        frames.append(observed)
    if len({m["synthetic"] for m in metadata.values()}) != 1:
        raise ValueError("Do not mix real and fixture futures")
    frame = pl.concat(frames, how="diagonal_relaxed").sort("timestamp", "contract")
    cutoff = datetime.fromisoformat(str(doc["data"]["holdout_start"]))
    if (
        "settlement_known_at" in frame.columns
        and frame["settlement_known_at"].drop_nulls().len()
        and frame["settlement_known_at"].max() >= cutoff
    ):
        raise ValueError("Protected settlement data cannot enter research")
    if frame["available_at"].max() >= cutoff:
        raise ValueError("Futures snapshots include protected holdout")
    base = {
        "asset_class": "futures",
        "source_sha256": version["source_sha256"],
        "git_commit": version["git_commit"],
        "holdout_start": cutoff.isoformat(),
        "synthetic": next(iter(metadata.values()))["synthetic"],
        "hypothesis": (
            "Bounded futures ML vs explicit conventional controls; no profitability assumption"
        ),
        "initial_cash": str(doc.get("initial_cash", "100000")),
        "overnight": doc.get("overnight", "flat_rth"),
        "execution": doc.get("execution", {}),
        "risk": doc.get("risk", {}),
        "training_sessions": doc.get("validation", {}).get("training_sessions", 1),
        "validation_sessions": doc.get("validation", {}).get("validation_sessions", 1),
        "test_sessions": doc.get("validation", {}).get("test_sessions", 1),
        **doc.get("validation", {}),
    }
    seal_id = fingerprint(
        {"metadata": metadata, "code": version["source_sha256"], "holdout": cutoff, "schema": 1}
    )
    sealed = root / "sealed" / seal_id
    sealed.mkdir(parents=True, exist_ok=True)
    if not (sealed / "seal.json").exists():
        mode = next(iter(metadata.values()))["quality"]["session_mode"]
        features = intraday_features(
            frame, annual_minutes_per_session=390 if mode == "rth" else 1380
        )
        common, _, _ = build_futures_dataset(
            frame,
            holdout_start=cutoff,
            horizon=60,
            groups=tuple(FEATURE_GROUPS),
            precomputed_features=features,
        )
        frame.write_parquet(sealed / "bars.parquet")
        features.write_parquet(sealed / "features.parquet")
        common.select("contract", "prediction_at").write_parquet(sealed / "common-keys.parquet")
        files = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sealed.glob("*.parquet")
        }
        write_json(
            sealed / "seal.json",
            {
                "seal_id": seal_id,
                "source_sha256": version["source_sha256"],
                "synthetic": base["synthetic"],
                "snapshots": metadata,
                "contracts": {k: c.as_dict() for k, c in contracts.items()},
                "calendar": next(iter(metadata.values()))["quality"].get(
                    "calendar_definition",
                    {"mode": next(iter(metadata.values()))["quality"]["session_mode"]},
                ),
                "files_sha256": files,
            },
        )
    base.update(
        sealed_dir=str(sealed.resolve()),
        seal_id=seal_id,
        seal_sha256=hashlib.sha256((sealed / "seal.json").read_bytes()).hexdigest(),
    )
    sealed_data(base)
    vault = HoldoutVault(holdout_vault_path or root.parent / "holdout-vault.sqlite")
    manifest = {
        "sources": {
            m["contract"]["identifier"]: f"{m['provider']}:{m['source']}" for m in metadata.values()
        },
        "start": cutoff.isoformat(),
        "end": str(doc["data"].get("holdout_end", cutoff.isoformat())),
        "purpose": "futures reserved period not downloaded/evaluated",
    }
    identifier = vault.register(manifest)
    if vault.status(identifier)["state"] != "SEALED":
        raise ValueError("Futures holdout already consumed/authorized")
    return base, vault, identifier


def run_futures_research(
    config_path, output, *, resume=False, stop_event=None, history_roots=(), holdout_vault_path=None
):
    doc = load_futures_research(config_path)
    root = Path(output).resolve()
    if root.exists() and not resume:
        raise ValueError("Research output exists; choose a new directory or explicit resume")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "controller.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Futures controller already running") from exc
        started = time.monotonic()
        base, vault, holdout_id = prepare_futures(doc, root, holdout_vault_path=holdout_vault_path)
        resources = Resources(**doc.get("resources", {}))
        engine = ExperimentEngine(root / "experiments", doc["study"]["name"], resources)
        if stop_event is not None:
            engine.cancel = stop_event
        policy = fingerprint(
            {"configuration": doc, "code": base["source_sha256"], "seal": base["seal_sha256"]}
        )
        elapsed = engine.registry.study(doc["study"]["name"], policy)
        deadline = started + max(0, doc["study"].get("max_wall_seconds", 900) - elapsed)
        optimizer = optuna.create_study(
            study_name=doc["study"]["name"],
            storage=f"sqlite:///{root / 'optuna.sqlite'}",
            direction="maximize",
            load_if_exists=True,
            sampler=optuna.samplers.RandomSampler(seed=doc["study"].get("seed", 42)),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=2, n_warmup_steps=1),
        )
        for trial in optimizer.get_trials(states=(optuna.trial.TrialState.RUNNING,)):
            optimizer.tell(trial.number, state=optuna.trial.TrialState.FAIL)
            engine.registry.link(
                doc["study"]["name"],
                trial.number,
                None,
                None,
                "INTERRUPTED",
                "orphan optimizer trial preserved",
            )
        try:
            while (
                len(optimizer.trials) < doc["study"].get("max_trials", 4)
                and time.monotonic() < deadline
                and not engine.cancel.is_set()
            ):
                optimizer.sampler = optuna.samplers.RandomSampler(
                    seed=doc["study"].get("seed", 42) + len(optimizer.trials)
                )
                trial = optimizer.ask()
                search = doc["search"]
                target = trial.suggest_categorical("target", search["targets"])
                classification = target in ("direction", "breakout_continuation")
                models = [m for m in search["models"] if m != "ridge" or not classification]
                models = [m for m in models if m != "logistic" or classification]
                if not models:
                    optimizer.tell(trial, state=optuna.trial.TrialState.FAIL)
                    engine.registry.link(
                        doc["study"]["name"],
                        trial.number,
                        None,
                        None,
                        "FAILED",
                        "no compatible model",
                    )
                    continue
                available_products = sorted(
                    {
                        m["contract"]["product"]
                        for m in read_json(Path(base["sealed_dir"]) / "seal.json")[
                            "snapshots"
                        ].values()
                    }
                )
                requested = search.get("instruments", available_products)
                if not requested or set(requested) - set(available_products):
                    raise ValueError("Requested futures product has no snapshot")
                instrument = trial.suggest_categorical("instrument", requested)
                model = trial.suggest_categorical(
                    "model.classification" if classification else "model.regression", models
                )
                groups = trial.suggest_categorical("feature_set", list(search["feature_sets"]))
                definition = {
                    **base,
                    "target": target,
                    "instrument": instrument,
                    "horizon": trial.suggest_categorical("horizon", search["horizons"]),
                    "groups": search["feature_sets"][groups],
                    "decision_minutes": trial.suggest_categorical(
                        "decision_minutes", search["decision_minutes"]
                    ),
                    "model": {
                        "type": model,
                        "objective": "classification" if classification else "regression",
                        "seed": doc["study"].get("seed", 42),
                        "parameters": {
                            k: _space(trial, f"{model}.{k}", v)
                            for k, v in search["models"][model].items()
                        },
                    },
                    "strategy": {
                        **doc.get("strategy", {}),
                        **{
                            k: _space(trial, f"strategy.{k}", v)
                            for k, v in search.get("strategy", {}).items()
                        },
                    },
                }
                if target in search.get("thresholds", {}):
                    definition["strategy"]["threshold"] = _space(
                        trial, f"threshold.{target}", search["thresholds"][target]
                    )
                result = engine.run(
                    definition, trial=trial, role="futures_trial", deadline=deadline
                )
                attempt = result["attempt"]
                payload = result["result"]
                state = (
                    optuna.trial.TrialState.PRUNED
                    if attempt["status"] == "PRUNED"
                    else optuna.trial.TrialState.COMPLETE
                    if payload
                    else optuna.trial.TrialState.FAIL
                )
                optimizer.tell(
                    trial,
                    payload["summary"]["objective"]
                    if payload and state == optuna.trial.TrialState.COMPLETE
                    else None,
                    state=state,
                )
                engine.registry.link(
                    doc["study"]["name"],
                    trial.number,
                    result["experiment_id"],
                    attempt["id"],
                    attempt["status"],
                    attempt.get("reason"),
                )
            # Each conventional control is also a separately tracked hypothesis, including failures.
            from itertools import product

            products = sorted(
                {
                    m["contract"]["product"]
                    for m in read_json(Path(base["sealed_dir"]) / "seal.json")["snapshots"].values()
                }
            )
            for instrument, family in product(
                products, ("vwap", "opening_range", "momentum", "regime", "buy_hold")
            ):
                if engine.cancel.is_set() or time.monotonic() >= deadline:
                    break
                definition = {
                    **base,
                    "strategy_family": family,
                    "instrument": instrument,
                    "target": "forward_return",
                    "horizon": 5,
                    "groups": list(FEATURE_GROUPS),
                    "decision_minutes": 1,
                    "model": {
                        "type": "none",
                        "objective": "regression",
                        "seed": doc["study"].get("seed", 42),
                        "parameters": {},
                    },
                    "strategy": {
                        "threshold": 0 if family == "buy_hold" else 0.0005,
                        "maximum_holding_minutes": 1440 if family == "buy_hold" else 15,
                        "stop_loss": 0.99 if family == "buy_hold" else 0.003,
                        "take_profit": 0.99 if family == "buy_hold" else 0.006,
                    },
                }
                engine.run(definition, role="futures_baseline", deadline=deadline)
        finally:
            engine.registry.add_elapsed(doc["study"]["name"], time.monotonic() - started)
        from quantlab.statistical.pipeline import history

        recorded_history = history([root.parent, *map(Path, history_roots)])
        rows = engine.registry.rows()
        results = []
        failed = []
        for row in rows:
            if row["result"]:
                payload = json.loads(row["result"])
                # Daily portfolio observations, not independent-minute claims.
                daily = []
                for window in payload["windows"]:
                    bt = read_json(
                        Path(row["artifact_path"]) / f"window-{window['number']}" / "backtest.json"
                    )
                    daily.extend(r["daily_return"] for r in bt["daily_equity"])
                statistics = {
                    "status": "insufficient_daily_observations",
                    "daily_observations": len(daily),
                    "probabilistic_sharpe": None,
                    "deflated_sharpe": None,
                    "one_sided_p": 1.0,
                }
                if len(daily) >= 20 and all(v is not None and v > -1 for v in daily):
                    psr = sharpe_probability(daily)
                    dsr = deflated_sharpe(daily, max(1, recorded_history["unique_hypotheses"]))
                    statistics.update(
                        status="approximate_daily_diagnostics",
                        probabilistic_sharpe=psr,
                        deflated_sharpe=dsr,
                        one_sided_p=1 - psr["probability"]
                        if psr.get("probability") is not None
                        else 1.0,
                    )
                results.append(
                    {
                        "experiment_id": row["experiment_id"],
                        "attempt_id": row["id"],
                        "role": row["role"],
                        "status": payload["research_status"],
                        "summary": payload["summary"],
                        "statistics": statistics,
                        "artifact_path": row["artifact_path"],
                        "definition": payload["definition"],
                    }
                )
            else:
                failed.append(
                    {k: row[k] for k in ("id", "experiment_id", "status", "reason", "role")}
                )
        adjusted = fdr_adjust(
            [r["statistics"]["one_sided_p"] for r in results],
            family_size=max(len(results), recorded_history["unique_hypotheses"]),
        )
        for r, q in zip(results, adjusted, strict=True):
            r["statistics"]["fdr_by_q"] = q
        report = {
            "configuration": doc,
            "code": code_version(),
            "counts": engine.registry.counts(),
            "recorded_history": recorded_history,
            "trial_history": engine.registry.links(),
            "results": results,
            "failed": failed,
            "holdout": vault.status(holdout_id),
            "final_holdout": "not_downloaded_or_evaluated",
            "paper_trading_shortlist": [],
            "synthetic": base["synthetic"],
            "limitations": [
                "Archival sample is too short for independent-session significance.",
                (
                    "Margins and fees are explicit assumptions, "
                    "not certified historical broker/exchange rates."
                ),
                "Continuous charts are not execution prices; actual contract transactions only.",
                "Intraday bootstrap does not make repeated-minute observations independent.",
                "No live futures trading is implemented or enabled.",
            ],
        }
        write_json(root / "research.json", report)
        return report

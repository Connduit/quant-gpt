"""Validation over fresh verified development data and complete recorded research history."""

import copy
import csv
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import numpy as np

from quantlab.discovery.common import code_version, fingerprint, read_json, write_json
from quantlab.discovery.data import _materialize, load_feeds, verify_seal
from quantlab.discovery.engine import ExperimentEngine
from quantlab.discovery.registry import Registry
from quantlab.research.config import load_experiment
from quantlab.statistical.config import load_config
from quantlab.statistical.holdout import HoldoutVault
from quantlab.statistical.statistics import (
    deflated_sharpe,
    effective_sample_size,
    fdr_adjust,
    max_test_bootstrap,
    search_complexity,
    sharpe_probability,
    uncertainty,
)


def history(roots):
    identities, attempts, trials, files = set(), 0, 0, []
    for root in roots:
        paths = (
            [root / "registry.sqlite"]
            if (root / "registry.sqlite").exists()
            else sorted(root.rglob("registry.sqlite"))
        )
        for path in paths:
            if str(path.resolve()) in files:
                continue
            files.append(str(path.resolve()))
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
                identities.update(r[0] for r in c.execute("SELECT id FROM experiments"))
                attempts += c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
                trials += c.execute("SELECT COUNT(*) FROM trial_links").fetchone()[0]
    return {
        "unique_hypotheses": len(identities),
        "attempts": attempts,
        "optimizer_trials": trials,
        "registry_files": files,
        "scope": (
            "all supplied registries including failures/prunes/variants; "
            "external/unrecorded searches unknown"
        ),
    }


def prepare_development(config, output):
    experiment = load_experiment(config["research_config"])
    manifest = config["holdout"]
    declared_sources = {
        s: v["snapshot_id"] if isinstance(v, dict) else v for s, v in experiment.snapshots.items()
    }
    if manifest["sources"] != declared_sources or str(manifest["start"]) != str(
        experiment.holdout_start
    ):
        raise ValueError("Holdout manifest must match the original research snapshots and cutoff")
    root = config["verified_inputs"]
    quality = read_json(root / "data_quality.json")
    from quantlab.data.providers.lean import verify_existing_import

    dates = next(iter(quality["quality"].values()))
    verify_existing_import(
        root,
        date.fromisoformat(dates["start"]),
        date.fromisoformat(dates["end"]),
        tuple(quality["snapshots"]),
    )
    if date.fromisoformat(dates["end"]) >= experiment.holdout_start:
        raise ValueError("Validation inputs must physically end before the final holdout")
    experiment = replace(experiment, data_dir=root, snapshots=quality["snapshots"])
    feeds = load_feeds(experiment, root)
    if any(b.session_date >= experiment.holdout_start for f in feeds.values() for b in f.bars):
        raise ValueError("Reserved holdout reached development adapter")
    version = code_version()
    identity = fingerprint(
        {
            "snapshots": quality["snapshots"],
            "code": version,
            "features": asdict(experiment.features),
            "holdout": config["holdout"],
        }
    )
    destination = output / "sealed" / identity
    destination.mkdir(parents=True)
    _materialize(feeds, experiment, (1, 5, 10), destination, identity, version["source_sha256"])
    seal = verify_seal(destination)
    return destination, seal, version, quality


def candidate_paths(discovery_root):
    found = {}
    for row in Registry(discovery_root).rows():
        if row["role"] == "trial" and row["status"] in ("COMPLETE", "REJECTED") and row["result"]:
            found.setdefault(row["experiment_id"], row)
    return list(found.values())


def robustness_definitions(definition, limit):
    scenarios = []
    for field in ("commission_per_share", "slippage_bps"):
        d = copy.deepcopy(definition)
        d["execution"][field] = str(float(d["execution"].get(field, 0)) * 2)
        scenarios.append((f"double_{field}", d))
    d = copy.deepcopy(definition)
    d["execution_delay_sessions"] = 1
    scenarios.append(("one_session_execution_delay", d))
    d = copy.deepcopy(definition)
    d["expanding"] = not d["expanding"]
    scenarios.append(("alternative_rolling_expanding", d))
    d = copy.deepcopy(definition)
    d["validation_sessions"] = max(3, round(d["validation_sessions"] * 1.2))
    scenarios.append(("alternative_validation_period", d))
    params = definition["model"]["parameters"]
    numeric = [k for k, v in params.items() if type(v) in (int, float) and v > 0]
    key = max(numeric, key=lambda k: abs(params[k])) if numeric else None
    if key:
        d = copy.deepcopy(definition)
        d["model"]["parameters"][key] = (
            max(params[key] + 1, round(params[key] * 1.1))
            if type(params[key]) is int
            else params[key] * 1.1
        )
        scenarios.append((f"nearby_{key}", d))
    d = copy.deepcopy(definition)
    d["strategy"]["position_sizing"] = (
        "inverse_volatility" if d["strategy"]["position_sizing"] == "equal" else "equal"
    )
    scenarios.append(("alternative_position_sizing", d))
    d = copy.deepcopy(definition)
    d["strategy"]["regime_filter"] = not d["strategy"]["regime_filter"]
    scenarios.append(("alternative_market_filter", d))
    return scenarios[:limit]


def return_folds(path, holdout_start):
    result = read_json(path / "result.json")
    folds = []
    for window in result["windows"]:
        directory = path / f"window-{window['number']}" / "backtest"
        metadata = read_json(directory / "report.json")
        for relative, checksum in metadata["artifacts_sha256"].items():
            file = (directory / relative).resolve()
            if (
                not file.is_relative_to(directory.resolve())
                or hashlib.sha256(file.read_bytes()).hexdigest() != checksum
            ):
                raise ValueError(f"Backtest artifact checksum mismatch: {relative}")
        with (directory / "equity.csv").open() as f:
            rows = list(csv.DictReader(f))
        with (directory / "benchmark_equity.csv").open() as f:
            benchmark = list(csv.DictReader(f))
        if [r["session_date"] for r in rows] != [r["session_date"] for r in benchmark]:
            raise ValueError("Benchmark calendar mismatch")
        if any(r["session_date"] >= holdout_start for r in rows):
            raise ValueError("Holdout appears in research returns")
        folds.append(
            {
                "number": window["number"],
                "dates": [r["session_date"] for r in rows],
                "returns": [float(r["daily_return"]) for r in rows],
                "excess": [
                    float(r["daily_return"]) - float(b["daily_return"])
                    for r, b in zip(rows, benchmark, strict=True)
                ],
            }
        )
    flat = [d for f in folds for d in f["dates"]]
    if len(flat) != len(set(flat)) or flat != sorted(flat):
        raise ValueError("Overlapping/nonchronological walk-forward trading periods")
    return folds


def assign_status(result, diagnostics, policy, *, evidence=None):
    reasons = list(result["summary"]["rejection_reasons"])
    if result["summary"]["mean_validation_return"] <= 0:
        reasons.append("nonpositive_net_validation_return")
    if result["summary"]["mean_baseline_excess"] <= 0:
        reasons.append("no_economic_edge_over_strongest_baseline")
    if reasons:
        return "REJECTED", sorted(set(reasons))
    if (
        diagnostics.get("sessions", 0) < policy.minimum_sessions
        or diagnostics.get("effective_sessions", 0) < policy.minimum_effective_sessions
        or len(result["windows"]) < policy.minimum_folds
    ):
        return "INSUFFICIENT_EVIDENCE", ["insufficient_independent_information"]
    if (
        diagnostics.get("fdr_by_q", 1) > policy.alpha
        or diagnostics.get("familywise_p", 1) > policy.alpha
        or diagnostics.get("deflated_sharpe", {}).get("probability") is None
        or diagnostics["deflated_sharpe"]["probability"] < 1 - policy.alpha
        or not diagnostics.get("all_excess_intervals_positive", False)
        or not diagnostics.get("robustness_passed", False)
    ):
        return "INSUFFICIENT_EVIDENCE", ["selection_adjusted_uncertainty_or_robustness_failed"]
    coverage = result.get("action_coverage", {})
    if (
        not coverage
        or not all(v["complete"] for v in coverage.values())
        or not evidence
        or evidence.get("historical_universe_certified") is not True
        or evidence.get("independent_selection_period") is not True
    ):
        return "REQUIRES_FURTHER_TESTING", ["data_certification_and_independent_selection_required"]
    return "VALIDATED_FOR_PAPER_TRADING", []


def aligned_family(candidates):
    # Intersect actual OOS sessions; preserve original fold blocks and cross-candidate dependence.
    lookups = []
    for candidate in candidates:
        lookups.append(
            {
                d: r
                for f in candidate["fold_returns"]
                for d, r in zip(f["dates"], f["excess"], strict=True)
            }
        )
    common = set.intersection(*(set(x) for x in lookups))
    matrices = []
    dates = []
    for fold in candidates[0]["fold_returns"]:
        selected = [d for d in fold["dates"] if d in common]
        if selected:
            dates.extend(selected)
            matrices.append(np.asarray([[lookup[d] for lookup in lookups] for d in selected]))
    return matrices, dates


def run_validation(config_path, output):
    config = load_config(config_path)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Validation output exists; choose a new directory to preserve evidence")
    output.mkdir(parents=True)
    policy = config["policy"]
    deadline = time.monotonic() + policy.max_wall_seconds
    write_json(output / "configuration.json", config["configuration"])
    vault = HoldoutVault(config["verified_inputs"].parent / "holdout-vault.sqlite")
    holdout_id = vault.register(config["holdout"])
    if vault.status(holdout_id)["state"] != "SEALED":
        raise ValueError("Final holdout is no longer fresh/sealed")
    destination, seal, version, quality = prepare_development(config, output)
    engine = ExperimentEngine(output / "experiments", "statistical_validation", config["resources"])
    selected = candidate_paths(config["discovery_root"])[: policy.max_candidates]
    if not selected:
        raise ValueError("No completed discovery candidates; failures remain in history")
    candidates, failures = [], []
    for parent in selected:
        definition = json.loads(parent["definition"])
        definition.update(
            sealed_dir=str(destination),
            seal_id=seal["seal_id"],
            seal_sha256=hashlib.sha256((destination / "seal.json").read_bytes()).hexdigest(),
            source_sha256=version["source_sha256"],
            git_commit=version["git_commit"],
        )
        for name in (
            "training_sessions",
            "validation_sessions",
            "test_sessions",
            "expanding",
            "embargo_sessions",
            "gap_sessions",
            "retraining_sessions",
        ):
            definition[name] = getattr(policy, name)
        definition["hypothesis"] = f"Statistical diagnostic of {parent['experiment_id']}"
        evaluated = engine.run(
            definition, role="statistical_validation", parent_id=parent["id"], deadline=deadline
        )
        if not evaluated["result"]:
            failures.append(
                {
                    "parent_attempt": parent["id"],
                    "attempt": evaluated["attempt"],
                    "status": "INSUFFICIENT_EVIDENCE",
                }
            )
            continue
        artifact = Path(evaluated["attempt"]["artifact_path"])
        folds = return_folds(artifact, definition["holdout_start"])
        candidates.append(
            {
                "strategy_id": parent["experiment_id"],
                "parent_attempt": parent["id"],
                "attempt_id": evaluated["attempt"]["id"],
                "configuration": definition,
                "artifact_path": str(artifact),
                "result": evaluated["result"],
                "fold_returns": folds,
            }
        )
    robustness = []
    # Diagnostics of top by score, even if all candidates are rejected. Never promote on ranking.
    if candidates:
        top = max(candidates, key=lambda c: c["result"]["summary"]["score"])
        for name, definition in robustness_definitions(
            top["configuration"], policy.max_robustness_variants
        ):
            evaluated = engine.run(
                definition,
                role="statistical_robustness",
                parent_id=top["attempt_id"],
                deadline=deadline,
            )
            robustness.append(
                {
                    "scenario": name,
                    "parent_attempt": top["attempt_id"],
                    "attempt_id": evaluated["attempt"]["id"],
                    "status": evaluated["attempt"]["status"],
                    "summary": evaluated["result"]["summary"] if evaluated["result"] else None,
                }
            )
    recorded = history([*config["history_roots"], output / "experiments"])
    count = max(1, recorded["unique_hypotheses"])
    family, dates = aligned_family(candidates) if candidates else ([], [])
    usable = bool(family) and all(len(f) >= max(policy.block_lengths) for f in family)
    multiple, complexity = {}, None
    if usable:
        complexity = search_complexity(np.concatenate(family), count)
        for block in policy.block_lengths:
            multiple[str(block)] = max_test_bootstrap(
                family, replications=policy.replications, block_length=block, seed=policy.seed
            )
    raw = (
        [max(m["pvalues"][i] for m in multiple.values()) for i in range(len(candidates))]
        if usable
        else [1.0] * len(candidates)
    )
    qvalues = fdr_adjust(raw, family_size=count)
    for i, candidate in enumerate(candidates):
        folds = candidate["fold_returns"]
        returns = np.concatenate([f["returns"] for f in folds])
        excess = np.concatenate([f["excess"] for f in folds])
        diagnostics = {
            "sessions": len(returns),
            "effective_sessions": sum(effective_sample_size(f["excess"]) for f in folds),
            "probabilistic_sharpe": sharpe_probability(
                returns, effective_n=effective_sample_size(returns)
            ),
            "deflated_sharpe": deflated_sharpe(returns, count),
            "fdr_by_q": qvalues[i],
            "fdr_bh_q_sensitivity": fdr_adjust(raw, dependence=False, family_size=count)[i],
            "familywise_p": max(
                max((m["familywise_pvalues"][i] for m in multiple.values()), default=1.0),
                min(1.0, count * raw[i]),
            ),
            "mean_excess_daily_return": float(excess.mean()),
            "uncertainty": {},
            "robustness_passed": False,
        }
        # Max-t covers observed family; full-count Bonferroni is a conservative sensitivity.
        for block in policy.block_lengths:
            if all(len(f["returns"]) >= block for f in folds):
                diagnostics["uncertainty"][str(block)] = {
                    "net": uncertainty(
                        [f["returns"] for f in folds],
                        replications=policy.replications,
                        block_length=block,
                        seed=policy.seed,
                        level=policy.confidence_level,
                    ),
                    "benchmark_relative": uncertainty(
                        [f["excess"] for f in folds],
                        replications=policy.replications,
                        block_length=block,
                        seed=policy.seed,
                        level=policy.confidence_level,
                    ),
                }
        diagnostics["all_excess_intervals_positive"] = bool(diagnostics["uncertainty"]) and all(
            v["benchmark_relative"]["percentile_intervals"]["mean_daily_return"][0] > 0
            for v in diagnostics["uncertainty"].values()
        )
        own = [r for r in robustness if r["parent_attempt"] == candidate["attempt_id"]]
        diagnostics["robustness_passed"] = bool(own) and all(
            r["summary"] and r["summary"]["eligible"] for r in own
        )
        candidate["diagnostics"] = diagnostics
        candidate["status"], candidate["rejection_reasons"] = assign_status(
            candidate["result"], diagnostics, policy
        )
        candidate["robustness"] = own
        # Volatility state determined from past SPY features, never future realized returns.
        import polars as pl

        predictions = pl.read_parquet(Path(candidate["artifact_path"]) / "predictions.parquet")
        daily = (
            predictions.group_by("session_date").agg(pl.col("spy_volatility").first())
            if "spy_volatility" in predictions.columns
            else None
        )
        candidate["volatility_regimes"] = {"status": "unavailable_feature"}
        if daily is not None:
            lookup = {str(r["session_date"]): r["spy_volatility"] for r in daily.to_dicts()}
            candidate["volatility_regimes"] = {}
            for name, condition in [("high", lambda v: v >= 0.2), ("low", lambda v: v < 0.2)]:
                values = [
                    r
                    for f in folds
                    for d, r in zip(f["dates"], f["excess"], strict=True)
                    if d in lookup and condition(lookup[d])
                ]
                candidate["volatility_regimes"][name] = {
                    "sessions": len(values),
                    "mean_excess": float(np.mean(values)) if values else None,
                }
        candidate["universe_robustness"] = "not run: no certified historical membership data"
    report = {
        "schema_version": 1,
        "configuration": config["configuration"],
        "code": version,
        "history": recorded,
        "effective_search_complexity": complexity,
        "multiple_testing": multiple,
        "aligned_family_sessions": len(dates),
        "candidates": candidates,
        "failed_evaluations": failures,
        "robustness": robustness,
        "data_sources": quality,
        "holdout": vault.status(holdout_id),
        "final_holdout": "not_read_or_evaluated",
        "research_role": "reused_development_diagnostics",
        "paper_trading_shortlist": [
            c["strategy_id"] for c in candidates if c["status"] == "VALIDATED_FOR_PAPER_TRADING"
        ],
        "limitations": [
            "Repeatedly inspected development data; no independent confirmation.",
            "PSR/DSR moment and null-dispersion assumptions are approximations.",
            "Bootstrap assumes local stationarity within folds; block-size sensitivity reported.",
            "Action completeness and historical universe are not certified.",
            "Recorded history excludes unknown external/manual searches.",
            "Daily cash-equity fills omit intraday liquidity/impact; no live authorization.",
        ],
    }
    write_json(output / "validation.json", report)
    lines = [
        "# Statistical validation outcomes",
        "",
        f"Recorded hypotheses: {count}. Final holdout: not evaluated.",
        "",
        "| Candidate | Status | Sessions | BY q | Reasons |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for c in candidates:
        lines.append(
            f"| `{c['strategy_id'][:16]}` | {c['status']} | {c['diagnostics']['sessions']} | "
            f"{c['diagnostics']['fdr_by_q']:.4f} | {', '.join(c['rejection_reasons'])} |"
        )
    lines += [
        "",
        "These are selection-aware diagnostics on reused development data. "
        "No independent edge is established.",
    ]
    (output / "validation.md").write_text("\n".join(lines) + "\n")
    return report

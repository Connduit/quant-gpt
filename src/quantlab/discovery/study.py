"""Persistent Optuna ask/tell orchestration with deterministic indexed proposals."""

import fcntl
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import optuna
import psutil

from quantlab.discovery.common import fingerprint, write_json
from quantlab.discovery.config import load_study, suggest
from quantlab.discovery.data import prepare
from quantlab.discovery.engine import ExperimentEngine
from quantlab.discovery.reports import generate_report


class FixedParameters:
    def __init__(self, values):
        self.values, self.used = values, set()

    def _get(self, name):
        if name not in self.values:
            raise ValueError(f"Missing fixed parameter: {name}")
        self.used.add(name)
        return self.values[name]

    def suggest_categorical(self, name, choices):
        value = self._get(name)
        if value not in choices:
            raise ValueError(f"Out-of-space fixed parameter: {name}")
        return value

    def suggest_int(self, name, low, high, step=1, log=False):
        value = self._get(name)
        if type(value) is not int or not low <= value <= high or (value - low) % step:
            raise ValueError(f"Out-of-space fixed integer: {name}")
        return value

    def suggest_float(self, name, low, high, step=None, log=False):
        import math

        value = self._get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError(f"Out-of-space fixed float: {name}")
        if step is not None and not math.isclose(
            (value - low) / step, round((value - low) / step), abs_tol=1e-8
        ):
            raise ValueError(f"Fixed float not on step: {name}")
        return value


def definition_for_number(config, base, number):
    # Private in-memory study used for proposal only; persistent trials live in optuna.sqlite.
    proposal = optuna.create_study(
        sampler=optuna.samplers.RandomSampler(seed=(config.seed + number) % 2**32)
    )
    return suggest(proposal.ask(), config, base)


def run_single(config_path: Path, root: Path, parameters=None, reproduce_id=None):
    started = time.monotonic()
    config = load_study(config_path)
    engine = ExperimentEngine(root, config.name, config.resources)
    if reproduce_id:
        original = engine.registry.attempt(reproduce_id)
        if not original:
            raise ValueError("Unknown attempt ID")
        definition = json.loads(original["definition"])
        from quantlab.discovery.common import code_version

        if code_version()["source_sha256"] != definition["source_sha256"]:
            raise ValueError("Exact reproduction requires the recorded source code version")
    else:
        base = prepare(config, engine.root)
        if parameters is None:
            definition = definition_for_number(config, base, 0)
        else:
            fixed = FixedParameters(parameters)
            definition = suggest(fixed, config, base)
            if set(parameters) - fixed.used:
                raise ValueError("Unused/unknown fixed parameters")
    return engine.run(
        definition,
        role="reproduction" if reproduce_id else "trial",
        parent_id=reproduce_id,
        reproduce=bool(reproduce_id),
        deadline=started + config.max_wall_seconds,
    )


def run_batch(config_path: Path, root: Path, parameter_sets: list[dict]):
    started = time.monotonic()
    config = load_study(config_path)
    if not 1 <= len(parameter_sets) <= config.max_trials:
        raise ValueError("Batch exceeds configured trial budget")
    engine = ExperimentEngine(root, config.name, config.resources)
    base = prepare(config, engine.root)
    definitions = []
    for params in parameter_sets:
        fixed = FixedParameters(params)
        definitions.append(suggest(fixed, config, base))
        if set(params) - fixed.used:
            raise ValueError("Unused/unknown batch parameters")
    results = []
    deadline = started + config.max_wall_seconds
    with ThreadPoolExecutor(max_workers=config.resources.workers) as pool:
        for start in range(0, len(definitions), config.resources.workers):
            futures = [
                pool.submit(engine.run, d, slot=i, deadline=deadline)
                for i, d in enumerate(definitions[start : start + config.resources.workers])
            ]
            results.extend(f.result() for f in futures)
    generate_report(engine.root)
    return results


def run_study(config_path: Path, root: Path, resume=False):
    config = load_study(config_path)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "study.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another study controller is active in this registry") from exc
        return _run(config, config_path, root, resume)


def _run(config, config_path, root, resume):
    started = time.monotonic()
    engine = ExperimentEngine(root, config.name, config.resources)
    base = prepare(config, root)
    policy = {
        "config": asdict(config),
        "data": {k: v for k, v in base.items() if k != "git_commit"},
    }
    elapsed = engine.registry.study(config.name, fingerprint(policy))
    deadline = started + max(0, config.max_wall_seconds - elapsed)
    storage = optuna.storages.RDBStorage(
        f"sqlite:///{root / 'optuna.sqlite'}", engine_kwargs={"connect_args": {"timeout": 30}}
    )
    existing = optuna.study.get_all_study_summaries(storage)
    if any(s.study_name == config.name for s in existing) and not resume:
        raise ValueError("Study already exists; use resume")
    pruner = (
        optuna.pruners.ThresholdPruner(lower=config.prune_below, n_warmup_steps=1)
        if config.prune_below is not None
        else optuna.pruners.NopPruner()
    )
    study = optuna.create_study(
        study_name=config.name,
        storage=storage,
        direction="maximize",
        load_if_exists=resume,
        pruner=pruner,
    )
    # A stale RUNNING Optuna trial remains visible as FAIL, then a new bounded trial can retry.
    for prior in study.get_trials(states=(optuna.trial.TrialState.RUNNING,)):
        try:
            owner = psutil.Process(prior.user_attrs.get("owner_pid", -1))
            live = abs(owner.create_time() - prior.user_attrs.get("owner_start", -1)) < 0.01
        except (psutil.Error, ValueError):
            live = False
        if live:
            raise ValueError("A live controller owns an unfinished trial")
        study.tell(prior.number, state=optuna.trial.TrialState.FAIL)
        engine.registry.link(
            config.name,
            prior.number,
            prior.user_attrs.get("experiment_id"),
            prior.user_attrs.get("attempt_id"),
            "INTERRUPTED",
            "Orphaned Optuna trial recovered",
        )
    active = []
    try:
        with ThreadPoolExecutor(max_workers=config.resources.workers) as pool:
            try:
                while len(study.trials) < config.max_trials and time.monotonic() < deadline:
                    active = []
                    remaining = config.max_trials - len(study.trials)
                    for slot in range(min(config.resources.workers, remaining)):
                        number = len(study.trials)
                        study.sampler = optuna.samplers.RandomSampler(
                            seed=(config.seed + number) % 2**32
                        )
                        trial = study.ask()
                        trial.set_user_attr("owner_pid", os.getpid())
                        trial.set_user_attr("owner_start", psutil.Process().create_time())
                        definition = suggest(trial, config, base)
                        active.append(
                            (
                                trial,
                                pool.submit(
                                    engine.run,
                                    definition,
                                    slot=slot,
                                    trial=trial,
                                    deadline=deadline,
                                ),
                            )
                        )
                    # Ordered tell makes optimization history independent of worker finish order.
                    for trial, future in active:
                        outcome = future.result()
                        attempt = outcome["attempt"]
                        trial.set_user_attr("experiment_id", outcome["experiment_id"])
                        trial.set_user_attr("attempt_id", attempt["id"])
                        trial.set_user_attr("mlflow_run_id", attempt.get("run_id"))
                        trial.set_user_attr(
                            "disposition",
                            "DUPLICATE" if outcome["duplicate"] else attempt["status"],
                        )
                        trial.set_user_attr("reason", attempt.get("reason"))
                        if outcome["result"] and attempt["status"] in ("COMPLETE", "REJECTED"):
                            study.tell(trial, outcome["result"]["summary"]["objective"])
                        else:
                            study.tell(
                                trial,
                                state=optuna.trial.TrialState.PRUNED
                                if attempt["status"] == "PRUNED"
                                else optuna.trial.TrialState.FAIL,
                            )
                        engine.registry.link(
                            config.name,
                            trial.number,
                            outcome["experiment_id"],
                            attempt["id"],
                            "DUPLICATE" if outcome["duplicate"] else attempt["status"],
                            attempt.get("reason"),
                        )
                    active = []
                from quantlab.discovery.robustness import run_robustness

                run_robustness(engine, config, deadline)
            except BaseException:
                engine.cancel.set()
                for trial, future in active:
                    future.result()
                    if study.trials[trial.number].state == optuna.trial.TrialState.RUNNING:
                        study.tell(trial, state=optuna.trial.TrialState.FAIL)
                raise
    finally:
        for trial, future in active:
            if (
                future.done()
                and study.trials[trial.number].state == optuna.trial.TrialState.RUNNING
            ):
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
        engine.registry.add_elapsed(config.name, time.monotonic() - started)
    report = generate_report(root)
    report["study"] = {
        "name": config.name,
        "trials": len(study.trials),
        "max_trials": config.max_trials,
        "max_wall_seconds": config.max_wall_seconds,
        "sampler": "indexed_seeded_random",
        "elapsed_seconds": elapsed + time.monotonic() - started,
        "final_holdout": "not_accessible_to_trials",
    }
    write_json(root / "reports" / "study.json", report)
    return report

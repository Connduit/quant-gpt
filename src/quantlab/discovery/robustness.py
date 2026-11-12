"""Bounded variants get separate identities/artifacts; original results remain immutable."""

import copy
import json
import time

from quantlab.discovery.common import fingerprint, write_json
from quantlab.discovery.reports import comparison


def variants(definition, config):
    result = []
    fraction = config.robustness.get("window_fraction", 0.2)

    def add(name, changed):
        if fingerprint(changed) != fingerprint(definition):
            result.append((name, changed))

    for sign in (-1, 1):
        changed = copy.deepcopy(definition)
        changed["training_sessions"] = max(
            5, round(definition["training_sessions"] * (1 + sign * fraction))
        )
        add(f"training_window_{sign:+d}", changed)
    changed = copy.deepcopy(definition)
    changed["validation_sessions"] = max(
        3, round(definition["validation_sessions"] * (1 + fraction))
    )
    add("alternative_validation_period", changed)
    params = definition["model"]["parameters"]
    numeric = next((name for name, value in params.items() if type(value) in (float, int)), None)
    if numeric:
        space = config.models[definition["model"]["type"]][numeric]
        for sign in (-1, 1):
            changed = copy.deepcopy(definition)
            value = params[numeric] * (1 + sign * config.robustness.get("parameter_fraction", 0.2))
            if space["type"] == "categorical":
                choices = sorted(v for v in space["choices"] if type(v) in (int, float))
                choices = (
                    [v for v in choices if v < params[numeric]]
                    if sign < 0
                    else [v for v in choices if v > params[numeric]]
                )
                if not choices:
                    continue
                value = choices[-1] if sign < 0 else choices[0]
            else:
                value = max(space["low"], min(space["high"], value))
                if space["type"] == "int":
                    value = int(round(value))
                if "step" in space:
                    value = (
                        space["low"] + round((value - space["low"]) / space["step"]) * space["step"]
                    )
                    value = max(space["low"], min(space["high"], value))
            changed["model"]["parameters"][numeric] = value
            add(f"neighbor_{numeric}_{sign:+d}", changed)
    changed = copy.deepcopy(definition)
    changed["strategy"]["position_sizing"] = (
        "inverse_volatility" if definition["strategy"]["position_sizing"] == "equal" else "equal"
    )
    add("alternative_position_sizing", changed)
    changed = copy.deepcopy(definition)
    changed["strategy"]["regime_filter"] = not definition["strategy"]["regime_filter"]
    add("alternative_regime_filter", changed)
    for name, universe in config.robustness.get("universe_subsets", {}).items():
        if not universe or set(universe) - set(definition["universe"]):
            raise ValueError("Robustness universe must be a nonempty declared subset")
        changed = copy.deepcopy(definition)
        changed["universe"] = list(universe)
        add(f"declared_static_universe_{name}", changed)
    return result[: config.robustness.get("max_variants", 6)]


def run_robustness(engine, config, deadline):
    ranked = comparison(engine.root)
    chosen = ranked["eligible"][: config.robustness.get("top_k", 1)]
    if not chosen and config.robustness.get("include_rejected_for_diagnostics", False):
        chosen = [r for r in ranked["rejected_or_failed"] if r["score"] is not None][
            : config.robustness.get("top_k", 1)
        ]
    report = {
        "candidates": [],
        "universe_note": (
            "Historical membership not supplied; configured static subsets are diagnostic only."
        ),
        "validation_is_reused": True,
        "final_holdout": "not_evaluated",
    }
    for parent in chosen:
        row = engine.registry.attempt(parent["attempt_id"])
        definition = json.loads(row["definition"])
        path = engine.root / "attempts" / parent["attempt_id"] / "result.json"
        original = path.read_bytes()
        outcomes = []
        for name, changed in variants(definition, config):
            if time.monotonic() >= deadline:
                outcomes.append({"scenario": name, "status": "NOT_RUN_BUDGET"})
                continue
            result = engine.run(changed, role="robustness", parent_id=row["id"], deadline=deadline)
            outcomes.append(
                {
                    "scenario": name,
                    "experiment_id": result["experiment_id"],
                    "attempt_id": result["attempt"]["id"],
                    "status": result["attempt"]["status"],
                    "summary": result["result"]["summary"] if result["result"] else None,
                }
            )
        result = json.loads(row["result"])
        environments = {}
        for window in result["windows"]:
            environments.setdefault(window["market_environment"], []).append(
                window["performance"]["total_return"]
            )
        report["candidates"].append(
            {
                "parent_attempt": row["id"],
                "original_eligible": parent["eligible"],
                "diagnostic_only": not parent["eligible"],
                "scenarios": outcomes,
                "market_environments": environments,
                "cost_stress_in_original_windows": True,
                "all_scenarios_eligible": all(o["status"] == "COMPLETE" for o in outcomes)
                if outcomes
                else None,
                "original_artifact_unchanged": original == path.read_bytes(),
            }
        )
    (engine.root / "reports").mkdir(exist_ok=True)
    write_json(engine.root / "reports" / "robustness.json", report)
    return report

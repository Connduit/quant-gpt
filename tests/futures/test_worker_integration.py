from pathlib import Path

import pytest

from quantlab.discovery.config import Resources
from quantlab.discovery.engine import ExperimentEngine
from quantlab.futures.evaluation import sealed_data
from quantlab.futures.research import prepare_futures
from quantlab.futures.synthetic import synthetic_futures_snapshot


def test_shared_supervisor_runs_futures_and_seals_holdout(tmp_path):
    inputs = tmp_path / "inputs"
    pointer = synthetic_futures_snapshot(inputs)
    doc = {
        "data": {
            "store": str(inputs),
            "snapshots": [pointer["snapshot_id"]],
            "holdout_start": pointer["holdout_start"],
            "holdout_end": "2024-06-11T00:00:00+00:00",
        },
        "validation": {"training_sessions": 1, "validation_sessions": 1, "test_sessions": 1},
        "execution": {
            "commission": ".5",
            "exchange_fee": ".5",
            "regulatory_fee": ".02",
            "slippage_ticks": 1,
            "spread_ticks": 0,
        },
        "risk": {"maximum_notional": 100000, "maximum_contracts": 1},
        "initial_cash": "100000",
    }
    root = tmp_path / "research"
    root.mkdir()
    base, vault, holdout = prepare_futures(doc, root)
    definition = {
        **base,
        "target": "forward_return",
        "horizon": 5,
        "groups": ["momentum", "volatility", "volume"],
        "instrument": "MES",
        "decision_minutes": 5,
        "model": {
            "type": "ridge",
            "objective": "regression",
            "seed": 42,
            "parameters": {"alpha": 1},
        },
        "strategy": {"threshold": 0.0001, "maximum_holding_minutes": 5},
    }
    resources = Resources(workers=1, trial_wall_seconds=90, trial_cpu_seconds=60)
    engine = ExperimentEngine(root / "experiments", "unit_futures", resources)
    result = engine.run(definition, role="futures_trial")
    assert result["result"], result["attempt"]
    assert result["result"]["synthetic"] is True
    assert result["result"]["summary"]["eligible"] is False
    assert (Path(result["attempt"]["artifact_path"]) / "predictions.parquet").exists()
    assert engine.run(definition)["duplicate"] is True
    assert vault.status(holdout)["state"] == "SEALED"
    assert len(vault.status(holdout)["events"]) == 1
    (Path(base["sealed_dir"]) / "bars.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        sealed_data(definition)

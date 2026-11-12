"""Export trusted local model diagnostics using its exact dependency environment."""

import argparse
import json
import statistics
from pathlib import Path

from quantlab.ml.models import ResearchModel


def extract(model_path, report_path, output):
    model = ResearchModel.load(model_path)
    manifest = json.loads((model_path / "manifest.json").read_text())
    report = json.loads(report_path.read_text())
    predictions = [p for p in report["predictions"] if p["model_hash"] == manifest["sha256"]]
    scores = [p["score"] for p in predictions]
    matured = [p["accuracy"] for p in predictions if p["accuracy"] is not None]
    document = {
        **manifest,
        "status": "UNVALIDATED",
        "feature_importance": model.importance(),
        "importance_semantics": "Standardized linear coefficients, descriptive not causal",
        "predictive": {
            "matured_direction_accuracy": statistics.mean(matured) if matured else None,
            "matured_observations": len(matured),
            "independent_sessions": report["daily_observations"],
        },
        "prediction_distribution": {
            "count": len(scores),
            "mean": statistics.mean(scores) if scores else None,
            "std": statistics.stdev(scores) if len(scores) > 1 else None,
            "minimum": min(scores) if scores else None,
            "maximum": max(scores) if scores else None,
        },
        "drift": {
            "mean_absolute_training_reference_z": statistics.mean(
                abs(p["feature_z"]) for p in predictions
            )
            if predictions
            else None,
            "note": "Overlapping quote-event features; not an independent significance test",
        },
        "limitations": [
            "Experimental model, not deployment validated.",
            "No external streaming or trading profitability established.",
        ],
    }
    output.write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.model, args.report, args.output)

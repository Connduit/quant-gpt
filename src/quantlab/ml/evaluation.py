import numpy as np
from scipy.stats import spearmanr


def evaluate(frame, predictions, objective: str) -> dict:
    predictions = np.asarray(predictions, dtype=float)
    if len(predictions) != frame.height or not np.isfinite(predictions).all():
        raise ValueError("Predictions must be finite and aligned to samples")
    y = frame["target"].to_numpy()
    classification = objective == "classification"
    labels = frame["target_class"].to_numpy() if classification else y
    signed = predictions >= (0.5 if classification else 0)
    result = {
        "samples": len(y),
        "mean_squared_error": float(np.mean((predictions - labels) ** 2)),
        "mean_absolute_error": float(np.mean(abs(predictions - labels))),
        "directional_accuracy": float(np.mean(signed == (y > 0))),
        "error_target": "positive_excess_probability" if classification else "excess_return",
    }
    ics = []
    dates = frame["session_date"].to_list()
    for day in sorted(set(dates)):
        indices = [i for i, d in enumerate(dates) if d == day]
        if len(indices) >= 2 and np.ptp(y[indices]) and np.ptp(predictions[indices]):
            ics.append(float(spearmanr(y[indices], predictions[indices]).statistic))
    result["rank_information_coefficient"] = float(np.mean(ics)) if ics else None
    result["rank_ic_sessions"] = len(ics)
    result["calibration"] = None
    if classification:
        if (predictions < 0).any() or (predictions > 1).any():
            raise ValueError("Classifier outputs must be probabilities")
        bins = []
        membership = np.minimum((predictions * 10).astype(int), 9)
        for index in range(10):
            low = index / 10
            mask = membership == index
            if mask.any():
                bins.append(
                    {
                        "lower": float(low),
                        "count": int(mask.sum()),
                        "predicted": float(predictions[mask].mean()),
                        "observed": float(labels[mask].mean()),
                    }
                )
        result["calibration"] = bins
        result["brier_score"] = result["mean_squared_error"]
    return result

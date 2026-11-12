"""Cross-check AAPL factor-proxy events against independent archived Yahoo adjustments.

This verifies inferred ex-date changes over an overlapping price-reference interval,
not authoritative payment dates or complete corporate-event coverage.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from quantlab.backtesting.report import dumps


def verify(root):
    quality = json.loads((root / "data_quality.json").read_text())
    reference = root / "source" / "aapl-independent-reference.csv"
    if (
        hashlib.sha256(reference.read_bytes()).hexdigest()
        != quality["independent_crosscheck"]["sha256"]
    ):
        raise ValueError("Independent reference checksum mismatch")
    with reference.open() as f:
        rows = list(csv.DictReader(f))
    ledger = json.loads((root / "actions" / "AAPL.json").read_text())
    provided = {r["ex_date"]: float(r["amount"]) for r in ledger["dividends"]}
    inferred = []
    for previous, current in zip(rows, rows[1:], strict=False):
        before = float(previous["AAPL.Adjusted"]) / float(previous["AAPL.Close"])
        after = float(current["AAPL.Adjusted"]) / float(current["AAPL.Close"])
        change = after / before - 1
        if abs(change) > 0.0001:
            amount = float(previous["AAPL.Close"]) * (1 - before / after)
            inferred.append(
                {
                    "ex_date": current["Date"],
                    "implied_distribution": amount,
                    "provided_proxy_amount": provided.get(current["Date"]),
                    "absolute_difference": abs(amount - provided[current["Date"]])
                    if current["Date"] in provided
                    else None,
                }
            )
    interior = [d for d in provided if rows[0]["Date"] < d <= rows[-1]["Date"]]
    matched = {r["ex_date"] for r in inferred if r["provided_proxy_amount"] is not None}
    return {
        "source": quality["independent_crosscheck"],
        "symbol": "AAPL",
        "period": [rows[0]["Date"], rows[-1]["Date"]],
        "inferred_events": inferred,
        "unmatched_provided_dates": sorted(set(interior) - matched),
        "unmatched_inferred_dates": [
            r["ex_date"] for r in inferred if r["provided_proxy_amount"] is None
        ],
        "coverage_certified": False,
        "limitations": [
            "Adjusted-close ratios infer distributions, not authoritative event records.",
            "Limited to AAPL in the overlapping archived reference interval.",
            "No payment dates or full split/noncash/delisting certification.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs", type=Path, default=Path("data/network-verification/real-inputs")
    )
    args = parser.parse_args()
    print(dumps(verify(args.inputs)))


if __name__ == "__main__":
    main()

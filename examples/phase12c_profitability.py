"""Bounded real-data exploratory demonstration. Never requests protected 2019 prices."""

import argparse
import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily
from quantlab.profitability.runner import run_profitability
from quantlab.web.workflow_worker import execute
from quantlab.web.workflows import ProfitabilityRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    symbols = ["SPY", "AAPL", "MSFT", "NVDA"]
    start, end = date(2016, 1, 1), date(2018, 12, 31)
    params = dict(
        symbols=",".join(symbols),
        timeframe="1Day",
        start="2016-01-01T00:00:00Z",
        end="2018-12-31T23:59:59Z",
        adjustment="raw",
        feed="sip",
        limit=10000,
    )
    rows = {s: [] for s in symbols}
    page = 0
    while True:
        page += 1
        if page > 5:
            raise ValueError("Download page budget exceeded")
        url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
                "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"],
            },
        )
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = json.load(response)
        for symbol, bars in payload["bars"].items():
            for bar in bars:
                day = date.fromisoformat(bar["t"][:10])
                if not start <= day <= end:
                    raise ValueError("Provider returned an out-of-bounds observation")
                rows[symbol].append([str(day), *[bar[k] for k in ("o", "h", "l", "c", "v")]])
        if not payload.get("next_page_token"):
            break
        params["page_token"] = payload["next_page_token"]
    library = root / "library"
    ids = []
    for symbol in symbols:
        csv_text = io.StringIO()
        writer = csv.writer(csv_text)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writerows(sorted(rows[symbol]))
        raw = csv_text.getvalue().encode()
        bounds = DataRequest(symbol, start, end)
        ids.append(
            SnapshotStore(library).write(
                "alpaca-sip-daily-raw",
                bounds,
                Download(
                    raw,
                    "Alpaca daily SIP raw; bounded 2016-2018; no action/PIT certification",
                    "unadjusted",
                    False,
                ),
                normalize_daily(raw, bounds),
            )
        )
    source = root / "training"
    training = dict(
        workflow="training",
        research_mode="exploratory",
        name="Phase 12C pre-2019 demonstration",
        snapshot_ids=ids,
        models=["ridge"],
        start=str(start),
        end=str(end),
        horizon=5,
        training_sessions=252,
        validation_sessions=63,
        test_sessions=126,
        top_n=2,
        max_trials=1,
        seed=42,
        confirmed=True,
    )
    result = execute({"workflow": "training", "payload": training, "library": str(library)}, source)
    if result["status"] != "COMPLETED":
        raise ValueError(result)
    request = ProfitabilityRequest(
        source_job_id="c" * 32,
        model="ridge",
        start=start,
        end=end,
        research_mode="exploratory",
        top_n=2,
        confirmed=True,
    )
    report = run_profitability(source, request, root / "evaluation", root / "registry")
    (root / "demonstration.json").write_text(
        json.dumps(
            {
                "data_source": "Alpaca SIP daily raw",
                "retrieved_at": datetime.now(UTC).isoformat(),
                "input_rows": {s: len(rows[s]) for s in symbols},
                "report": str(root / "evaluation/profitability_report.json"),
                "mode": report["performance_kind"],
                "qualified": False,
                "protected_holdout_requested_or_read": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "mode": report["performance_kind"],
                "qualified": False,
                "report": str(root / "evaluation/profitability_report.json"),
                "baseline_net": report["scenarios"]["baseline"]["strategies"]["ml"]["net"][
                    "total_return"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()

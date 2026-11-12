"""Offline end-to-end demonstration. All prices are explicitly synthetic."""

import argparse
import json
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from quantlab.backtesting.data import DailyData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.report import export_report
from quantlab.data.ingestion import ingest
from quantlab.data.providers.base import DataRequest
from quantlab.data.providers.fixture import FixtureProvider
from quantlab.data.storage import SnapshotStore
from quantlab.logging import configure_logging
from quantlab.strategies.baselines import BuyAndHold, MeanReversion, Momentum


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("data/backtests/milestone-2-demo"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; use a new directory to preserve prior reports")
    configure_logging("INFO")
    store = SnapshotStore(args.data_dir)
    request = DataRequest("SYNTH", date(2024, 1, 2), date(2024, 1, 8))
    snapshot, _ = ingest(FixtureProvider(), request, store)
    data = DailyData.from_snapshot(store, snapshot)
    config = BacktestConfig(initial_cash=Decimal("10000"))
    benchmark = run_backtest(data, BuyAndHold(), config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".pending-demo-", dir=args.output.parent))
    try:
        for name, strategy in (
            ("momentum", Momentum(lookback=2)),
            ("mean-reversion", MeanReversion(lookback=2, threshold=Decimal("0.001"))),
            ("buy-and-hold", BuyAndHold()),
        ):
            result = run_backtest(data, strategy, config)
            report = export_report(result, benchmark, temporary / name)
            print(
                json.dumps(
                    {
                        "strategy": name,
                        "synthetic": True,
                        "snapshot_id": snapshot,
                        "fills": len(result.trades),
                        "report": str(args.output / name / "report.json"),
                        "run_id": report["run_id"],
                    }
                )
            )
        temporary.rename(args.output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


if __name__ == "__main__":
    main()

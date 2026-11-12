import json
import math
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from quantlab.backtesting.engine import run_backtest
from quantlab.backtesting.metrics import performance
from quantlab.backtesting.report import export_report
from quantlab.cli import main
from quantlab.strategies.baselines import BuyAndHold, MeanReversion, Momentum


def test_hand_calculated_returns_sharpe_and_drawdown():
    rows = [
        {
            "equity": D(value),
            "quantity": D(1),
            "gross_exposure": D(1),
            "realized_pnl": D(0),
            "unrealized_pnl": D(0),
            "dividend_income": D(0),
            "commissions": D(0),
            "spread_cost": D(0),
            "slippage_cost": D(0),
        }
        for value in ("110", "99", "108.9")
    ]
    result = performance(rows, [], D(100), 252)
    assert [row["daily_return"] for row in rows] == pytest.approx([0.1, -0.1, 0.1])
    assert result["sharpe_ratio"] == pytest.approx(math.sqrt(21))
    assert result["sortino_ratio"] == pytest.approx(math.sqrt(84))
    assert result["maximum_drawdown"] == pytest.approx(-0.1)
    assert result["annualized_return"] == pytest.approx(1.089**84 - 1)
    assert result["total_return"] == pytest.approx(0.089)
    assert result["win_rate"] is None and result["profit_factor"] is None


def test_no_trade_ratios_are_null_not_nan(make_data, targets, no_costs):
    result = run_backtest(make_data([(100, 100)] * 3), targets({}), no_costs)
    assert result.metrics["total_return"] == 0
    assert result.metrics["maximum_drawdown"] == 0
    assert result.metrics["annualized_volatility"] == 0
    assert result.metrics["sharpe_ratio"] is None
    assert result.metrics["sortino_ratio"] is None


@pytest.mark.parametrize(
    "strategy", [Momentum(1), MeanReversion(2, threshold=D("0.001")), BuyAndHold()]
)
def test_baselines_end_to_end_export_and_repeatability(make_data, no_costs, tmp_path, strategy):
    data = make_data([(100, 100), (100, 110), (110, 90), (90, 100), (100, 110), (110, 90)])
    first = run_backtest(data, strategy, no_costs)
    second = run_backtest(data, strategy, no_costs)
    assert first.trades and first.trades == second.trades
    assert first.equity == second.equity
    benchmark = run_backtest(data, BuyAndHold(), no_costs)
    output = tmp_path / "report"
    report = export_report(first, benchmark, output)
    saved = json.loads((output / "report.json").read_text())
    assert saved["metadata"]["performance_kind"] == "hypothetical_backtest"
    assert saved["metadata"]["synthetic"] is True
    assert saved["performance"]["final_equity"] == str(first.equity[-1]["equity"])
    assert (output / "trades.csv").read_text().count("\n") == len(first.trades) + 1
    assert (output / "equity.csv").exists()
    assert (output / "benchmark_equity.csv").exists()
    repeated = export_report(second, benchmark, tmp_path / "second")
    assert repeated["run_id"] == report["run_id"]
    with pytest.raises(ValueError, match="already exists"):
        export_report(first, benchmark, output)


def test_cli_backtest(make_snapshot, tmp_path, capsys):
    store, snapshot = make_snapshot([(100, 100), (100, 110), (110, 90), (90, 100)])
    output = tmp_path / "cli-report"
    args = [
        "--data-dir",
        str(store.root.parent),
        "backtest",
        snapshot,
        "--strategy",
        "momentum",
        "--lookback",
        "1",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["synthetic"] is True
    assert result["performance"]["fill_count"] == 2
    assert main(args) == 1  # preserves prior artifacts
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["event"] == "command_failed"


def test_demo_script_runs_every_baseline(tmp_path):
    example = Path(__file__).resolve().parents[2] / "examples" / "backtest_demo.py"
    result = subprocess.run(
        [
            sys.executable,
            str(example),
            "--data-dir",
            str(tmp_path / "data"),
            "--output",
            str(tmp_path / "demo"),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    runs = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(runs) == 3
    assert all(run["synthetic"] and run["fills"] > 0 for run in runs)
    assert {run["strategy"] for run in runs} == {"momentum", "mean-reversion", "buy-and-hold"}
    for run in runs:
        report = json.loads(Path(run["report"]).read_text())
        assert report["metadata"]["data_manifest"]["synthetic"] is True


def test_explicit_csv_import_and_action_ledger_path(tmp_path, capsys):
    # Invented values exercise the caller-declared raw-data path, not real market evidence.
    csv = tmp_path / "synthetic-raw.csv"
    csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,100,101,99,100,1000\n"
        "2024-01-03,100,101,99,100,1000\n"
        "2024-01-04,50,51,49,50,1000\n"
    )
    prefix = ["--data-dir", str(tmp_path / "imported")]
    imported = prefix + [
        "import-csv",
        "TEST",
        "--csv",
        str(csv),
        "--source",
        "synthetic test of the declared raw-price contract",
        "--price-basis",
        "unadjusted",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-04",
    ]
    assert main(imported) == 0
    snapshot = json.loads(capsys.readouterr().out)["snapshot_id"]
    args = prefix + [
        "backtest",
        snapshot,
        "--strategy",
        "buy-hold",
        "--shares",
        "10",
        "--commission-per-share",
        "0",
        "--slippage-bps",
        "0",
        "--output",
        str(tmp_path / "raw-report"),
    ]
    assert main(args) == 1
    assert "corporate-action ledger" in capsys.readouterr().err
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            {
                "symbol": "TEST",
                "coverage_start": "2024-01-02",
                "coverage_end": "2024-01-04",
                "source": "synthetic test ledger",
                "complete": True,
                "splits": [{"date": "2024-01-04", "ratio": "2"}],
                "dividends": [],
            }
        )
    )
    assert main(args + ["--actions", str(actions)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert D(value["performance"]["final_equity"]) == 100000
    report = json.loads((tmp_path / "raw-report" / "report.json").read_text())
    assert report["metadata"]["corporate_actions"]["splits"][0]["ratio"] == "2"
    assert len(report["metadata"]["package_source_sha256"]) == 64

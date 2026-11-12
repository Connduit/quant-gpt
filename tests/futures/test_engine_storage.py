from dataclasses import replace
from datetime import timedelta

import polars as pl
import pytest

from quantlab.futures.engine import FuturesBacktestConfig, FuturesCosts, run_futures_backtest
from quantlab.futures.risk import FuturesRisk
from quantlab.futures.storage import FuturesStore, normalize

META = {"tradable": True, "price_basis": "actual_contract_unadjusted", "synthetic": True}


class OneShot:
    def __init__(self, identifier):
        self.identifier = identifier
        self.sent = False

    def on_bar(self, context):
        if self.sent:
            return {}
        self.sent = True
        return {self.identifier: 1}


def config():
    return FuturesBacktestConfig(
        "100000",
        FuturesCosts(0, 0, 0, 0, 0),
        FuturesRisk(),
        overnight="hold",
        settlement_policy="none",
    )


def test_strictly_later_open_fills_and_actual_multiplier(contract, minute_frame):
    frame, _, _ = minute_frame
    result = run_futures_backtest(
        frame,
        {contract.identifier: contract},
        OneShot(contract.identifier),
        config=config(),
        metadata=META,
    )
    fill = result["trades"][0]
    assert fill["timestamp"] == frame["timestamp"][2]
    assert fill["price"] == frame["open"][2]
    expected = (float(frame["close"][-1]) - float(frame["open"][2])) * 50
    assert result["performance"]["net_pnl"] == pytest.approx(expected)
    assert result["performance"]["maximum_margin_utilization"] > 0


def test_continuous_prices_and_future_margin_metadata_rejected(contract, minute_frame):
    frame, _, _ = minute_frame
    with pytest.raises(ValueError, match="actual tradable"):
        run_futures_backtest(
            frame,
            {contract.identifier: contract},
            OneShot(contract.identifier),
            metadata={**META, "tradable": False},
        )
    future = replace(contract, margin_as_of="2025-01-01")
    with pytest.raises(ValueError, match="Future margin"):
        run_futures_backtest(
            frame, {future.identifier: future}, OneShot(future.identifier), metadata=META
        )


def test_maintenance_gap_liquidation_waits_for_next_open(contract, minute_frame):
    frame, _, _ = minute_frame
    rows = frame.to_dicts()
    for i, row in enumerate(rows):
        price = 100 if i < 4 else 20 if i == 4 else 10
        for field in ("open", "high", "low", "close"):
            row[field] = price
    frame = pl.DataFrame(rows)
    limits = FuturesRisk(
        maximum_margin_utilization=1,
        maximum_daily_loss=1,
        maximum_drawdown=1,
        maximum_strategy_drawdown=1,
    )
    result = run_futures_backtest(
        frame,
        {contract.identifier: contract},
        OneShot(contract.identifier),
        config=replace(config(), initial_cash="11000", risk=limits),
        metadata=META,
    )
    assert result["halts"]
    assert result["trades"][1]["timestamp"] > result["halts"][0]["at"]
    assert result["final_positions"][contract.identifier]["quantity"] == 0
    assert result["performance"]["net_pnl"] == pytest.approx(-4500)


def test_snapshot_integrity_query_and_validation(contract, minute_frame, tmp_path):
    frame, quality, raw = minute_frame
    store = FuturesStore(tmp_path)
    identifier = store.write(
        frame,
        raw,
        contract,
        provider="synthetic-test",
        source="invented fixture",
        synthetic=True,
        quality=quality,
    )
    assert store.read(identifier).equals(frame)
    assert store.query(identifier, "SELECT count(*) AS n FROM bars")["n"][0] == 30
    assert (
        store.write(
            frame,
            raw,
            contract,
            provider="synthetic-test",
            source="invented fixture",
            synthetic=True,
            quality=quality,
        )
        == identifier
    )
    with pytest.raises(ValueError, match="Missing minute"):
        normalize(raw, contract)
    bad = pl.read_csv(raw).with_columns(pl.lit(100.1).alias("close")).write_csv().encode()
    with pytest.raises(ValueError, match="tick"):
        normalize(bad, contract, allow_sparse=True)
    (tmp_path / identifier / "source.csv").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        store.read(identifier)


def test_repeated_targets_do_not_starve_next_open_orders(contract, minute_frame):
    frame, _, _ = minute_frame

    class Repeated:
        def on_bar(self, context):
            return {contract.identifier: 1}

    result = run_futures_backtest(
        frame, {contract.identifier: contract}, Repeated(), config=config(), metadata=META
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0]["timestamp"] == frame["timestamp"][2]
    assert result["performance"]["average_gross_exposure"] > 0
    assert result["performance"]["time_in_market"] > 0


def test_new_signal_at_open_does_not_cancel_preexisting_open_order(contract, minute_frame):
    frame, _, _ = minute_frame
    first = frame["available_at"][0]

    class Reverse:
        def on_bar(self, context):
            return {contract.identifier: 1 if context["now"] == first else -1}

    result = run_futures_backtest(
        frame, {contract.identifier: contract}, Reverse(), config=config(), metadata=META
    )
    assert result["trades"][0]["signed_quantity"] == 1
    assert result["trades"][0]["timestamp"] == frame["timestamp"][2]
    assert result["trades"][1]["signed_quantity"] == -2
    assert result["trades"][1]["timestamp"] == frame["timestamp"][3]


def test_insolvency_records_debt_and_stops_new_exposure(contract, minute_frame):
    frame, _, _ = minute_frame
    rows = frame.to_dicts()
    for i, row in enumerate(rows):
        price = 300 if i < 4 else 80 if i == 4 else 70
        for key in ("open", "high", "low", "close"):
            row[key] = price
    limits = FuturesRisk(
        maximum_margin_utilization=1,
        maximum_daily_loss=1,
        maximum_drawdown=1,
        maximum_strategy_drawdown=1,
    )
    result = run_futures_backtest(
        pl.DataFrame(rows),
        {contract.identifier: contract},
        OneShot(contract.identifier),
        config=replace(config(), initial_cash="11000", risk=limits),
        metadata=META,
    )
    assert result["performance"]["account_status"] == "INSOLVENT"
    assert result["performance"]["net_pnl"] == pytest.approx(-11500)
    assert result["final_positions"][contract.identifier]["quantity"] == 0


def test_expiry_closes_on_real_pre_expiry_quote(contract, minute_frame):
    frame, _, _ = minute_frame
    c = replace(contract, last_trade=frame["timestamp"][-1] + timedelta(minutes=1))
    result = run_futures_backtest(
        frame, {c.identifier: c}, OneShot(c.identifier), config=config(), metadata=META
    )
    assert result["final_positions"][c.identifier]["quantity"] == 0
    assert result["trades"][-1]["reason"] == "scheduled_expiry_exit"
    assert result["trades"][-1]["timestamp"] < c.last_trade


def test_official_settlement_waits_for_publication(contract, minute_frame):
    frame, _, _ = minute_frame
    known = frame["available_at"][-1] + timedelta(minutes=5)
    rows = frame.to_dicts()
    for i, row in enumerate(rows):
        row["settlement_price"] = 108 if i == len(rows) - 1 else None
        row["settlement_known_at"] = known if i == len(rows) - 1 else None
    result = run_futures_backtest(
        pl.DataFrame(rows, infer_schema_length=None),
        {contract.identifier: contract},
        OneShot(contract.identifier),
        config=replace(config(), settlement_policy="official"),
        metadata={**META, "settlement_source": "explicit synthetic publication fixture"},
    )
    assert result["settlements"][0]["timestamp"] == known
    assert result["final_account"]["cash"] == 100375
    assert result["final_account"]["equity"] == 100337.5

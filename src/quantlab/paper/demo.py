"""Real archival ES quote replay; experimental strategies, no paper promotion."""

import hashlib
import json
from pathlib import Path

import polars as pl

from quantlab.backtesting.report import dumps
from quantlab.futures.contracts import contract_from_dict
from quantlab.futures.storage import FuturesStore
from quantlab.ml.models import ModelSpec, ResearchModel
from quantlab.paper.events import MarketEvent
from quantlab.paper.reports import compare, report
from quantlab.paper.runtime import PaperRuntime
from quantlab.paper.strategies import QuoteMomentum


def demonstrate(output, *, source=Path("data/futures/real-inputs")):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    pointer = json.loads((source / "dataset.json").read_text())
    store = FuturesStore(source)
    frame = store.read(pointer["snapshot_id"])
    holdout = pointer["holdout_start"]
    if frame["available_at"].max().isoformat() >= holdout:
        raise ValueError("Source crosses reserved period")
    contract = contract_from_dict(pointer["contract"])
    symbol = contract.identifier
    rows = frame.to_dicts()
    train = [r for r in rows if str(r["session_date"]) < "2013-10-10"]
    records = []
    for i in range(5, len(train) - 5):
        a, b, c = train[i - 5], train[i], train[i + 5]
        if a["session_date"] != c["session_date"]:
            continue
        mid = (b["bid"] + b["ask"]) / 2
        start = (a["bid"] + a["ask"]) / 2
        end = (c["bid"] + c["ask"]) / 2
        records.append(
            {
                "quote_return": mid / start - 1,
                "quote_spread": (b["ask"] - b["bid"]) / mid,
                "target": end / mid - 1,
            }
        )
    training = pl.DataFrame(records)
    model = ResearchModel(ModelSpec("ridge")).fit(training, ("quote_return", "quote_spread"))
    model_path = output / "model"
    model.save(model_path)
    sha = hashlib.sha256((model_path / "model.joblib").read_bytes()).hexdigest()
    test = [r for r in rows if "2013-10-10" <= str(r["session_date"]) < "2013-10-14"]

    def events():
        for r in test:
            # Closing quote aggregated over the minute is available only at completed bar time.
            # Historical quote depth is absent: explicitly modeled 1% traded-volume proxy.
            yield MarketEvent(
                symbol,
                "lean-minute-quote-archive",
                r["available_at"],
                r["available_at"],
                "quote",
                "replay",
                r["timestamp"].isoformat(),
                str(r["bid"]),
                str(r["ask"]),
                max(0, int(r["volume"] * 0.01)),
                max(0, int(r["volume"] * 0.01)),
                session=str(r["session_date"]),
                liquidity_basis="bar_volume_proxy",
            )

    kwargs = {"contracts": {symbol: contract}, "participation": 0.1}
    db = output / "account.sqlite"
    runtime = PaperRuntime(db, **kwargs)
    for sid in ("momentum", "ml"):
        runtime.register(
            sid,
            capital=50000,
            experimental=True,
            version="experimental-quote-v1",
            model_hash=sha if sid == "ml" else None,
        )
    strategies = [
        QuoteMomentum("momentum", symbol, lookback=5, threshold=0.0003),
        QuoteMomentum(
            "ml",
            symbol,
            lookback=5,
            model=model_path,
            model_hash=sha,
            threshold=0.0001,
            training_mean=float(training["quote_return"].mean()),
            training_std=float(training["quote_return"].std()),
        ),
    ]
    recovered = False
    duplicate_safe = False
    for i, event in enumerate(events()):
        runtime.ingest(event, now=event.received_at)
        if i == 0 or i == len(test) // 4:
            runtime.control("connect", reason="verified archive replay clock and reconciled state")
            if not runtime.state["killed"]:
                for sid in ("momentum", "ml"):
                    runtime.control("resume", strategy=sid, reason="experimental replay only")
        for strategy in strategies:
            strategy.on_event(runtime, event)
        if i == len(test) // 4 - 1:
            before = dumps(runtime.account.view())
            count = len(runtime.account.fills)
            runtime.close()
            runtime = PaperRuntime(db, **kwargs)
            recovered = dumps(runtime.account.view()) == before
            duplicate_safe = (
                not runtime.ingest(event, now=event.received_at)
                and len(runtime.account.fills) == count
            )
    runtime.control("kill", reason="demonstration verified global kill; no liquidation requested")
    result = report(runtime)
    result.update(
        {
            "snapshot_id": pointer["snapshot_id"],
            "holdout_accessed": False,
            "restart_reconciled": recovered,
            "duplicate_event_no_extra_fill": duplicate_safe,
            "training_end": "2013-10-09",
            "liquidity_model": (
                "Minute closing quotes; 1% trade volume as modeled depth, "
                "then 10% participation; actual quoted depth unavailable"
            ),
            "eligibility": "Both strategies RESEARCH only; no validated paper strategy exists",
            "source": "Pinned LEAN archive; historical margins assumed, limited two-day replay",
        }
    )
    (output / "report.json").write_text(dumps(result) + "\n")
    # Compare actual recorded M7 conventional backtest on the same development dates.
    reference = Path("data/futures/milestone-7-final/research.json")
    ref = json.loads(reference.read_text()) if reference.exists() else None
    benchmark = (
        next(
            (r for r in ref["results"] if r["definition"].get("strategy_family") == "momentum"),
            None,
        )
        if ref
        else None
    )
    comparison = compare(
        {
            "mode": "M7 contract backtest",
            "fills": benchmark["summary"]["fills"] if benchmark else None,
        },
        {
            "mode": "experimental quote replay",
            "fills": len(runtime.account.fills),
            "fees": float(result["account"]["fees"]),
        },
    )
    comparison["scope"] = (
        "Different models, feature schemas and execution granularity; a "
        "diagnostic, not matched-strategy equivalence"
    )
    (output / "comparison.json").write_text(dumps(comparison) + "\n")
    runtime.close()
    return {
        k: result[k]
        for k in (
            "snapshot_id",
            "restart_reconciled",
            "duplicate_event_no_extra_fill",
            "holdout_accessed",
            "eligibility",
        )
    } | {
        "output": str(output),
        "fills": len(result["fills"]),
        "equity": result["account"]["equity"],
    }

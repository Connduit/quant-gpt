"""Explicit deterministic fixtures only; never a fallback for unavailable market data."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from quantlab.backtesting.report import dumps
from quantlab.futures.calendar import FuturesCalendar
from quantlab.futures.contracts import Contract
from quantlab.futures.storage import FuturesStore, normalize


def synthetic_futures_snapshot(root, *, product="MES", seed=42):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    contract = Contract(
        product,
        f"{product}M24",
        6,
        2024,
        datetime(2024, 6, 21, 13, 30, tzinfo=UTC),
        datetime(2024, 6, 21, 13, 30, tzinfo=UTC),
        (
            "synthetic fixture contract; standard product "
            "tick/multiplier, invented market observations"
        ),
        initial_margin="2000",
        maintenance_margin="1500",
        margin_as_of="2024-06-01",
        margin_source="explicit synthetic margin assumption",
    )
    calendar = FuturesCalendar()
    rng = np.random.default_rng(seed)
    rows = []
    ticks = 20000 if product in ("ES", "MES") else 76000
    for day in ("2024-06-03", "2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07"):
        for i, t in enumerate(calendar.expected(day)):
            ticks += int(rng.choice([-2, -1, 1, 2]))
            price = ticks * 0.25
            rows.append(
                {
                    "timestamp": t,
                    "open": price,
                    "high": price + 0.5,
                    "low": price - 0.5,
                    "close": price,
                    "volume": 10000 + i,
                    "contract": contract.identifier,
                }
            )
    raw = pl.DataFrame(rows).write_csv().encode()
    frame, quality = normalize(raw, contract)
    identifier = FuturesStore(root).write(
        frame,
        raw,
        contract,
        provider="explicit-synthetic-futures-fixture",
        source=f"invented deterministic prices, seed {seed}",
        synthetic=True,
        quality=quality,
    )
    pointer = {
        "snapshot_id": identifier,
        "contract": contract.as_dict(),
        "quality": quality,
        "synthetic": True,
        "holdout_start": "2024-06-10T00:00:00+00:00",
        "reserved_period_downloaded": False,
    }
    (root / "dataset.json").write_text(dumps(pointer))
    return pointer

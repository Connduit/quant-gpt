"""Explicitly invented multi-stock data for deterministic integration demonstrations."""

from pathlib import Path

import exchange_calendars as xcals
import numpy as np

from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily


def synthetic_snapshots(root: Path, sessions: int = 360, seed: int = 42):
    calendar = xcals.get_calendar("XNYS", start="2022-01-01", end="2024-12-31")
    dates = [s.date() for s in calendar.sessions[:sessions]]
    if len(dates) != sessions:
        raise ValueError("Synthetic demonstration supports at most 2022-2024 sessions")
    common = np.random.default_rng(seed).normal(0.0001, 0.008, sessions)
    store = SnapshotStore(root)
    snapshots = {}
    for offset, symbol in enumerate(("SPY", "AAA", "BBB", "CCC")):
        rng = np.random.default_rng(seed + offset + 1)
        innovations = common + (rng.normal(0, 0.012, sessions) if offset else 0)
        prices = 100 * np.exp(np.cumsum(innovations))
        previous = 100
        lines = ["Date,Open,High,Low,Close,Volume"]
        for day, closing in zip(dates, prices, strict=True):
            opening = previous * np.exp(rng.normal(0, 0.002))
            high, low = max(opening, closing) * 1.003, min(opening, closing) * 0.997
            volume = int(rng.integers(500000, 2000000))
            lines.append(f"{day},{opening:.6f},{high:.6f},{low:.6f},{closing:.6f},{volume}")
            previous = closing
        raw = ("\n".join(lines) + "\n").encode()
        request = DataRequest(symbol, dates[0], dates[-1])
        frame = normalize_daily(raw, request)
        snapshot = store.write(
            "synthetic-ml-demo",
            request,
            Download(raw, f"explicitly synthetic seeded paths v1 seed={seed}", "synthetic", True),
            frame,
        )
        snapshots[symbol] = snapshot
    return snapshots, dates

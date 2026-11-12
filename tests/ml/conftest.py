import pytest

from quantlab.backtesting.data import DailyData
from quantlab.data.storage import SnapshotStore
from quantlab.features import FeatureConfig
from quantlab.research.synthetic import synthetic_snapshots


@pytest.fixture(scope="session")
def ml_feeds(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-ml-inputs")
    snapshots, dates = synthetic_snapshots(root, sessions=180)
    store = SnapshotStore(root)
    feeds = {s: DailyData.from_snapshot(store, snapshot) for s, snapshot in snapshots.items()}
    return feeds, snapshots, dates, root


@pytest.fixture
def small_features():
    return FeatureConfig(
        return_windows=(1, 3, 5, 10),
        short_window=3,
        long_window=5,
        atr_window=3,
        rsi_window=3,
        macd_fast=2,
        macd_slow=4,
        macd_signal=2,
        bollinger_window=3,
    )

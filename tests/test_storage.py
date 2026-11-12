from dataclasses import replace
from datetime import date

import duckdb
import pytest
from polars.testing import assert_frame_equal

from quantlab.data.ingestion import ingest
from quantlab.data.providers.fixture import FixtureProvider
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily


def test_roundtrip_cache_refresh_and_query(tmp_path, request_range):
    store = SnapshotStore(tmp_path)
    provider = FixtureProvider()
    first, cached = ingest(provider, request_range, store)
    assert not cached
    assert_frame_equal(
        store.read(first), normalize_daily(provider.fetch(request_range).raw, request_range)
    )
    assert store.query(first, "SELECT count(*) AS n FROM bars")["n"][0] == 5
    assert ingest(provider, request_range, store) == (first, True)
    second, cached = ingest(provider, request_range, store, refresh=True)
    assert not cached and second != first
    assert ingest(provider, request_range, store) == (second, True)
    assert store.read(first).height == 5
    assert store.manifest(first)["point_in_time"] is False


@pytest.mark.parametrize("filename", ["bars.parquet", "source.csv", "manifest.json"])
def test_tampering_detected(tmp_path, request_range, filename):
    store = SnapshotStore(tmp_path)
    snapshot, _ = ingest(FixtureProvider(), request_range, store)
    path = store.root / snapshot / filename
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError):
        store.read(snapshot)


def test_validation_failure_publishes_nothing(tmp_path, request_range):
    class BrokenProvider(FixtureProvider):
        def fetch(self, request):
            return replace(super().fetch(request), raw=b"broken")

    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        ingest(BrokenProvider(), request_range, store)
    assert not list(tmp_path.glob("snapshots/*"))


def test_extend_preserves_parent(tmp_path, request_range):
    store = SnapshotStore(tmp_path)
    provider = FixtureProvider()
    short = replace(request_range, end=date(2024, 1, 4))
    first, _ = ingest(provider, short, store)
    second, _ = ingest(provider, request_range, store, extend=first)
    assert store.read(second).height == 5
    assert store.read(first).height == 3
    assert store.manifest(second)["parent_snapshot"] == first
    with pytest.raises(ValueError, match="after"):
        ingest(provider, short, store, extend=first)
    with pytest.raises(ValueError, match="same provider and symbol"):
        ingest(provider, replace(request_range, symbol="OTHER"), store, extend=first)


def test_query_restrictions(tmp_path, request_range):
    store = SnapshotStore(tmp_path)
    snapshot, _ = ingest(FixtureProvider(), request_range, store)
    for sql in ["DROP TABLE bars", "SELECT 1; SELECT 2"]:
        with pytest.raises(ValueError, match="single SELECT"):
            store.query(snapshot, sql)
    with pytest.raises(duckdb.Error):
        store.query(snapshot, "SELECT * FROM read_csv('/etc/passwd')")
    with pytest.raises(ValueError, match="SHA-256"):
        store.read("../../etc/passwd")

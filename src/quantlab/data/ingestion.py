import logging

import polars as pl

from quantlab.data.providers.base import DataRequest, HistoricalProvider
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily

logger = logging.getLogger(__name__)


def ingest(
    provider: HistoricalProvider,
    request: DataRequest,
    store: SnapshotStore,
    refresh: bool = False,
    extend: str | None = None,
) -> tuple[str, bool]:
    """Cache exact requests; optionally append sessions to an immutable parent snapshot."""
    if not refresh and not extend:
        cached = store.find_cached(provider.name, request)
        if cached:
            logger.info("Using verified cached snapshot", extra={"event": "cache_hit"})
            return cached, True
    actual_request = request
    previous = None
    if extend:
        from datetime import timedelta

        metadata = store.manifest(extend)
        if metadata["price_basis"] == "vendor_adjustment_unspecified":
            raise ValueError("Unknown vendor adjustments make appending unsafe; refresh full range")
        if metadata["provider"] != provider.name or metadata["request"]["symbol"] != request.symbol:
            raise ValueError("Extension must use the same provider and symbol")
        if metadata["request"]["start"] != request.start.isoformat():
            raise ValueError("Extension start must equal the parent request start")
        previous = store.read(extend)
        last = previous["session_date"].max()
        if request.end <= last:
            raise ValueError("Extension end must be after the parent's final session")
        actual_request = DataRequest(request.symbol, last + timedelta(days=1), request.end)
    download = provider.fetch(actual_request)
    frame = normalize_daily(download.raw, actual_request)
    if previous is not None:
        if (
            metadata["price_basis"] != download.price_basis
            or metadata["synthetic"] != download.synthetic
        ):
            raise ValueError("Extension cannot change the price basis or synthetic status")
        frame = pl.concat([previous, frame]).sort("session_date")
    snapshot_id = store.write(provider.name, request, download, frame, extend)
    logger.info("Created immutable snapshot", extra={"event": "snapshot_created"})
    return snapshot_id, False

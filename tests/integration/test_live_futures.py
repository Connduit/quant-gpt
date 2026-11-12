import os
from datetime import UTC, datetime

import pytest

from quantlab.futures.contracts import Contract
from quantlab.futures.providers import FuturesRequest, LeanFuturesProvider
from quantlab.futures.storage import FuturesStore, normalize


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("QUANTLAB_LIVE_FUTURES") != "1", reason="explicit live futures opt-in"
)
def test_real_es_minute_download(tmp_path):
    contract = Contract(
        "ES",
        "ESZ13",
        12,
        2013,
        datetime(2013, 12, 20, 14, 30, tzinfo=UTC),
        datetime(2013, 12, 20, 14, 30, tzinfo=UTC),
        "dated CME quarterly December 2013 contract; data test only, no margin assumptions",
    )
    request = FuturesRequest(
        contract, datetime(2013, 10, 8, 13, 30, tzinfo=UTC), datetime(2013, 10, 8, 20, tzinfo=UTC)
    )
    provider = LeanFuturesProvider(include_auxiliary=True)
    download = provider.fetch(request)
    frame, quality = normalize(download.raw, contract, request=request)
    assert frame.height == 390 and quality["missing_minutes"] == {}
    assert frame["ask_open"].is_not_null().all()
    store = FuturesStore(tmp_path)
    identifier = store.write(
        frame,
        download.raw,
        contract,
        provider=provider.name,
        source=download.source,
        synthetic=False,
        quality=quality,
    )
    assert store.read(identifier).equals(frame)
    assert store.manifest(identifier)["synthetic"] is False

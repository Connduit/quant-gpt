import httpx
import pytest

from quantlab.data.providers.base import ProviderError
from quantlab.data.providers.fixture import FIXTURE, FixtureProvider
from quantlab.data.providers.stooq import StooqProvider


def test_stooq_request_and_provenance(request_range):
    def respond(request):
        assert request.url.host == "stooq.com"
        assert dict(request.url.params) == {
            "s": "synth.us",
            "d1": "20240102",
            "d2": "20240108",
            "i": "d",
        }
        return httpx.Response(200, content=FIXTURE)

    data = StooqProvider(transport=httpx.MockTransport(respond)).fetch(request_range)
    assert data.raw == FIXTURE
    assert not data.synthetic
    assert data.price_basis == "vendor_adjustment_unspecified"
    assert data.source.startswith("https://stooq.com/")


@pytest.mark.parametrize(
    "status,body",
    [(403, b"Denied"), (429, b"Limit"), (200, b"No data"), (200, b"<html>captcha</html>")],
)
def test_provider_errors(request_range, status, body):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=body))
    with pytest.raises(ProviderError):
        StooqProvider(transport=transport).fetch(request_range)


def test_timeout(request_range):
    def fail(request):
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(ProviderError, match="ReadTimeout"):
        StooqProvider(transport=httpx.MockTransport(fail)).fetch(request_range)


def test_fixture_is_explicitly_synthetic(request_range):
    assert FixtureProvider().fetch(request_range).synthetic
    from dataclasses import replace

    with pytest.raises(ProviderError, match="SYNTH"):
        FixtureProvider().fetch(replace(request_range, symbol="SPY"))

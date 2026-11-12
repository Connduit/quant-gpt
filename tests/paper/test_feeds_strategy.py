import hashlib
import json

import httpx
import polars as pl
import pytest
from conftest import T, quote

from quantlab.ml.models import ModelSpec, ResearchModel
from quantlab.paper.feeds import AlpacaQuotes, FeedRateLimited, FeedUnavailable
from quantlab.paper.reports import compare, report
from quantlab.paper.strategies import QuoteMomentum


def test_alpaca_normalization_poll_and_rate_limit():
    def respond(req):
        assert req.headers["APCA-API-KEY-ID"] == "test"
        assert req.url.host == "data.alpaca.markets"
        return httpx.Response(
            200,
            json={
                "quotes": {"SPY": {"t": T.isoformat(), "bp": 100, "ap": 100.02, "bs": 2, "as": 3}}
            },
        )

    f = AlpacaQuotes(
        ["SPY"],
        credentials=("test", "test"),
        feed="delayed_sip",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    e = f.poll()[0]
    assert e.mode == "delayed" and e.bid_size == 200 and e.ask_size == 300
    f.close()
    f = AlpacaQuotes(
        ["SPY"],
        credentials=("test", "test"),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(429, headers={"Retry-After": "2"})
            )
        ),
    )
    with pytest.raises(FeedRateLimited) as exc:
        f.poll()
    assert exc.value.retry_after == 2
    f.close()


def test_provider_failure_separate_from_data_validation():
    f = AlpacaQuotes(
        ["SPY"],
        credentials=("test", "test"),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))),
    )
    with pytest.raises(FeedUnavailable, match="HTTP 403"):
        f.poll()
    f.close()


def test_ml_pinned_features_and_repeat_decision(runtime, tmp_path):
    path = tmp_path / "model"
    frame = pl.DataFrame(
        {
            "quote_return": [-0.01, 0, 0.01, 0.02],
            "quote_spread": [0.0002] * 4,
            "target": [-0.01, 0, 0.01, 0.02],
        }
    )
    ResearchModel(ModelSpec("ridge")).fit(frame, ("quote_return", "quote_spread")).save(path)
    sha = hashlib.sha256((path / "model.joblib").read_bytes()).hexdigest()
    runtime.state["strategies"]["s"]["model_hash"] = sha
    # Persist the deployment pin through a normal transaction.
    runtime._transaction("pin", "test", {}, lambda: None)
    strategy = QuoteMomentum("s", "SPY", lookback=1, model=path, model_hash=sha)
    for n in (1, 2, 3):
        e = quote(n, bid=str(100 + n), ask=str(100.02 + n))
        runtime.ingest(e, now=e.received_at)
        strategy.on_event(runtime, e)
    count = len(runtime.state["predictions"])
    orders = len(runtime.orders)
    strategy.on_event(runtime, e)
    assert len(runtime.state["predictions"]) == count and len(runtime.orders) == orders
    assert runtime.state["predictions"][-1]["model_hash"] == sha
    assert report(runtime)["model_accuracy"] is None
    with pytest.raises(ValueError):
        QuoteMomentum("s", "SPY", model=path, model_hash="wrong")
    doc = json.loads((path / "manifest.json").read_text())
    assert doc["features"] == ["quote_return", "quote_spread"]


def test_no_invented_comparison_causes():
    r = compare({"mode": "backtest", "fees": 1}, {"mode": "replay", "fees": 2})
    assert r["comparison"]["fees"]["difference"] == 1
    assert r["comparison"]["signals"]["equal"] is None


def test_stream_authentication_and_quote_normalization(monkeypatch):
    import websockets.sync.client

    sent = []

    class Socket:
        replies = iter(
            [
                [{"msg": "connected"}],
                [{"msg": "authenticated"}],
                [
                    {
                        "T": "q",
                        "S": "SPY",
                        "t": T.isoformat(),
                        "bp": 100,
                        "ap": 100.02,
                        "bs": 1,
                        "as": 1,
                    }
                ],
            ]
        )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def recv(self, timeout):
            return json.dumps(next(self.replies))

        def send(self, payload):
            sent.append(json.loads(payload))

    monkeypatch.setattr(websockets.sync.client, "connect", lambda url, **kwargs: Socket())
    feed = AlpacaQuotes(["SPY"], credentials=("test", "test"))
    stream = feed.stream()
    event = next(stream)
    stream.close()
    feed.close()
    assert event.instrument == "SPY" and sent[-1]["action"] == "subscribe"


def test_duplicate_quotes_after_later_receive_time_do_not_backdate_orders(runtime):
    strategy = QuoteMomentum("s", "SPY", lookback=1, threshold=0)
    for n in (1, 2):
        e = quote(n, bid=str(100 + n), ask=str(100.02 + n))
        runtime.ingest(e, now=e.received_at)
        strategy.on_event(runtime, e)
    e2 = quote(3)
    runtime.ingest(e2, now=e2.received_at)
    before = len(runtime.orders)
    strategy.on_event(runtime, e)
    assert len(runtime.orders) == before


def test_direction_labels_mature_only_after_prespecified_horizon(runtime):
    strategy = QuoteMomentum("s", "SPY", lookback=1, horizon_events=2)
    for n in (1, 2, 3):
        e = quote(n, bid=str(100 + n), ask=str(100.02 + n))
        runtime.ingest(e, now=e.received_at)
        strategy.on_event(runtime, e)
        if n < 3:
            assert runtime.state["predictions"][0]["outcome"] is None
    assert runtime.state["predictions"][0]["matured_at"] == e.event_at.isoformat()

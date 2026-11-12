"""Official Alpaca quote transports and a licensed futures client boundary.

No historical provider is relabeled as streaming. Secrets stay in environment;
normal proxy and certificate settings are inherited by both transports.
"""

import json
import os
from datetime import UTC, datetime

import httpx

from quantlab.paper.events import MarketEvent, instant


class FeedUnavailable(RuntimeError):
    pass


class FeedRateLimited(FeedUnavailable):
    def __init__(self, retry_after):
        try:
            self.retry_after = min(60, max(1, float(retry_after)))
        except (ValueError, TypeError):
            self.retry_after = 60
        super().__init__(f"Provider rate limited; retry after {self.retry_after}s")


class AlpacaQuotes:
    base = "https://data.alpaca.markets"

    def __init__(self, symbols, *, feed="iex", client=None, credentials=None):
        if feed not in ("iex", "delayed_sip", "sip") or not symbols:
            raise ValueError("Explicit supported feed and symbols required")
        self.symbols = tuple(symbols)
        self.feed = feed
        key, secret = credentials or (
            os.getenv("APCA_API_KEY_ID"),
            os.getenv("APCA_API_SECRET_KEY"),
        )
        if not key or not secret:
            raise FeedUnavailable("Alpaca market-data credentials not configured")
        self._credentials = (key, secret)
        self.client = client or httpx.Client(timeout=20)
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.mode = "delayed" if feed == "delayed_sip" else "realtime"

    def normalize(self, symbol, quote, received=None, *, mode=None):
        return MarketEvent(
            symbol,
            "alpaca:" + self.feed,
            instant(quote["t"]),
            received or datetime.now(UTC),
            "quote",
            mode or self.mode,
            str(quote["t"]),
            str(quote["bp"]),
            str(quote["ap"]),
            int(quote["bs"]) * 100,
            int(quote["as"]) * 100,
        )

    def _get(self, path, params):
        try:
            response = self.client.get(self.base + path, params=params, headers=self.headers)
        except httpx.TransportError as exc:
            # Do not include request headers or credential-bearing objects in logs.
            raise FeedUnavailable("Alpaca transport failure: " + type(exc).__name__) from None
        if response.status_code == 429:
            raise FeedRateLimited(response.headers.get("retry-after"))
        if response.status_code != 200:
            raise FeedUnavailable(f"Alpaca HTTP {response.status_code}")
        return response.json()

    def poll(self):
        doc = self._get(
            "/v2/stocks/quotes/latest", {"symbols": ",".join(self.symbols), "feed": self.feed}
        )
        received = datetime.now(UTC)
        return [
            self.normalize(s, q, received) for s, q in doc["quotes"].items() if s in self.symbols
        ]

    def recover(self, start, end, *, max_pages=10):
        start, end = instant(start), instant(end)
        if not 0 < (end - start).total_seconds() <= 86400 or not 1 <= max_pages <= 100:
            raise ValueError("Bound quote recovery to one day and 1–100 pages")
        params = {
            "symbols": ",".join(self.symbols),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "feed": self.feed,
            "limit": 1000,
        }
        result = []
        for _ in range(max_pages):
            doc = self._get("/v2/stocks/quotes", params)
            for s, quotes in doc.get("quotes", {}).items():
                if s in self.symbols:
                    result.extend(self.normalize(s, q, mode="replay") for q in quotes)
            token = doc.get("next_page_token")
            if not token:
                return sorted(result, key=lambda e: e.event_at)
            params["page_token"] = token
        raise FeedUnavailable("Recovery page budget exhausted; gap remains unresolved")

    def stream(self):
        from websockets.sync.client import connect

        # websockets uses the inherited HTTPS proxy and default certificate verification.
        with connect(
            "wss://stream.data.alpaca.markets/v2/" + self.feed,
            open_timeout=20,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            welcome = json.loads(ws.recv(timeout=20))
            if not any(x.get("msg") == "connected" for x in welcome):
                raise FeedUnavailable("Alpaca stream did not acknowledge connection")
            ws.send(
                json.dumps(
                    {"action": "auth", "key": self._credentials[0], "secret": self._credentials[1]}
                )
            )
            ack = json.loads(ws.recv(timeout=20))
            if not any(x.get("msg") == "authenticated" for x in ack):
                raise FeedUnavailable("Alpaca streaming authentication failed")
            ws.send(json.dumps({"action": "subscribe", "quotes": list(self.symbols)}))
            while True:
                for q in json.loads(ws.recv(timeout=30)):
                    if q.get("T") == "error":
                        raise FeedUnavailable("Alpaca stream provider error")
                    if q.get("T") == "q" and q["S"] in self.symbols:
                        yield self.normalize(q["S"], q)

    def close(self):
        self.client.close()


class LicensedFuturesQuotes:
    """Inject an officially supported, authorized transport; no implicit direct TCP.

    Standard normalized records require actual contract mapping and explicit
    quote observation/receive times. No SDK credentials or network policy bypass
    is embedded here. Licensed transport deployment is unverified in this runtime.
    """

    def __init__(self, client, contracts, *, provider, mode):
        if not client or not provider or mode not in ("realtime", "delayed"):
            raise FeedUnavailable("Configured licensed futures transport required")
        self.client = client
        self.contracts = contracts
        self.provider = provider
        self.mode = mode

    def stream(self):
        for record in self.client:
            if record["instrument"] not in self.contracts:
                raise FeedUnavailable("Unknown contract mapping from futures feed")
            yield MarketEvent(provider=self.provider, mode=self.mode, **record)

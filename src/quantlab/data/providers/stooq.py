"""Stooq's free daily CSV endpoint; no broker or paid subscription required."""

import httpx

from quantlab.data.providers.base import DataRequest, Download, ProviderError


class StooqProvider:
    name = "stooq"

    def __init__(self, timeout_seconds: float = 30, transport=None) -> None:
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def fetch(self, request: DataRequest) -> Download:
        # Tickers are local US symbols; the adapter alone owns vendor suffixes.
        params = {
            "s": f"{request.symbol.lower()}.us",
            "d1": request.start.strftime("%Y%m%d"),
            "d2": request.end.strftime("%Y%m%d"),
            "i": "d",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.get("https://stooq.com/q/d/l/", params=params)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Stooq request failed ({type(exc).__name__})") from exc
        raw = response.content
        if not raw.lstrip().startswith(b"Date,Open,High,Low,Close,Volume"):
            raise ProviderError("Stooq returned no CSV data; check symbol, dates or source access")
        return Download(raw, str(response.url), "vendor_adjustment_unspecified", False)

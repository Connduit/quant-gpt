"""Import user-supplied daily OHLCV; adjustment semantics must be declared."""

from pathlib import Path

from quantlab.data.providers.base import DataRequest, Download


class CsvProvider:
    name = "local-csv"

    def __init__(self, path: Path, source: str, price_basis: str) -> None:
        if not source.strip() or price_basis not in ("unadjusted", "adjusted"):
            raise ValueError("CSV import needs a source and explicit adjustment basis")
        self.path, self.source, self.price_basis = path, source, price_basis

    def fetch(self, request: DataRequest) -> Download:
        return Download(self.path.read_bytes(), self.source, self.price_basis, False)

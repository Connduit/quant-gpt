"""Explicit synthetic daily bars for offline development, never market evidence."""

from quantlab.data.providers.base import DataRequest, Download, ProviderError

FIXTURE = b"""Date,Open,High,Low,Close,Volume
2024-01-02,100,102,99,101,1000
2024-01-03,101,103,100,102,1100
2024-01-04,102,104,101,103,1200
2024-01-05,103,104,101,102,1300
2024-01-08,102,105,102,104,1400
"""


class FixtureProvider:
    name = "fixture"

    def fetch(self, request: DataRequest) -> Download:
        if request.symbol != "SYNTH":
            raise ProviderError("Fixture only supports SYNTH, 2024-01-02 through 2024-01-08")
        return Download(FIXTURE, "builtin:synthetic-v1", "synthetic", True)

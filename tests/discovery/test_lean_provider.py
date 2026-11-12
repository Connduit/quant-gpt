import io
import zipfile
from datetime import date
from decimal import Decimal

import httpx
import pytest

from quantlab.backtesting.actions import CorporateActions, Dividend
from quantlab.data.providers.base import DataRequest, ProviderError
from quantlab.data.providers.lean import LeanProvider, decode_daily, decode_factors
from quantlab.data.validation import normalize_daily


def archive(symbol, lines):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(symbol.lower() + ".csv", lines)
    return stream.getvalue()


def test_lean_deci_cent_import_and_explicit_factor_proxy():
    request = DataRequest("TEST", date(2024, 1, 2), date(2024, 1, 5))
    raw = archive(
        "TEST",
        "20240102 00:00,1000000,1010000,990000,1000000,1000\n"
        "20240103 00:00,1000000,1010000,990000,1000000,1000\n"
        "20240104 00:00,500000,510000,490000,500000,2000\n"
        "20240105 00:00,490000,500000,480000,490000,2000\n",
    )
    provider = LeanProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))
    )
    download = provider.fetch(request)
    frame = normalize_daily(download.raw, request)
    assert frame["open"].to_list() == [100, 100, 50, 49]
    assert download.price_basis == "unadjusted" and not download.synthetic
    factors = b"20200101,0.98,0.5,1\n20240103,0.98,0.5,100\n20240104,0.98,1,50\n20501231,1,1,0\n"
    record = decode_factors(factors, request, frame)
    actions = record["actions"]
    assert not actions.complete and actions.coverage_method == "factor_file_proxy"
    assert actions.splits[0].ratio == 2
    assert actions.dividends[0].amount == 1
    assert actions.dividends[0].pay_date is None
    assert record["split_checks"][0]["price_jump_over_split"] == 1


def test_unknown_pay_dates_are_not_fabricated_and_require_explicit_alternative():

    with pytest.raises(ValueError, match="Unknown pay dates"):
        CorporateActions(
            "TEST",
            date(2024, 1, 2),
            date(2024, 1, 5),
            "unknown",
            dividends=(Dividend(date(2024, 1, 3), None, Decimal(1)),),
        )
    with pytest.raises(ValueError, match="cannot claim"):
        CorporateActions(
            "TEST",
            date(2024, 1, 2),
            date(2024, 1, 5),
            "proxy",
            coverage_method="factor_file_proxy",
            limitations=("unknown pay dates",),
        )


def test_bad_archive_and_unbracketed_factor_coverage_fail():
    request = DataRequest("TEST", date(2024, 1, 2), date(2024, 1, 3))
    with pytest.raises(ProviderError):
        decode_daily(b"not zip", request)
    frame = normalize_daily(
        b"Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,1,2,1\n2024-01-03,1,2,1,2,1\n", request
    )
    with pytest.raises(ProviderError, match="bracket"):
        decode_factors(b"20250101,1,1,1\n20501231,1,1,0\n", request, frame)


def test_verified_import_reuses_ids_and_preserves_modified_user_files(tmp_path, monkeypatch):
    import hashlib

    from quantlab.data.providers import lean

    raw = archive(
        "TEST",
        "20240102 00:00,1000000,1010000,990000,1000000,1000\n"
        "20240103 00:00,1000000,1010000,990000,1000000,1000\n"
        "20240104 00:00,500000,510000,490000,500000,2000\n"
        "20240105 00:00,490000,500000,480000,490000,2000\n",
    )
    factors = b"20200101,0.98,0.5,1\n20240103,0.98,0.5,100\n20240104,0.98,1,50\n20501231,1,1,0\n"

    def fetch(self, path):
        payload = raw if path.endswith(".zip") else factors
        self.evidence[f"{lean.BASE}/{path}"] = hashlib.sha256(payload).hexdigest()
        self.payloads[path] = payload
        return payload

    monkeypatch.setattr(LeanProvider, "_get", fetch)
    root = tmp_path / "real-interface-fixture"
    first = lean.import_lean_universe(
        root, date(2024, 1, 2), date(2024, 1, 5), allow_factor_proxy=True, symbols=["TEST"]
    )

    def no_network(*args):
        raise AssertionError("Verified inputs must be reused")

    monkeypatch.setattr(LeanProvider, "_get", no_network)
    repeated = lean.import_lean_universe(
        root, date(2024, 1, 2), date(2024, 1, 5), allow_factor_proxy=True, symbols=["TEST"]
    )
    assert first["snapshots"] == repeated["snapshots"]
    ledger = root / "actions" / "TEST.json"
    changed = ledger.read_text().replace("QuantConnect LEAN", "User edit: QuantConnect LEAN")
    ledger.write_text(changed)
    with pytest.raises(ValueError, match="has not been overwritten"):
        lean.import_lean_universe(
            root, date(2024, 1, 2), date(2024, 1, 5), allow_factor_proxy=True, symbols=["TEST"]
        )
    assert ledger.read_text() == changed

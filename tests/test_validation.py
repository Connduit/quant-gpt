from datetime import date, datetime

import pytest

from quantlab.data.providers.base import DataRequest
from quantlab.data.providers.fixture import FIXTURE
from quantlab.data.validation import ValidationError, normalize_daily


def test_normalized_schema_and_session_close(request_range):
    frame = normalize_daily(FIXTURE, request_range)
    assert frame.height == 5
    assert frame["symbol"].unique().to_list() == ["SYNTH"]
    assert str(frame.schema["timestamp"]) == "Datetime(time_unit='us', time_zone='UTC')"
    assert frame["timestamp"][0].isoformat() == "2024-01-02T21:00:00+00:00"
    assert frame["available_at"][0].isoformat() == "2024-01-03T05:00:00+00:00"
    assert frame["session_date"][0] == date(2024, 1, 2)


@pytest.mark.parametrize(
    "replacement",
    [
        b"2024-01-02,,102,99,101,1000",
        b"2024-01-02,NaN,102,99,101,1000",
        b"2024-01-02,inf,102,99,101,1000",
        b"2024-01-02,-1,102,99,101,1000",
        b"2024-01-02,100,98,99,101,1000",
        b"2024-01-02,100,102,101,101,1000",
        b"2024-01-02,100,102,99,101,-1",
        b"2024-01-02,100,102,99,101,1.5",
        b"not-a-date,100,102,99,101,1000",
    ],
)
def test_rejects_invalid_values(request_range, replacement):
    raw = FIXTURE.replace(b"2024-01-02,100,102,99,101,1000", replacement)
    with pytest.raises(ValidationError):
        normalize_daily(raw, request_range)


def test_duplicate_and_missing_sessions(request_range):
    with pytest.raises(ValidationError, match="Duplicate"):
        normalize_daily(FIXTURE + b"2024-01-02,100,102,99,101,1000\n", request_range)
    with pytest.raises(ValidationError, match="Missing XNYS"):
        normalize_daily(FIXTURE.replace(b"2024-01-03,101,103,100,102,1100\n", b""), request_range)


def test_rejects_nontrading_days():
    raw = b"Date,Open,High,Low,Close,Volume\n2024-01-01,1,2,1,2,5\n"
    with pytest.raises(ValidationError, match="non-XNYS"):
        normalize_daily(raw, DataRequest("X", date(2024, 1, 1), date(2024, 1, 2)))


def test_early_close_and_dst():
    raw = b"Date,Open,High,Low,Close,Volume\n2024-11-29,1,2,1,2,5\n"
    frame = normalize_daily(raw, DataRequest("X", date(2024, 11, 29), date(2024, 11, 29)))
    assert frame["timestamp"][0].isoformat() == "2024-11-29T18:00:00+00:00"
    raw = raw.replace(b"2024-11-29", b"2024-07-03")
    frame = normalize_daily(raw, DataRequest("X", date(2024, 7, 3), date(2024, 7, 3)))
    assert frame["timestamp"][0].isoformat() == "2024-07-03T17:00:00+00:00"
    assert frame["available_at"][0].hour == 4


def test_sorts_and_filters_vendor_rows():
    lines = FIXTURE.splitlines()
    frame = normalize_daily(
        b"\n".join([lines[0], *reversed(lines[1:])]),
        DataRequest("SYNTH", date(2024, 1, 3), date(2024, 1, 4)),
    )
    assert frame["session_date"].to_list() == [date(2024, 1, 3), date(2024, 1, 4)]


@pytest.mark.parametrize("raw", [b"", b"Date,Close\n2024-01-02,1\n", b"<html>blocked</html>"])
def test_malformed_csv(request_range, raw):
    with pytest.raises(ValidationError):
        normalize_daily(raw, request_range)


def test_empty_range():
    with pytest.raises(ValidationError, match="No data"):
        normalize_daily(FIXTURE, DataRequest("SYNTH", date(2023, 1, 3), date(2023, 1, 4)))


@pytest.mark.parametrize("symbol", ["../SPY", "SPY/us", "", "A?x=1"])
def test_invalid_symbol(symbol):
    with pytest.raises(ValueError):
        DataRequest(symbol, date(2024, 1, 2), date(2024, 1, 3))


def test_request_dates():
    with pytest.raises(ValueError, match="start"):
        DataRequest("SPY", date(2024, 1, 3), date(2024, 1, 2))
    with pytest.raises(ValueError, match="historical"):
        DataRequest("SPY", date(2024, 1, 2), datetime.now().date())

"""Pinned QuantConnect LEAN sample archive, with explicit factor-file limitations."""

import csv
import hashlib
import io
import zipfile
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import exchange_calendars as xcals
import httpx

from quantlab.backtesting.actions import CorporateActions, Dividend, Split
from quantlab.backtesting.report import dumps
from quantlab.data.providers.base import (
    DataRequest,
    Download,
    ProviderError,
    ProviderHTTPError,
    ProviderNetworkError,
)
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily

PINNED_COMMIT = "655ac6d475ad8539ff54583a26327e63b59c5703"
BASE = f"https://raw.githubusercontent.com/QuantConnect/Lean/{PINNED_COMMIT}"
# A source-constrained, survivor-prone selection; not historical index membership.
STOCKS = {
    "AAPL": "technology",
    "AIG": "financials",
    "BAC": "financials",
    "FB": "communications",
    "GOOGL": "communications",
    "IBM": "technology",
    "WM": "industrials",
}
LIMITATIONS = (
    "Corporate-event completeness is not certified; supplied factor changes are represented.",
    "Distributions are reconstructed from rounded factors, not authoritative dividend records.",
    "Unknown payment dates stay null; distributions remain non-spendable receivables.",
    "Non-cash distributions may be cash-equivalent proxies; this is not full action coverage.",
)


class LeanProvider:
    name = "quantconnect-lean-archive"

    def __init__(self, *, transport=None, timeout=30):
        self.transport, self.timeout = transport, timeout
        self.evidence = {}
        self.payloads = {}

    def _get(self, path):
        url = f"{BASE}/{path}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderHTTPError(
                f"LEAN archive HTTP status {exc.response.status_code}: {path}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderNetworkError(
                f"LEAN archive network request failed: {path} ({type(exc).__name__})"
            ) from exc
        self.evidence[url] = hashlib.sha256(response.content).hexdigest()
        self.payloads[path] = response.content
        return response.content

    def fetch(self, request: DataRequest) -> Download:
        payload = self._get(f"Data/equity/usa/daily/{request.symbol.lower()}.zip")
        raw = decode_daily(payload, request)
        return Download(
            raw,
            f"{BASE}/Data/equity/usa/daily/{request.symbol.lower()}.zip; LEAN raw deci-cent format",
            "unadjusted",
            False,
        )

    def factors(self, request, frame):
        raw = self._get(f"Data/equity/usa/factor_files/{request.symbol.lower()}.csv")
        return decode_factors(raw, request, frame), raw


def decode_daily(payload: bytes, request: DataRequest) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if archive.namelist() != [f"{request.symbol.lower()}.csv"]:
                raise ValueError("Unexpected ZIP members")
            info = archive.infolist()[0]
            if info.file_size > 100_000_000:
                raise ValueError("Oversized daily archive")
            lines = archive.read(info).decode("utf-8").splitlines()
        for row in csv.reader(lines):
            if len(row) != 6:
                raise ValueError("Invalid daily row")
            day = datetime.strptime(row[0], "%Y%m%d %H:%M").date()
            if request.start <= day <= request.end:
                writer.writerow(
                    [day.isoformat(), *[str(Decimal(p) / 10000) for p in row[1:5]], row[5]]
                )
    except (ValueError, zipfile.BadZipFile, UnicodeError) as exc:
        raise ProviderError("Malformed LEAN daily archive") from exc
    return output.getvalue().encode()


def decode_factors(raw, request, frame):
    rows = []
    for row in csv.reader(raw.decode().splitlines()):
        if len(row) != 4:
            raise ProviderError("Expected four-column factor records")
        day = datetime.strptime(row[0], "%Y%m%d").date()
        price, split, reference = map(Decimal, row[1:])
        if (
            not all(v.is_finite() for v in (price, split, reference))
            or min(price, split) <= 0
            or reference < 0
        ):
            raise ProviderError("Invalid factor values")
        rows.append((day, price, split, reference))
    if (
        any(a[0] >= b[0] for a, b in zip(rows, rows[1:], strict=False))
        or not rows
        or rows[0][0] > request.start
        or rows[-1][0] <= request.end
    ):
        raise ProviderError("Factor file does not bracket the requested interval")
    calendar = xcals.get_calendar(
        "XNYS", start=request.start - timedelta(days=14), end=request.end + timedelta(days=14)
    )
    sessions = [s.date() for s in calendar.sessions]
    splits, dividends = [], []
    split_checks = []
    by_date = {r["session_date"]: r for r in frame.iter_rows(named=True)}
    for current, next_row in zip(rows, rows[1:], strict=False):
        day, price, split, reference = current
        if day < request.start - timedelta(days=7) or day >= request.end:
            continue
        effective = next((s for s in sessions if s > day), None)
        if effective is None or not request.start <= effective <= request.end:
            continue
        if price != next_row[1]:
            amount = (reference * (1 - price / next_row[1])).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_EVEN
            )
            if amount < 0:
                raise ProviderError("Negative factor distribution is unsupported")
            if amount:
                dividends.append(Dividend(effective, None, amount))
        if split != next_row[2]:
            ratio = next_row[2] / split
            # Recover simple rational split ratios from the archive's rounded factors.
            from fractions import Fraction

            rational = Fraction(float(ratio)).limit_denominator(100)
            candidate = Decimal(rational.numerator) / Decimal(rational.denominator)
            if abs(candidate / ratio - 1) > Decimal("0.0001"):
                raise ProviderError("Cannot resolve a reliable split ratio")
            ratio = candidate
            before = by_date.get(day)
            after = by_date.get(effective)
            if before and after:
                observed = Decimal(str(before["close"])) / Decimal(str(after["open"]))
                relative = float(observed / ratio)
                if not 0.7 <= relative <= 1.3:
                    raise ProviderError("Raw-price split discontinuity does not match factor split")
                split_checks.append(
                    {"date": effective, "ratio": str(ratio), "price_jump_over_split": relative}
                )
            splits.append(Split(effective, ratio))
    actions = CorporateActions(
        request.symbol,
        request.start,
        request.end,
        f"QuantConnect LEAN factor-file proxy at {PINNED_COMMIT}",
        tuple(splits),
        tuple(dividends),
        complete=False,
        coverage_method="factor_file_proxy",
        limitations=LIMITATIONS,
    )
    return {
        "actions": actions,
        "split_checks": split_checks,
        "factor_rows": len(rows),
        "factor_file_brackets_interval": True,
        "full_corporate_action_certification": False,
    }


def crosscheck_aapl(root, snapshot_id):
    import statistics

    url = (
        "https://raw.githubusercontent.com/plotly/datasets/"
        "0c447c47b757ad74edecab31f0d72f849d2e67c2/finance-charts-apple.csv"
    )
    with httpx.Client(timeout=30) as client:
        response = client.get(url)
        response.raise_for_status()
    frame = SnapshotStore(root).read(snapshot_id)
    lookup = {str(r["session_date"]): r["close"] for r in frame.iter_rows(named=True)}
    errors = []
    for row in csv.DictReader(io.StringIO(response.text)):
        if row["Date"] in lookup:
            errors.append(abs(float(row["AAPL.Close"]) - lookup[row["Date"]]))
    if len(errors) < 100 or statistics.median(errors) > 0.01:
        raise ProviderError("Independent archived AAPL cross-check failed")
    (root / "source" / "aapl-independent-reference.csv").write_bytes(response.content)
    return {
        "url": url,
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "overlapping_sessions": len(errors),
        "median_close_error": statistics.median(errors),
        "maximum_close_error": max(errors),
        "fraction_within_one_cent": sum(e <= 0.01001 for e in errors) / len(errors),
        "scope": "AAPL price-level check only; no full-universe or corporate-event certification",
    }


def verify_existing_import(root, start, end, symbols):
    import json

    report = json.loads((root / "data_quality.json").read_text())
    if report["commit"] != PINNED_COMMIT or set(report["snapshots"]) != set(symbols):
        raise ValueError(
            "Existing inputs have different provenance/universe; choose a new data directory"
        )
    store = SnapshotStore(root)
    for symbol in symbols:
        request = DataRequest(symbol, start, end)
        metadata = store.manifest(report["snapshots"][symbol]["snapshot_id"])
        if metadata["request"] != request.as_dict():
            raise ValueError("Existing input time range differs; choose a new data directory")
        zipped = (root / "source" / f"{symbol}.zip").read_bytes()
        factors = (root / "source" / f"{symbol}-factors.csv").read_bytes()
        for kind, payload in (("daily", zipped), ("factor_files", factors)):
            suffix = "zip" if kind == "daily" else "csv"
            url = f"{BASE}/Data/equity/usa/{kind}/{symbol.lower()}.{suffix}"
            if hashlib.sha256(payload).hexdigest() != report["source_hashes"][url]:
                raise ValueError("Existing source artifact changed; choose a new data directory")
        raw = decode_daily(zipped, request)
        frame = store.read(report["snapshots"][symbol]["snapshot_id"])
        if hashlib.sha256(raw).hexdigest() != metadata["raw_sha256"] or not frame.equals(
            normalize_daily(raw, request)
        ):
            raise ValueError("Existing normalized prices differ from the pinned source")
        actual = CorporateActions.load(Path(report["snapshots"][symbol]["actions"]))
        expected = decode_factors(factors, request, frame)["actions"]
        if asdict(actual) != asdict(expected):
            raise ValueError("Existing action ledger was changed; it has not been overwritten")
    reference = report.get("independent_crosscheck")
    if (
        reference
        and hashlib.sha256(
            (root / "source" / "aapl-independent-reference.csv").read_bytes()
        ).hexdigest()
        != reference["sha256"]
    ):
        raise ValueError("Existing independent reference artifact changed")
    return report


def import_lean_universe(
    root: Path, start: date, end: date, *, allow_factor_proxy=False, symbols=None
):
    if not allow_factor_proxy:
        raise ValueError(
            "Missing pay dates/event certification: explicitly enable the factor proxy"
        )
    requested = tuple(symbols or (*STOCKS, "SPY"))
    if (root / "data_quality.json").exists():
        return verify_existing_import(root, start, end, requested)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Unverified existing input files: choose an empty data directory")
    root.mkdir(parents=True, exist_ok=True)
    (root / "actions").mkdir(exist_ok=True)
    (root / "source").mkdir(exist_ok=True)
    provider = LeanProvider()
    snapshots, quality = {}, {}
    for symbol in symbols or (*STOCKS, "SPY"):
        request = DataRequest(symbol, start, end)
        download = provider.fetch(request)
        frame = normalize_daily(download.raw, request)
        record, factor_raw = provider.factors(request, frame)
        identifier = SnapshotStore(root).write(provider.name, request, download, frame)
        ledger = root / "actions" / f"{symbol}.json"
        ledger.write_text(dumps(asdict(record["actions"])))
        (root / "source" / f"{symbol}-factors.csv").write_bytes(factor_raw)
        (root / "source" / f"{symbol}.zip").write_bytes(
            provider.payloads[f"Data/equity/usa/daily/{symbol.lower()}.zip"]
        )
        snapshots[symbol] = {"snapshot_id": identifier, "actions": str(ledger.resolve())}
        quality[symbol] = {k: v for k, v in record.items() if k != "actions"}
        quality[symbol].update(
            rows=frame.height,
            start=str(start),
            end=str(end),
            sectors=STOCKS.get(symbol, "benchmark"),
        )
    crosscheck = (
        crosscheck_aapl(root, snapshots["AAPL"]["snapshot_id"]) if "AAPL" in snapshots else None
    )
    report = {
        "independent_crosscheck": crosscheck,
        "provider": provider.name,
        "commit": PINNED_COMMIT,
        "source_hashes": provider.evidence,
        "snapshots": snapshots,
        "quality": quality,
        "limitations": LIMITATIONS,
        "raw_price_evidence": f"{BASE}/Data/equity/readme.md; raw reader and split checks",
        "universe_bias": "Fixed archive survivors/share classes; not an unbiased universe.",
        "unavailable_preference": (
            "Archive lacks 10-20 suitable distinct stock histories; "
            "seven stocks selected across four sectors."
        ),
    }
    (root / "data_quality.json").write_text(dumps(report))
    return report

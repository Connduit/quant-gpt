"""UTC storage with CME-local sessions and explicit dated operating-hour overrides."""

from dataclasses import dataclass, field
from datetime import UTC, date, time, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

CT = ZoneInfo("America/Chicago")


@dataclass
class FuturesCalendar:
    mode: str = "rth"
    # RTH is the declared cash-index research window, not all exchange trading hours.
    rth_open: time = time(8, 30)
    rth_close: time = time(15)
    holidays: set = field(default_factory=set)
    early_closes: dict = field(default_factory=dict)
    maintenance_breaks: tuple = ((time(16), time(17)),)
    overrides_source: str = "exchange_calendars CMES + caller-supplied dated CME exceptions"

    def __post_init__(self):
        if self.mode not in ("rth", "eth"):
            raise ValueError("Session mode must be rth or eth")
        self.calendar = xcals.get_calendar("CMES", start="2000-01-01", end="2035-12-31")

    def session(self, timestamp):
        if timestamp.tzinfo is None:
            raise ValueError("Timezone-aware UTC timestamps required")
        local = timestamp.astimezone(CT)
        label = local.date() + timedelta(days=1) if local.time() >= time(17) else local.date()
        if label in self.holidays or not self.calendar.is_session(label.isoformat()):
            return None
        start = self.calendar.session_open(label.isoformat()).to_pydatetime()
        end = self.calendar.session_close(label.isoformat()).to_pydatetime()
        if not start <= timestamp < end:
            return None
        close = self.early_closes.get(label)
        if close is not None and local.date() == label and local.time() >= close:
            return None
        if any(a <= local.time() < b for a, b in self.maintenance_breaks):
            return None
        if self.mode == "rth":
            if local.date() != label or not self.rth_open <= local.time() < min(
                self.rth_close, close or self.rth_close
            ):
                return None
        return label

    def expected(self, session, minutes=1):
        if type(minutes) is not int or minutes < 1:
            raise ValueError("Positive bar minutes required")
        day = date.fromisoformat(str(session))
        if day in self.holidays or not self.calendar.is_session(str(day)):
            return []
        start = self.calendar.session_open(str(day)).to_pydatetime()
        end = self.calendar.session_close(str(day)).to_pydatetime()
        result = []
        t = start
        while t < end:
            if self.session(t) == day:
                result.append(t.astimezone(UTC))
            t += timedelta(minutes=minutes)
        return result


def calendar_definition(calendar):
    return {
        "mode": calendar.mode,
        "rth_open": calendar.rth_open.isoformat(),
        "rth_close": calendar.rth_close.isoformat(),
        "holidays": sorted(str(d) for d in calendar.holidays),
        "early_closes": {str(k): v.isoformat() for k, v in calendar.early_closes.items()},
        "maintenance_breaks": [
            [a.isoformat(), b.isoformat()] for a, b in calendar.maintenance_breaks
        ],
        "overrides_source": calendar.overrides_source,
    }


def calendar_from_dict(values):
    values = values.copy()
    for key in ("rth_open", "rth_close"):
        if key in values:
            values[key] = time.fromisoformat(str(values[key]))
    if "holidays" in values:
        values["holidays"] = {date.fromisoformat(str(d)) for d in values["holidays"]}
    if "early_closes" in values:
        values["early_closes"] = {
            date.fromisoformat(str(k)): time.fromisoformat(str(v))
            for k, v in values["early_closes"].items()
        }
    if "maintenance_breaks" in values:
        values["maintenance_breaks"] = tuple(
            (time.fromisoformat(str(a)), time.fromisoformat(str(b)))
            for a, b in values["maintenance_breaks"]
        )
    return FuturesCalendar(**values)

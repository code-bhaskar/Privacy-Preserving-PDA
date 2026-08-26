import re
from datetime import datetime, timedelta, timezone

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", re.I
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _apply_time(base: datetime, hour: int, minute: int) -> datetime:
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_relative_datetime(text: str, ref: datetime | None = None) -> datetime | None:
    """FR-8: resolve 'tomorrow', 'next monday', 'in 3 days', 'at 10 am'."""
    ref = ref or now_utc()
    t = text.lower()
    date_part: datetime | None = None

    if "day after tomorrow" in t:
        date_part = ref + timedelta(days=2)
    elif "tomorrow" in t:
        date_part = ref + timedelta(days=1)
    elif "today" in t or "tonight" in t:
        date_part = ref
    else:
        m = re.search(r"in\s+(\d+)\s+day", t)
        if m:
            date_part = ref + timedelta(days=int(m.group(1)))
        else:
            for name, idx in WEEKDAYS.items():
                if name in t:
                    delta = (idx - ref.weekday()) % 7
                    if delta == 0 or "next" in t:
                        delta = delta or 7
                    date_part = ref + timedelta(days=delta)
                    break

    hour = minute = None
    for m in _TIME_RE.finditer(text):
        raw_h, raw_m, mer = m.group(1), m.group(2), m.group(3)
        h = int(raw_h)
        if h > 24:
            continue
        mm = int(raw_m) if raw_m else 0
        if mer:
            mer = mer.replace(".", "").lower()
            if mer == "pm" and h < 12:
                h += 12
            if mer == "am" and h == 12:
                h = 0
        elif h <= 7:            # "at 3" in an assistant context → afternoon
            h += 12
        if 0 <= h <= 23:
            hour, minute = h, mm
            break

    if date_part is None and hour is None:
        return None
    base = date_part or ref
    if hour is not None:
        base = _apply_time(base, hour, minute or 0)
        if date_part is None and base < ref:
            base += timedelta(days=1)
    else:
        base = _apply_time(base, 9, 0)
    return base

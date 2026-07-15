"""Date utilities — MMDD parsing, Excel serial date conversion, time labels.

Key conventions:
- MMDD format: 4-digit string like '0522' (month + day, no year = 2026)
- Excel serial date: days since 1899-12-30 (the Excel epoch)
- 96-point time labels: 00:15, 00:30, ..., 24:00
"""

from datetime import datetime, date, timedelta


def parse_mmdd(date_str: str) -> tuple[int, int]:
    """Parse MMDD string to (month, day) tuple.

    Args:
        date_str: 4-digit string like '0522' or '0501'.

    Returns:
        (month, day) as integers.
    """
    if len(date_str) != 4:
        raise ValueError(f"Expected MMDD format (4 chars), got: {date_str}")
    month = int(date_str[:2])
    day = int(date_str[2:])
    return month, day


def mmdd_to_date(date_str: str, year: int = 2026) -> date:
    """Convert MMDD string to a date object.

    Args:
        date_str: 4-digit string like '0522'.
        year: Default year (2026).

    Returns:
        datetime.date object.
    """
    month, day = parse_mmdd(date_str)
    return date(year, month, day)


def date_to_mmdd(d: date) -> str:
    """Convert a date object to MMDD string."""
    return d.strftime("%m%d")


def date_to_iso(d: date) -> str:
    """Convert a date object to ISO format string (YYYY-MM-DD)."""
    return d.isoformat()


def to_excel_serial(d: date) -> int:
    """Convert a date to Excel serial number (days since 1899-12-30).

    Args:
        d: Python date object.

    Returns:
        Integer Excel serial number (e.g., 46163 for a 2026 date).
    """
    epoch = date(1899, 12, 30)
    return (d - epoch).days


def from_excel_serial(serial: int) -> date:
    """Convert an Excel serial number back to a Python date.

    Args:
        serial: Excel serial number (integer).

    Returns:
        datetime.date object.
    """
    epoch = date(1899, 12, 30)
    return epoch + timedelta(days=serial)


def expand_mmdd_range(range_str: str, year: int = 2026) -> list[date]:
    """Parse a date range string like '0522-0531' into a list of dates.

    Args:
        range_str: 'MMDD-MMDD' or 'MMDD' (single date).
        year: Default year.

    Returns:
        List of date objects, inclusive.
    """
    if "-" in range_str:
        start_str, end_str = range_str.split("-")
        start = mmdd_to_date(start_str, year)
        end = mmdd_to_date(end_str, year)
        if end < start:
            # Cross-month: e.g., '0531-0603'
            end = end.replace(year=end.year + 1) if end.month < start.month else end
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)
        return dates
    else:
        return [mmdd_to_date(range_str, year)]


def get_96point_labels() -> list[str]:
    """Generate 96 time labels: 00:15, 00:30, ..., 24:00."""
    labels = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            labels.append(f"{h:02d}:{m:02d}")
    return labels


def time_label_to_index(label: str) -> int:
    """Convert a time label like '08:45' to a 0-based index in the 96-point array.

    Args:
        label: Time string like '08:45' or '14:00'.

    Returns:
        0-based index (0-95).
    """
    parts = label.split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    return hour * 4 + minute // 15


def time_label_to_hours(label: str) -> float:
    """Convert a time label to decimal hours."""
    parts = label.split(":")
    return int(parts[0]) + int(parts[1]) / 60.0
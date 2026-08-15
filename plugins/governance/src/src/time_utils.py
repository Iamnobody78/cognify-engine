"""Time utilities for scheduler tasks (TASK-SCHED-001)."""

from datetime import datetime, timezone

EPOCH: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)


def format_ts(dt: datetime) -> str:
    """Format a datetime as an ISO-8601 string with 'Z' suffix (UTC)."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ts(s: str) -> datetime:
    """Parse an ISO-8601 string ('Z' or '+00:00' suffix) back to an aware UTC datetime.

    Raises ValueError on malformed input.
    """
    if not isinstance(s, str) or not s:
        raise ValueError(f"malformed timestamp: {s!r}")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    elif not s.endswith("+00:00"):
        raise ValueError(f"timestamp must end with 'Z' or '+00:00': {s!r}")
    return datetime.fromisoformat(s)


def is_weekend(dt: datetime) -> bool:
    """Return True if dt falls on a weekend (Saturday or Sunday)."""
    return dt.weekday() >= 5

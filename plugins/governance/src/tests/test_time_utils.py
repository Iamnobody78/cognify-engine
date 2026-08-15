"""Tests for src.time_utils (TASK-SCHED-001 builder)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.time_utils import EPOCH, format_ts, is_weekend, parse_ts


def test_format_ts_z_suffix_utc():
    dt = datetime(2026, 8, 3, 12, 34, 56, tzinfo=timezone.utc)
    assert format_ts(dt) == "2026-08-03T12:34:56Z"


def test_format_ts_converts_to_utc():
    # Non-UTC aware datetime must be normalized to UTC and gain 'Z'.
    dt = datetime(2026, 8, 3, 14, 34, 56, tzinfo=timezone(timedelta(hours=2)))
    assert format_ts(dt) == "2026-08-03T12:34:56Z"


def test_format_parse_roundtrip():
    dt = datetime(2026, 8, 8, 23, 59, 59, 123456, tzinfo=timezone.utc)
    parsed = parse_ts(format_ts(dt))
    assert parsed == dt
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_parse_z_suffix_aware_utc():
    parsed = parse_ts("2026-08-08T10:00:00Z")
    assert parsed == datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_plus_00_00_equivalent_to_z():
    z = parse_ts("2026-08-08T10:00:00Z")
    plus = parse_ts("2026-08-08T10:00:00+00:00")
    assert z == plus
    assert z.tzinfo is not None and plus.tzinfo is not None


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-timestamp",
        "2026-08-08T10:00:00",          # missing suffix -> naive
        "2026-08-08T10:00:00Z trailing",  # trailing garbage
        "2026-13-99T99:99:99Z",          # out-of-range fields
        "2026-08-08T10:00:00+02:00",     # non-UTC offset suffix not accepted
    ],
)
def test_parse_malformed_raises(bad):
    with pytest.raises(ValueError):
        parse_ts(bad)


def test_is_weekend_saturday_true():
    assert is_weekend(datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)) is True


def test_is_weekend_sunday_true():
    assert is_weekend(datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)) is True


def test_is_weekend_friday_false():
    assert is_weekend(datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)) is False


def test_epoch_value():
    expected = datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert EPOCH == expected
    assert EPOCH.tzinfo == timezone.utc
    assert format_ts(EPOCH) == "1970-01-01T00:00:00Z"
    assert parse_ts("1970-01-01T00:00:00Z") == EPOCH

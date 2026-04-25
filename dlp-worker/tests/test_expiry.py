"""Tests for expiry-bucket selection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from expiry import expiry_bucket


_NOW = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)


def _yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


class TestExpiryBucket:
    def test_uploaded_today(self) -> None:
        assert expiry_bucket(_yyyymmdd(_NOW), _NOW) == "expire-1d"

    def test_uploaded_three_days_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=3))
        assert expiry_bucket(d, _NOW) == "expire-1d"

    def test_uploaded_four_days_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=4))
        assert expiry_bucket(d, _NOW) == "expire-3d"

    def test_uploaded_seven_days_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=7))
        assert expiry_bucket(d, _NOW) == "expire-3d"

    def test_uploaded_eight_days_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=8))
        assert expiry_bucket(d, _NOW) == "expire-6d"

    def test_uploaded_fourteen_days_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=14))
        assert expiry_bucket(d, _NOW) == "expire-6d"

    def test_uploaded_fifteen_days_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=15))
        assert expiry_bucket(d, _NOW) == "expire-8w"

    def test_uploaded_long_ago(self) -> None:
        d = _yyyymmdd(_NOW - timedelta(days=365))
        assert expiry_bucket(d, _NOW) == "expire-8w"

    def test_empty_upload_date_falls_back_to_default(self) -> None:
        assert expiry_bucket("", _NOW) == "expire-8w"

    def test_unparseable_upload_date_falls_back_to_default(self) -> None:
        assert expiry_bucket("not-a-date", _NOW) == "expire-8w"

    def test_short_upload_date_falls_back_to_default(self) -> None:
        assert expiry_bucket("2026", _NOW) == "expire-8w"

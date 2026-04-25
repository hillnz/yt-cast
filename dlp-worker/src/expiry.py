"""Choose an R2 retention bucket for a downloaded video.

Each bucket name is also a key prefix in R2; lifecycle rules on the
bucket (configured externally) delete objects under each prefix after
the matching number of days.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Ordered (max video age, bucket) pairs. The first matching bucket
# wins; videos older than the last bucket fall back to ``_DEFAULT_BUCKET``.
_BUCKETS: tuple[tuple[timedelta, str], ...] = (
    (timedelta(days=3), "expire-1d"),
    (timedelta(days=7), "expire-3d"),
    (timedelta(days=14), "expire-6d"),
)
_DEFAULT_BUCKET = "expire-8w"

ALL_BUCKETS: tuple[str, ...] = tuple(b for _, b in _BUCKETS) + (_DEFAULT_BUCKET,)


def _parse_upload_date(upload_date: str) -> datetime | None:
    """Parse the DLP ``YYYYMMDD`` upload_date into a UTC datetime."""
    if not upload_date or len(upload_date) < 8:
        return None
    try:
        dt = datetime.strptime(upload_date[:8], "%Y%m%d")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


def expiry_bucket(upload_date: str, now: datetime) -> str:
    """Return the R2 prefix the video should be stored under."""
    yt_uploaded = _parse_upload_date(upload_date)
    if yt_uploaded is None:
        return _DEFAULT_BUCKET
    age = now - yt_uploaded
    for max_age, bucket in _BUCKETS:
        if age <= max_age:
            return bucket
    return _DEFAULT_BUCKET

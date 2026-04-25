"""Choose an R2 retention bucket for a downloaded video.

Each bucket name is also a key prefix in R2; lifecycle rules on the
bucket (configured externally) delete objects under each prefix after
the matching number of days.
"""

from __future__ import annotations

from datetime import date, datetime

# Ordered (max video age in days, bucket) pairs. The first matching
# bucket wins; videos older than the last bucket fall back to
# ``_DEFAULT_BUCKET``. Age is measured in whole days because the DLP
# ``upload_date`` is date-only.
_BUCKETS: tuple[tuple[int, str], ...] = (
    (3, "expire-1d"),
    (7, "expire-3d"),
    (14, "expire-6d"),
)
_DEFAULT_BUCKET = "expire-8w"

ALL_BUCKETS: tuple[str, ...] = tuple(b for _, b in _BUCKETS) + (_DEFAULT_BUCKET,)


def _parse_upload_date(upload_date: str) -> date | None:
    """Parse the DLP ``YYYYMMDD`` upload_date into a date."""
    if not upload_date or len(upload_date) < 8:
        return None
    try:
        return datetime.strptime(upload_date[:8], "%Y%m%d").date()
    except ValueError:
        return None


def expiry_bucket(upload_date: str, now: datetime) -> str:
    """Return the R2 prefix the video should be stored under."""
    yt_uploaded = _parse_upload_date(upload_date)
    if yt_uploaded is None:
        return _DEFAULT_BUCKET
    age_days = (now.date() - yt_uploaded).days
    for max_days, bucket in _BUCKETS:
        if age_days <= max_days:
            return bucket
    return _DEFAULT_BUCKET

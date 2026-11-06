"""Age bands for open jobs. Pure functions with no database access."""
from datetime import date

BUCKETS = (
    ("0-2", "0 to 2 days", 0, 2),
    ("3-7", "3 to 7 days", 3, 7),
    ("8-14", "8 to 14 days", 8, 14),
    ("15+", "15 days or more", 15, None),
)


def age_days(opened_on: date, today: date) -> int:
    """Whole days since the job opened. Never negative."""
    return max(0, (today - opened_on).days)


def bucket_key(age: int) -> str:
    if isinstance(age, bool) or not isinstance(age, int):
        raise TypeError("Age must be an integer")
    if age < 0:
        raise ValueError("Age cannot be negative")
    for key, _label, low, high in BUCKETS:
        if age >= low and (high is None or age <= high):
            return key
    raise ValueError("No band for this age")
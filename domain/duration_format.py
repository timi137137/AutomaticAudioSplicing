"""Human-readable duration formatting for segment output."""

from __future__ import annotations

import math

from domain.models import SAMPLE_RATE


def format_duration_from_samples(samples: int) -> str:
    """Format sample count as Chinese duration; sub-second values ceil to 1 second."""
    if samples <= 0:
        return "0秒"
    total_seconds = math.ceil(samples / SAMPLE_RATE)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours}时{minutes}分{seconds}秒"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"

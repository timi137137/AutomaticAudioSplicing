"""Download schedule entries and their time-range parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from aas.errors import SheetError

_TIME_RANGE = re.compile(r"^\s*(\d{1,3}):([0-5]\d)\s*-\s*(\d{1,3}):([0-5]\d)\s*$")
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class SheetEntry:
    code: str
    title: str
    start_seconds: float
    end_seconds: float
    url: str

    @property
    def filename(self) -> str:
        return f"[{self.code}] {self.title}"

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def parse_time_range(text: str) -> tuple[float, float]:
    """Parse a ``mm:ss - mm:ss`` interval into (start, end) seconds."""
    match = _TIME_RANGE.match(text or "")
    if match is None:
        raise SheetError(f"时间区间格式应为 mm:ss - mm:ss: {text!r}")
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    if end <= start:
        raise SheetError(f"时间区间结束须晚于开始: {text!r}")
    return float(start), float(end)


def safe_title(title: str) -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub("_", title).strip()
    return cleaned or "未命名"


def source_filename(code: str, title: str, ext: str = "flac") -> str:
    """Build a scanner-compatible ``[code] title.ext`` file name."""
    if "[" in code or "]" in code:
        raise SheetError(f"编码不能包含方括号: {code!r}")
    return f"[{code}] {safe_title(title)}.{ext}"

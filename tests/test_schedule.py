"""Unit tests for schedule entries and time-range parsing."""

from __future__ import annotations

import unittest

from aas.domain.schedule import SheetEntry, parse_time_range, safe_title, source_filename
from aas.errors import SheetError


class ParseTimeRangeTest(unittest.TestCase):
    def test_valid_range(self) -> None:
        self.assertEqual(parse_time_range("01:30 - 02:45"), (90.0, 165.0))

    def test_minutes_over_sixty(self) -> None:
        self.assertEqual(parse_time_range("75:00-76:30"), (4500.0, 4590.0))

    def test_seconds_must_be_two_digits(self) -> None:
        with self.assertRaises(SheetError):
            parse_time_range("01:3 - 02:45")

    def test_requires_separator(self) -> None:
        with self.assertRaises(SheetError):
            parse_time_range("01:30~02:45")

    def test_end_must_follow_start(self) -> None:
        with self.assertRaises(SheetError):
            parse_time_range("02:45 - 01:30")
        with self.assertRaises(SheetError):
            parse_time_range("01:30 - 01:30")


class SourceFilenameTest(unittest.TestCase):
    def test_basic_name(self) -> None:
        self.assertEqual(source_filename("101", "此刻Memories"), "[101] 此刻Memories.flac")

    def test_sanitizes_illegal_characters(self) -> None:
        self.assertEqual(source_filename("101", "a/b:c"), "[101] a_b_c.flac")

    def test_rejects_bracketed_code(self) -> None:
        with self.assertRaises(SheetError):
            source_filename("[101]", "x")

    def test_blank_title_falls_back(self) -> None:
        self.assertEqual(safe_title("  "), "未命名")


class SheetEntryTest(unittest.TestCase):
    def test_derived_fields(self) -> None:
        entry = SheetEntry("101", "歌", 10.0, 70.0, "https://example.com/v")
        self.assertEqual(entry.filename, "[101] 歌")
        self.assertEqual(entry.duration_seconds, 60.0)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for ffmpeg progress parsing."""

from __future__ import annotations

import unittest

from adapters.ffmpeg_adapter import _parse_out_time_seconds
from adapters.progress_ui import format_clock, format_progress_range


class FfmpegProgressParseTest(unittest.TestCase):
    def test_out_time_us(self) -> None:
        self.assertAlmostEqual(
            _parse_out_time_seconds("out_time_us=1500000"), 1.5
        )

    def test_out_time_ms(self) -> None:
        self.assertAlmostEqual(
            _parse_out_time_seconds("out_time_ms=3000000"), 3.0
        )

    def test_out_time_hhmmss(self) -> None:
        self.assertAlmostEqual(
            _parse_out_time_seconds("out_time=00:01:05.500"), 65.5
        )

    def test_ignore_unknown(self) -> None:
        self.assertIsNone(_parse_out_time_seconds("progress=continue"))


class ProgressFormatTest(unittest.TestCase):
    def test_clock(self) -> None:
        self.assertEqual(format_clock(65), "01:05")
        self.assertEqual(format_clock(3665), "1:01:05")

    def test_range(self) -> None:
        self.assertEqual(format_progress_range(30, 90), "00:30/01:30")


if __name__ == "__main__":
    unittest.main()

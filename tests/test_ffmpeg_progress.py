"""Unit tests for ffmpeg progress parsing."""

from __future__ import annotations

import unittest
from pathlib import Path

from adapters.ffmpeg_adapter import (
    _adaptive_chunk_size,
    _build_mix_filter,
    _parse_out_time_seconds,
)
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


class MixChunkingTest(unittest.TestCase):
    def test_adaptive_chunk_shrinks_for_long_paths(self) -> None:
        long = Path("D:/Data/" + ("很长路径名" * 20) + "/file.flac")
        specs = [(long, 0.0, 1.0, float(i)) for i in range(80)]
        size = _adaptive_chunk_size(specs)
        self.assertLessEqual(size, 12)
        self.assertGreaterEqual(size, 1)

    def test_filter_labels(self) -> None:
        specs = [
            (Path("a.wav"), 0.0, 1.0, 0.0),
            (Path("b.wav"), 0.0, 1.0, 1.0),
        ]
        filters = _build_mix_filter(specs)
        self.assertTrue(any("amix=inputs=3" in f for f in filters))


if __name__ == "__main__":
    unittest.main()

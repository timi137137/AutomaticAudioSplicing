"""Unit tests for segment MP3 export helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

from adapters.segment_exporter import segment_mp3_filename
from domain.models import (
    SAMPLE_RATE,
    AudioFile,
    Clip,
    ClipKind,
    ProcessedSource,
    SegmentTimeline,
)
from adapters.segment_exporter import _clip_specs


class SegmentExportNamingTest(unittest.TestCase):
    def test_mp3_filename(self) -> None:
        self.assertEqual(segment_mp3_filename("混音项目", 0), "混音项目_1.mp3")
        self.assertEqual(segment_mp3_filename("demo", 1), "demo_2.mp3")


class SegmentClipSpecsTest(unittest.TestCase):
    def test_specs_use_only_segment_clips(self) -> None:
        audio = AudioFile("101-1", Path("a.wav"), "[101-1] a.wav")
        middle = AudioFile("0-0", Path("m.wav"), "[0-0] m.wav")
        seg = SegmentTimeline(
            index=0,
            middle_clips=[
                Clip(
                    ClipKind.MIDDLE,
                    middle,
                    0,
                    SAMPLE_RATE // 2,
                    0,
                    SAMPLE_RATE // 2,
                )
            ],
            main_clips=[
                Clip(
                    ClipKind.MAIN,
                    audio,
                    SAMPLE_RATE // 2,
                    SAMPLE_RATE // 2 + SAMPLE_RATE,
                    0,
                    SAMPLE_RATE,
                )
            ],
        )
        processed = [
            ProcessedSource(audio=middle, relative_path="Sources/m.wav"),
            ProcessedSource(audio=audio, relative_path="Sources/a.wav"),
        ]
        root = Path("/proj")
        specs = _clip_specs(seg, processed, root)
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0][3], 0.0)
        self.assertEqual(specs[1][3], 0.5)


if __name__ == "__main__":
    unittest.main()

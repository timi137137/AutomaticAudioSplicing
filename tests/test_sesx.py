"""Unit tests for SESX generation from processed sources."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from aas.domain.models import (
    SAMPLE_RATE,
    AudioFile,
    Clip,
    ClipKind,
    ProcessedSource,
    SegmentTimeline,
)
from aas.infra.resources import resource_path
from aas.infra.sesx import SesxBuilder


def _clip(kind: ClipKind, audio: AudioFile, start: int, dur: int) -> Clip:
    return Clip(
        kind=kind,
        audio=audio,
        start_point=start,
        end_point=start + dur,
        source_in_point=0,
        source_out_point=dur,
    )


class SesxBuilderTest(unittest.TestCase):
    def _build(self, segments: list[SegmentTimeline]) -> ET.Element:
        middle = AudioFile("0-0", Path("/src/[0-0] mid.wav"), "[0-0] mid.wav")
        main = AudioFile("101-1", Path("/src/[101-1] a.wav"), "[101-1] a.wav")
        processed = [
            ProcessedSource(middle, "Sources/[0-0] mid.flac"),
            ProcessedSource(main, "Sources/[101-1] a.flac"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml = (
                SesxBuilder(resource_path("resources/base.sesx"))
                .load_template()
                .add_files(processed)
                .add_segment_tracks(segments)
                .build(root)
            )
        return ET.fromstring(xml)

    def test_clip_uses_processed_display_name(self) -> None:
        middle = AudioFile("0-0", Path("/src/[0-0] mid.wav"), "[0-0] mid.wav")
        main = AudioFile("101-1", Path("/src/[101-1] a.wav"), "[101-1] a.wav")
        segment = SegmentTimeline(
            index=0,
            main_clips=[_clip(ClipKind.MAIN, main, SAMPLE_RATE, SAMPLE_RATE)],
            middle_clips=[_clip(ClipKind.MIDDLE, middle, 0, SAMPLE_RATE)],
        )
        root = self._build([segment])
        names = [el.get("name") for el in root.iter("audioClip")]
        self.assertIn("[0-0] mid.flac", names)
        self.assertIn("[101-1] a.flac", names)

    def test_file_entries_use_windows_relative_path(self) -> None:
        segment = SegmentTimeline(index=0, main_clips=[], middle_clips=[])
        root = self._build([segment])
        rel_paths = {el.get("relativePath") for el in root.iter("file")}
        self.assertEqual(
            rel_paths, {"Sources\\[0-0] mid.flac", "Sources\\[101-1] a.flac"}
        )

    def test_single_segment_track_names(self) -> None:
        segment = SegmentTimeline(index=0, main_clips=[], middle_clips=[])
        root = self._build([segment])
        names = [el.text for el in root.iter("name")]
        self.assertIn("编号音频", names)
        self.assertIn("中间音频", names)

    def test_multi_segment_track_names_are_numbered(self) -> None:
        segments = [
            SegmentTimeline(index=0, main_clips=[], middle_clips=[]),
            SegmentTimeline(index=1, main_clips=[], middle_clips=[]),
        ]
        root = self._build(segments)
        names = [el.text for el in root.iter("name")]
        for expected in ("编号音频 1", "中间音频 1", "编号音频 2", "中间音频 2"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()

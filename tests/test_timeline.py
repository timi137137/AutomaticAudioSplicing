"""Unit tests for timeline and segmentation."""

from __future__ import annotations

import unittest

from aas.domain.models import (
    SAMPLE_RATE,
    AudioFile,
    Clip,
    ClipKind,
    GlobalTimeline,
)
from aas.domain.timeline import split_timeline


def _clip(kind: ClipKind, start: int, dur: int, code: str = "x") -> Clip:
    audio = AudioFile(code=code, path=__file__, filename=f"[{code}] t.wav")
    return Clip(
        kind=kind,
        audio=audio,
        start_point=start,
        end_point=start + dur,
        source_in_point=0,
        source_out_point=dur,
    )


class SegmentSplitterTest(unittest.TestCase):
    def test_two_segments(self) -> None:
        m_dur = SAMPLE_RATE
        a_dur = SAMPLE_RATE * 2
        tl = GlobalTimeline(
            middle_clips=[
                _clip(ClipKind.MIDDLE, 0, m_dur, "m0"),
                _clip(ClipKind.MIDDLE, m_dur + a_dur, m_dur, "m1"),
                _clip(ClipKind.MIDDLE, 2 * (m_dur + a_dur), m_dur, "m2"),
            ],
            main_clips=[
                _clip(ClipKind.MAIN, m_dur, a_dur, "a0"),
                _clip(ClipKind.MAIN, 2 * m_dur + a_dur, a_dur, "a1"),
                _clip(ClipKind.MAIN, 3 * m_dur + 2 * a_dur, a_dur, "a2"),
            ],
        )
        segments = split_timeline(tl, 2)
        self.assertEqual(len(segments), 2)
        # Segment 0: M0 then A1 — middle at 0, main after middle duration
        self.assertEqual(segments[0].middle_clips[0].start_point, 0)
        self.assertEqual(
            segments[0].main_clips[0].start_point, segments[0].middle_clips[0].end_point
        )
        # Segment 1: local timeline also starts with middle before main
        self.assertEqual(segments[1].middle_clips[0].start_point, 0)
        self.assertEqual(
            segments[1].main_clips[0].start_point, segments[1].middle_clips[0].end_point
        )


class TimelineBuilderTest(unittest.TestCase):
    def test_alternating_duration(self) -> None:
        from aas.domain.models import AudioCatalog
        from aas.domain.timeline import TimelineBuilder

        catalog = AudioCatalog(
            audio_dir=__file__,
            middle_code="0-0",
            ordered_codes=["101-1", "101-2"],
            files_by_code={
                "0-0": AudioFile("0-0", __file__, "[0-0] m.wav", 1.0, SAMPLE_RATE),
                "101-1": AudioFile("101-1", __file__, "[101-1] a.wav", 2.0, SAMPLE_RATE),
                "101-2": AudioFile("101-2", __file__, "[101-2] b.wav", 2.0, SAMPLE_RATE),
            },
            middle_file=AudioFile("0-0", __file__, "[0-0] m.wav", 1.0, SAMPLE_RATE),
        )
        tl = TimelineBuilder().build(catalog)
        self.assertEqual(len(tl.middle_clips), 2)
        self.assertEqual(len(tl.main_clips), 2)
        self.assertEqual(tl.middle_clips[0].start_point, 0)
        self.assertEqual(tl.main_clips[0].start_point, SAMPLE_RATE)


if __name__ == "__main__":
    unittest.main()

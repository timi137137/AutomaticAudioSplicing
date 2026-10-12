"""Unit tests for timeline layout selection."""

from __future__ import annotations

import unittest

from aas.domain.models import (
    SAMPLE_RATE,
    AudioFile,
    Clip,
    ClipKind,
    GlobalTimeline,
)
from aas.domain.timeline import layout_segments
from aas.errors import SegmentSplitError


def _alternating_timeline(n_main: int) -> GlobalTimeline:
    """Build M0 A0 M1 A1 … with 1s middle and 2s main clips."""
    middle_dur = SAMPLE_RATE
    main_dur = SAMPLE_RATE * 2
    middle_clips: list[Clip] = []
    main_clips: list[Clip] = []
    cursor = 0
    for i in range(n_main):
        middle_clips.append(
            Clip(ClipKind.MIDDLE, AudioFile("0-0", __file__, "m.wav"), cursor, cursor + middle_dur)
        )
        cursor += middle_dur
        main_clips.append(
            Clip(
                ClipKind.MAIN,
                AudioFile(f"{i}-1", __file__, "a.wav"),
                cursor,
                cursor + main_dur,
            )
        )
        cursor += main_dur
    return GlobalTimeline(middle_clips=middle_clips, main_clips=main_clips)


class LayoutSegmentsTest(unittest.TestCase):
    def test_none_yields_single_segment(self) -> None:
        segments = layout_segments(_alternating_timeline(3), None)
        self.assertEqual(len(segments), 1)
        self.assertEqual(len(segments[0].main_clips), 3)
        self.assertEqual(segments[0].main_clips[0].start_point, SAMPLE_RATE)

    def test_single_digit_is_not_split(self) -> None:
        segments = layout_segments(_alternating_timeline(3), 1)
        self.assertEqual(len(segments), 1)

    def test_even_count_splits(self) -> None:
        segments = layout_segments(_alternating_timeline(4), 2)
        self.assertEqual(len(segments), 2)
        self.assertEqual([len(s.main_clips) for s in segments], [2, 2])
        # Each segment is retimed so its middle clip starts at 0.
        for segment in segments:
            self.assertEqual(segment.middle_clips[0].start_point, 0)

    def test_too_few_songs_raises(self) -> None:
        with self.assertRaises(SegmentSplitError):
            layout_segments(_alternating_timeline(1), 2)

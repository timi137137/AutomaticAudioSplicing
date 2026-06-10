"""Timeline layout strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import GlobalTimeline, SegmentTimeline
from domain.segment_splitter import split_timeline


class TimelineLayoutStrategy(ABC):
    @abstractmethod
    def layout(self, global_tl: GlobalTimeline) -> list[SegmentTimeline]:
        ...


class SingleSegmentStrategy(TimelineLayoutStrategy):
    def layout(self, global_tl: GlobalTimeline) -> list[SegmentTimeline]:
        return [
            SegmentTimeline(
                index=0,
                main_clips=list(global_tl.main_clips),
                middle_clips=list(global_tl.middle_clips),
            )
        ]


class MultiSegmentStrategy(TimelineLayoutStrategy):
    def __init__(self, segments: int) -> None:
        self.segments = segments

    def layout(self, global_tl: GlobalTimeline) -> list[SegmentTimeline]:
        return split_timeline(global_tl, self.segments)

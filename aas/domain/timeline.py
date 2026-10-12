"""Global timeline construction and segment layout."""

from __future__ import annotations

from aas.domain.models import (
    AudioCatalog,
    Clip,
    ClipKind,
    GlobalTimeline,
    SegmentTimeline,
)
from aas.errors import SegmentSplitError


class TimelineBuilder:
    """Build the global M → A1 → M → A2 … alternating timeline."""

    def build(self, catalog: AudioCatalog) -> GlobalTimeline:
        middle = catalog.middle_file
        middle_samples = middle.duration_samples
        timeline = GlobalTimeline()
        cursor = 0

        for code in catalog.ordered_codes:
            main = catalog.files_by_code[code]
            main_samples = main.duration_samples

            timeline.middle_clips.append(
                Clip(
                    kind=ClipKind.MIDDLE,
                    audio=middle,
                    start_point=cursor,
                    end_point=cursor + middle_samples,
                    source_in_point=0,
                    source_out_point=middle_samples,
                )
            )
            cursor += middle_samples

            timeline.main_clips.append(
                Clip(
                    kind=ClipKind.MAIN,
                    audio=main,
                    start_point=cursor,
                    end_point=cursor + main_samples,
                    source_in_point=0,
                    source_out_point=main_samples,
                )
            )
            cursor += main_samples

        return timeline


def _valid_split_indices(global_tl: GlobalTimeline) -> list[tuple[int, int]]:
    """Return (end_sample, main_index) for splits after each main clip except last."""
    return [
        (global_tl.main_clips[i].end_point, i)
        for i in range(len(global_tl.main_clips) - 1)
    ]


def _pick_split_indices(
    candidates: list[tuple[int, int]], total: int, segments: int
) -> list[int]:
    chosen_indices: list[int] = []
    used = 0
    for part in range(1, segments):
        target = total * part // segments
        best = used
        best_dist = abs(candidates[used][0] - target)
        for j in range(used, len(candidates)):
            dist = abs(candidates[j][0] - target)
            if dist < best_dist:
                best_dist = dist
                best = j
        chosen_indices.append(candidates[best][1])
        used = best + 1
    return chosen_indices


def _retime_segment_clips(
    main_clips: list[Clip], middle_clips: list[Clip]
) -> tuple[list[Clip], list[Clip]]:
    """Retime both tracks using the same segment origin so M precedes A locally."""
    all_clips = main_clips + middle_clips
    if not all_clips:
        return [], []
    seg_start = min(c.start_point for c in all_clips)

    def _shift(c: Clip) -> Clip:
        return Clip(
            kind=c.kind,
            audio=c.audio,
            start_point=c.start_point - seg_start,
            end_point=c.end_point - seg_start,
            source_in_point=c.source_in_point,
            source_out_point=c.source_out_point,
        )

    return [_shift(c) for c in main_clips], [_shift(c) for c in middle_clips]


def split_timeline(global_tl: GlobalTimeline, segments: int) -> list[SegmentTimeline]:
    if segments < 2 or segments % 2 != 0:
        raise SegmentSplitError("--segments 必须为不小于 2 的偶数。")

    n_main = len(global_tl.main_clips)
    if n_main == 0:
        raise SegmentSplitError("时间轴为空，无法分段。")

    candidates = _valid_split_indices(global_tl)
    if len(candidates) < segments - 1:
        raise SegmentSplitError(
            f"编号音频数量 ({n_main}) 不足以分成 {segments} 段，"
            f"至少需要 {segments} 个编号音频。"
        )

    split_after = _pick_split_indices(candidates, global_tl.total_duration, segments)
    boundaries = [-1] + split_after
    result: list[SegmentTimeline] = []

    for seg_i in range(segments):
        start_idx = boundaries[seg_i] + 1
        end_idx = (
            boundaries[seg_i + 1] + 1
            if seg_i + 1 < len(boundaries)
            else n_main
        )
        if start_idx >= end_idx:
            raise SegmentSplitError(f"分段 {seg_i + 1} 为空，请检查分段参数。")
        main_raw = global_tl.main_clips[start_idx:end_idx]
        middle_raw = global_tl.middle_clips[start_idx:end_idx]
        main, middle = _retime_segment_clips(main_raw, middle_raw)
        result.append(
            SegmentTimeline(index=seg_i, main_clips=main, middle_clips=middle)
        )

    covered = sum(len(seg.main_clips) for seg in result)
    if covered != n_main:
        raise SegmentSplitError(
            f"分段覆盖异常：期望 {n_main} 首，实际 {covered} 首。"
        )
    return result


def layout_segments(
    global_tl: GlobalTimeline, segments: int | None
) -> list[SegmentTimeline]:
    """Single track pair by default; split into ``segments`` equal-length pairs otherwise."""
    if segments and segments >= 2:
        return split_timeline(global_tl, segments)
    return [
        SegmentTimeline(
            index=0,
            main_clips=list(global_tl.main_clips),
            middle_clips=list(global_tl.middle_clips),
        )
    ]

"""Export each segment as MP3 by mixing only that segment's tracks."""

from __future__ import annotations

from pathlib import Path

from aas.domain.models import (
    SAMPLE_RATE,
    Clip,
    ProcessedSource,
    SegmentTimeline,
    source_key,
)
from aas.errors import FfmpegError, SegmentExportError
from aas.infra.ffmpeg import ensure_ffmpeg, mix_tracks_to_mp3_320k
from aas.infra.progress import TaskProgress, format_progress_range


def segment_mp3_filename(output_name: str, segment_index: int) -> str:
    return f"{output_name}_{segment_index + 1}.mp3"


def source_paths(
    processed: list[ProcessedSource], project_root: Path
) -> dict[str, Path]:
    """Map each processed source to its on-disk path inside the project."""
    return {
        ps.key: project_root / ps.relative_path.replace("\\", "/") for ps in processed
    }


def _track_clip_specs(
    clips: list[Clip],
    paths_by_key: dict[str, Path],
) -> list[tuple[Path, float, float, float]]:
    ordered = sorted(clips, key=lambda c: (c.start_point, c.end_point))
    specs: list[tuple[Path, float, float, float]] = []
    for clip in ordered:
        path = paths_by_key.get(source_key(clip.audio.path))
        if path is None:
            raise SegmentExportError(f"找不到已处理音频: {clip.audio.filename}")
        specs.append(
            (
                path,
                clip.source_in_point / SAMPLE_RATE,
                clip.source_out_point / SAMPLE_RATE,
                clip.start_point / SAMPLE_RATE,
            )
        )
    return specs


def export_segments(
    segments: list[SegmentTimeline],
    processed: list[ProcessedSource],
    project_root: Path,
    output_name: str,
    progress: TaskProgress,
) -> list[Path]:
    """Render one MP3 per segment (middle + main tracks mixed; other segments muted)."""
    ensure_ffmpeg()
    if not segments:
        return []

    segment_durations = [seg.duration / SAMPLE_RATE for seg in segments]
    total_seconds = sum(segment_durations)
    progress.begin_work("导出 MP3", total_seconds)

    paths_by_key = source_paths(processed, project_root)
    exported: list[Path] = []
    finished_seconds = 0.0
    total_count = len(segments)

    for segment, duration_seconds in zip(segments, segment_durations, strict=True):
        seg_num = segment.index + 1
        out_path = project_root / segment_mp3_filename(output_name, segment.index)
        tracks = [
            _track_clip_specs(segment.middle_clips, paths_by_key),
            _track_clip_specs(segment.main_clips, paths_by_key),
        ]
        tracks = [t for t in tracks if t]
        if not tracks:
            raise SegmentExportError(f"段 {seg_num} 没有可导出的 clip。")

        expected_mains = len(segment.main_clips)
        expected_middles = len(segment.middle_clips)
        if expected_mains != expected_middles:
            raise SegmentExportError(
                f"段 {seg_num} 轨道数量不一致："
                f"编号 {expected_mains} / 中间 {expected_middles}"
            )

        def on_progress(
            current: float,
            total: float,
            *,
            seg_num: int = seg_num,
            out_name: str = out_path.name,
            base: float = finished_seconds,
        ) -> None:
            progress.update_work(
                base + current,
                (
                    f"导出 MP3 段 {seg_num}/{total_count}  "
                    f"{format_progress_range(current, total)}  {out_name}  "
                    f"总进度 {format_progress_range(base + current, total_seconds)}"
                ),
            )

        try:
            mix_tracks_to_mp3_320k(
                tracks=tracks,
                duration_seconds=duration_seconds,
                dst=out_path,
                on_progress=on_progress,
            )
        except FfmpegError as exc:
            raise SegmentExportError(str(exc)) from exc

        finished_seconds += duration_seconds
        exported.append(out_path)
        progress.update_work(
            finished_seconds,
            (
                f"导出 MP3 段 {seg_num}/{total_count}  "
                f"{format_progress_range(duration_seconds, duration_seconds)}  "
                f"{out_path.name}  "
                f"总进度 {format_progress_range(finished_seconds, total_seconds)}"
            ),
        )

    return exported

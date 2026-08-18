"""Export each segment as MP3 by mixing only that segment's tracks."""

from __future__ import annotations

from pathlib import Path

from adapters.ffmpeg_adapter import FfmpegError, ensure_ffmpeg, mix_tracks_to_mp3_320k
from adapters.progress_ui import TaskProgress, format_progress_range
from domain.models import SAMPLE_RATE, AudioFile, Clip, ProcessedSource, SegmentTimeline


class SegmentExportError(Exception):
    pass


def segment_mp3_filename(output_name: str, segment_index: int) -> str:
    return f"{output_name}_{segment_index + 1}.mp3"


def _resolve_source_path(
    audio: AudioFile, processed: list[ProcessedSource], project_root: Path
) -> Path:
    key = str(audio.path.resolve())
    for ps in processed:
        if str(ps.audio.path.resolve()) == key:
            return project_root / ps.relative_path.replace("\\", "/")
    raise SegmentExportError(f"找不到已处理音频: {audio.filename}")


def _track_clip_specs(
    clips: list[Clip],
    processed: list[ProcessedSource],
    project_root: Path,
) -> list[tuple[Path, float, float, float]]:
    ordered = sorted(clips, key=lambda c: (c.start_point, c.end_point))
    specs: list[tuple[Path, float, float, float]] = []
    for clip in ordered:
        path = _resolve_source_path(clip.audio, processed, project_root)
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

    exported: list[Path] = []
    finished_seconds = 0.0
    total_count = len(segments)

    for segment, duration_seconds in zip(segments, segment_durations):
        seg_num = segment.index + 1
        out_path = project_root / segment_mp3_filename(output_name, segment.index)
        tracks = [
            _track_clip_specs(segment.middle_clips, processed, project_root),
            _track_clip_specs(segment.main_clips, processed, project_root),
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

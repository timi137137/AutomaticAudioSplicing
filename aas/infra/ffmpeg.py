"""FFmpeg detection, transcoding, and progress reporting."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from aas.errors import FfmpegError

ProgressCallback = Callable[[float, float], None]

_OUT_TIME_US = re.compile(r"^out_time_us=(\d+)$")
_OUT_TIME_MS = re.compile(r"^out_time_ms=(\d+)$")
_OUT_TIME = re.compile(r"^out_time=(?P<t>\d{2}:\d{2}:\d{2}\.\d+)$")

# Windows CreateProcess command-line limit is ~32k; stay well below.
_MAX_CMD_CHARS = 7000
_MAX_CLIPS_PER_CHUNK = 12


def ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegError(
            "未找到 ffmpeg。请安装 ffmpeg 并加入 PATH，或不要使用 --ignore-sample-rate。"
        )
    return path


def _parse_out_time_seconds(line: str) -> float | None:
    line = line.strip()
    match = _OUT_TIME_US.match(line)
    if match:
        return int(match.group(1)) / 1_000_000
    match = _OUT_TIME_MS.match(line)
    if match:
        return int(match.group(1)) / 1_000_000
    match = _OUT_TIME.match(line)
    if match:
        parts = match.group("t").split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    return None


def _insert_progress_flags(cmd: list[str]) -> list[str]:
    if len(cmd) < 2:
        return cmd
    return cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]


def _cmd_length(cmd: list[str]) -> int:
    return sum(len(part) + 3 for part in cmd)


def run_ffmpeg_with_progress(
    cmd: list[str],
    duration_seconds: float,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Run ffmpeg and stream encoding progress via ``-progress pipe:1``."""
    if duration_seconds <= 0:
        raise FfmpegError("导出时长必须大于 0。")

    run_cmd = _insert_progress_flags(cmd) if on_progress else cmd
    try:
        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE if on_progress else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise FfmpegError(f"无法启动 ffmpeg（命令过长或系统限制）: {exc}") from exc

    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    if on_progress and proc.stdout is not None:
        for line in proc.stdout:
            parsed = _parse_out_time_seconds(line)
            if parsed is not None:
                on_progress(min(parsed, duration_seconds), duration_seconds)
            elif line.strip() == "progress=end":
                on_progress(duration_seconds, duration_seconds)

    proc.wait()
    stderr_thread.join()
    if proc.returncode != 0:
        stderr = "".join(stderr_chunks)
        raise FfmpegError(f"ffmpeg 执行失败\n{stderr}")


def convert_to_flac_48k24(
    src: Path,
    dst: Path,
    *,
    duration_seconds: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> None:
    ffmpeg = ensure_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-ar",
        "48000",
        "-c:a",
        "flac",
        "-sample_fmt",
        "s32",
        str(dst),
    ]
    if on_progress and duration_seconds and duration_seconds > 0:
        run_ffmpeg_with_progress(cmd, duration_seconds, on_progress)
    else:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if proc.returncode != 0:
            raise FfmpegError(f"ffmpeg 转码失败: {src.name}\n{proc.stderr}")


def _write_filter_script(path: Path, filters: list[str]) -> None:
    path.write_text(";\n".join(filters) + "\n", encoding="utf-8", newline="\n")


def _adaptive_chunk_size(clip_specs: list[tuple[Path, float, float, float]]) -> int:
    if not clip_specs:
        return _MAX_CLIPS_PER_CHUNK
    avg_path = sum(len(str(path)) for path, _, _, _ in clip_specs) / len(clip_specs)
    budget_for_paths = max(1500, _MAX_CMD_CHARS - 1200)
    by_path = max(1, int(budget_for_paths / max(avg_path + 8, 1)))
    return max(1, min(_MAX_CLIPS_PER_CHUNK, by_path))


def _stage_short_path(src: Path, work_dir: Path, idx: int) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    short = work_dir / f"i{idx:04d}{src.suffix.lower() or '.wav'}"
    if short.exists():
        short.unlink()
    try:
        os.link(src, short)
        return short
    except OSError:
        try:
            short.symlink_to(src.resolve())
            return short
        except OSError:
            return src


def _build_track_concat_filter(
    clip_specs: list[tuple[Path, float, float, float]],
    duration_seconds: float,
    track_label: str,
) -> tuple[list[str], int]:
    """Build one non-overlapping track with silence gaps + concat."""
    filters: list[str] = []
    parts: list[str] = []
    cursor = 0.0
    part_i = 0

    for clip_i, (_, src_start, src_end, timeline_start) in enumerate(clip_specs):
        gap = timeline_start - cursor
        if gap > 1e-6:
            g_label = f"{track_label}g{part_i}"
            filters.append(
                "anullsrc=r=48000:cl=stereo:d="
                f"{gap:.6f},aformat=sample_rates=48000:channel_layouts=stereo[{g_label}]"
            )
            parts.append(f"[{g_label}]")
            part_i += 1
            cursor += gap

        c_label = f"{track_label}c{part_i}"
        clip_dur = max(src_end - src_start, 0.0)
        filters.append(
            f"[{clip_i}:a]atrim=start={src_start:.6f}:end={src_end:.6f},"
            f"asetpts=PTS-STARTPTS,aresample=48000,"
            f"aformat=sample_rates=48000:channel_layouts=stereo[{c_label}]"
        )
        parts.append(f"[{c_label}]")
        part_i += 1
        cursor = timeline_start + clip_dur

    tail = duration_seconds - cursor
    if tail > 1e-6:
        g_label = f"{track_label}g{part_i}"
        filters.append(
            "anullsrc=r=48000:cl=stereo:d="
            f"{tail:.6f},aformat=sample_rates=48000:channel_layouts=stereo[{g_label}]"
        )
        parts.append(f"[{g_label}]")

    if not parts:
        filters.append(
            "anullsrc=r=48000:cl=stereo:d="
            f"{duration_seconds:.6f},aformat=sample_rates=48000:channel_layouts=stereo"
            f"[{track_label}]"
        )
        return filters, 0

    filters.append(f"{''.join(parts)}concat=n={len(parts)}:v=0:a=1[{track_label}]")
    return filters, len(clip_specs)


def _render_track_flac(
    *,
    ffmpeg: str,
    clip_specs: list[tuple[Path, float, float, float]],
    duration_seconds: float,
    dst: Path,
    work_dir: Path,
    on_progress: ProgressCallback | None = None,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    staged = [
        (_stage_short_path(path, work_dir, idx), src_in, src_out, start)
        for idx, (path, src_in, src_out, start) in enumerate(clip_specs)
    ]

    if not staged:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=48000:cl=stereo:d={duration_seconds:.6f}",
            "-c:a",
            "flac",
            str(dst),
        ]
        run_ffmpeg_with_progress(cmd, duration_seconds, on_progress)
        return

    chunk_size = _adaptive_chunk_size(staged)
    chunks = [staged[i : i + chunk_size] for i in range(0, len(staged), chunk_size)]
    piece_files: list[Path] = []

    # Piece boundaries include inter-chunk gaps so sequential concat stays continuous.
    boundaries = [0.0]
    for chunk in chunks[:-1]:
        last = chunk[-1]
        boundaries.append(last[3] + max(last[2] - last[1], 0.0))
    boundaries.append(duration_seconds)

    for chunk_index, chunk in enumerate(chunks):
        piece_start = boundaries[chunk_index]
        piece_end = boundaries[chunk_index + 1]
        local_specs = [
            (path, src_in, src_out, timeline_start - piece_start)
            for path, src_in, src_out, timeline_start in chunk
        ]
        local_duration = max(piece_end - piece_start, 0.001)
        piece_path = work_dir / f"piece_{chunk_index:03d}.flac"
        script_path = work_dir / f"piece_{chunk_index:03d}_filter.txt"
        filters, n_inputs = _build_track_concat_filter(local_specs, local_duration, "tout")
        _write_filter_script(script_path, filters)

        cmd: list[str] = [ffmpeg, "-y"]
        for path, _, _, _ in local_specs:
            cmd.extend(["-i", str(path)])
        cmd.extend(
            [
                "-filter_complex_script",
                str(script_path),
                "-map",
                "[tout]",
                "-ar",
                "48000",
                "-c:a",
                "flac",
                str(piece_path),
            ]
        )
        if _cmd_length(cmd) > _MAX_CMD_CHARS:
            raise FfmpegError(
                f"单轨混音命令过长（{n_inputs} 个输入），请缩短 Sources 路径后重试。"
            )
        run_ffmpeg_with_progress(cmd, local_duration, None)
        piece_files.append(piece_path)

    if len(piece_files) == 1:
        shutil.copy2(piece_files[0], dst)
        if on_progress:
            on_progress(duration_seconds, duration_seconds)
        return

    list_path = work_dir / "track_concat.txt"
    lines = ["ffconcat version 1.0"]
    for piece in piece_files:
        p = piece.resolve().as_posix().replace("'", r"\'")
        lines.append(f"file '{p}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c:a",
        "flac",
        str(dst),
    ]
    run_ffmpeg_with_progress(cmd, duration_seconds, on_progress)


def mix_tracks_to_mp3_320k(
    *,
    tracks: list[list[tuple[Path, float, float, float]]],
    duration_seconds: float,
    dst: Path,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Render each track by concat, then amix tracks into MP3 320k."""
    ffmpeg = ensure_ffmpeg()
    if duration_seconds <= 0:
        raise FfmpegError("导出时长必须大于 0。")
    usable = [list(track) for track in tracks if track]
    if not usable:
        raise FfmpegError("没有可混音的 clip。")
    dst.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aas_mix_", dir=str(dst.parent)) as tmp:
        work_dir = Path(tmp)
        track_files: list[Path] = []
        total_tracks = len(usable)

        for track_index, specs in enumerate(usable):
            track_dir = work_dir / f"t{track_index}"
            track_path = work_dir / f"track_{track_index:02d}.flac"

            def track_cb(
                current: float,
                total: float,
                *,
                idx: int = track_index,
            ) -> None:
                if not on_progress:
                    return
                ratio = min(current / total, 1.0) if total > 0 else 1.0
                overall = (idx + ratio) / (total_tracks + 1)
                on_progress(overall * duration_seconds, duration_seconds)

            _render_track_flac(
                ffmpeg=ffmpeg,
                clip_specs=specs,
                duration_seconds=duration_seconds,
                dst=track_path,
                work_dir=track_dir,
                on_progress=track_cb if on_progress else None,
            )
            track_files.append(track_path)

        def final_cb(current: float, total: float) -> None:
            if not on_progress:
                return
            ratio = min(current / total, 1.0) if total > 0 else 1.0
            overall = (total_tracks + ratio) / (total_tracks + 1)
            on_progress(overall * duration_seconds, duration_seconds)

        if len(track_files) == 1:
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(track_files[0]),
                "-ar",
                "48000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "320k",
                str(dst),
            ]
            run_ffmpeg_with_progress(cmd, duration_seconds, final_cb if on_progress else None)
        else:
            script_path = work_dir / "mix_tracks.txt"
            labels = "".join(f"[{i}:a]" for i in range(len(track_files)))
            _write_filter_script(
                script_path,
                [
                    f"{labels}amix=inputs={len(track_files)}:duration=first:"
                    "dropout_transition=0:normalize=0[aout]"
                ],
            )
            cmd = [ffmpeg, "-y"]
            for path in track_files:
                cmd.extend(["-i", str(path)])
            cmd.extend(
                [
                    "-filter_complex_script",
                    str(script_path),
                    "-map",
                    "[aout]",
                    "-ar",
                    "48000",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "320k",
                    str(dst),
                ]
            )
            run_ffmpeg_with_progress(cmd, duration_seconds, final_cb if on_progress else None)

    if on_progress:
        on_progress(duration_seconds, duration_seconds)

"""FFmpeg detection, transcoding, and progress reporting."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

ProgressCallback = Callable[[float, float], None]

_OUT_TIME_US = re.compile(r"^out_time_us=(\d+)$")
_OUT_TIME_MS = re.compile(r"^out_time_ms=(\d+)$")
_OUT_TIME = re.compile(r"^out_time=(?P<t>\d{2}:\d{2}:\d{2}\.\d+)$")


class FfmpegError(Exception):
    pass


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


def run_ffmpeg_with_progress(
    cmd: list[str],
    duration_seconds: float,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Run ffmpeg and stream encoding progress via ``-progress pipe:1``."""
    if duration_seconds <= 0:
        raise FfmpegError("导出时长必须大于 0。")

    run_cmd = _insert_progress_flags(cmd) if on_progress else cmd
    proc = subprocess.Popen(
        run_cmd,
        stdout=subprocess.PIPE if on_progress else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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


def mix_to_mp3_320k(
    *,
    clip_specs: list[tuple[Path, float, float, float]],
    duration_seconds: float,
    dst: Path,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Mix clips onto a silent bed and encode MP3 at 320 kbps."""
    ffmpeg = ensure_ffmpeg()
    if duration_seconds <= 0:
        raise FfmpegError("导出时长必须大于 0。")
    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=48000:cl=stereo:d={duration_seconds:.6f}",
    ]
    for path, _, _, _ in clip_specs:
        cmd.extend(["-i", str(path)])

    filters: list[str] = []
    mix_labels = ["[0:a]"]
    for idx, (_, src_start, src_end, timeline_start) in enumerate(clip_specs):
        input_idx = idx + 1
        delay_ms = max(0, int(round(timeline_start * 1000)))
        label = f"c{input_idx}"
        filters.append(
            f"[{input_idx}:a]atrim=start={src_start:.6f}:end={src_end:.6f},"
            f"asetpts=PTS-STARTPTS,aresample=48000,"
            f"aformat=sample_rates=48000:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        mix_labels.append(f"[{label}]")

    mix_count = len(mix_labels)
    filters.append(
        f"{''.join(mix_labels)}amix=inputs={mix_count}:duration=first:"
        f"dropout_transition=0:normalize=0[aout]"
    )

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
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
    run_ffmpeg_with_progress(cmd, duration_seconds, on_progress)

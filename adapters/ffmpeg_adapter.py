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

ProgressCallback = Callable[[float, float], None]

_OUT_TIME_US = re.compile(r"^out_time_us=(\d+)$")
_OUT_TIME_MS = re.compile(r"^out_time_ms=(\d+)$")
_OUT_TIME = re.compile(r"^out_time=(?P<t>\d{2}:\d{2}:\d{2}\.\d+)$")

# Windows CreateProcess command-line limit is ~32k; stay well below.
_MAX_CMD_CHARS = 7000
_MAX_CLIPS_PER_CHUNK = 12


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


def _build_mix_filter(
    clip_specs: list[tuple[Path, float, float, float]],
) -> list[str]:
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
    return filters


def _stage_short_inputs(
    clip_specs: list[tuple[Path, float, float, float]],
    work_dir: Path,
) -> list[tuple[Path, float, float, float]]:
    """Map sources to short local names to shrink Windows command lines."""
    staged: list[tuple[Path, float, float, float]] = []
    for idx, (src, src_start, src_end, timeline_start) in enumerate(clip_specs):
        short = work_dir / f"i{idx:04d}{src.suffix.lower() or '.wav'}"
        if short.exists():
            short.unlink()
        linked = False
        try:
            os.link(src, short)
            linked = True
        except OSError:
            try:
                short.symlink_to(src.resolve())
                linked = True
            except OSError:
                linked = False
        staged.append(
            (
                short if linked else src,
                src_start,
                src_end,
                timeline_start,
            )
        )
    return staged


def _adaptive_chunk_size(clip_specs: list[tuple[Path, float, float, float]]) -> int:
    if not clip_specs:
        return _MAX_CLIPS_PER_CHUNK
    avg_path = sum(len(str(path)) for path, _, _, _ in clip_specs) / len(clip_specs)
    budget_for_paths = max(1500, _MAX_CMD_CHARS - 1200)
    by_path = max(1, int(budget_for_paths / max(avg_path + 8, 1)))
    return max(1, min(_MAX_CLIPS_PER_CHUNK, by_path))


def _build_mix_cmd(
    *,
    ffmpeg: str,
    clip_specs: list[tuple[Path, float, float, float]],
    duration_seconds: float,
    dst: Path,
    script_path: Path,
    audio_codec: list[str],
) -> list[str]:
    filters = _build_mix_filter(clip_specs)
    _write_filter_script(script_path, filters)
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
    cmd.extend(
        [
            "-filter_complex_script",
            str(script_path),
            "-map",
            "[aout]",
            "-ar",
            "48000",
            *audio_codec,
            str(dst),
        ]
    )
    return cmd


def _amix_two(
    *,
    ffmpeg: str,
    left: Path,
    right: Path,
    duration_seconds: float,
    dst: Path,
    work_dir: Path,
    on_progress: ProgressCallback | None = None,
) -> None:
    script_path = work_dir / f"{dst.stem}_amix.txt"
    _write_filter_script(
        script_path,
        [
            "[0:a][1:a]amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0[aout]"
        ],
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(left),
        "-i",
        str(right),
        "-filter_complex_script",
        str(script_path),
        "-map",
        "[aout]",
        "-ar",
        "48000",
        "-c:a",
        "flac",
        str(dst),
    ]
    run_ffmpeg_with_progress(cmd, duration_seconds, on_progress)


def mix_to_mp3_320k(
    *,
    clip_specs: list[tuple[Path, float, float, float]],
    duration_seconds: float,
    dst: Path,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Mix clips onto a silent bed and encode MP3 at 320 kbps.

    Avoids Windows WinError 206 by:
    1. staging inputs under short temp names when possible
    2. moving filter graphs into ``-filter_complex_script`` files
    3. folding oversized mixes into sequential chunks
    """
    ffmpeg = ensure_ffmpeg()
    if duration_seconds <= 0:
        raise FfmpegError("导出时长必须大于 0。")
    if not clip_specs:
        raise FfmpegError("没有可混音的 clip。")
    dst.parent.mkdir(parents=True, exist_ok=True)

    mp3_codec = ["-c:a", "libmp3lame", "-b:a", "320k"]
    flac_codec = ["-c:a", "flac"]

    with tempfile.TemporaryDirectory(prefix="aas_mix_", dir=str(dst.parent)) as tmp:
        work_dir = Path(tmp)
        staged = _stage_short_inputs(clip_specs, work_dir)
        script_path = work_dir / "mix_filter.txt"
        direct_cmd = _build_mix_cmd(
            ffmpeg=ffmpeg,
            clip_specs=staged,
            duration_seconds=duration_seconds,
            dst=dst,
            script_path=script_path,
            audio_codec=mp3_codec,
        )

        if _cmd_length(direct_cmd) <= _MAX_CMD_CHARS:
            run_ffmpeg_with_progress(direct_cmd, duration_seconds, on_progress)
            return

        # Fold chunks sequentially so only ~2 intermediate files exist at a time.
        chunk_size = _adaptive_chunk_size(staged)
        chunks = [
            staged[i : i + chunk_size] for i in range(0, len(staged), chunk_size)
        ]
        chunk_count = len(chunks)
        accumulator: Path | None = None

        for chunk_index, chunk in enumerate(chunks):
            piece = work_dir / f"piece_{chunk_index:03d}.flac"

            def chunk_cb(
                current: float,
                total: float,
                *,
                idx: int = chunk_index,
            ) -> None:
                if not on_progress:
                    return
                ratio = min(current / total, 1.0) if total > 0 else 1.0
                # Leave a little room for final mp3 encode.
                overall = (idx + ratio) / (chunk_count + 1)
                on_progress(overall * duration_seconds, duration_seconds)

            piece_cmd = _build_mix_cmd(
                ffmpeg=ffmpeg,
                clip_specs=chunk,
                duration_seconds=duration_seconds,
                dst=piece,
                script_path=work_dir / f"piece_{chunk_index:03d}_filter.txt",
                audio_codec=flac_codec,
            )
            if _cmd_length(piece_cmd) > _MAX_CMD_CHARS:
                raise FfmpegError(
                    f"单次混音仍过长（{len(chunk)} 个输入），请缩短 Sources 路径后重试。"
                )
            run_ffmpeg_with_progress(
                piece_cmd, duration_seconds, chunk_cb if on_progress else None
            )

            if accumulator is None:
                accumulator = piece
            else:
                merged = work_dir / f"acc_{chunk_index:03d}.flac"
                _amix_two(
                    ffmpeg=ffmpeg,
                    left=accumulator,
                    right=piece,
                    duration_seconds=duration_seconds,
                    dst=merged,
                    work_dir=work_dir,
                )
                if accumulator.exists():
                    accumulator.unlink(missing_ok=True)
                piece.unlink(missing_ok=True)
                accumulator = merged

        assert accumulator is not None

        def final_cb(current: float, total: float) -> None:
            if not on_progress:
                return
            ratio = min(current / total, 1.0) if total > 0 else 1.0
            overall = (chunk_count + ratio) / (chunk_count + 1)
            on_progress(overall * duration_seconds, duration_seconds)

        encode_cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(accumulator),
            "-ar",
            "48000",
            *mp3_codec,
            str(dst),
        ]
        run_ffmpeg_with_progress(
            encode_cmd, duration_seconds, final_cb if on_progress else None
        )

    if on_progress:
        on_progress(duration_seconds, duration_seconds)

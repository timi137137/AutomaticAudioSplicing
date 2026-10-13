"""Trim and loudness-normalize a downloaded source into FLAC 48kHz/24bit."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aas.errors import FfmpegError
from aas.infra.ffmpeg import ensure_ffmpeg, run_ffmpeg_with_progress

TARGET_I = -16.0
TARGET_TP = -1.5
TARGET_LRA = 11.0
TARGET_SAMPLE_RATE = 48000
TARGET_SAMPLE_FMT = "s32"

_JSON_BLOCK = re.compile(r"\{[^{}]*\}", re.DOTALL)


@dataclass(frozen=True)
class LoudnessMeasurement:
    """First-pass loudnorm result, fed back into the linear second pass."""

    input_i: str
    input_tp: str
    input_lra: str
    input_thresh: str
    target_offset: str

    def filter_suffix(self) -> str:
        return (
            f"measured_I={self.input_i}:measured_TP={self.input_tp}:"
            f"measured_LRA={self.input_lra}:measured_thresh={self.input_thresh}:"
            f"offset={self.target_offset}:linear=true"
        )


def parse_loudnorm_json(text: str) -> LoudnessMeasurement:
    matches = _JSON_BLOCK.findall(text)
    if not matches:
        raise FfmpegError("loudnorm 未返回测量结果。")
    try:
        payload = json.loads(matches[-1])
        return LoudnessMeasurement(
            input_i=payload["input_i"],
            input_tp=payload["input_tp"],
            input_lra=payload["input_lra"],
            input_thresh=payload["input_thresh"],
            target_offset=payload["target_offset"],
        )
    except (ValueError, KeyError) as exc:
        raise FfmpegError(f"loudnorm 测量结果无法解析: {exc}") from exc


def _base_filter() -> str:
    return f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"


def measure(src: Path, start: float, end: float) -> LoudnessMeasurement:
    """First pass: measure the trimmed segment without writing output."""
    ffmpeg = ensure_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-af",
        f"{_base_filter()}:print_format=json",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise FfmpegError(f"响度测量失败: {src.name}\n{proc.stderr}")
    return parse_loudnorm_json(proc.stderr)


def render(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    measurement: LoudnessMeasurement,
) -> None:
    """Second pass: apply linear normalization and encode FLAC 48kHz/24bit."""
    ffmpeg = ensure_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-nostats",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-af",
        f"{_base_filter()}:{measurement.filter_suffix()}",
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-sample_fmt",
        TARGET_SAMPLE_FMT,
        "-c:a",
        "flac",
        str(dst),
    ]
    run_ffmpeg_with_progress(cmd, end - start)


def normalize_segment(src: Path, dst: Path, start: float, end: float) -> None:
    render(src, dst, start, end, measure(src, start, end))

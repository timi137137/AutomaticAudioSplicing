"""Scan audio directory and probe metadata."""

from __future__ import annotations

import re
from pathlib import Path

import soundfile as sf

from adapters.progress_ui import TaskProgress, run_parallel
from domain.models import SAMPLE_RATE, AudioCatalog, AudioFile

FILENAME_PATTERN = re.compile(
    r"^\[(?P<code>[^\]]+)\]\s+(?P<title>.+)\.(?P<ext>wav|flac)$",
    re.IGNORECASE,
)


class ScanError(Exception):
    pass


def _read_order(path: Path) -> list[str]:
    if not path.is_file():
        raise ScanError(f"顺序文件不存在: {path}")
    codes: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.strip()
        if code:
            codes.append(code)
    if not codes:
        raise ScanError("顺序文件为空。")
    return codes


def scan(audio_dir: Path, order_path: Path, middle_code: str) -> AudioCatalog:
    if not audio_dir.is_dir():
        raise ScanError(f"音频目录不存在: {audio_dir}")

    files_by_code: dict[str, AudioFile] = {}
    for entry in audio_dir.iterdir():
        if not entry.is_file():
            continue
        match = FILENAME_PATTERN.match(entry.name)
        if not match:
            continue
        code = match.group("code")
        if code in files_by_code:
            raise ScanError(f"编码重复: [{code}] 对应多个文件。")
        files_by_code[code] = AudioFile(
            code=code,
            path=entry,
            filename=entry.name,
        )

    ordered_codes = _read_order(order_path)
    for code in ordered_codes:
        if code not in files_by_code:
            raise ScanError(f"顺序文件中的编码未找到音频: {code}")

    if middle_code not in files_by_code:
        raise ScanError(f"中间音频编码未找到: {middle_code}")

    return AudioCatalog(
        audio_dir=audio_dir,
        middle_code=middle_code,
        ordered_codes=ordered_codes,
        files_by_code=files_by_code,
        middle_file=files_by_code[middle_code],
    )


def _probe_one(audio: AudioFile, ignore_sample_rate: bool) -> AudioFile:
    info = sf.info(str(audio.path))
    audio.duration_seconds = float(info.duration)
    audio.sample_rate = int(info.samplerate)
    if not ignore_sample_rate and audio.sample_rate != SAMPLE_RATE:
        raise ScanError(
            f"[{audio.code}] {audio.filename} 采样率为 {audio.sample_rate} Hz，"
            f"需要 {SAMPLE_RATE} Hz。请使用 --ignore-sample-rate 或预先统一采样率。"
        )
    return audio


def probe_parallel(
    catalog: AudioCatalog,
    progress: TaskProgress,
    ignore_sample_rate: bool,
) -> None:
    files = catalog.used_files()

    def worker(audio: AudioFile) -> AudioFile:
        return _probe_one(audio, ignore_sample_rate)

    run_parallel(files, "检测音频", worker, progress)

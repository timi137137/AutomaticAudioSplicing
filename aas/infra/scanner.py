"""Scan audio directory and probe metadata."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import soundfile as sf

from aas.domain.models import SAMPLE_RATE, AudioCatalog, AudioFile
from aas.errors import ScanError
from aas.infra.progress import TaskProgress, run_parallel

# Allow "[code] title.ext" and "[code][tag] title.ext" (no space after ]).
FILENAME_PATTERN = re.compile(
    r"^\[(?P<code>[^\]]+)\]\s*(?P<title>.+)\.(?P<ext>wav|flac)$",
    re.IGNORECASE,
)


def read_order(path: Path) -> list[str]:
    if not path.is_file():
        raise ScanError(f"顺序文件不存在: {path}")
    # utf-8-sig strips BOM so the first code is not corrupted.
    codes: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        code = line.strip()
        if code:
            codes.append(code)
    if not codes:
        raise ScanError("顺序文件为空。")
    return codes


def _expand_order_codes(
    ordered_codes: list[str],
    files_by_code: dict[str, AudioFile],
    middle_code: str | None = None,
) -> list[str]:
    """Resolve order entries.

    - Full code (e.g. ``101-2``): use that file exactly.
    - Main number only (e.g. ``101``): use ``101-1`` only (not all parts).
    """
    middle_main = middle_code.split("-", 1)[0] if middle_code else None
    expanded: list[str] = []
    seen: set[str] = set()
    missing: list[str] = []

    for code in ordered_codes:
        if middle_code and code == middle_code:
            continue
        if middle_main and code == middle_main and code not in files_by_code:
            continue

        # Exact full code (contains '-' or exact filename code without needing -1).
        if "-" in code:
            if code in files_by_code:
                if code not in seen:
                    expanded.append(code)
                    seen.add(code)
                continue
            missing.append(code)
            continue

        # Main number only → prefer exact code, else ``{main}-1``.
        if code in files_by_code:
            if code not in seen:
                expanded.append(code)
                seen.add(code)
            continue

        part_one = f"{code}-1"
        if part_one in files_by_code:
            if part_one not in seen:
                expanded.append(part_one)
                seen.add(part_one)
            continue

        missing.append(code)

    if missing:
        uniq = list(dict.fromkeys(missing))
        preview = ", ".join(uniq[:10])
        more = f" 等 {len(uniq)} 个" if len(uniq) > 10 else ""
        raise ScanError(f"顺序文件中的编码未找到音频: {preview}{more}")
    if not expanded:
        raise ScanError("顺序展开后没有可用的编号音频。")
    return expanded


def scan(
    audio_dirs: Sequence[Path],
    ordered_codes: list[str],
    middle_code: str,
) -> AudioCatalog:
    files_by_code: dict[str, AudioFile] = {}
    for audio_dir in audio_dirs:
        if not audio_dir.is_dir():
            raise ScanError(f"音频目录不存在: {audio_dir}")
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

    if middle_code not in files_by_code:
        raise ScanError(f"中间音频编码未找到: {middle_code}")

    expanded = _expand_order_codes(ordered_codes, files_by_code, middle_code=middle_code)

    return AudioCatalog(
        middle_code=middle_code,
        ordered_codes=expanded,
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

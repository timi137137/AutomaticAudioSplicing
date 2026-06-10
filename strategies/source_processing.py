"""Source file processing strategies."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from adapters.ffmpeg_adapter import convert_to_flac_48k24, ensure_ffmpeg
from adapters.progress_ui import TaskProgress, run_parallel, run_parallel_timed
from domain.models import SAMPLE_RATE, AudioFile, ProcessedSource


class SourceProcessingStrategy(ABC):
    @abstractmethod
    def process(
        self,
        files: list[AudioFile],
        dest_dir: Path,
        progress: TaskProgress,
    ) -> list[ProcessedSource]:
        ...


class CopyStrategy(SourceProcessingStrategy):
    def process(
        self,
        files: list[AudioFile],
        dest_dir: Path,
        progress: TaskProgress,
    ) -> list[ProcessedSource]:
        dest_dir.mkdir(parents=True, exist_ok=True)

        def _copy(audio: AudioFile) -> ProcessedSource:
            dest = dest_dir / audio.filename
            shutil.copy2(audio.path, dest)
            rel = f"Sources/{audio.filename}"
            audio.sources_name = audio.filename
            return ProcessedSource(audio=audio, relative_path=rel)

        results = run_parallel(files, "复制音频", _copy, progress)
        return list(results)


class TranscodeStrategy(SourceProcessingStrategy):
    def process(
        self,
        files: list[AudioFile],
        dest_dir: Path,
        progress: TaskProgress,
    ) -> list[ProcessedSource]:
        ensure_ffmpeg()
        dest_dir.mkdir(parents=True, exist_ok=True)

        def _transcode(
            audio: AudioFile,
            _idx: int,
            on_progress,
        ) -> ProcessedSource:
            flac_name = f"{audio.path.stem}.flac"
            dest = dest_dir / flac_name
            convert_to_flac_48k24(
                audio.path,
                dest,
                duration_seconds=audio.duration_seconds,
                on_progress=on_progress,
            )
            audio.duration_seconds = _probe_duration(dest)
            audio.sample_rate = SAMPLE_RATE
            audio.sources_name = flac_name
            rel = f"Sources/{flac_name}"
            return ProcessedSource(audio=audio, relative_path=rel)

        results = run_parallel_timed(
            files,
            "转码 FLAC",
            _transcode,
            progress,
            duration_fn=lambda audio: audio.duration_seconds,
            name_fn=lambda audio: audio.filename,
        )
        return list(results)


def _probe_duration(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    return info.duration

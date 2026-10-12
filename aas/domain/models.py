"""Core domain dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

SAMPLE_RATE = 48000
BIT_DEPTH = 24


def source_key(path: Path) -> str:
    """Stable identity for a source file, shared by every lookup table."""
    return str(path.resolve())


class ClipKind(Enum):
    MAIN = "main"
    MIDDLE = "middle"


@dataclass
class SplicingConfig:
    audio_dir: Path
    order_path: Path
    middle_code: str
    output_name: str
    ignore_sample_rate: bool = False
    segments: int | None = None
    export_audio: bool = False


@dataclass
class AudioFile:
    code: str
    path: Path
    filename: str
    duration_seconds: float = 0.0
    sample_rate: int = 0

    @property
    def duration_samples(self) -> int:
        return int(round(self.duration_seconds * SAMPLE_RATE))


@dataclass
class Clip:
    kind: ClipKind
    audio: AudioFile
    start_point: int
    end_point: int
    source_in_point: int = 0
    source_out_point: int = 0


@dataclass
class GlobalTimeline:
    middle_clips: list[Clip] = field(default_factory=list)
    main_clips: list[Clip] = field(default_factory=list)

    @property
    def total_duration(self) -> int:
        if not self.main_clips:
            return 0
        return max(c.end_point for c in self.main_clips)


@dataclass
class SegmentTimeline:
    index: int
    main_clips: list[Clip] = field(default_factory=list)
    middle_clips: list[Clip] = field(default_factory=list)

    @property
    def duration(self) -> int:
        ends: list[int] = [c.end_point for c in self.main_clips + self.middle_clips]
        return max(ends) if ends else 0


@dataclass
class ProcessedSource:
    """A source that now lives inside the project's Sources directory."""

    audio: AudioFile
    relative_path: str

    @property
    def key(self) -> str:
        return source_key(self.audio.path)

    @property
    def display_name(self) -> str:
        return Path(self.relative_path).name


@dataclass
class AudioCatalog:
    audio_dir: Path
    middle_code: str
    ordered_codes: list[str]
    files_by_code: dict[str, AudioFile]
    middle_file: AudioFile

    def used_files(self) -> list[AudioFile]:
        seen: set[str] = set()
        result: list[AudioFile] = []
        for code in self.ordered_codes:
            f = self.files_by_code[code]
            key = source_key(f.path)
            if key not in seen:
                seen.add(key)
                result.append(f)
        key = source_key(self.middle_file.path)
        if key not in seen:
            result.append(self.middle_file)
        return result

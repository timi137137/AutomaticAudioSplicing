"""Expected, user-facing failures shared across layers."""

from __future__ import annotations


class SplicingError(Exception):
    """Base class for failures that should be reported to the user as-is."""


class ScanError(SplicingError):
    """Source directory, order file, or audio metadata is unusable."""


class FfmpegError(SplicingError):
    """ffmpeg is missing or a conversion/mix command failed."""


class PackageError(SplicingError):
    """The output project directory cannot be prepared."""


class SegmentSplitError(SplicingError):
    """The requested segment count cannot be satisfied."""


class SegmentExportError(SplicingError):
    """A segment could not be rendered to MP3."""

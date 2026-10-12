"""Resolve bundled resource paths for dev and PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # aas/infra/resources.py -> repository root
    return Path(__file__).resolve().parents[2]


def resource_path(relative: str) -> Path:
    return project_root() / relative

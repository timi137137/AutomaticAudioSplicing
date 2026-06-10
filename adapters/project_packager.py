"""Create project directory and write SESX."""

from __future__ import annotations

from pathlib import Path


class PackageError(Exception):
    pass


def prepare_project_root(output_name: str) -> tuple[Path, Path]:
    root = Path.cwd() / output_name
    if root.exists() and any(root.iterdir()):
        raise PackageError(f"项目目录已存在且非空: {root}")
    sources = root / "Sources"
    root.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    return root, sources


def write_sesx(project_root: Path, output_name: str, sesx_xml: str) -> Path:
    sesx_path = project_root / f"{output_name}.sesx"
    sesx_path.write_text(sesx_xml, encoding="utf-8")
    return sesx_path

"""Download scheduled sources with yt-dlp and normalize them into FLAC."""

from __future__ import annotations

from pathlib import Path

from aas.domain.schedule import SheetEntry, source_filename
from aas.errors import DownloadError, SplicingError
from aas.infra import normalize
from aas.infra.ffmpeg import ensure_ffmpeg
from aas.infra.progress import TaskProgress, run_parallel

RAW_SUBDIR = "raw"


def ensure_ytdlp() -> None:
    try:
        import yt_dlp  # noqa: F401
    except ImportError as exc:
        raise DownloadError("未找到 yt-dlp，请先安装（pip install yt-dlp）。") from exc


def _download_raw(
    entry: SheetEntry,
    raw_dir: Path,
    cookies_path: Path | None,
    proxy: str | None,
) -> Path:
    import yt_dlp

    raw_dir.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {
        "format": "bestaudio/best",
        "outtmpl": str(raw_dir / f"{entry.code}.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
    }
    if cookies_path is not None:
        options["cookiefile"] = str(cookies_path)
    if proxy:
        options["proxy"] = proxy

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(entry.url, download=True)
        if info is None:
            raise DownloadError(f"[{entry.code}] yt-dlp 未返回结果。")
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return Path(requested[0]["filepath"])
        return Path(ydl.prepare_filename(info))


def _is_ready(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def prepare_sources(
    entries: list[SheetEntry],
    download_dir: Path,
    cookies_path: Path | None,
    proxy: str | None,
    progress: TaskProgress,
) -> None:
    """Fetch every entry in parallel; fail only after the whole batch settles."""
    download_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = download_dir / RAW_SUBDIR

    def target_of(entry: SheetEntry) -> Path:
        return download_dir / source_filename(entry.code, entry.title)

    # yt-dlp and ffmpeg are only required when at least one row still needs work.
    if any(not _is_ready(target_of(entry)) for entry in entries):
        ensure_ytdlp()
        ensure_ffmpeg()

    def worker(entry: SheetEntry) -> tuple[SheetEntry, Path | None, str | None]:
        dst = target_of(entry)
        try:
            if _is_ready(dst):
                return entry, dst, None
            raw = _download_raw(entry, raw_dir, cookies_path, proxy)
            normalize.normalize_segment(
                raw, dst, entry.start_seconds, entry.end_seconds
            )
            return entry, dst, None
        except SplicingError as exc:
            return entry, None, str(exc)
        except Exception as exc:  # yt-dlp and ffmpeg raise assorted types
            return entry, None, f"{type(exc).__name__}: {exc}"

    outcomes = run_parallel(entries, "下载音源", worker, progress)
    failures = [(entry, error) for entry, _, error in outcomes if error]
    if failures:
        preview = "; ".join(f"[{entry.code}] {error}" for entry, error in failures[:5])
        more = f" 等共 {len(failures)} 行" if len(failures) > 5 else ""
        raise DownloadError(f"以下音源下载/归一化失败: {preview}{more}")

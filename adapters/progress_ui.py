"""Multi-phase CLI progress UI (yarn-install style)."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

T = TypeVar("T")
R = TypeVar("R")

MAX_PARALLEL_WORKERS = 20

console = Console(stderr=True)


def format_clock(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_progress_range(current: float, total: float) -> str:
    return f"{format_clock(current)}/{format_clock(total)}"


class TaskProgress:
    """Show one completed line per phase; update the active phase in place."""

    def __init__(self) -> None:
        self._use_rich = sys.stderr.isatty()
        self._live: Live | None = None
        self._lock = threading.Lock()
        self._completed_lines: list[str] = []
        self._current_text = ""
        self._work_total = 0.0
        self._last_plain_pct = -1
        self._last_refresh = 0.0

    def __enter__(self) -> TaskProgress:
        if self._use_rich:
            self._live = Live(
                self._render(),
                console=console,
                refresh_per_second=10,
                transient=False,
            )
            self._live.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._complete_current_phase()
        if self._live:
            self._live.update(self._render())
            self._live.stop()

    def _render(self) -> Group | Text:
        rows: list[Spinner | Text] = []
        for line in self._completed_lines:
            rows.append(Text.from_markup(f"[green]✔[/green] {line}"))
        if self._current_text:
            rows.append(Spinner("dots", text=self._current_text, style="cyan"))
        if not rows:
            return Text("")
        return Group(*rows)

    def _refresh(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_refresh < 0.08:
            return
        self._last_refresh = now
        if self._live:
            self._live.update(self._render())

    def _complete_current_phase(self) -> None:
        if self._current_text:
            self._completed_lines.append(self._current_text)
            self._current_text = ""

    def log(self, message: str) -> None:
        if self._use_rich and self._live:
            self._live.console.log(f"[dim]{message}[/dim]")
        else:
            console.print(message)

    def status(self, message: str) -> None:
        self.log(message)

    def begin_work(self, label: str, total: float) -> None:
        with self._lock:
            self._complete_current_phase()
            self._work_total = max(total, 0.001)
            self._last_plain_pct = -1
            self._current_text = label
            self._refresh(force=True)

    def update_work(self, completed: float, description: str) -> None:
        with self._lock:
            self._current_text = description
            if self._live:
                self._refresh()
            elif not self._use_rich:
                pct = int(completed / self._work_total * 100) if self._work_total else 0
                if pct != self._last_plain_pct:
                    self._last_plain_pct = pct
                    console.print(description)

    def add_overall(self, label: str, total: int) -> None:
        self.begin_work(label, float(total))

    def update_overall(self, description: str, completed: int | None = None) -> None:
        completed_value = float(completed) if completed is not None else 0.0
        self.update_work(completed_value, description)

    def advance_overall(self, description: str | None = None) -> None:
        if description:
            self.update_work(0.0, description)


class DurationWorkTracker:
    """Aggregate ffmpeg time-based progress across parallel workers."""

    def __init__(self, progress: TaskProgress, label: str) -> None:
        self._progress = progress
        self._label = label
        self._lock = threading.Lock()
        self._items: dict[int, tuple[float, float, str]] = {}
        self._total_seconds = 0.0
        self._started = False

    def register(self, index: int, duration_seconds: float, name: str) -> None:
        with self._lock:
            self._items[index] = (0.0, max(duration_seconds, 0.001), name)
            self._total_seconds = sum(item[1] for item in self._items.values())
            if not self._started:
                self._progress.begin_work(self._label, self._total_seconds)
                self._started = True
            self._flush_unlocked(active_index=index)

    def update(self, index: int, current_seconds: float) -> None:
        with self._lock:
            if index not in self._items:
                return
            _, total, name = self._items[index]
            self._items[index] = (
                min(max(current_seconds, 0.0), total),
                total,
                name,
            )
            self._flush_unlocked(active_index=index)

    def complete(self, index: int) -> None:
        with self._lock:
            if index not in self._items:
                return
            _, total, name = self._items[index]
            self._items[index] = (total, total, name)
            self._flush_unlocked(active_index=index)

    def _flush_unlocked(self, active_index: int) -> None:
        completed = sum(current for current, _, _ in self._items.values())
        current, total, name = self._items[active_index]
        desc = (
            f"{self._label}  {format_progress_range(current, total)}  {name}  "
            f"总进度 {format_progress_range(completed, self._total_seconds)}"
        )
        self._progress.update_work(completed, desc)


def _worker_count(item_count: int, max_workers: int | None) -> int:
    cap = max_workers if max_workers is not None else MAX_PARALLEL_WORKERS
    return min(cap, MAX_PARALLEL_WORKERS, max(item_count, 1))


def run_parallel(
    items: list[T],
    label: str,
    worker_fn: Callable[[T], R],
    progress: TaskProgress,
    max_workers: int | None = None,
) -> list[R]:
    if not items:
        return []

    workers = _worker_count(len(items), max_workers)
    total = len(items)
    progress.add_overall(f"{label} 0/{total}", total)
    results: list[R | None] = [None] * total
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(worker_fn, item): idx for idx, item in enumerate(items)
        }
        try:
            for future in as_completed(future_map):
                idx = future_map[future]
                results[idx] = future.result()
                completed += 1
                name = getattr(items[idx], "filename", str(items[idx]))
                progress.update_overall(
                    f"{label} {completed}/{total}  {name}", completed
                )
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    return list(results)  # type: ignore[return-value]


def run_parallel_timed(
    items: list[T],
    label: str,
    worker_fn: Callable[[T, int, Callable[[float, float], None]], R],
    progress: TaskProgress,
    duration_fn: Callable[[T], float],
    name_fn: Callable[[T], str],
    max_workers: int | None = None,
) -> list[R]:
    if not items:
        return []

    tracker = DurationWorkTracker(progress, label)
    for idx, item in enumerate(items):
        tracker.register(idx, duration_fn(item), name_fn(item))

    workers = _worker_count(len(items), max_workers)
    results: list[R | None] = [None] * len(items)

    def _run(idx: int, item: T) -> R:
        def on_progress(current: float, total: float) -> None:
            tracker.update(idx, current)

        result = worker_fn(item, idx, on_progress)
        tracker.complete(idx)
        return result

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_run, idx, item): idx
            for idx, item in enumerate(items)
        }
        try:
            for future in as_completed(future_map):
                idx = future_map[future]
                results[idx] = future.result()
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    return list(results)  # type: ignore[return-value]

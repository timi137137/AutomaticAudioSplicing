"""Unit tests for parallel download orchestration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aas.domain.schedule import SheetEntry
from aas.errors import DownloadError
from aas.infra import downloader


class _FakeProgress:
    def begin_work(self, label: str, total: float) -> None:
        pass

    def update_work(self, completed: float, description: str) -> None:
        pass


def _entry(code: str) -> SheetEntry:
    return SheetEntry(code, f"title {code}", 0.0, 30.0, f"https://e/{code}")


class PrepareSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher_ytdlp = mock.patch.object(downloader, "ensure_ytdlp")
        patcher_ffmpeg = mock.patch.object(downloader, "ensure_ffmpeg")
        patcher_raw = mock.patch.object(downloader, "_download_raw")
        patcher_norm = mock.patch.object(downloader.normalize, "normalize_segment")
        self.addCleanup(patcher_ytdlp.stop)
        self.addCleanup(patcher_ffmpeg.stop)
        self.addCleanup(patcher_raw.stop)
        self.addCleanup(patcher_norm.stop)
        patcher_ytdlp.start()
        patcher_ffmpeg.start()
        self.download_raw = patcher_raw.start()
        self.normalize = patcher_norm.start()

    def test_success_downloads_every_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            downloader.prepare_sources(
                [_entry("101"), _entry("102")], Path(tmp), None, None, _FakeProgress()
            )
        self.assertEqual(self.download_raw.call_count, 2)
        self.assertEqual(self.normalize.call_count, 2)

    def test_existing_output_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "[101] title 101.flac").write_bytes(b"fLaC")
            downloader.prepare_sources([_entry("101")], root, None, None, _FakeProgress())
        self.download_raw.assert_not_called()

    def test_failure_after_batch_settles(self) -> None:
        self.download_raw.side_effect = RuntimeError("boom")
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(DownloadError) as ctx:
            downloader.prepare_sources(
                [_entry("101"), _entry("102")],
                Path(tmp),
                None,
                None,
                _FakeProgress(),
            )
        # Both rows were attempted despite the first failing.
        self.assertEqual(self.download_raw.call_count, 2)
        self.assertIn("101", str(ctx.exception))
        self.assertIn("102", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

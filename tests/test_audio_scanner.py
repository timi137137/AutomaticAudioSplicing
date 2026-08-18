"""Unit tests for audio scanning / order code expansion."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.audio_scanner import FILENAME_PATTERN, ScanError, _expand_order_codes, scan
from domain.models import AudioFile


class FilenamePatternTest(unittest.TestCase):
    def test_space_after_bracket(self) -> None:
        m = FILENAME_PATTERN.match("[156-1] 我最可爱的地方.wav")
        self.assertIsNotNone(m)
        assert m is not None
        self.assertEqual(m.group("code"), "156-1")

    def test_no_space_tag_after_bracket(self) -> None:
        m = FILENAME_PATTERN.match("[13-1][PJSK] 不知醉.wav")
        self.assertIsNotNone(m)
        assert m is not None
        self.assertEqual(m.group("code"), "13-1")
        self.assertEqual(m.group("title"), "[PJSK] 不知醉")


class ExpandOrderCodesTest(unittest.TestCase):
    def test_main_expands_to_dash_one_only(self) -> None:
        files = {
            "121-2": AudioFile("121-2", Path("a"), "a"),
            "121-1": AudioFile("121-1", Path("b"), "b"),
            "121-3": AudioFile("121-3", Path("c"), "c"),
            "38-1": AudioFile("38-1", Path("d"), "d"),
        }
        self.assertEqual(
            _expand_order_codes(["38", "121"], files),
            ["38-1", "121-1"],
        )

    def test_exact_full_code_kept(self) -> None:
        files = {
            "101-1": AudioFile("101-1", Path("a"), "a"),
            "101-2": AudioFile("101-2", Path("b"), "b"),
        }
        self.assertEqual(_expand_order_codes(["101-2"], files), ["101-2"])
        self.assertEqual(
            _expand_order_codes(["101-1", "101-2"], files),
            ["101-1", "101-2"],
        )

    def test_main_then_exact_no_duplicate(self) -> None:
        files = {
            "101-1": AudioFile("101-1", Path("a"), "a"),
            "101-2": AudioFile("101-2", Path("b"), "b"),
        }
        self.assertEqual(
            _expand_order_codes(["101", "101-1"], files),
            ["101-1"],
        )
        self.assertEqual(
            _expand_order_codes(["101", "101-2"], files),
            ["101-1", "101-2"],
        )

    def test_skip_middle_code_in_order(self) -> None:
        files = {
            "0-4": AudioFile("0-4", Path("m"), "m"),
            "156-1": AudioFile("156-1", Path("a"), "a"),
        }
        self.assertEqual(
            _expand_order_codes(["0-4", "156"], files, middle_code="0-4"),
            ["156-1"],
        )

    def test_missing_raises(self) -> None:
        with self.assertRaises(ScanError):
            _expand_order_codes(["999"], {})


class ScanIntegrationTest(unittest.TestCase):
    def test_scan_main_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio"
            audio.mkdir()
            (audio / "[0-4] mid.wav").write_bytes(b"RIFF")
            (audio / "[156-1] a.wav").write_bytes(b"RIFF")
            (audio / "[13-1][PJSK] b.wav").write_bytes(b"RIFF")
            (audio / "[459-1] c.wav").write_bytes(b"RIFF")
            (audio / "[459-2] d.wav").write_bytes(b"RIFF")
            order = root / "order.txt"
            order.write_text("156\n13\n459\n", encoding="utf-8")
            catalog = scan(audio, order, "0-4")
            self.assertEqual(catalog.ordered_codes, ["156-1", "13-1", "459-1"])
            # used_files = 3 songs + 1 middle
            self.assertEqual(len(catalog.used_files()), 4)


if __name__ == "__main__":
    unittest.main()

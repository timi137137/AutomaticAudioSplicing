"""Unit tests for reading the download schedule workbook."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from aas.errors import SheetError
from aas.infra.sheet import read_sheet

HEADERS = ["编码", "歌名", "时间区间", "音源地址"]


def _write_workbook(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


class ReadSheetTest(unittest.TestCase):
    def _read(self, rows: list[list[object]]) -> list:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.xlsx"
            _write_workbook(path, rows)
            return read_sheet(path)

    def test_reads_entries_in_row_order(self) -> None:
        entries = self._read(
            [
                ["101", "第一首", "00:00 - 01:30", "https://e/1"],
                ["13", "第二首", "01:30 - 02:45", "https://e/2"],
            ]
        )
        self.assertEqual([e.code for e in entries], ["101", "13"])
        self.assertEqual(entries[0].start_seconds, 0.0)
        self.assertEqual(entries[1].end_seconds, 165.0)

    def test_skips_blank_rows(self) -> None:
        entries = self._read(
            [
                ["101", "第一首", "00:00 - 01:30", "https://e/1"],
                [None, None, None, None],
            ]
        )
        self.assertEqual(len(entries), 1)

    def test_missing_header_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.xlsx"
            workbook = Workbook()
            workbook.active.append(["编码", "歌名"])
            workbook.save(path)
            with self.assertRaises(SheetError):
                read_sheet(path)

    def test_missing_cell_raises(self) -> None:
        with self.assertRaises(SheetError):
            self._read([["101", "第一首", "", "https://e/1"]])

    def test_duplicate_code_raises(self) -> None:
        with self.assertRaises(SheetError):
            self._read(
                [
                    ["101", "一", "00:00 - 00:30", "https://e/1"],
                    ["101", "二", "00:30 - 01:00", "https://e/2"],
                ]
            )

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(SheetError):
            read_sheet(Path("/nonexistent/plan.xlsx"))


if __name__ == "__main__":
    unittest.main()

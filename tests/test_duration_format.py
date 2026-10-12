"""Unit tests for duration formatting."""

from __future__ import annotations

import unittest

from aas.domain.duration import format_duration_from_samples
from aas.domain.models import SAMPLE_RATE


class DurationFormatTest(unittest.TestCase):
    def test_zero(self) -> None:
        self.assertEqual(format_duration_from_samples(0), "0秒")

    def test_sub_second_rounds_up(self) -> None:
        self.assertEqual(format_duration_from_samples(1), "1秒")
        self.assertEqual(format_duration_from_samples(SAMPLE_RATE - 1), "1秒")

    def test_exact_second(self) -> None:
        self.assertEqual(format_duration_from_samples(SAMPLE_RATE), "1秒")

    def test_partial_second_rounds_up(self) -> None:
        self.assertEqual(format_duration_from_samples(SAMPLE_RATE + 1), "2秒")

    def test_minutes_and_seconds(self) -> None:
        samples = SAMPLE_RATE * (5 * 60 + 20)
        self.assertEqual(format_duration_from_samples(samples), "5分20秒")

    def test_hours_minutes_seconds(self) -> None:
        samples = SAMPLE_RATE * (3600 + 5 * 60 + 20)
        self.assertEqual(format_duration_from_samples(samples), "1时5分20秒")


if __name__ == "__main__":
    unittest.main()

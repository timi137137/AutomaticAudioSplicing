"""Unit tests for loudnorm measurement parsing."""

from __future__ import annotations

import unittest

from aas.errors import FfmpegError
from aas.infra.normalize import parse_loudnorm_json

SAMPLE_STDERR = """
[Parsed_loudnorm_0 @ 0x55]
{
	"input_i" : "-23.45",
	"input_tp" : "-2.10",
	"input_lra" : "7.20",
	"input_thresh" : "-33.60",
	"output_i" : "-16.00",
	"output_tp" : "-1.50",
	"output_lra" : "7.20",
	"output_thresh" : "-26.15",
	"normalization_type" : "linear",
	"target_offset" : "0.20"
}
"""


class ParseLoudnormJsonTest(unittest.TestCase):
    def test_extracts_measurement(self) -> None:
        measurement = parse_loudnorm_json(SAMPLE_STDERR)
        self.assertEqual(measurement.input_i, "-23.45")
        self.assertEqual(measurement.target_offset, "0.20")

    def test_filter_suffix_carries_linear_mode(self) -> None:
        suffix = parse_loudnorm_json(SAMPLE_STDERR).filter_suffix()
        self.assertIn("measured_I=-23.45", suffix)
        self.assertIn("offset=0.20", suffix)
        self.assertIn("linear=true", suffix)

    def test_missing_json_raises(self) -> None:
        with self.assertRaises(FfmpegError):
            parse_loudnorm_json("no json here")

    def test_incomplete_json_raises(self) -> None:
        with self.assertRaises(FfmpegError):
            parse_loudnorm_json('{"input_i" : "-23.45"}')


if __name__ == "__main__":
    unittest.main()

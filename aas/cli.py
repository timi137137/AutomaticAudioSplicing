"""Command-line interface for the SESX splicing tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aas.domain.duration import format_duration_from_samples
from aas.domain.models import SplicingConfig
from aas.errors import SplicingError
from aas.service import SplicingService


def _parse_segments(value: str) -> int:
    n = int(value)
    if n < 2 or n % 2 != 0:
        raise argparse.ArgumentTypeError("--segments 必须为不小于 2 的偶数")
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adobe Audition 多轨 SESX 自动拼接工具",
        allow_abbrev=False,
    )
    parser.add_argument("--audio-dir", required=True, type=Path, help="源音频目录")
    parser.add_argument("--order", required=True, type=Path, help="顺序 txt 文件")
    parser.add_argument(
        "--middle-code", required=True, help="中间音频编码（不含方括号）"
    )
    parser.add_argument("--output", required=True, help="项目文件夹名称")
    parser.add_argument(
        "--ignore-sample-rate",
        action="store_true",
        help="忽略采样率差异，ffmpeg 统一转 FLAC 48kHz 24bit",
    )
    parser.add_argument(
        "--segments",
        type=_parse_segments,
        default=None,
        help="分段数（偶数 ≥2，默认不分段）",
    )
    parser.add_argument(
        "--export-audio",
        action="store_true",
        help="拼接后导出 MP3（每段一个，320kbps，仅混该段轨道）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if argv and not argv[0].startswith("-"):
        parser.error("禁止使用位置参数，请使用 --audio-dir 等具名参数。")

    args = parser.parse_args(argv)
    config = SplicingConfig(
        audio_dir=args.audio_dir,
        order_path=args.order,
        middle_code=args.middle_code,
        output_name=args.output,
        ignore_sample_rate=args.ignore_sample_rate,
        segments=args.segments,
        export_audio=args.export_audio,
    )

    try:
        result = SplicingService().run(config)
    except SplicingError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # unexpected failure: still report instead of a traceback
        print(f"意外错误: {exc}", file=sys.stderr)
        return 1

    print(f"已生成项目: {result.sesx_path}")
    for seg in result.segments:
        duration_text = format_duration_from_samples(seg.duration)
        print(f"段 {seg.index + 1} 总时长: {duration_text}")
    for mp3_path in result.exported_mp3:
        print(f"已导出音频: {mp3_path}")
    return 0

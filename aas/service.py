"""Orchestrate the end-to-end splicing workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aas.domain.models import SegmentTimeline, SplicingConfig
from aas.domain.timeline import TimelineBuilder, layout_segments
from aas.infra import downloader, packaging, scanner, sheet
from aas.infra.exporter import export_segments
from aas.infra.processing import CopyStrategy, TranscodeStrategy
from aas.infra.progress import TaskProgress
from aas.infra.resources import resource_path
from aas.infra.sesx import SesxBuilder

DOWNLOAD_DIRNAME = "downloads"


@dataclass
class SplicingResult:
    sesx_path: Path
    segments: list[SegmentTimeline]
    exported_mp3: list[Path] = field(default_factory=list)


class SplicingService:
    def run(self, config: SplicingConfig) -> SplicingResult:
        with TaskProgress() as progress:
            audio_dirs, codes = self._resolve_sources(config, progress)
            catalog = scanner.scan(audio_dirs, codes, config.middle_code)
            scanner.probe_parallel(catalog, progress, config.ignore_sample_rate)

            project_root, sources_dir = packaging.prepare_project_root(
                config.output_name
            )

            source_strategy = (
                TranscodeStrategy()
                if config.ignore_sample_rate
                else CopyStrategy()
            )
            processed = source_strategy.process(
                catalog.used_files(), sources_dir, progress
            )

            progress.log("拼接项目…")
            global_tl = TimelineBuilder().build(catalog)
            segments = layout_segments(global_tl, config.segments)

            template = resource_path("resources/base.sesx")
            sesx_xml = (
                SesxBuilder(template)
                .load_template()
                .add_files(processed)
                .add_segment_tracks(segments)
                .build(project_root)
            )

            sesx_path = packaging.write_sesx(
                project_root, config.output_name, sesx_xml
            )

            exported: list[Path] = []
            if config.export_audio:
                exported = export_segments(
                    segments,
                    processed,
                    project_root,
                    config.output_name,
                    progress,
                )

        return SplicingResult(
            sesx_path=sesx_path,
            segments=segments,
            exported_mp3=exported,
        )

    @staticmethod
    def _resolve_sources(
        config: SplicingConfig, progress: TaskProgress
    ) -> tuple[list[Path], list[str]]:
        """Return the directories to scan and the main-audio codes in order."""
        if config.excel_path is not None:
            entries = sheet.read_sheet(config.excel_path)
            download_dir = config.download_dir or (Path.cwd() / DOWNLOAD_DIRNAME)
            downloader.prepare_sources(
                entries,
                download_dir,
                config.cookies_path,
                config.proxy,
                progress,
            )
            # Downloaded audio lives in download_dir; the middle audio stays local.
            return [download_dir, config.audio_dir], [entry.code for entry in entries]
        if config.order_path is None:
            raise ValueError("需要 --order 或 --excel 之一。")
        return [config.audio_dir], scanner.read_order(config.order_path)

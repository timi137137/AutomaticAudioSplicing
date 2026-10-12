"""Orchestrate the end-to-end splicing workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aas.domain.models import SegmentTimeline, SplicingConfig
from aas.domain.timeline import TimelineBuilder, layout_segments
from aas.infra import packaging, scanner
from aas.infra.exporter import export_segments
from aas.infra.processing import CopyStrategy, TranscodeStrategy
from aas.infra.progress import TaskProgress
from aas.infra.resources import resource_path
from aas.infra.sesx import SesxBuilder


@dataclass
class SplicingResult:
    sesx_path: Path
    segments: list[SegmentTimeline]
    exported_mp3: list[Path] = field(default_factory=list)


class SplicingService:
    def run(self, config: SplicingConfig) -> SplicingResult:
        with TaskProgress() as progress:
            catalog = scanner.scan(
                config.audio_dir, config.order_path, config.middle_code
            )
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

"""Facade orchestrating the splicing workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from adapters import audio_scanner, project_packager
from adapters.progress_ui import TaskProgress
from adapters.resource_paths import resource_path
from adapters.segment_exporter import export_segments
from builders.sesx_builder import SesxBuilder
from domain.models import ProcessedSource, SegmentTimeline, SplicingConfig
from domain.timeline_builder import TimelineBuilder
from strategies.source_processing import CopyStrategy, TranscodeStrategy
from strategies.timeline_layout import MultiSegmentStrategy, SingleSegmentStrategy


@dataclass
class SplicingResult:
    sesx_path: Path
    segments: list[SegmentTimeline]
    exported_mp3: list[Path] = field(default_factory=list)


class SplicingFacade:
    def run(self, config: SplicingConfig) -> SplicingResult:
        with TaskProgress() as progress:
            catalog = audio_scanner.scan(
                config.audio_dir, config.order_path, config.middle_code
            )
            audio_scanner.probe_parallel(
                catalog, progress, config.ignore_sample_rate
            )

            project_root, sources_dir = project_packager.prepare_project_root(
                config.output_name
            )

            source_strategy = (
                TranscodeStrategy()
                if config.ignore_sample_rate
                else CopyStrategy()
            )
            processed: list[ProcessedSource] = source_strategy.process(
                catalog.used_files(), sources_dir, progress
            )
            self._apply_sources_names(catalog, processed)

            progress.log("拼接项目…")
            global_tl = TimelineBuilder().build(catalog)
            if config.segments and config.segments >= 2:
                layout = MultiSegmentStrategy(config.segments)
            else:
                layout = SingleSegmentStrategy()
            segments = layout.layout(global_tl)

            template = resource_path("resources/base.sesx")
            sesx_xml = (
                SesxBuilder(template)
                .load_template()
                .add_files(processed)
                .add_segment_tracks(segments)
                .build(project_root)
            )

            sesx_path = project_packager.write_sesx(
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
    def _apply_sources_names(
        catalog,
        processed: list[ProcessedSource],
    ) -> None:
        by_path = {str(p.audio.path.resolve()): p for p in processed}
        for audio in catalog.used_files():
            key = str(audio.path.resolve())
            if key in by_path:
                ps = by_path[key]
                audio.sources_name = Path(ps.relative_path).name

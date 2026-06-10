"""Build global M-A alternating timeline."""

from __future__ import annotations

from domain.models import (
    SAMPLE_RATE,
    AudioCatalog,
    Clip,
    ClipKind,
    GlobalTimeline,
)


class TimelineBuilder:
    """Builder: construct GlobalTimeline from catalog."""

    def build(self, catalog: AudioCatalog) -> GlobalTimeline:
        middle = catalog.middle_file
        middle_samples = middle.duration_samples
        timeline = GlobalTimeline()
        cursor = 0

        for code in catalog.ordered_codes:
            main = catalog.files_by_code[code]
            main_samples = main.duration_samples

            timeline.middle_clips.append(
                Clip(
                    kind=ClipKind.MIDDLE,
                    audio=middle,
                    start_point=cursor,
                    end_point=cursor + middle_samples,
                    source_in_point=0,
                    source_out_point=middle_samples,
                    global_start=cursor,
                )
            )
            cursor += middle_samples

            timeline.main_clips.append(
                Clip(
                    kind=ClipKind.MAIN,
                    audio=main,
                    start_point=cursor,
                    end_point=cursor + main_samples,
                    source_in_point=0,
                    source_out_point=main_samples,
                    global_start=cursor,
                )
            )
            cursor += main_samples

        return timeline

"""SESX project builder."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from aas.domain.models import (
    BIT_DEPTH,
    SAMPLE_RATE,
    Clip,
    ProcessedSource,
    SegmentTimeline,
    source_key,
)

_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE sesx>\n'

MASTER_TRACK_ID = "100000003"
DEFAULT_HARDWARE_OUTPUT_ID = "1"


def _new_id() -> str:
    return str(abs(hash(uuid.uuid4())) % 900_000_000 + 100_000_000)


class SesxBuilder:
    """Builder: assemble SESX XML from template."""

    def __init__(self, template_path: Path) -> None:
        self._template_path = template_path
        self._tree: ET.ElementTree | None = None
        self._root: ET.Element | None = None
        self._session: ET.Element | None = None
        self._tracks_el: ET.Element | None = None
        self._track_template: ET.Element | None = None
        self._files: list[ProcessedSource] = []
        self._segments: list[SegmentTimeline] = []
        self._file_id_by_path: dict[str, int] = {}
        self._display_name_by_path: dict[str, str] = {}

    def load_template(self) -> SesxBuilder:
        self._tree = ET.parse(self._template_path)
        self._root = self._tree.getroot()
        self._session = self._root.find("session")
        if self._session is None:
            raise ValueError("模板缺少 session 节点")
        tracks = self._session.find("tracks")
        if tracks is None:
            raise ValueError("模板缺少 tracks 节点")
        audio_tracks = tracks.findall("audioTrack")
        if not audio_tracks:
            raise ValueError("模板缺少 audioTrack")
        self._track_template = copy.deepcopy(audio_tracks[0])
        self._tracks_el = tracks
        return self

    def add_files(self, sources: list[ProcessedSource]) -> SesxBuilder:
        self._files = list(sources)
        return self

    def add_segment_tracks(self, segments: list[SegmentTimeline]) -> SesxBuilder:
        self._segments = list(segments)
        return self

    def build(self, project_root: Path) -> str:
        if self._root is None or self._session is None or self._tracks_el is None:
            raise RuntimeError("请先调用 load_template()")

        max_duration = max((s.duration for s in self._segments), default=0)
        self._session.set("sampleRate", str(SAMPLE_RATE))
        self._session.set("bitDepth", str(BIT_DEPTH))
        self._session.set("duration", str(max_duration))

        self._write_files(project_root)
        self._write_tracks()
        self._ensure_audio_device()

        xml_body = ET.tostring(self._root, encoding="unicode")
        return _XML_DECL + xml_body

    def _write_files(self, project_root: Path) -> None:
        assert self._root is not None
        files_el = self._root.find("files")
        if files_el is None:
            files_el = ET.SubElement(self._root, "files")
        else:
            files_el.clear()

        unique: list[ProcessedSource] = []
        seen: set[str] = set()
        for ps in self._files:
            if ps.key in seen:
                continue
            seen.add(ps.key)
            unique.append(ps)

        self._file_id_by_path = {}
        self._display_name_by_path = {}
        for file_id, ps in enumerate(unique):
            abs_path = str((project_root / ps.relative_path).resolve())
            ET.SubElement(
                files_el,
                "file",
                {
                    "id": str(file_id),
                    "absolutePath": abs_path,
                    "relativePath": ps.relative_path.replace("/", "\\"),
                    "mediaHandler": "WaveHandler",
                },
            )
            self._file_id_by_path[ps.key] = file_id
            self._display_name_by_path[ps.key] = ps.display_name

    def _write_tracks(self) -> None:
        assert self._tracks_el is not None
        assert self._track_template is not None

        master = self._tracks_el.find("masterTrack")
        master_id = master.get("id", MASTER_TRACK_ID) if master is not None else MASTER_TRACK_ID
        for child in list(self._tracks_el):
            if child.tag == "audioTrack":
                self._tracks_el.remove(child)

        new_tracks: list[ET.Element] = []
        clip_id = 1
        for seg in self._segments:
            seg_num = seg.index + 1
            if len(self._segments) == 1:
                main_name = "编号音频"
                mid_name = "中间音频"
            else:
                main_name = f"编号音频 {seg_num}"
                mid_name = f"中间音频 {seg_num}"
            main_track = self._make_track(0, main_name, "000000000", master_id)
            mid_track = self._make_track(0, mid_name, "120000000", master_id)
            for clip in seg.main_clips:
                main_track.append(self._make_clip(clip, clip_id))
                clip_id += 1
            for clip in seg.middle_clips:
                mid_track.append(self._make_clip(clip, clip_id))
                clip_id += 1
            new_tracks.extend([main_track, mid_track])

        for idx, track in enumerate(new_tracks):
            track.set("index", str(idx))
            self._tracks_el.insert(idx, track)
        if master is not None:
            master.set("index", str(len(new_tracks)))
            self._configure_master_routing(master)

    @staticmethod
    def _configure_audio_track_routing(track: ET.Element, master_id: str) -> None:
        tap = track.find("trackAudioParameters")
        if tap is None:
            tap = ET.SubElement(
                track,
                "trackAudioParameters",
                {
                    "audioChannelType": "stereo",
                    "automationMode": "1",
                    "monitoring": "false",
                    "recordArmed": "false",
                    "solo": "false",
                    "soloSafe": "false",
                },
            )
        for tag in ("trackOutput", "trackInput"):
            existing = tap.find(tag)
            if existing is not None:
                tap.remove(existing)
        ET.SubElement(
            tap,
            "trackOutput",
            {"outputID": master_id, "type": "trackID"},
        )
        ET.SubElement(tap, "trackInput", {"inputID": "-1"})

    @staticmethod
    def _configure_master_routing(master: ET.Element) -> None:
        tap = master.find("trackAudioParameters")
        if tap is None:
            tap = ET.SubElement(
                master,
                "trackAudioParameters",
                {
                    "audioChannelType": "stereo",
                    "automationMode": "1",
                    "monitoring": "false",
                    "recordArmed": "false",
                    "solo": "false",
                    "soloSafe": "true",
                },
            )
        for tag in ("trackOutput", "trackInput"):
            existing = tap.find(tag)
            if existing is not None:
                tap.remove(existing)
        ET.SubElement(
            tap,
            "trackOutput",
            {
                "outputID": DEFAULT_HARDWARE_OUTPUT_ID,
                "type": "hardwareOutput",
            },
        )
        ET.SubElement(tap, "trackInput", {"inputID": "-1"})

    def _ensure_audio_device(self) -> None:
        assert self._root is not None
        device = self._root.find("audioDevice")
        if device is None:
            device = ET.SubElement(self._root, "audioDevice")
        else:
            device.clear()
        device.set("inputID", "00000000-0000-0000-0000-000000000001")
        device.set("outputID", "00000000-0000-0000-0000-000000000002")
        ET.SubElement(device, "inputPort", {"id": "1", "name": "Default Stereo Input"})
        ET.SubElement(device, "outputPort", {"id": "1", "name": "Default Output"})

    def _make_track(self, index: int, name: str, hue: str, master_id: str) -> ET.Element:
        assert self._track_template is not None
        track = copy.deepcopy(self._track_template)
        track.set("id", _new_id())
        track.set("index", str(index))
        params = track.find("trackParameters")
        if params is not None:
            params.set("trackHue", hue)
            name_el = params.find("name")
            if name_el is not None:
                name_el.text = name
        for old_clip in track.findall("audioClip"):
            track.remove(old_clip)
        self._configure_audio_track_routing(track, master_id)
        return track

    def _make_clip(self, clip: Clip, clip_id: int) -> ET.Element:
        path_key = source_key(clip.audio.path)
        file_id = self._file_id_by_path.get(path_key, 0)
        display_name = self._display_name_by_path.get(path_key, clip.audio.filename)
        el = ET.Element(
            "audioClip",
            {
                "clipAutoCrossfade": "false",
                "crossFadeHeadClipID": "-1",
                "crossFadeTailClipID": "-1",
                "startPoint": str(clip.start_point),
                "endPoint": str(clip.end_point),
                "sourceInPoint": str(clip.source_in_point),
                "sourceOutPoint": str(clip.source_out_point),
                "fileID": str(file_id),
                "hue": str((clip_id * 37) % 360).zfill(9),
                "id": str(clip_id),
                "lockedInTime": "false",
                "looped": "false",
                "name": display_name,
                "offline": "false",
                "select": "false",
                "zOrder": "0",
            },
        )
        self._add_clip_components(el)
        fade_attrs = {
            "crossFadeLinkType": "linkedAsymmetric",
            "type": "log",
            "shape": "19",
        }
        # No fade-in: both points at clip start (source sample 0).
        ET.SubElement(
            el,
            "fadeIn",
            {"startPoint": "0", "endPoint": "0", **fade_attrs},
        )
        # No fade-out: both points at sourceOutPoint (Audition native "no fade" encoding).
        src_out = str(clip.source_out_point)
        ET.SubElement(
            el,
            "fadeOut",
            {"startPoint": src_out, "endPoint": src_out, **fade_attrs},
        )
        ch_map = ET.SubElement(el, "channelMap")
        ET.SubElement(ch_map, "channel", {"index": "0", "sourceIndex": "0"})
        ET.SubElement(ch_map, "channel", {"index": "1", "sourceIndex": "1"})
        return el

    @staticmethod
    def _add_clip_components(parent: ET.Element) -> None:
        fader = ET.SubElement(
            parent,
            "component",
            {
                "componentID": "Audition.Fader",
                "id": "clipGain",
                "name": "volume",
                "powered": "true",
                "componentGuid": str(uuid.uuid4()),
            },
        )
        ET.SubElement(
            fader,
            "parameter",
            {"index": "0", "name": "volume", "parameterValue": "1"},
        )
        ET.SubElement(
            fader,
            "parameter",
            {"index": "1", "name": "static gain", "parameterValue": "1"},
        )
        mute = ET.SubElement(
            parent,
            "component",
            {
                "componentID": "Audition.Mute",
                "id": "clipMute",
                "name": "Mute",
                "powered": "true",
                "componentGuid": str(uuid.uuid4()),
            },
        )
        ET.SubElement(mute, "parameter", {"index": "0", "parameterValue": "0"})
        ET.SubElement(mute, "parameter", {"index": "1", "name": "mute", "parameterValue": "0"})
        pan = ET.SubElement(
            parent,
            "component",
            {
                "componentID": "Audition.StereoPanner",
                "id": "clipPan",
                "name": "StereoPanner",
                "powered": "true",
                "componentGuid": str(uuid.uuid4()),
            },
        )
        ET.SubElement(pan, "parameter", {"index": "0", "name": "Pan", "parameterValue": "0"})

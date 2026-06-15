#!/usr/bin/env python3
"""
Generate a DaVinci Resolve-compatible FCPXML v1.11 timeline from selected segments.
Supports single media file or multi-source media via manifest.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

DEFAULT_FPS = 24


def to_tc(seconds: float, fps: int = DEFAULT_FPS) -> str:
    """Convert seconds to FCPXML time value: frames/denominator s."""
    frames = int(round(seconds * fps))
    return f"{frames}/{fps}s"


def load_media_manifest(manifest_path: str) -> list:
    """Load a media manifest JSON that maps timeline ranges to source files.

    Format:
    [
      {"source": "/path/to/clip1.mp4", "start": 0, "end": 1800},
      {"source": "/path/to/clip2.mp4", "start": 1800, "end": 3600}
    ]
    """
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_source_for_segment(seg_start: float, seg_end: float, manifest: list) -> dict | None:
    """Find which source file a segment belongs to based on timeline position."""
    mid = (seg_start + seg_end) / 2
    for entry in manifest:
        if entry["start"] <= mid < entry["end"]:
            return entry
    # Fallback: check overlap
    for entry in manifest:
        if entry["start"] < seg_end and entry["end"] > seg_start:
            return entry
    return None


def generate_fcpxml(segments, media_path: str, output_path: str,
                    media_manifest: list | None = None):
    """Generate FCPXML. If media_manifest is provided, uses multi-source mode."""

    if media_manifest:
        _generate_multi_source(segments, output_path, media_manifest)
    else:
        _generate_single_source(segments, media_path, output_path)


def _make_file_url(path: str) -> str:
    """Convert a file path to a file:// URL for FCPXML."""
    abs_path = os.path.abspath(path)
    # URL-encode special characters (spaces, Chinese, etc.)
    from urllib.parse import quote
    # Split into parts to preserve slashes
    parts = abs_path.split("/")
    encoded = "/".join(quote(p, safe="") for p in parts)
    return "file://" + encoded


def _generate_single_source(segments, media_path: str, output_path: str):
    """Generate FCPXML. Auto-detects multi-source if segments have source_path."""
    # Check if segments have been mapped to original source clips
    has_source_mapping = any(s.get("source_path") for s in segments)

    if has_source_mapping:
        _generate_from_mapped_sources(segments, output_path)
    else:
        _generate_from_single_file(segments, media_path, output_path)


def _generate_from_mapped_sources(segments, output_path: str):
    """Generate FCPXML from segments mapped to original DaVinci source clips."""
    # Build unique source file list
    source_map = {}
    asset_id = 2  # r1 is format
    for seg in segments:
        src = seg.get("source_path", "")
        if not src:
            continue
        if src not in source_map:
            source_map[src] = f"r{asset_id}"
            asset_id += 1

    # Detect FPS from segments
    fps = 24
    for seg in segments:
        if seg.get("clip_fps"):
            fps = round(seg["clip_fps"])
            break

    root = ET.Element("fcpxml", version="1.11")

    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources, "format", id="r1", name=f"FFVideoFormat1080p{fps}",
        frameDuration=f"1/{fps}s", width="1920", height="1080",
    )

    # Create assets for each source file
    for src_path, aid in source_map.items():
        src_name = os.path.splitext(os.path.basename(src_path))[0]
        file_url = _make_file_url(src_path)
        # Estimate total duration from mapped segments
        max_end = max(
            seg["source_end_sec"] for seg in segments
            if seg.get("source_path") == src_path
        )
        ET.SubElement(
            resources, "asset", id=aid, name=src_name, src=file_url,
            hasVideo="1", hasAudio="1", duration=to_tc(max_end + 10, fps),
        )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="粗剪")
    project = ET.SubElement(event, "project", name="粗剪时间线")

    total_timeline_duration = sum(seg["end"] - seg["start"] for seg in segments)
    sequence = ET.SubElement(
        project, "sequence", duration=to_tc(total_timeline_duration, fps), format="r1",
    )
    spine = ET.SubElement(sequence, "spine")

    offset = 0.0
    for seg in segments:
        src_path = seg.get("source_path", "")
        if not src_path:
            continue
        asset_ref = source_map.get(src_path)
        if not asset_ref:
            continue

        src_start = seg["source_start_sec"]
        src_end = seg["source_end_sec"]
        duration = seg["end"] - seg["start"]
        name = f"{seg.get('speaker', '?')} {seg['start']:.1f}s"

        ET.SubElement(
            spine, "asset-clip", name=name, ref=asset_ref,
            offset=to_tc(offset, fps), start=to_tc(src_start, fps), duration=to_tc(duration, fps),
        )
        offset += duration

    _write_xml(root, output_path)
    print(f"FCPXML saved to {output_path}")
    print(f"Timeline: {len(segments)} clips from {len(source_map)} source files, total {offset:.1f}s")


def _generate_from_single_file(segments, media_path: str, output_path: str):
    """Generate FCPXML referencing a single media file (fallback)."""
    total_duration_sec = max(seg["end"] for seg in segments) if segments else 1.0
    file_url = _make_file_url(media_path)
    is_audio_only = media_path.lower().endswith((".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a"))

    root = ET.Element("fcpxml", version="1.11")

    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources, "format", id="r1", name="FFVideoFormat1080p24",
        frameDuration=f"1/{FPS}s", width="1920", height="1080",
    )
    asset_attrs = {
        "id": "r2",
        "name": os.path.splitext(os.path.basename(media_path))[0],
        "src": file_url,
        "hasAudio": "1",
        "duration": to_tc(total_duration_sec + 1),
    }
    if not is_audio_only:
        asset_attrs["hasVideo"] = "1"
    ET.SubElement(resources, "asset", **asset_attrs)

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="粗剪")
    project = ET.SubElement(event, "project", name="粗剪时间线")

    total_timeline_duration = sum(seg["end"] - seg["start"] for seg in segments)
    sequence = ET.SubElement(
        project, "sequence", duration=to_tc(total_timeline_duration), format="r1",
    )
    spine = ET.SubElement(sequence, "spine")

    offset = 0.0
    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        duration = end - start
        name = f"{seg.get('speaker', '?')} {start:.1f}s"
        ET.SubElement(
            spine, "asset-clip", name=name, ref="r2",
            offset=to_tc(offset), start=to_tc(start), duration=to_tc(duration),
        )
        offset += duration

    _write_xml(root, output_path)
    print(f"FCPXML saved to {output_path}")
    print(f"Timeline contains {len(segments)} clips, total duration {offset:.1f}s")


def _generate_multi_source(segments, output_path: str, manifest: list):
    """Multi-source FCPXML generation with separate assets per source file."""
    # Build unique source list
    source_map = {}
    asset_id = 2  # r1 is format
    for entry in manifest:
        src = os.path.abspath(entry["source"])
        if src not in source_map:
            source_map[src] = f"r{asset_id}"
            asset_id += 1

    root = ET.Element("fcpxml", version="1.11")

    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources, "format", id="r1", name="FFVideoFormat1080p24",
        frameDuration=f"1/{FPS}s", width="1920", height="1080",
    )

    # Create assets for each source file
    for src_path, aid in source_map.items():
        src_name = os.path.splitext(os.path.basename(src_path))[0]
        max_end = max(e["end"] for e in manifest if os.path.abspath(e["source"]) == src_path)
        file_url = _make_file_url(src_path)
        ET.SubElement(
            resources, "asset", id=aid, name=src_name, src=file_url,
            hasVideo="1", hasAudio="1", duration=to_tc(max_end),
        )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="Rough Cut Event")
    project = ET.SubElement(event, "project", name="Rough Cut")

    total_timeline_duration = sum(seg["end"] - seg["start"] for seg in segments)
    sequence = ET.SubElement(
        project, "sequence", duration=to_tc(total_timeline_duration), format="r1",
    )
    spine = ET.SubElement(sequence, "spine")

    offset = 0.0
    for seg in segments:
        source_entry = find_source_for_segment(seg["start"], seg["end"], manifest)
        if not source_entry:
            print(f"Warning: segment {seg['start']:.1f}-{seg['end']:.1f}s not found in manifest, skipping")
            continue

        src_path = os.path.abspath(source_entry["source"])
        asset_ref = source_map[src_path]
        # Calculate position within the source file
        source_offset = seg["start"] - source_entry["start"]
        duration = seg["end"] - seg["start"]
        name = f"{seg.get('speaker', 'Clip')} {seg['start']:.1f}s"

        ET.SubElement(
            spine, "asset-clip", name=name, ref=asset_ref,
            offset=to_tc(offset), start=to_tc(source_offset), duration=to_tc(duration),
        )
        offset += duration

    _write_xml(root, output_path)
    print(f"FCPXML saved to {output_path}")
    print(f"Timeline contains {len(segments)} clips from {len(source_map)} sources, total duration {offset:.1f}s")


def _write_xml(root, output_path: str):
    """Pretty-print and write XML."""
    rough_string = ET.tostring(root, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    pretty = reparsed.toprettyxml(indent="  ")
    lines = [line for line in pretty.splitlines() if line.strip()]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Generate FCPXML from selections")
    parser.add_argument("selections", help="Path to selections JSON")
    parser.add_argument("--media", default="", help="Path to original media file (single-source mode)")
    parser.add_argument("--media-manifest", default=None,
                        help="Path to media manifest JSON (multi-source mode). "
                             "Format: [{\"source\": \"path/to/clip.mp4\", \"start\": 0, \"end\": 1800}, ...]")
    parser.add_argument("-o", "--output", default="rough_cut.fcpxml", help="Output FCPXML path")
    args = parser.parse_args()

    with open(args.selections, "r", encoding="utf-8") as f:
        segments = json.load(f)

    if not segments:
        print("Warning: no segments in selections file. Output will be empty timeline.")

    manifest = None
    if args.media_manifest:
        manifest = load_media_manifest(args.media_manifest)
    elif not args.media:
        print("Error: provide either --media or --media-manifest")
        return

    generate_fcpxml(segments, args.media, args.output, manifest)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate DaVinci Resolve compatible XML (xmeml 5) from rough-cut selections.

Generates XML that exactly matches DaVinci Resolve's own export format,
ensuring proper media linking on re-import.
"""
from __future__ import annotations

import json
import sys
import os
from urllib.parse import quote
from pathlib import Path


def seconds_to_frames(seconds: float, fps: int = 50) -> int:
    return round(seconds * fps)


def frames_to_tc(frames: int, fps: int = 50) -> str:
    """Convert frame count to timecode string HH:MM:SS:FF"""
    h = frames // (fps * 3600)
    frames %= fps * 3600
    m = frames // (fps * 60)
    frames %= fps * 60
    s = frames // fps
    f = frames % fps
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def escape_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def file_url(path: str) -> str:
    """Generate file:// URL matching DaVinci's own export format."""
    # DaVinci uses file:/// (three slashes, no localhost)
    return "file://" + quote(path, safe="/:")


# Video filter template (Basic Motion + Crop + Opacity) - matches DaVinci export
VIDEO_FILTERS = """                            <filter>
                                <enabled>TRUE</enabled>
                                <start>{start}</start>
                                <end>{end}</end>
                                <effect>
                                    <name>Basic Motion</name>
                                    <effectid>basic</effectid>
                                    <effecttype>motion</effecttype>
                                    <mediatype>video</mediatype>
                                    <effectcategory>motion</effectcategory>
                                    <parameter>
                                        <name>Scale</name>
                                        <parameterid>scale</parameterid>
                                        <value>100</value>
                                        <valuemin>0</valuemin>
                                        <valuemax>10000</valuemax>
                                    </parameter>
                                    <parameter>
                                        <name>Center</name>
                                        <parameterid>center</parameterid>
                                        <value>
                                            <horiz>0</horiz>
                                            <vert>0</vert>
                                        </value>
                                    </parameter>
                                    <parameter>
                                        <name>Rotation</name>
                                        <parameterid>rotation</parameterid>
                                        <value>0</value>
                                        <valuemin>-100000</valuemin>
                                        <valuemax>100000</valuemax>
                                    </parameter>
                                    <parameter>
                                        <name>Anchor Point</name>
                                        <parameterid>centerOffset</parameterid>
                                        <value>
                                            <horiz>0</horiz>
                                            <vert>0</vert>
                                        </value>
                                    </parameter>
                                </effect>
                            </filter>
                            <filter>
                                <enabled>TRUE</enabled>
                                <start>{start}</start>
                                <end>{end}</end>
                                <effect>
                                    <name>Crop</name>
                                    <effectid>crop</effectid>
                                    <effecttype>motion</effecttype>
                                    <mediatype>video</mediatype>
                                    <effectcategory>motion</effectcategory>
                                    <parameter>
                                        <name>left</name>
                                        <parameterid>left</parameterid>
                                        <value>0</value>
                                        <valuemin>0</valuemin>
                                        <valuemax>100</valuemax>
                                    </parameter>
                                    <parameter>
                                        <name>right</name>
                                        <parameterid>right</parameterid>
                                        <value>0</value>
                                        <valuemin>0</valuemin>
                                        <valuemax>100</valuemax>
                                    </parameter>
                                    <parameter>
                                        <name>top</name>
                                        <parameterid>top</parameterid>
                                        <value>0</value>
                                        <valuemin>0</valuemin>
                                        <valuemax>100</valuemax>
                                    </parameter>
                                    <parameter>
                                        <name>bottom</name>
                                        <parameterid>bottom</parameterid>
                                        <value>0</value>
                                        <valuemin>0</valuemin>
                                        <valuemax>100</valuemax>
                                    </parameter>
                                </effect>
                            </filter>
                            <filter>
                                <enabled>TRUE</enabled>
                                <start>{start}</start>
                                <end>{end}</end>
                                <effect>
                                    <name>Opacity</name>
                                    <effectid>opacity</effectid>
                                    <effecttype>motion</effecttype>
                                    <mediatype>video</mediatype>
                                    <effectcategory>motion</effectcategory>
                                    <parameter>
                                        <name>opacity</name>
                                        <parameterid>opacity</parameterid>
                                        <value>100</value>
                                        <valuemin>0</valuemin>
                                        <valuemax>100</valuemax>
                                    </parameter>
                                </effect>
                            </filter>"""

# Audio filter template
AUDIO_FILTERS = """                            <filter>
                                <enabled>TRUE</enabled>
                                <start>{start}</start>
                                <end>{end}</end>
                                <effect>
                                    <name>Audio Levels</name>
                                    <effectid>audiolevels</effectid>
                                    <effecttype>audiolevels</effecttype>
                                    <mediatype>audio</mediatype>
                                    <effectcategory>audiolevels</effectcategory>
                                    <parameter>
                                        <name>Level</name>
                                        <parameterid>level</parameterid>
                                        <value>1</value>
                                        <valuemin>1e-05</valuemin>
                                        <valuemax>31.6228</valuemax>
                                    </parameter>
                                </effect>
                            </filter>
                            <filter>
                                <enabled>TRUE</enabled>
                                <start>{start}</start>
                                <end>{end}</end>
                                <effect>
                                    <name>Audio Pan</name>
                                    <effectid>audiopan</effectid>
                                    <effecttype>audiopan</effecttype>
                                    <mediatype>audio</mediatype>
                                    <effectcategory>audiopan</effectcategory>
                                    <parameter>
                                        <name>Pan</name>
                                        <parameterid>pan</parameterid>
                                        <value>0</value>
                                        <valuemin>-1</valuemin>
                                        <valuemax>1</valuemax>
                                    </parameter>
                                </effect>
                            </filter>"""


def generate_davinci_xml(
    selections_path: str,
    output_path: str,
    media_path: str | None = None,
    fps: int = 50,
    timeline_name: str = "粗剪时间线",
) -> str:
    """Generate DaVinci Resolve XML from selection data."""

    with open(selections_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        segments = data
    else:
        segments = data.get("segments", [])
    if not segments:
        raise ValueError("No segments found in selections")

    # Group segments by source file
    source_groups: dict[str, list] = {}
    for seg in segments:
        src = seg.get("source_path", media_path or "unknown")
        if src not in source_groups:
            source_groups[src] = []
        source_groups[src].append(seg)

    # Build clip ranges per source
    # Each source file -> list of (source_start_sec, source_end_sec) ranges to keep
    clips_by_source: dict[str, list[tuple[float, float]]] = {}
    for src, segs in source_groups.items():
        ranges = []
        for seg in segs:
            src_start = seg.get("source_start_sec", seg.get("start", 0))
            src_end = seg.get("source_end_sec", seg.get("end", 0))
            ranges.append((src_start, src_end))
        # Sort and merge overlapping ranges
        ranges.sort()
        merged = []
        for start, end in ranges:
            if merged and start <= merged[-1][1] + 0.04:  # 40ms gap tolerance
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        clips_by_source[src] = merged

    # Compute total timeline duration in frames
    total_frames = 0
    clip_info = []  # (source_path, source_start_sec, source_end_sec, timeline_start_frame, timeline_end_frame)

    for src in sorted(clips_by_source.keys()):
        for src_start, src_end in clips_by_source[src]:
            dur_frames = seconds_to_frames(src_end - src_start, fps)
            clip_info.append((src, src_start, src_end, total_frames, total_frames + dur_frames))
            total_frames += dur_frames

    if total_frames == 0:
        raise ValueError("No clips to export")

    # Source file metadata - try to load from reference XML data
    # Default: estimate from segment data
    source_meta: dict[str, dict] = {}
    for src in source_groups:
        segs = source_groups[src]
        max_end = max(s.get("source_end_sec", 0) for s in segs)
        source_meta[src] = {
            "duration_frames": seconds_to_frames(max_end, fps) + fps,  # +1sec padding
            "name": os.path.basename(src),
            "path": src,
            "timecode": "",
        }

    # Load reference timeline info if available (from DaVinci export or DRT mapping)
    ref_path = os.environ.get("DAVINCI_REF_PATH", "")
    if ref_path and os.path.exists(ref_path):
        import xml.etree.ElementTree as ET
        tree = ET.parse(ref_path)
        root = tree.getroot()
        # Extract file info from reference
        for file_elem in root.iter('file'):
            fid = file_elem.get('id', '')
            fname = file_elem.findtext('name', '')
            dur = file_elem.findtext('duration', '0')
            pathurl = file_elem.findtext('pathurl', '')
            tc_elem = file_elem.find('timecode')
            tc_str = tc_elem.findtext('string', '') if tc_elem is not None else ''

            # Match to our sources by filename
            for src in source_meta:
                if os.path.basename(src) == fname:
                    source_meta[src]["duration_frames"] = int(dur)
                    source_meta[src]["timecode"] = tc_str
                    break

    # Generate XML
    xml_parts = []
    xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml_parts.append('<!DOCTYPE xmeml>')
    xml_parts.append('<xmeml version="5">')
    xml_parts.append('    <sequence>')
    xml_parts.append(f'        <name>{escape_xml(timeline_name)}</name>')
    xml_parts.append(f'        <duration>{total_frames}</duration>')
    xml_parts.append('        <rate>')
    xml_parts.append(f'            <timebase>{fps}</timebase>')
    xml_parts.append('            <ntsc>FALSE</ntsc>')
    xml_parts.append('        </rate>')
    xml_parts.append('        <in>-1</in>')
    xml_parts.append('        <out>-1</out>')
    xml_parts.append('        <timecode>')
    xml_parts.append('            <string>01:00:00:00</string>')
    xml_parts.append(f'            <frame>{180000}</frame>')
    xml_parts.append('            <displayformat>NDF</displayformat>')
    xml_parts.append('            <rate>')
    xml_parts.append(f'                <timebase>{fps}</timebase>')
    xml_parts.append('                <ntsc>FALSE</ntsc>')
    xml_parts.append('            </rate>')
    xml_parts.append('        </timecode>')
    xml_parts.append('        <media>')
    xml_parts.append('            <video>')
    xml_parts.append('                <track>')

    # Video clipitems
    clip_counter = 0
    for src, src_start, src_end, tl_start, tl_end in clip_info:
        fname = os.path.basename(src)
        dur_frames = tl_end - tl_start
        src_in_frames = seconds_to_frames(src_start, fps)
        src_out_frames = seconds_to_frames(src_end, fps)
        source_dur = source_meta[src]["duration_frames"]
        file_id = f"file_{fname}_{clip_counter}"
        clip_id_v = f"{fname} {clip_counter}"
        clip_id_a = f"{fname} {clip_counter + 1}"

        xml_parts.append(f'                    <clipitem id="{escape_xml(clip_id_v)}">')
        xml_parts.append(f'                        <name>{escape_xml(fname)}</name>')
        xml_parts.append(f'                        <duration>{source_dur}</duration>')
        xml_parts.append('                        <rate>')
        xml_parts.append(f'                            <timebase>{fps}</timebase>')
        xml_parts.append('                            <ntsc>FALSE</ntsc>')
        xml_parts.append('                        </rate>')
        xml_parts.append(f'                        <start>{tl_start}</start>')
        xml_parts.append(f'                        <end>{tl_end}</end>')
        xml_parts.append('                        <enabled>TRUE</enabled>')
        xml_parts.append(f'                        <in>{src_in_frames}</in>')
        xml_parts.append(f'                        <out>{src_out_frames}</out>')

        # Full file definition for every clipitem (DaVinci needs this for video)
        xml_parts.append(f'                        <file id="{escape_xml(file_id)}">')
        xml_parts.append(f'                            <duration>{source_dur}</duration>')
        xml_parts.append('                            <rate>')
        xml_parts.append(f'                                <timebase>{fps}</timebase>')
        xml_parts.append('                                <ntsc>FALSE</ntsc>')
        xml_parts.append('                            </rate>')
        xml_parts.append(f'                            <name>{escape_xml(fname)}</name>')
        xml_parts.append(f'                            <pathurl>{file_url(src)}</pathurl>')

        tc = source_meta[src].get("timecode", "")
        if tc:
            xml_parts.append('                            <timecode>')
            xml_parts.append(f'                                <string>{tc}</string>')
            xml_parts.append('                                <displayformat>NDF</displayformat>')
            xml_parts.append('                                <rate>')
            xml_parts.append(f'                                    <timebase>{fps}</timebase>')
            xml_parts.append('                                    <ntsc>FALSE</ntsc>')
            xml_parts.append('                                </rate>')
            xml_parts.append('                            </timecode>')

        xml_parts.append('                            <media>')
        xml_parts.append('                                <video>')
        xml_parts.append(f'                                    <duration>{source_dur}</duration>')
        xml_parts.append('                                    <samplecharacteristics>')
        xml_parts.append('                                        <width>1920</width>')
        xml_parts.append('                                        <height>1080</height>')
        xml_parts.append('                                    </samplecharacteristics>')
        xml_parts.append('                                </video>')
        xml_parts.append('                                <audio>')
        xml_parts.append('                                    <channelcount>2</channelcount>')
        xml_parts.append('                                </audio>')
        xml_parts.append('                            </media>')
        xml_parts.append('                        </file>')

        xml_parts.append('                        <compositemode>normal</compositemode>')
        xml_parts.append(VIDEO_FILTERS.format(start=tl_start, end=tl_end))

        # Link to video self + audio
        xml_parts.append('                        <link>')
        xml_parts.append(f'                            <linkclipref>{escape_xml(clip_id_v)}</linkclipref>')
        xml_parts.append('                        </link>')
        xml_parts.append('                        <link>')
        xml_parts.append(f'                            <linkclipref>{escape_xml(clip_id_a)}</linkclipref>')
        xml_parts.append('                        </link>')
        xml_parts.append('                        <comments/>')
        xml_parts.append('                    </clipitem>')
        clip_counter += 2

    xml_parts.append('                    <enabled>TRUE</enabled>')
    xml_parts.append('                    <locked>FALSE</locked>')
    xml_parts.append('                </track>')

    # Video format
    xml_parts.append('                <format>')
    xml_parts.append('                    <samplecharacteristics>')
    xml_parts.append('                        <width>1920</width>')
    xml_parts.append('                        <height>1080</height>')
    xml_parts.append('                        <pixelaspectratio>square</pixelaspectratio>')
    xml_parts.append('                        <rate>')
    xml_parts.append(f'                            <timebase>{fps}</timebase>')
    xml_parts.append('                            <ntsc>FALSE</ntsc>')
    xml_parts.append('                        </rate>')
    xml_parts.append('                        <codec>')
    xml_parts.append('                            <appspecificdata>')
    xml_parts.append('                                <appname>Final Cut Pro</appname>')
    xml_parts.append('                                <appmanufacturer>Apple Inc.</appmanufacturer>')
    xml_parts.append('                                <data>')
    xml_parts.append('                                    <qtcodec/>')
    xml_parts.append('                                </data>')
    xml_parts.append('                            </appspecificdata>')
    xml_parts.append('                        </codec>')
    xml_parts.append('                    </samplecharacteristics>')
    xml_parts.append('                </format>')
    xml_parts.append('            </video>')

    # Audio track
    xml_parts.append('            <audio>')
    xml_parts.append('                <track>')

    clip_counter = 0
    for src, src_start, src_end, tl_start, tl_end in clip_info:
        fname = os.path.basename(src)
        src_in_frames = seconds_to_frames(src_start, fps)
        src_out_frames = seconds_to_frames(src_end, fps)
        source_dur = source_meta[src]["duration_frames"]
        file_id = f"file_{fname}_{clip_counter}"
        clip_id_v = f"{fname} {clip_counter}"
        clip_id_a = f"{fname} {clip_counter + 1}"

        xml_parts.append(f'                    <clipitem id="{escape_xml(clip_id_a)}">')
        xml_parts.append(f'                        <name>{escape_xml(fname)}</name>')
        xml_parts.append(f'                        <duration>{source_dur}</duration>')
        xml_parts.append('                        <rate>')
        xml_parts.append(f'                            <timebase>{fps}</timebase>')
        xml_parts.append('                            <ntsc>FALSE</ntsc>')
        xml_parts.append('                        </rate>')
        xml_parts.append(f'                        <start>{tl_start}</start>')
        xml_parts.append(f'                        <end>{tl_end}</end>')
        xml_parts.append('                        <enabled>TRUE</enabled>')
        xml_parts.append(f'                        <in>{src_in_frames}</in>')
        xml_parts.append(f'                        <out>{src_out_frames}</out>')
        xml_parts.append(f'                        <file id="{escape_xml(file_id)}"/>')
        xml_parts.append('                        <sourcetrack>')
        xml_parts.append('                            <mediatype>audio</mediatype>')
        xml_parts.append('                            <trackindex>1</trackindex>')
        xml_parts.append('                        </sourcetrack>')
        xml_parts.append(AUDIO_FILTERS.format(start=tl_start, end=tl_end))

        # Link back to video
        xml_parts.append('                        <link>')
        xml_parts.append(f'                            <linkclipref>{escape_xml(clip_id_v)}</linkclipref>')
        xml_parts.append('                            <mediatype>video</mediatype>')
        xml_parts.append('                        </link>')
        xml_parts.append('                        <link>')
        xml_parts.append(f'                            <linkclipref>{escape_xml(clip_id_a)}</linkclipref>')
        xml_parts.append('                        </link>')
        xml_parts.append('                        <comments/>')
        xml_parts.append('                    </clipitem>')
        clip_counter += 2

    xml_parts.append('                    <enabled>TRUE</enabled>')
    xml_parts.append('                    <locked>FALSE</locked>')
    xml_parts.append('                </track>')
    xml_parts.append('            </audio>')
    xml_parts.append('        </media>')
    xml_parts.append('    </sequence>')
    xml_parts.append('</xmeml>')

    xml_content = '\n'.join(xml_parts)

    # Write output
    output_dir = os.path.dirname(output_path) or '.'
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    print(f"Generated DaVinci XML: {output_path}")
    print(f"  Total clips: {len(clip_info)}")
    print(f"  Total duration: {total_frames / fps:.1f}s ({total_frames} frames @ {fps}fps)")
    for src, ss, se, ts, te in clip_info:
        fname = os.path.basename(src)
        print(f"  - {fname}: source {ss:.1f}s-{se:.1f}s -> timeline frames {ts}-{te}")

    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("selections", help="Path to selections JSON")
    parser.add_argument("-o", "--output", default="粗剪时间线.xml", help="Output path")
    parser.add_argument("--media", default=None, help="Source media file path")
    parser.add_argument("--fps", type=int, default=50, help="Frame rate (default: 50)")
    parser.add_argument("--name", default="粗剪时间线", help="Timeline name")
    args = parser.parse_args()

    generate_davinci_xml(args.selections, args.output, args.media, args.fps, args.name)

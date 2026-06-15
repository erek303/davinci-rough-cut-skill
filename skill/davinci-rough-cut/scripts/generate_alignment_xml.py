#!/usr/bin/env python3
"""Generate DaVinci Resolve FCP7 XML for audio-video alignment.

Use a match CSV that places camera clips on a continuous WAV timeline, plus
a timecode CSV for source MP4 files. The XML structure intentionally follows
a known-good Resolve/FCP7 xmeml pattern rather than generic XML intuition.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import quote
from xml.dom import minidom

FPS = 50
WAV_FILE_RATE = 24


def child(parent: ET.Element, tag: str, text: object | None = None, **attrs: str) -> ET.Element:
    elem = ET.SubElement(parent, tag, attrs)
    if text is not None:
        elem.text = str(text)
    return elem


def add_rate(parent: ET.Element, fps: int) -> ET.Element:
    rate = child(parent, 'rate')
    child(rate, 'timebase', fps)
    child(rate, 'ntsc', 'FALSE')
    return rate


def pathurl(path: Path) -> str:
    return 'file://' + quote(str(path.resolve()), safe='/:')


def read_csv_dict(path: Path) -> List[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def load_timecodes(path: Path) -> Dict[str, str]:
    return {row['filename']: row.get('timecode', '').strip() for row in read_csv_dict(path)}


def probe_duration(path: Path) -> float:
    cmd = [
        'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
        '-of', 'csv=p=0', str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f'Could not read duration from {path}')


def load_wav_durations(audio_dir: Path, overrides: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    overrides = overrides or {}
    wavs = sorted(audio_dir.glob('*.WAV')) + sorted(audio_dir.glob('*.wav'))
    durations: Dict[str, float] = {}
    for wav in wavs:
        durations[wav.name] = overrides[wav.name] if wav.name in overrides else probe_duration(wav)
    return durations


def add_video_format(parent: ET.Element, fps: int) -> None:
    fmt = child(parent, 'format')
    sc = child(fmt, 'samplecharacteristics')
    child(sc, 'width', 3840)
    child(sc, 'height', 2160)
    child(sc, 'pixelaspectratio', 'square')
    add_rate(sc, fps)
    codec = child(sc, 'codec')
    app = child(codec, 'appspecificdata')
    child(app, 'appname', 'Final Cut Pro')
    child(app, 'appmanufacturer', 'Apple Inc.')
    data = child(app, 'data')
    child(data, 'qtcodec')


def add_basic_motion_filters(parent: ET.Element, duration_frames: int) -> None:
    f = child(parent, 'filter')
    child(f, 'enabled', 'TRUE')
    child(f, 'start', 0)
    child(f, 'end', duration_frames)
    effect = child(f, 'effect')
    child(effect, 'name', 'Basic Motion')
    child(effect, 'effectid', 'basic')
    child(effect, 'effecttype', 'motion')
    child(effect, 'mediatype', 'video')
    child(effect, 'effectcategory', 'motion')
    p = child(effect, 'parameter')
    child(p, 'name', 'Scale')
    child(p, 'parameterid', 'scale')
    child(p, 'value', 100)
    child(p, 'valuemin', 0)
    child(p, 'valuemax', 10000)
    p = child(effect, 'parameter')
    child(p, 'name', 'Center')
    child(p, 'parameterid', 'center')
    value = child(p, 'value')
    child(value, 'horiz', 0)
    child(value, 'vert', 0)
    p = child(effect, 'parameter')
    child(p, 'name', 'Rotation')
    child(p, 'parameterid', 'rotation')
    child(p, 'value', 0)
    child(p, 'valuemin', -100000)
    child(p, 'valuemax', 100000)
    p = child(effect, 'parameter')
    child(p, 'name', 'Anchor Point')
    child(p, 'parameterid', 'centerOffset')
    value = child(p, 'value')
    child(value, 'horiz', 0)
    child(value, 'vert', 0)

    f = child(parent, 'filter')
    child(f, 'enabled', 'TRUE')
    child(f, 'start', 0)
    child(f, 'end', duration_frames)
    effect = child(f, 'effect')
    child(effect, 'name', 'Crop')
    child(effect, 'effectid', 'crop')
    child(effect, 'effecttype', 'motion')
    child(effect, 'mediatype', 'video')
    child(effect, 'effectcategory', 'motion')
    for name in ['left', 'right', 'top', 'bottom']:
        p = child(effect, 'parameter')
        child(p, 'name', name)
        child(p, 'parameterid', name)
        child(p, 'value', 0)
        child(p, 'valuemin', 0)
        child(p, 'valuemax', 100)

    f = child(parent, 'filter')
    child(f, 'enabled', 'TRUE')
    child(f, 'start', 0)
    child(f, 'end', duration_frames)
    effect = child(f, 'effect')
    child(effect, 'name', 'Opacity')
    child(effect, 'effectid', 'opacity')
    child(effect, 'effecttype', 'motion')
    child(effect, 'mediatype', 'video')
    child(effect, 'effectcategory', 'motion')
    p = child(effect, 'parameter')
    child(p, 'name', 'opacity')
    child(p, 'parameterid', 'opacity')
    child(p, 'value', 100)
    child(p, 'valuemin', 0)
    child(p, 'valuemax', 100)


def add_audio_filters(parent: ET.Element, duration_frames: int) -> None:
    f = child(parent, 'filter')
    child(f, 'enabled', 'TRUE')
    child(f, 'start', 0)
    child(f, 'end', duration_frames)
    effect = child(f, 'effect')
    child(effect, 'name', 'Audio Levels')
    child(effect, 'effectid', 'audiolevels')
    child(effect, 'effecttype', 'audiolevels')
    child(effect, 'mediatype', 'audio')
    child(effect, 'effectcategory', 'audiolevels')
    p = child(effect, 'parameter')
    child(p, 'name', 'Level')
    child(p, 'parameterid', 'level')
    child(p, 'value', 1)
    child(p, 'valuemin', '1e-05')
    child(p, 'valuemax', '31.6228')

    f = child(parent, 'filter')
    child(f, 'enabled', 'TRUE')
    child(f, 'start', 0)
    child(f, 'end', duration_frames)
    effect = child(f, 'effect')
    child(effect, 'name', 'Audio Pan')
    child(effect, 'effectid', 'audiopan')
    child(effect, 'effecttype', 'audiopan')
    child(effect, 'mediatype', 'audio')
    child(effect, 'effectcategory', 'audiopan')
    p = child(effect, 'parameter')
    child(p, 'name', 'Pan')
    child(p, 'parameterid', 'pan')
    child(p, 'value', 0)
    child(p, 'valuemin', -1)
    child(p, 'valuemax', 1)


def add_video_clip(track: ET.Element, row: dict, video_dir: Path, timecode: str, fps: int, ordinal: int) -> None:
    filename = row['filename']
    duration_frames = round(float(row['duration']) * fps)
    start = round(float(row['wav_time_sec']) * fps)
    end = start + duration_frames
    video_id = f'{filename} {ordinal * 2}'
    audio_id = f'{filename} {ordinal * 2 + 1}'

    clip = child(track, 'clipitem', id=video_id)
    child(clip, 'name', filename)
    child(clip, 'duration', duration_frames)
    add_rate(clip, fps)
    child(clip, 'start', start)
    child(clip, 'end', end)
    child(clip, 'enabled', 'TRUE')
    child(clip, 'in', 0)
    child(clip, 'out', duration_frames)
    file_elem = child(clip, 'file', id=audio_id)
    child(file_elem, 'duration', duration_frames)
    add_rate(file_elem, fps)
    child(file_elem, 'name', filename)
    child(file_elem, 'pathurl', pathurl(video_dir / filename))
    tc = child(file_elem, 'timecode')
    child(tc, 'string', timecode)
    child(tc, 'displayformat', 'NDF')
    add_rate(tc, fps)
    media = child(file_elem, 'media')
    video = child(media, 'video')
    child(video, 'duration', duration_frames)
    sc = child(video, 'samplecharacteristics')
    child(sc, 'width', 3840)
    child(sc, 'height', 2160)
    audio = child(media, 'audio')
    child(audio, 'channelcount', 2)
    child(clip, 'compositemode', 'normal')
    add_basic_motion_filters(clip, duration_frames)
    link = child(clip, 'link')
    child(link, 'linkclipref', video_id)
    link = child(clip, 'link')
    child(link, 'linkclipref', audio_id)
    child(clip, 'comments')


def add_camera_audio_clip(track: ET.Element, row: dict, fps: int, ordinal: int) -> None:
    filename = row['filename']
    duration_frames = round(float(row['duration']) * fps)
    start = round(float(row['wav_time_sec']) * fps)
    end = start + duration_frames
    video_id = f'{filename} {ordinal * 2}'
    audio_id = f'{filename} {ordinal * 2 + 1}'

    clip = child(track, 'clipitem', id=audio_id)
    child(clip, 'name', filename)
    child(clip, 'duration', duration_frames)
    add_rate(clip, fps)
    child(clip, 'start', start)
    child(clip, 'end', end)
    child(clip, 'enabled', 'TRUE')
    child(clip, 'in', 0)
    child(clip, 'out', duration_frames)
    child(clip, 'file', id=audio_id)
    source = child(clip, 'sourcetrack')
    child(source, 'mediatype', 'audio')
    child(source, 'trackindex', 1)
    add_audio_filters(clip, duration_frames)
    link = child(clip, 'link')
    child(link, 'linkclipref', video_id)
    child(link, 'mediatype', 'video')
    link = child(clip, 'link')
    child(link, 'linkclipref', audio_id)
    child(clip, 'comments')


def add_wav_clip(track: ET.Element, wav_path: Path, timeline_start: int, clip_frames: int, seq_duration: int, fps: int) -> None:
    filename = wav_path.name
    clip = child(track, 'clipitem', id=f'{filename} 0')
    child(clip, 'name', filename)
    child(clip, 'duration', seq_duration)
    add_rate(clip, fps)
    child(clip, 'start', timeline_start)
    child(clip, 'end', timeline_start + clip_frames)
    child(clip, 'enabled', 'TRUE')
    child(clip, 'in', 0)
    child(clip, 'out', clip_frames)
    file_elem = child(clip, 'file', id=f'{filename} 1')
    child(file_elem, 'duration', round((clip_frames / fps) * WAV_FILE_RATE))
    rate = child(file_elem, 'rate')
    child(rate, 'timebase', WAV_FILE_RATE)
    child(rate, 'ntsc', 'FALSE')
    child(file_elem, 'name', filename)
    child(file_elem, 'pathurl', pathurl(wav_path))
    media = child(file_elem, 'media')
    audio = child(media, 'audio')
    child(audio, 'channelcount', 1)
    source = child(clip, 'sourcetrack')
    child(source, 'mediatype', 'audio')
    child(source, 'trackindex', 1)
    add_audio_filters(clip, clip_frames)
    child(clip, 'comments')


def select_rows(matches: Iterable[dict], timecodes: Dict[str, str], video_dir: Path, min_ncc: float, selected_names: Optional[Set[str]]) -> tuple[List[dict], List[dict]]:
    included: List[dict] = []
    audit: List[dict] = []
    for row in matches:
        filename = row['filename']
        ncc = float(row.get('ncc') or 0)
        status = 'included'
        if selected_names is not None and filename not in selected_names:
            status = 'excluded_not_selected'
        elif ncc < min_ncc:
            status = 'excluded_low_ncc'
        elif not timecodes.get(filename):
            status = 'excluded_missing_timecode'
        elif not (video_dir / filename).exists():
            status = 'excluded_missing_video_file'
        row_copy = dict(row)
        row_copy['status'] = status
        row_copy['has_timecode'] = 'yes' if timecodes.get(filename) else 'no'
        row_copy['video_path_exists'] = 'yes' if (video_dir / filename).exists() else 'no'
        row_copy['start_frame'] = str(round(float(row.get('wav_time_sec') or 0) * FPS))
        row_copy['end_frame'] = str(round((float(row.get('wav_time_sec') or 0) + float(row.get('duration') or 0)) * FPS))
        audit.append(row_copy)
        if status == 'included':
            included.append(row)
    included.sort(key=lambda r: float(r['wav_time_sec']))
    return included, audit


def write_audit(path: Path, rows: List[dict]) -> None:
    base_fields = ['filename', 'duration', 'timecode', 'wav_time_sec', 'wav_time_min', 'ncc', 'peak_ratio']
    extra_fields = ['status', 'has_timecode', 'video_path_exists', 'start_frame', 'end_frame']
    fields = [f for f in base_fields if any(f in row for row in rows)] + extra_fields
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def generate_xml(
    matches_csv: Path,
    timecodes_csv: Path,
    video_dir: Path,
    audio_dir: Path,
    output_xml: Path,
    audit_csv: Path,
    project_name: str,
    min_ncc: float,
    selected_names: Optional[Set[str]],
    fps: int,
    wav_durations: Optional[Dict[str, float]] = None,
) -> None:
    matches = read_csv_dict(matches_csv)
    timecodes = load_timecodes(timecodes_csv)
    included, audit_rows = select_rows(matches, timecodes, video_dir, min_ncc, selected_names)
    wav_duration_map = load_wav_durations(audio_dir, wav_durations)
    wav_files = [audio_dir / name for name in sorted(wav_duration_map)]
    wav_frames = {name: round(sec * fps) for name, sec in wav_duration_map.items()}
    total_wav_frames = sum(wav_frames.values())
    last_video_frame = max((round((float(r['wav_time_sec']) + float(r['duration'])) * fps) for r in included), default=0)
    seq_duration = max(total_wav_frames, last_video_frame)

    root = ET.Element('xmeml', version='5')
    seq = child(root, 'sequence')
    child(seq, 'name', project_name)
    child(seq, 'duration', seq_duration)
    add_rate(seq, fps)
    child(seq, 'in', -1)
    child(seq, 'out', -1)
    tc = child(seq, 'timecode')
    child(tc, 'string', '01:00:00:00')
    child(tc, 'frame', 3600 * fps)
    child(tc, 'displayformat', 'NDF')
    add_rate(tc, fps)
    media = child(seq, 'media')
    video = child(media, 'video')
    video_track = child(video, 'track')
    for ordinal, row in enumerate(included):
        add_video_clip(video_track, row, video_dir, timecodes[row['filename']], fps, ordinal)
    add_video_format(video, fps)
    audio = child(media, 'audio')
    camera_track = child(audio, 'track')
    for ordinal, row in enumerate(included):
        add_camera_audio_clip(camera_track, row, fps, ordinal)
    child(camera_track, 'enabled', 'TRUE')
    child(camera_track, 'locked', 'FALSE')
    wav_track = child(audio, 'track')
    cursor = 0
    for wav in wav_files:
        frames = wav_frames[wav.name]
        add_wav_clip(wav_track, wav, cursor, frames, seq_duration, fps)
        cursor += frames
    child(wav_track, 'enabled', 'TRUE')
    child(wav_track, 'locked', 'FALSE')

    output_xml.parent.mkdir(parents=True, exist_ok=True)
    raw = ET.tostring(root, encoding='utf-8')
    pretty = minidom.parseString(raw).toprettyxml(indent='    ', encoding='UTF-8')
    text = pretty.decode('utf-8').replace('<?xml version="1.0" encoding="UTF-8"?>', '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>', 1)
    output_xml.write_text(text, encoding='utf-8')
    write_audit(audit_csv, audit_rows)


def parse_selected(value: Optional[str]) -> Optional[Set[str]]:
    if not value:
        return None
    return {item.strip() for item in value.split(',') if item.strip()}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Generate DaVinci xmeml from an audio-video match CSV.')
    parser.add_argument('--matches', type=Path, required=True, help='CSV with filename,duration,wav_time_sec,ncc columns.')
    parser.add_argument('--timecodes', type=Path, required=True, help='CSV with filename,timecode columns.')
    parser.add_argument('--video-dir', type=Path, required=True, help='Directory containing source MP4 files.')
    parser.add_argument('--audio-dir', type=Path, required=True, help='Directory containing continuous WAV files.')
    parser.add_argument('--output', type=Path, required=True, help='Output DaVinci/FCP7 xmeml path.')
    parser.add_argument('--audit', type=Path, required=True, help='Output audit CSV path.')
    parser.add_argument('--project-name', default='Audio Video Alignment')
    parser.add_argument('--min-ncc', type=float, default=0.5)
    parser.add_argument('--selected', help='Comma-separated filenames for a small test XML.')
    parser.add_argument('--fps', type=int, default=FPS)
    args = parser.parse_args(argv)

    generate_xml(
        matches_csv=args.matches,
        timecodes_csv=args.timecodes,
        video_dir=args.video_dir,
        audio_dir=args.audio_dir,
        output_xml=args.output,
        audit_csv=args.audit,
        project_name=args.project_name,
        min_ncc=args.min_ncc,
        selected_names=parse_selected(args.selected),
        fps=args.fps,
    )
    print(f'Wrote {args.output}')
    print(f'Wrote {args.audit}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

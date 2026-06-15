# Audio-Video Alignment Workflow

Use when source footage has camera audio and separate continuous recorder WAVs, and the goal is a DaVinci Resolve timeline with camera clips aligned on top of the recorder audio.

## Core Rule

Do not mix failure layers. Classify the problem first:

| Layer | Evidence | Fix surface |
|---|---|---|
| Audio matching | NCC low, non-monotonic positions, wrong clip time | matching algorithm / CSV |
| XML structure | Resolve import fails, empty timeline, crashes | xmeml structure |
| Media linking | offline media, path/timecode warnings | pathurl / file timecode |
| Timeline layout | wrong tracks, WAVs overlap, clips offset | start/end, track layout |

Only change one layer per iteration.

## Proven Pattern

1. Build or load a match CSV with: `filename,duration,wav_time_sec,ncc`.
2. Build or load a timecode CSV with: `filename,timecode`.
3. Generate a small sample XML first, using 3-6 high-confidence clips from early/mid/late positions.
4. Import the sample XML into Resolve and verify linking + sync.
5. Generate full XML only after the sample passes.
6. Keep an audit CSV for every generated XML.

## Matching Guidance

- Prefer direct FFT correlation on downsampled 8000 Hz mono audio when the camera audio and recorder audio came from the same microphone path but differ by codec/wireless encoding.
- Avoid using file `mtime` or `creation_time` for precision alignment; they are at best rough clues.
- Filter low-confidence rows. Start conservative (`ncc >= 0.9`) for sample XML; relax only after structure is proven.

## Commands

Generate a sample XML:

```bash
python3 ~/.agents/skills/davinci-rough-cut/scripts/generate_alignment_xml.py \
  --matches /path/to/匹配报告.csv \
  --timecodes /path/to/timecodes.csv \
  --video-dir /path/to/mp4_dir \
  --audio-dir /path/to/wav_dir \
  --output /path/to/alignment_sample.xml \
  --audit /path/to/alignment_sample_audit.csv \
  --selected C2851.MP4,C2900.MP4,C3000.MP4 \
  --project-name "alignment_sample" \
  --fps 50 \
  --min-ncc 0.5
```

Generate full XML:

```bash
python3 ~/.agents/skills/davinci-rough-cut/scripts/generate_alignment_xml.py \
  --matches /path/to/匹配报告.csv \
  --timecodes /path/to/timecodes.csv \
  --video-dir /path/to/mp4_dir \
  --audio-dir /path/to/wav_dir \
  --output /path/to/alignment_full.xml \
  --audit /path/to/alignment_full_audit.csv \
  --project-name "alignment_full" \
  --fps 50 \
  --min-ncc 0.5
```

## Resolve Import Check

After importing sample XML:

- If all clips share the same sync offset, add a global offset option to the generator or adjust `wav_time_sec` upstream.
- If only some clips are wrong, inspect audit CSV and raise `--min-ncc` or exclude specific clips.
- If files are offline, inspect `<pathurl>` and MP4 `<timecode>` values.
- If XML imports empty or crashes, compare generated xmeml against a known-good Resolve export before changing match data.

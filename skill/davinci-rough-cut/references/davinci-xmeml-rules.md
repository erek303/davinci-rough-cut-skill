# DaVinci FCP7 xmeml Rules

Resolve accepts XML that is syntactically valid but still semantically fragile. When a Resolve-exported or previously importable XML exists, treat it as the gold sample.

## Required Structure

- Root: `<xmeml version="5">` with `<!DOCTYPE xmeml>`.
- Sequence includes `<duration>`, `<rate>`, `<in>-1</in>`, `<out>-1</out>`, and sequence `<timecode>`.
- `<media>` contains sibling `<video>` and `<audio>` sections.
- In `<video>`, place `<track>` before `<format>`.
- Use one video track for camera picture, one audio track for camera audio, one audio track for continuous WAV recorder audio.

## Clip Rules

Video clipitem:

- Has `id="FILENAME evenNumber"`.
- Contains full `<file id="FILENAME oddNumber">` definition.
- File includes `<pathurl>`, real source `<timecode>`, video sample characteristics, and audio channel count.
- Contains `Basic Motion`, `Crop`, and `Opacity` filters with `enabled/start/end`.
- Contains two separate `<link>` blocks: one to video clip id, one to camera audio clip id.

Camera audio clipitem:

- Has `id="FILENAME oddNumber"` matching the video clip's file id.
- Uses self-closing `<file id="FILENAME oddNumber"/>` reference.
- Contains `<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>`.
- The link to the video clip includes `<mediatype>video</mediatype>`.

Recorder WAV clipitem:

- All WAVs belong on one audio track, placed end-to-end.
- Do not put each WAV on a separate track.
- Use channel count 1 for mono recorder WAVs when applicable.

## Path and Timecode Rules

- Use `<pathurl>`, not `<fileurl>`.
- Use `file://` plus URL-encoded paths for Chinese characters and spaces.
- MP4 file definitions must contain real source timecode. Do not use fake `01:00:00:00` source timecode.
- Some cameras store timecode on a timed metadata stream; `ffprobe -select_streams v:0` can miss it. Extract all stream timecode tags and choose the actual source timecode.

## Timeline Start Caution

Do not blindly add the sequence timecode frame (for example 180000 for `01:00:00:00`) to every clip `start/end`. In known-good Resolve xmeml examples, clip `start/end` can be sequence-relative frames while sequence timecode controls display timecode.

## Static Validation Checklist

Before telling the user to import into Resolve, verify:

- XML parses.
- video clip count equals camera audio clip count.
- recorder WAV track has expected WAV count.
- every included MP4 has a file timecode.
- every pathurl decodes to an existing local file.
- video clip `start/end` values are monotonic and non-overlapping.
- generated audit CSV explains included and excluded rows.

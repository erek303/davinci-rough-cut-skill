# Alignment Debugging Pattern

This pattern preserves the reusable repair logic from a real alignment project
without bundling any project names, media paths, clip names, device names, or
private durations.

## Situation

- Continuous recorder audio spans the whole shoot or recording session.
- Camera clips are fragmented and each clip also has camera scratch audio.
- The goal is a DaVinci Resolve timeline with camera clips aligned above the
  continuous recorder audio.

## What Usually Works

- Treat a Resolve-exported or previously importable XML as the known-good
  structure sample.
- Treat a high-confidence match CSV as the known-good position source.
- Combine the known-good XML structure with the known-good match positions.
- Generate a small sample XML first, then generate the full XML only after
  Resolve verifies media linking and sync.

## Important Correction

Do not blindly add the sequence timecode frame offset to every clip
`start` / `end`. In known-good Resolve xmeml examples, clip `start` / `end`
can be sequence-relative frames while sequence timecode controls display
timecode.

## Reusable Repair Order

1. Classify the failure layer: matching, XML structure, media linking, or
   timeline layout.
2. Change only one layer per iteration.
3. Build a 3-6 clip sample from early, middle, and late positions.
4. Import the sample into Resolve and verify linking plus sync.
5. Keep an audit CSV for both sample and full exports.

## Verification Before Full Export

- The sample XML parses.
- The sample imports in Resolve.
- Video and camera-audio clip counts match.
- Recorder audio appears on the intended audio track.
- The audit CSV explains skipped or low-confidence clips.

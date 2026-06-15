# DaVinci Rough Cut Skill User Manual

This manual is for editors and operators who want a repeatable Agent-assisted rough-cut workflow for DaVinci Resolve.

## Mental Model

The skill does not generate new voice, synthesize footage, or make the final edit. It helps produce a first rough-cut timeline from existing source material.

Two stable workflows are supported:

- **Transcript-guided rough cut**: audio + Resolve reference XML -> ASR -> AI keep/delete suggestions -> human review panel -> Resolve XML timeline.
- **Audio-video alignment**: fragmented camera MP4 clips + continuous recorder WAV -> sample Resolve XML -> verified full synchronized XML.

The original media stays on disk. The exported XML references those original files.

## Agent Commands

Use these commands with the Agent where the skill is already installed:

```text
/davinci-rough-cut
```

Default router. Use this when you are not sure which workflow you need.

```text
/davinci-rough-cut rough-cut
```

Transcript-guided rough cut. Use this when you have Resolve-exported audio and a reference FCP7 XML, and you want ASR, AI keep/delete suggestions, a browser review panel, and a Resolve rough-cut timeline.

```text
/davinci-rough-cut align
```

Audio-video alignment. Use this when you have camera MP4 files, continuous recorder WAV files, `matches.csv`, and `timecodes.csv`.

```text
/davinci-rough-cut update
```

Update the installed skill without asking for the repository URL again.

Installation is a first-time setup action, not a normal installed-skill command. If the skill is not installed yet, use the Agent-neutral install prompt in the root README. Installation should target the skill directory used by the current Agent. Do not default to Codex paths.

## Runtime Services And Secrets

The public package does not include private keys, hosted ASR access, or a bundled LLM account. Keep real keys in local environment variables, a shell profile, a system keychain, or an uncommitted `.env`. Do not paste real API keys into an agent chat.

### ASR Key

Recommended default: Volcengine audio-file fast mode.

```bash
export VOLCENGINE_API_KEY="your-volcengine-api-key"
```

Legacy auth:

```bash
export VOLCENGINE_APP_ID="your-volcengine-app-id"
export VOLCENGINE_ACCESS_TOKEN="your-volcengine-access-token"
```

Fast mode sends local audio data directly to the ASR API. Ordinary users do not need TOS object storage or a private bucket.

Only use this advanced legacy URL mode if you explicitly need it:

```bash
export VOLCENGINE_ASR_MODE="standard-url"
export VOLCENGINE_ACCESS_KEY="your-volcengine-iam-access-key"
export VOLCENGINE_SECRET_KEY="your-volcengine-iam-secret-key"
export VOLCENGINE_TOS_BUCKET="your-tos-bucket"
export VOLCENGINE_TOS_REGION="cn-shanghai"
```

### LLM Key

Configure at least one keep/delete backend:

```bash
export GLM_API_KEY="your-glm-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export MIMO_API_KEY="your-xiaomi-mimo-api-key"
# or export XIAOMI_API_KEY="your-xiaomi-mimo-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

Optionally force one backend:

```bash
export AI_EDIT_BACKEND="deepseek"  # glm / deepseek / mimo / anthropic
```

Xiaomi MiMo `mimo-v2.5-asr` is available for short-audio experiments, but the recommended long-form rough-cut ASR path is Volcengine fast mode.

## Workflow A: Transcript-Guided Rough Cut

Use this for long video, multi-clip spoken material, podcast, documentary footage, talking-head material, or other speech-heavy source material where you want a content-based first cut.

### A1. Prepare Files in DaVinci Resolve

Do not start with only a folder of source videos. A video folder does not contain the timeline-to-source mapping that the XML generator needs.

From the original Resolve timeline:

1. Export audio as `MP3` or `WAV`.
2. Export the timeline as `FCP 7 XML`.

Recommended working folder:

```text
my-project/
├── audio.wav
├── reference.xml
├── context.md
└── work/
```

Operator prompt template:

```text
/davinci-rough-cut rough-cut

Please make a transcript-guided rough cut.
Audio export: /path/to/audio.wav
Reference FCP7 XML: /path/to/reference.xml
Project context: /path/to/context.md
Work folder: /path/to/work
FPS: 50
Goal: keep the strongest material for a first rough cut.
```

### A2. Transcribe Audio

```bash
SKILL="${DAVINCI_ROUGH_CUT_SKILL_DIR:-/path/to/installed/davinci-rough-cut}"
PY="$SKILL/.venv/bin/python"

"$PY" "$SKILL/scripts/volcengine_asr.py" \
  /path/to/my-project/audio.wav \
  -o /path/to/my-project/work/transcript.json
```

Use the legacy URL/TOS mode only when required:

```bash
"$PY" "$SKILL/scripts/volcengine_asr.py" \
  /path/to/my-project/audio.wav \
  --mode standard-url \
  -o /path/to/my-project/work/transcript.json
```

### A3. Run AI Editing

```bash
"$PY" "$SKILL/scripts/ai_edit_transcript.py" \
  /path/to/my-project/work/transcript.json \
  -o /path/to/my-project/work/edited.json \
  --context /path/to/my-project/context.md
```

The AI adds:

- `ai_action`: `keep` or `delete`
- `ai_reason`: why that sentence helps or does not help the rough cut

Write `context.md` like a short editor brief:

```markdown
# Project Context

Audience:
Main story:
What must stay:
What can be removed:
Tone:
Target length:
```

### A4. Review In Browser

```bash
"$PY" "$SKILL/scripts/web_editor.py" \
  --transcript /path/to/my-project/work/transcript.json \
  --edited /path/to/my-project/work/edited.json \
  --audio /path/to/my-project/audio.wav \
  --davinci-ref /path/to/my-project/reference.xml \
  --fps 50 \
  --port 5001
```

Open `http://localhost:5001`.

Review actions:

- Click a sentence to play that part of the audio.
- Right-click a sentence to toggle keep/delete.
- Review AI reasons before trusting the cut.
- Export the DaVinci XML after review.

### A5. Import Into DaVinci Resolve

In Resolve:

1. File -> Import -> Timeline
2. Choose the exported XML.
3. If Resolve asks for media relink, point it to the original media folder.
4. Check the first, middle, and last clips before continuing to fine cut.

## Mandatory Review Panel Rule

For transcript-guided rough cuts, the browser review panel is mandatory unless the user explicitly says to skip manual review.

Do not jump directly from `transcript.json` / `edited.json` to `rough_cut.xml`. That skips the core human review step. If the panel does not appear, report the exact command and error instead of silently generating XML.

## Workflow B: Audio-Video Alignment

Use this when you have:

- continuous external recorder WAV files
- camera MP4 clips with scratch audio
- a match CSV that says where each MP4 appears on the WAV timeline
- a timecode CSV with real camera source timecode

This workflow does not require ASR or an LLM if the CSV inputs are ready.

### B1. Input CSVs

`matches.csv` must include:

```csv
filename,duration,wav_time_sec,ncc
C0001.MP4,31.68,85.9,0.9924
```

`timecodes.csv` must include:

```csv
filename,timecode
C0001.MP4,19:13:18:38
```

### B2. Generate Sample XML First

```bash
"$PY" "$SKILL/scripts/generate_alignment_xml.py" \
  --matches /path/to/matches.csv \
  --timecodes /path/to/timecodes.csv \
  --video-dir /path/to/mp4_dir \
  --audio-dir /path/to/wav_dir \
  --output /path/to/alignment_sample.xml \
  --audit /path/to/alignment_sample_audit.csv \
  --selected C0001.MP4,C0050.MP4,C0100.MP4 \
  --project-name "alignment_sample" \
  --fps 50 \
  --min-ncc 0.5
```

Import the sample into Resolve and verify:

- media links correctly
- MP4 picture and camera audio stay together
- external WAV appears on a separate audio track
- sync is correct in early, middle, and late clips

### B3. Generate Full XML

```bash
"$PY" "$SKILL/scripts/generate_alignment_xml.py" \
  --matches /path/to/matches.csv \
  --timecodes /path/to/timecodes.csv \
  --video-dir /path/to/mp4_dir \
  --audio-dir /path/to/wav_dir \
  --output /path/to/alignment_full.xml \
  --audit /path/to/alignment_full_audit.csv \
  --project-name "alignment_full" \
  --fps 50 \
  --min-ncc 0.5
```

Do not skip the sample step. Resolve XML is structurally fragile, and small samples make mistakes cheaper.

## Troubleshooting

### XML imports but media is offline

Check that original files have not moved. Resolve XML stores file paths. If needed, relink media manually in Resolve.

### AI deletes too much

Improve the context file. Explain the story, audience, must-keep moments, and target output. The review panel is the final authority.

### ASR fails before processing

Check:

- `VOLCENGINE_API_KEY` is exported in the same terminal session
- audio path is local and readable
- FFmpeg/ffprobe are installed
- if using `--mode standard-url`, TOS variables and bucket permissions are configured

### Browser panel starts but export is wrong

Confirm `--davinci-ref` points to the original Resolve FCP7 XML, and `--fps` matches the Resolve project.

## Stable vs Experimental

The stable public path is the explicit script workflow documented above.

A one-command dashboard can be added later, but it should not replace the stable workflow until it embeds the existing review panel and export path end to end.

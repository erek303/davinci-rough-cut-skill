---
name: davinci-rough-cut
description: Use when the user says /davinci-rough-cut, /davinci-rough-cut update, /davinci-rough-cut rough-cut, /davinci-rough-cut align, rough cut, 粗剪, DaVinci Resolve XML, Resolve timeline export, transcript-based video editing, or wants to align camera MP4 clips with separate recorder WAV audio.
---

# DaVinci Rough Cut

Use this skill for DaVinci Resolve rough-cut workflows that turn speech-heavy source material into reviewable transcript decisions and Resolve-importable XML timelines.

## Choose the Workflow

Recognized chat commands:

- `/davinci-rough-cut`: default router; choose the right workflow from the user's files and goal.
- `/davinci-rough-cut update`: update the installed skill without asking for the repository URL again.
- `/davinci-rough-cut rough-cut`: run Workflow A.
- `/davinci-rough-cut align`: run Workflow B.

Use **Workflow A: Transcript-Guided Rough Cut** when the user has long video, multi-clip spoken material, podcast, documentary, talking-head, or other speech-heavy source material and wants AI-assisted keep/delete decisions from the transcript.

Use **Workflow B: Audio-Video Alignment** when the user has camera MP4 clips plus separate continuous recorder WAV files and needs a Resolve timeline with the clips synchronized to the WAV track.

If the user asks for a one-command dashboard, explain that the stable path is currently the explicit script workflow. Do not rely on an unverified dashboard unless it has been tested in the current environment.

## Runtime Requirements and Secret Handling

This public skill does not include API keys, ASR access, or an LLM account. Before running Workflow A, verify the local environment has:

- ASR auth: `VOLCENGINE_API_KEY`, or `VOLCENGINE_APP_ID` plus `VOLCENGINE_ACCESS_TOKEN`
- AI editing auth: `GLM_API_KEY`, `DEEPSEEK_API_KEY`, `MIMO_API_KEY` / `XIAOMI_API_KEY`, or `ANTHROPIC_API_KEY`
- `ffmpeg` and `ffprobe`

Do not ask the user to paste real API keys into chat. If keys are missing, tell the user which environment variables to set locally and stop before ASR or AI editing. Never print, commit, or upload secrets.

Use Volcengine ASR fast mode as the default for long rough-cut audio. It sends local audio data directly to the ASR API and only needs ASR auth. TOS object storage is an advanced legacy URL mode, not the ordinary setup path. Xiaomi MiMo `mimo-v2.5-asr` is available through `scripts/mimo_asr.py` and `transcribe.py --provider mimo`, but only as a short-audio fallback because the documented request sends wav/mp3 as base64 with a 10MB payload limit.

## Updating This Skill

Canonical chat command:

```text
/davinci-rough-cut update
```

When the user sends `/davinci-rough-cut update`, treat it as an Agent instruction, not as a shell path. Do not ask them to paste the repository URL again. Run the installed updater directly. If both Codex and Agents installs exist, update both installed copies:

```bash
updated=0
for skill_dir in \
  "${DAVINCI_ROUGH_CUT_SKILL_DIR:-}" \
  "$HOME/.codex/skills/davinci-rough-cut" \
  "$HOME/.agents/skills/davinci-rough-cut" \
  "$HOME/.claude/skills/davinci-rough-cut" \
  "$HOME/.newmax/skills/davinci-rough-cut"; do
  if [ -n "$skill_dir" ] && [ -x "$skill_dir/update.sh" ]; then
    bash "$skill_dir/update.sh"
    updated=1
  fi
done
if [ "$updated" -eq 0 ] && command -v davinci-rough-cut-update >/dev/null 2>&1; then
  davinci-rough-cut-update
fi
```

Other agents may install skills outside Codex paths. Prefer this order when locating the installed skill:

1. The current skill directory, if the agent exposes it.
2. `davinci-rough-cut-update` on `PATH`.
3. `DAVINCI_ROUGH_CUT_SKILL_DIR`.
4. Common skill roots: `~/.codex/skills`, `~/.agents/skills`, `~/.claude/skills`, `~/.newmax/skills`.

If the user asks to update this skill, do not ask them to copy the repository URL again. Prefer the stable launcher:

```bash
davinci-rough-cut-update
```

If the launcher is not on `PATH`, run `update.sh` from the current installed skill directory:

```bash
bash /path/to/installed/davinci-rough-cut/update.sh
```

The updater fetches the latest public GitHub package, runs the offline test suite by default, prunes stale packaged files, repairs the stable launcher when possible, and then syncs packaged skill files while preserving local `.venv`, `.env`, `work`, and `output` folders. If the update script is missing because the user has an older install, clone `https://github.com/erek303/davinci-rough-cut-skill.git` once, run `bash install.sh --target auto`, then future updates can use `update.sh`.

## Mandatory Review Panel Rule

For Workflow A, the review panel is a core feature, not an optional extra. After transcription and AI keep/delete decisions finish, you must start `scripts/web_editor.py` and give the user the local URL, normally `http://localhost:5001`.

Do not generate or hand off a final DaVinci XML directly after ASR/AI unless the user explicitly says to skip manual review. If the panel fails to start, stop and report the exact command and error. A rough-cut result that skips the review panel is incomplete.

## Input Contract

For Workflow A, a raw video folder alone is insufficient. Ask for the Resolve audio export and the Resolve FCP 7 XML export before running the rough-cut flow, unless the user only wants a command template.

Required mapping rule: ASR timestamps must be mapped through the Resolve reference XML back to original media. The media folder can help Resolve relink files later, but it does not replace the reference XML.

## Workflow A: Transcript-Guided Rough Cut

Required inputs:

- Resolve audio export: `MP3` or `WAV`
- Resolve reference timeline export: FCP 7 XML
- Optional project context: file path or short editor brief
- Correct FPS for the Resolve project

Run from the installed skill directory. Prefer the current skill directory if the Agent exposes it; otherwise use `DAVINCI_ROUGH_CUT_SKILL_DIR` or the path printed by `install.sh`:

```bash
SKILL="${DAVINCI_ROUGH_CUT_SKILL_DIR:-/path/to/installed/davinci-rough-cut}"
PY="$SKILL/.venv/bin/python"
```

Optional local preflight:

```bash
python3 - <<'PY'
import os, shutil
asr_ok = bool(os.getenv("VOLCENGINE_API_KEY")) or (
    bool(os.getenv("VOLCENGINE_APP_ID")) and bool(os.getenv("VOLCENGINE_ACCESS_TOKEN"))
)
llm_ok = any(os.getenv(k) for k in ("GLM_API_KEY", "DEEPSEEK_API_KEY", "MIMO_API_KEY", "XIAOMI_API_KEY", "ANTHROPIC_API_KEY"))
tool_missing = [x for x in ("ffmpeg", "ffprobe") if not shutil.which(x)]
missing = tool_missing
if not asr_ok:
    missing.append("VOLCENGINE_API_KEY or VOLCENGINE_APP_ID + VOLCENGINE_ACCESS_TOKEN")
if not llm_ok:
    missing.append("GLM_API_KEY or DEEPSEEK_API_KEY or MIMO_API_KEY/XIAOMI_API_KEY or ANTHROPIC_API_KEY")
print("OK" if not missing else "Missing: " + ", ".join(missing))
PY
```

1. Transcribe:

```bash
"$PY" "$SKILL/scripts/volcengine_asr.py" \
  /path/to/audio.wav \
  -o /path/to/work/transcript.json
```

2. Ask AI to mark keep/delete:

```bash
"$PY" "$SKILL/scripts/ai_edit_transcript.py" \
  /path/to/work/transcript.json \
  -o /path/to/work/edited.json \
  --context /path/to/context.md
```

3. Start the review panel:

```bash
"$PY" "$SKILL/scripts/web_editor.py" \
  --transcript /path/to/work/transcript.json \
  --edited /path/to/work/edited.json \
  --audio /path/to/audio.wav \
  --davinci-ref /path/to/reference.xml \
  --fps 50 \
  --port 5001
```

4. Open `http://localhost:5001`, review decisions, export XML, and import it into Resolve.

Key behavior: the AI does not rewrite or synthesize footage. It marks original spoken segments as keep/delete. The exported XML references original media.

## Workflow B: Audio-Video Alignment

Read `references/audio-video-alignment.md` and `references/davinci-xmeml-rules.md` before generating XML.

Required inputs:

- `matches.csv` with `filename,duration,wav_time_sec,ncc`
- `timecodes.csv` with `filename,timecode`
- camera MP4 directory
- recorder WAV directory

Always generate and import a small sample before generating the full XML:

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

After Resolve verifies sample linking and sync, generate the full XML by removing `--selected`.

## Validation Before Handoff

Before telling the user the result is ready:

- Verify the XML parses.
- Verify referenced paths exist when local files are available.
- For alignment XML, verify video and camera-audio clip counts match.
- For alignment XML, inspect the audit CSV for excluded rows.
- Confirm FPS matches the Resolve project.
- State clearly what was verified and what still requires Resolve import testing.

## References

- `references/audio-video-alignment.md`: alignment workflow and sample/full commands
- `references/davinci-xmeml-rules.md`: Resolve FCP7 XML structure rules
- `references/alignment-debugging-pattern.md`: anonymized alignment debugging pattern; use only for layer classification and repair strategy

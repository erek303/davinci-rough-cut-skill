#!/usr/bin/env python3
"""
Unified transcription entry point.
Priority: Volcengine fast ASR → Xiaomi MiMo ASR (short audio) → faster-whisper (local).
Outputs JSON with speaker labels and word-level timestamps.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _use_volcengine() -> bool:
    """Check if Volcengine ASR credentials are configured."""
    return bool(os.environ.get("VOLCENGINE_API_KEY")) or bool(
        os.environ.get("VOLCENGINE_APP_ID") and os.environ.get("VOLCENGINE_ACCESS_TOKEN")
    )


def _use_mimo() -> bool:
    """Check if Xiaomi MiMo ASR credentials are configured."""
    return bool(os.environ.get("MIMO_API_KEY") or os.environ.get("XIAOMI_API_KEY"))


def transcribe_volcengine(audio_path: str, output_path: str):
    """Transcribe via Volcengine fast cloud ASR with speaker diarization."""
    from volcengine_asr import transcribe as volc_transcribe

    result = volc_transcribe(audio_path)
    if not result:
        print("Volcengine ASR failed.", file=sys.stderr)
        sys.exit(1)

    segments = result["segments"]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)

    print(f"\n[Volcengine] {len(segments)} segments, {len(result['speakers'])} speakers, {result['duration']:.1f}s")
    print(f"Saved to {output_path}")


def transcribe_mimo(audio_path: str, output_path: str, language: str):
    """Transcribe short audio via Xiaomi MiMo ASR."""
    from mimo_asr import transcribe as mimo_transcribe

    result = mimo_transcribe(audio_path, language=language)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[MiMo] {len(result.get('segments', []))} segment(s), {result.get('duration', 0):.1f}s")
    print(f"Saved to {output_path}")


def transcribe_local(audio_path: str, output_path: str, hf_token: "str | None", model_size: str):
    """Transcribe locally with faster-whisper + optional pyannote diarization."""
    import torch
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError("faster-whisper not installed. Run install_deps.py first.") from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"[Local] Loading Whisper model ({model_size}) on {device}...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print("Transcribing...")
    segments_gen, info = model.transcribe(audio_path, beam_size=5, word_timestamps=True)
    segments = []
    for seg in segments_gen:
        words = [{"start": w.start, "end": w.end, "word": w.word} for w in seg.words]
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
            "speaker": "SPEAKER_00",
        })
    print(f"Transcribed {len(segments)} segments (language: {info.language})")

    if hf_token:
        try:
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise ImportError("pyannote.audio not installed. Run install_deps.py first.") from exc

        print("Running speaker diarization...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        pipeline.to(torch.device(device))
        diarization = pipeline(audio_path)

        for seg in segments:
            overlaps = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                overlap = min(seg["end"], turn.end) - max(seg["start"], turn.start)
                if overlap > 0:
                    overlaps[speaker] = overlaps.get(speaker, 0.0) + overlap
            if overlaps:
                seg["speaker"] = max(overlaps, key=overlaps.get)
        print("Speaker diarization complete.")
    else:
        print("No HF token provided; skipping speaker diarization.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    print(f"Saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio with speaker diarization")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("-o", "--output", default="transcription.json", help="Output JSON path")
    parser.add_argument("--hf-token", default=None, help="HuggingFace token for pyannote (local mode only)")
    parser.add_argument("--model", default="large-v3", help="Whisper model size (local mode only)")
    parser.add_argument("--provider", choices=["auto", "volcengine", "mimo", "local"], default="auto",
                        help="Transcription provider. auto prefers Volcengine fast mode, then MiMo, then local.")
    parser.add_argument("--language", default="zh", choices=["auto", "zh", "en"],
                        help="Language hint for MiMo ASR")
    parser.add_argument("--force-local", action="store_true", help="Force local transcription even if Volcengine is configured")
    args = parser.parse_args()

    provider = "local" if args.force_local else args.provider
    if provider == "volcengine":
        print("Using Volcengine ASR fast mode (cloud, with speaker diarization)")
        transcribe_volcengine(args.audio, args.output)
    elif provider == "mimo":
        print("Using Xiaomi MiMo ASR (short-audio fallback)")
        transcribe_mimo(args.audio, args.output, args.language)
    elif provider == "auto" and _use_volcengine():
        print("Using Volcengine ASR fast mode (cloud, with speaker diarization)")
        transcribe_volcengine(args.audio, args.output)
    elif provider == "auto" and _use_mimo():
        print("Using Xiaomi MiMo ASR (short-audio fallback)")
        transcribe_mimo(args.audio, args.output, args.language)
    else:
        print("Using local transcription (faster-whisper)")
        transcribe_local(args.audio, args.output, args.hf_token, args.model)


if __name__ == "__main__":
    main()

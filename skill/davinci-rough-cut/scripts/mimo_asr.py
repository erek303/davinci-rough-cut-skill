#!/usr/bin/env python3
"""
Xiaomi MiMo ASR integration for davinci-rough-cut.

MiMo V2.5 ASR currently accepts wav/mp3 audio as a base64 data URL through
/v1/chat/completions. Because the documented base64 payload limit is 10MB,
this script is intended as a short-audio fallback, not the default long
long-form rough-cut ASR path.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path

MAX_BASE64_BYTES = 10 * 1024 * 1024


def get_audio_duration(audio_path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _api_key() -> str:
    key = os.environ.get("MIMO_API_KEY") or os.environ.get("XIAOMI_API_KEY")
    if not key:
        print("ERROR: Set MIMO_API_KEY or XIAOMI_API_KEY for Xiaomi MiMo ASR.", file=sys.stderr)
        sys.exit(1)
    return key


def _audio_data_url(audio_path: str) -> str:
    mime = mimetypes.guess_type(audio_path)[0]
    if mime not in {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3"}:
        suffix = Path(audio_path).suffix.lower()
        if suffix == ".wav":
            mime = "audio/wav"
        elif suffix == ".mp3":
            mime = "audio/mpeg"
        else:
            raise ValueError("MiMo ASR currently supports wav and mp3 only. Convert audio with ffmpeg first.")

    audio_bytes = Path(audio_path).read_bytes()
    encoded = base64.b64encode(audio_bytes).decode("utf-8")
    if len(encoded.encode("utf-8")) > MAX_BASE64_BYTES:
        raise ValueError(
            "MiMo ASR base64 payload exceeds 10MB. Use Volcengine ASR for long rough-cut audio, "
            "or split/compress the audio before using MiMo."
        )
    return f"data:{mime};base64,{encoded}"


def _extract_text(resp) -> str:
    content = resp.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(text)
            elif hasattr(item, "text"):
                parts.append(item.text)
        return "\n".join(parts).strip()
    return str(content).strip()


def _normalise_transcript(text: str, duration: float) -> dict:
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "segments" in data:
            return data
        if isinstance(data, list):
            return {
                "segments": data,
                "speakers": sorted({seg.get("speaker", "spk1") for seg in data if isinstance(seg, dict)}),
                "duration": duration,
                "provider": "mimo",
            }
    except json.JSONDecodeError:
        pass

    return {
        "segments": [
            {
                "start": 0.0,
                "end": duration,
                "text": text,
                "speaker": "spk1",
                "words": [],
            }
        ],
        "speakers": ["spk1"],
        "duration": duration,
        "provider": "mimo",
        "note": "MiMo ASR returned plain text; this script mapped it to one full-duration segment.",
    }


def transcribe(audio_path: str, language: str = "zh", model: str | None = None) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package not installed. Run: pip install -r requirements-core.txt", file=sys.stderr)
        sys.exit(1)

    key = _api_key()
    base_url = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    client = OpenAI(
        api_key=key,
        base_url=base_url,
        default_headers={"api-key": key},
    )

    data_url = _audio_data_url(audio_path)
    duration = get_audio_duration(audio_path)
    completion = client.chat.completions.create(
        model=model or os.environ.get("MIMO_ASR_MODEL", "mimo-v2.5-asr"),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": data_url,
                        },
                    }
                ],
            }
        ],
        extra_body={
            "asr_options": {
                "language": language,
            }
        },
    )
    return _normalise_transcript(_extract_text(completion), duration)


def main():
    parser = argparse.ArgumentParser(description="Transcribe short wav/mp3 audio with Xiaomi MiMo ASR")
    parser.add_argument("audio", help="Path to wav/mp3 audio file")
    parser.add_argument("-o", "--output", default="transcript.json", help="Output transcript JSON path")
    parser.add_argument("--language", default="zh", choices=["auto", "zh", "en"], help="ASR language hint")
    parser.add_argument("--model", default=None, help="MiMo ASR model, default MIMO_ASR_MODEL or mimo-v2.5-asr")
    args = parser.parse_args()

    result = transcribe(args.audio, language=args.language, model=args.model)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[MiMo] Saved transcript to {args.output}")
    print("[MiMo] Note: use Volcengine ASR for long audio or timestamp-heavy rough cuts.")


if __name__ == "__main__":
    main()

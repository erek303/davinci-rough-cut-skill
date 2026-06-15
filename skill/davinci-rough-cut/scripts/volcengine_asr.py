#!/usr/bin/env python3
"""
Volcengine ASR integration for davinci-rough-cut.
Default path: call the Volcengine audio-file fast API with local audio data.
Advanced path: upload to TOS → call standard URL API → poll results.

Environment variables:
  VOLCENGINE_API_KEY          - ASR API Key (recommended, fast mode)
  VOLCENGINE_ASR_MODE         - fast (default) or standard-url
  VOLCENGINE_APP_ID           - ASR App Key / App ID (legacy auth)
  VOLCENGINE_ACCESS_TOKEN     - ASR Access Token (legacy auth)
  VOLCENGINE_ACCESS_KEY       - IAM Access Key (standard-url/TOS only)
  VOLCENGINE_SECRET_KEY       - IAM Secret Key (standard-url/TOS only)
  VOLCENGINE_TOS_BUCKET       - TOS bucket name (standard-url/TOS only)
  VOLCENGINE_TOS_REGION       - TOS region (standard-url/TOS only)
  VOLCENGINE_TOS_ENDPOINT     - TOS endpoint (standard-url/TOS only)

Usage:
  python3 volcengine_asr.py /path/to/audio.mp3 -o transcript.json
  python3 volcengine_asr.py /path/to/audio.mp3 --mode standard-url -o transcript.json
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import mimetypes
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests


# ── TOS Upload ──────────────────────────────────────────────────────────

def upload_to_tos(audio_path: str) -> str:
    """Upload audio file to TOS and return a presigned URL (valid 24h)."""
    try:
        import tos
    except ImportError:
        print("ERROR: tos package not installed. Run: pip install tos", file=sys.stderr)
        sys.exit(1)

    ak = os.environ.get("VOLCENGINE_ACCESS_KEY")
    sk = os.environ.get("VOLCENGINE_SECRET_KEY")
    bucket = os.environ.get("VOLCENGINE_TOS_BUCKET")
    region = os.environ.get("VOLCENGINE_TOS_REGION", "cn-shanghai")
    # Handle both "cn-shanghai" and "tos-cn-shanghai" formats
    region_stripped = region.removeprefix("tos-")
    endpoint = os.environ.get("VOLCENGINE_TOS_ENDPOINT", f"tos-{region_stripped}.volces.com")

    if not all([ak, sk, bucket]):
        print(
            "ERROR: TOS credentials not configured.\n"
            "Please set these environment variables:\n"
            "  export VOLCENGINE_ACCESS_KEY='your-iam-ak'\n"
            "  export VOLCENGINE_SECRET_KEY='your-iam-sk'\n"
            "  export VOLCENGINE_TOS_BUCKET='your-bucket'\n"
            "Get your IAM keys from: Volcengine Console → Profile → Access Key Management",
            file=sys.stderr,
        )
        sys.exit(1)

    client = tos.TosClientV2(ak=ak, sk=sk, endpoint=endpoint, region=region)

    # Generate a unique object key
    filename = Path(audio_path).name
    ext = Path(audio_path).suffix
    object_key = f"rough-cut/{uuid.uuid4().hex[:8]}_{filename}"

    print(f"  Uploading {audio_path} to TOS://{bucket}/{object_key} ...")

    # Determine content type
    content_type = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"

    with open(audio_path, "rb") as f:
        client.put_object(bucket, object_key, content=f.read(), content_type=content_type)

    # Generate presigned URL (valid 24 hours)
    try:
        from tos.enum import HttpMethodType
        method = HttpMethodType.Http_Method_Get
    except ImportError:
        method = "GET"
    presigned = client.pre_signed_url(
        http_method=method,
        bucket=bucket,
        key=object_key,
        expires=86400,  # 24 hours
    )

    url = presigned.signed_url
    print(f"  Upload done. URL ready.")

    # Schedule cleanup: we'll delete the file after transcription
    # Store object_key for later cleanup
    return url, bucket, object_key, client


def cleanup_tos(client, bucket: str, object_key: str):
    """Delete uploaded file from TOS after transcription."""
    try:
        client.delete_object(bucket, object_key)
        print(f"  Cleaned up TOS://{bucket}/{object_key}")
    except Exception as e:
        print(f"  Warning: TOS cleanup failed: {e}", file=sys.stderr)


# ── ASR API ─────────────────────────────────────────────────────────────

ASR_FAST_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel_nostream"
ASR_SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
ASR_QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = "volc.seedasr.auc"  # 豆包录音文件识别模型2.0


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def write_progress(path: str, data: dict):
    """Write progress state to JSON for UI monitoring."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _asr_headers(task_id: str, include_sequence: bool = False) -> dict:
    api_key = os.environ.get("VOLCENGINE_API_KEY")
    if api_key:
        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Request-Id": task_id,
            "Content-Type": "application/json",
        }
    else:
        app_id = os.environ.get("VOLCENGINE_APP_ID")
        access_token = os.environ.get("VOLCENGINE_ACCESS_TOKEN")
        if not app_id or not access_token:
            print("ERROR: VOLCENGINE_API_KEY or (VOLCENGINE_APP_ID + VOLCENGINE_ACCESS_TOKEN) must be set", file=sys.stderr)
            sys.exit(1)
        headers = {
            "X-Api-App-Key": app_id,
            "X-Api-Access-Key": access_token,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Request-Id": task_id,
            "Content-Type": "application/json",
        }
    if include_sequence:
        headers["X-Api-Sequence"] = "-1"
    return headers


def infer_audio_format(audio_path: str) -> str:
    """Infer the audio format label expected by the ASR API."""
    suffix = Path(audio_path).suffix.lower().lstrip(".")
    return suffix or "mp3"


def build_asr_body(audio: dict, context: str | None = None) -> dict:
    request = {
        "model_name": "bigmodel",
        "enable_itn": True,
        "enable_punc": True,
        "enable_ddc": True,
        "enable_speaker_info": True,
        "show_utterances": True,
        "enable_lid": True,
        "enable_emotion_detection": True,
        "ssd_version": "200",
    }
    if context:
        request["corpus"] = {"context": context}
    return {
        "user": {"uid": "davinci-rough-cut"},
        "audio": audio,
        "request": request,
    }


def build_local_audio_payload(audio_path: str) -> dict:
    """Read local audio and build the fast-mode base64 payload."""
    data = Path(audio_path).read_bytes()
    return {
        "data": base64.b64encode(data).decode("utf-8"),
        "format": infer_audio_format(audio_path),
    }


def call_fast_asr(audio_path: str, task_id: str, context: str | None = None) -> dict:
    """Call Volcengine audio-file fast mode with local base64 audio data."""
    body = build_asr_body(build_local_audio_payload(audio_path), context=context)
    headers = _asr_headers(task_id, include_sequence=True)
    timeout = int(os.environ.get("VOLCENGINE_ASR_TIMEOUT", "600"))

    resp = requests.post(ASR_FAST_URL, headers=headers, json=body, timeout=timeout)
    status = resp.headers.get("X-Api-Status-Code", "")
    message = resp.headers.get("X-Api-Message", "")

    if status and status != "20000000":
        print(f"  ASR fast mode failed: {status} - {message}", file=sys.stderr)
        return {}
    if not status and resp.status_code >= 400:
        print(f"  ASR fast mode HTTP error: {resp.status_code} - {resp.text[:500]}", file=sys.stderr)
        return {}

    try:
        return resp.json()
    except ValueError:
        print(f"  ASR fast mode returned non-JSON response: {resp.text[:500]}", file=sys.stderr)
        return {}


def submit_asr(audio_url: str, task_id: str, context: str | None = None) -> bool:
    """Submit ASR task. Returns True if accepted."""
    body = build_asr_body(
        {
            "url": audio_url,
            "format": "mp3",
        },
        context=context,
    )

    headers = _asr_headers(task_id, include_sequence=True)

    resp = requests.post(ASR_SUBMIT_URL, headers=headers, json=body, timeout=30)

    status = resp.headers.get("X-Api-Status-Code", "")
    message = resp.headers.get("X-Api-Message", "")

    if status == "20000000":
        print(f"  ASR task submitted: {task_id}")
        return True
    else:
        print(f"  ASR submit failed: {status} - {message}", file=sys.stderr)
        return False


def poll_asr_result(task_id: str, max_wait: int = 7200, interval: int = 10, on_tick=None) -> dict:
    """Poll for ASR result. Returns the full result dict."""
    headers = _asr_headers(task_id)

    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.post(ASR_QUERY_URL, headers=headers, json={}, timeout=30)
        status = resp.headers.get("X-Api-Status-Code", "")

        elapsed = int(time.time() - start)
        if on_tick:
            on_tick(elapsed)

        if status == "20000000":
            data = resp.json()
            if data.get("result"):
                print(f"\n  ASR completed in {elapsed}s")
                return data
            # Still processing
            print(f"  Processing... ({elapsed}s)", end="\r")
        elif status == "20000001":
            # Still processing
            print(f"  Processing... ({elapsed}s)", end="\r")
        else:
            message = resp.headers.get("X-Api-Message", "")
            print(f"\n  ASR error: {status} - {message}", file=sys.stderr)
            return {}

        time.sleep(interval)

    print("  ERROR: ASR timeout", file=sys.stderr)
    return {}


# ── Result Processing ───────────────────────────────────────────────────

def format_asr_result(raw: dict) -> list:
    """
    Convert Volcengine ASR result to our standard format.

    Returns list of segments:
    [
        {
            "id": 0,
            "start": 0.0,         # seconds
            "end": 3.5,           # seconds
            "text": "说了什么",
            "speaker": "spk0",    # speaker label
            "words": [...],       # word-level timestamps (optional)
        },
        ...
    ]
    """
    result = raw.get("result", {})
    utterances = result.get("utterances", [])

    segments = []
    for i, utt in enumerate(utterances):
        # Speaker label is inside additions.speaker
        additions = utt.get("additions", {})
        speaker = additions.get("speaker", "unknown")
        if not speaker:
            speaker = utt.get("speaker", "unknown")

        seg = {
            "id": i,
            "start": utt.get("start_time", 0) / 1000.0,  # ms → s
            "end": utt.get("end_time", 0) / 1000.0,
            "text": utt.get("text", "").strip(),
            "speaker": f"spk{speaker}" if speaker != "unknown" else "unknown",
        }

        # Word-level timestamps
        words = utt.get("words", [])
        if words:
            seg["words"] = [
                {
                    "text": w.get("text", ""),
                    "start": w.get("start_time", 0) / 1000.0,
                    "end": w.get("end_time", 0) / 1000.0,
                }
                for w in words
            ]

        segments.append(seg)

    return segments


def get_speaker_map(segments: list) -> dict:
    """Get a summary of speakers and their speaking time."""
    speakers = {}
    for seg in segments:
        spk = seg.get("speaker", "unknown")
        duration = seg["end"] - seg["start"]
        if spk not in speakers:
            speakers[spk] = {"total_seconds": 0, "segment_count": 0}
        speakers[spk]["total_seconds"] += duration
        speakers[spk]["segment_count"] += 1
    return speakers


# ── Main Entry Point ────────────────────────────────────────────────────

def _build_result(raw: dict, audio_path: str) -> dict:
    segments = format_asr_result(raw)
    speakers = get_speaker_map(segments)
    full_text = " ".join(seg["text"] for seg in segments)
    duration = raw.get("audio_info", {}).get("duration", 0) / 1000.0
    if not duration:
        duration = max((seg.get("end", 0) for seg in segments), default=0)

    return {
        "segments": segments,
        "speakers": speakers,
        "duration": duration,
        "text": full_text,
        "source": "volcengine",
        "audio_path": str(audio_path),
    }


def transcribe(audio_path: str, context: str = None, mode: str | None = None) -> dict:
    """
    Full pipeline: transcribe local audio → return structured result.
    Also writes progress.json for UI monitoring.
    """
    if not Path(audio_path).exists():
        print(f"ERROR: Audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[Volcengine ASR] Processing: {audio_path}")

    progress_path = str(Path(audio_path).parent / "progress.json")
    audio_duration = get_audio_duration(audio_path)
    estimated_total = int(audio_duration * 0.25 + 120) if audio_duration else 1200

    def update_progress(status: str, stage: str, elapsed: int = 0, extra: dict = None):
        percent = 0
        if status == "processing":
            percent = min(99, int(elapsed / estimated_total * 100))
        elif status == "completed":
            percent = 100
        data = {
            "status": status,
            "stage": stage,
            "filename": Path(audio_path).name,
            "audio_duration": audio_duration,
            "elapsed_seconds": elapsed,
            "estimated_total_seconds": estimated_total,
            "percent": percent,
            "updated_at": datetime.datetime.now().isoformat(),
        }
        if extra:
            data.update(extra)
        write_progress(progress_path, data)

    mode = (mode or os.environ.get("VOLCENGINE_ASR_MODE", "fast")).lower().replace("_", "-")
    task_id = str(uuid.uuid4())

    if mode in {"fast", "flash", "local-data", "data"}:
        update_progress("processing", "asr_fast", 0, {"task_id": task_id})
        start = time.time()
        raw = call_fast_asr(audio_path, task_id=task_id, context=context)
        if not raw:
            update_progress("error", "asr_fast", int(time.time() - start), {"task_id": task_id})
            return {}
        result = _build_result(raw, audio_path)
        print(f"  Segments: {len(result['segments'])}")
        print(f"  Speakers: {list(result['speakers'].keys())}")
        print(f"  Duration: {result['duration']:.1f}s")
        update_progress("completed", "done", int(time.time() - start), {
            "segments": len(result["segments"]),
            "speakers": list(result["speakers"].keys()),
            "output_file": str(Path(audio_path).with_suffix(".asr.json")),
        })
        return result

    if mode not in {"standard-url", "standard", "url"}:
        print(f"ERROR: unknown VOLCENGINE_ASR_MODE/--mode: {mode}", file=sys.stderr)
        sys.exit(1)

    update_progress("processing", "uploading", 0)
    url, bucket, object_key, tos_client = upload_to_tos(audio_path)

    try:
        update_progress("processing", "asr_polling", 0, {"task_id": task_id})

        if not submit_asr(url, task_id, context=context):
            update_progress("error", "submit_failed", 0, {"message": "ASR submit failed"})
            return {}

        start_poll = time.time()

        def on_tick(elapsed):
            update_progress("processing", "asr_polling", elapsed, {"task_id": task_id})

        raw = poll_asr_result(task_id, on_tick=on_tick)
        if not raw:
            update_progress("error", "asr_polling", int(time.time() - start_poll), {"task_id": task_id})
            return {}

        result = _build_result(raw, audio_path)

        print(f"  Segments: {len(result['segments'])}")
        print(f"  Speakers: {list(result['speakers'].keys())}")
        print(f"  Duration: {result['duration']:.1f}s")

        update_progress("completed", "done", int(time.time() - start_poll), {
            "segments": len(result["segments"]),
            "speakers": list(result["speakers"].keys()),
            "output_file": str(Path(audio_path).with_suffix(".asr.json")),
        })

        return result

    finally:
        cleanup_tos(tos_client, bucket, object_key)


def main():
    parser = argparse.ArgumentParser(description="Volcengine ASR transcription with speaker diarization")
    parser.add_argument("audio", help="Path to audio file (mp3/wav/ogg)")
    parser.add_argument("--output", "-o", help="Output JSON path", default=None)
    parser.add_argument("--context", help="Project context for better recognition", default=None)
    parser.add_argument(
        "--mode",
        choices=["fast", "standard-url"],
        default=os.environ.get("VOLCENGINE_ASR_MODE", "fast"),
        help="ASR mode. fast uses local audio data and only needs VOLCENGINE_API_KEY. standard-url uses TOS URL upload.",
    )
    args = parser.parse_args()

    result = transcribe(args.audio, context=args.context, mode=args.mode)

    if not result:
        print("Transcription failed.", file=sys.stderr)
        sys.exit(1)

    # Output
    output_path = args.output or str(Path(args.audio).with_suffix(".asr.json"))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nResult saved to: {output_path}")


if __name__ == "__main__":
    main()

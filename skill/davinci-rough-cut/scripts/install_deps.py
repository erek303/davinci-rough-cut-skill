#!/usr/bin/env python3
"""Install Python dependencies for davinci-rough-cut."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description="Install davinci-rough-cut dependencies")
    parser.add_argument(
        "--local-asr",
        action="store_true",
        help="Also install heavier local Whisper/pyannote dependencies",
    )
    args = parser.parse_args()

    requirements = [ROOT / "requirements-core.txt"]
    if args.local_asr:
        requirements.append(ROOT / "requirements-local-asr.txt")

    for req in requirements:
        if not req.exists():
            raise FileNotFoundError(f"Missing requirements file: {req}")
        print(f"Installing {req.name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req)])

    print("Done. Make sure ffmpeg/ffprobe are installed and available on PATH.")

if __name__ == "__main__":
    main()

"""Transcribe voice clips with Meta's muse-voice-transcribe-1.0 (POST /v1/asr/transcribe, WAV only).

    python scripts/transcribe.py <voice_dir>  ->  <voice_dir>/transcripts.json
ENDPOINTING mode returns one turn per pause, with timing, which the video builder uses for subtitles.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import requests

BASE = os.getenv("META_API_BASE", "https://api.meta.ai/v1").rstrip("/")
KEY = os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY")
AUDIO = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".webm")


def to_wav(src: Path) -> Path:
    dst = src.with_name(f"_asr_{src.stem}.wav")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)], check=True)
    return dst


def transcribe(path: Path, mode: str = "ENDPOINTING") -> dict:
    wav = to_wav(path)
    try:
        with open(wav, "rb") as f:
            r = requests.post(
                f"{BASE}/asr/transcribe",
                headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
                files={
                    "request": (None, json.dumps({"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV",
                                                  "mode": mode}), "application/json"),
                    "audio": (wav.name, f, "audio/wav"),
                },
                timeout=300,
            )
    finally:
        wav.unlink(missing_ok=True)
    if r.status_code >= 400:
        raise SystemExit(f"{path.name}: HTTP {r.status_code} {r.text[:500]}")
    return r.json()


def main() -> None:
    d = Path(sys.argv[1])
    out = {}
    for f in sorted(p for p in d.iterdir() if p.suffix.lower() in AUDIO and not p.stem.startswith("_")):
        out[f.stem] = transcribe(f)
        print(f"--- {f.stem}\n{json.dumps(out[f.stem], ensure_ascii=False)[:1500]}\n")
    (d / "transcripts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

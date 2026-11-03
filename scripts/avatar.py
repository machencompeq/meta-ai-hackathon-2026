"""Voice-reactive "speaking" avatar track for the demo video.

render_track(photo, audio, out, fps) writes a 360x360 RGBA .mov (qtrle) in which the round portrait
pulses, bobs and glows with the loudness of the voice-over, with a small equaliser under it.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FF = imageio_ffmpeg.get_ffmpeg_exe()
BOX = 360
DIAM = 268
ACCENT = (240, 163, 94)


def _loudness(audio: Path, fps: int) -> np.ndarray:
    """Per-video-frame loudness in 0..1 (smoothed)."""
    sr = 16000
    raw = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-i", str(audio), "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = sr // fps
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-9)
    db = 20 * np.log10(rms)
    lv = np.clip((db + 45) / 30, 0, 1)            # -45 dB -> 0, -15 dB -> 1
    out = np.zeros_like(lv)
    for i, v in enumerate(lv):                      # fast attack, slow release
        prev = out[i - 1] if i else 0
        out[i] = v if v > prev else prev * 0.82 + v * 0.18
    return out


def _portrait(photo: Path) -> Image.Image:
    im = Image.open(photo).convert("RGB")
    w, h = im.size
    side = int(w * 0.80)                            # head and shoulders
    left, top = (w - side) // 2, int(h * 0.04)
    im = im.crop((left, top, left + side, top + side)).resize((DIAM * 2, DIAM * 2), Image.LANCZOS)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, *im.size), fill=255)
    im.putalpha(mask)
    return im


def render_track(photo: Path, audio: Path, out: Path, fps: int = 30) -> Path:
    lv = _loudness(audio, fps)
    face = _portrait(photo)
    proc = subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                             "-s", f"{BOX}x{BOX}", "-r", str(fps), "-i", "-", "-c:v", "qtrle", str(out)],
                            stdin=subprocess.PIPE)
    c = BOX / 2
    bars = 7
    phases = np.random.default_rng(7).uniform(0, math.tau, bars)
    for i, a in enumerate(lv.tolist()):
        t = i / fps
        frame = Image.new("RGBA", (BOX, BOX), (0, 0, 0, 0))
        # glow ring
        glow = Image.new("RGBA", (BOX, BOX), (0, 0, 0, 0))
        r = DIAM / 2 + 10 + 10 * a
        ImageDraw.Draw(glow).ellipse((c - r, c - 18 - r, c + r, c - 18 + r),
                                     outline=(*ACCENT, int(90 + 150 * a)), width=int(6 + 10 * a))
        frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4 + 6 * a)))
        # portrait: slight zoom and bob while speaking
        s = 1 + 0.035 * a
        d = int(DIAM * s)
        img = face.resize((d, d), Image.BILINEAR)
        bob = int(2.5 * a * math.sin(t * 9))
        frame.alpha_composite(img, (int(c - d / 2), int(c - 18 - d / 2 + bob)))
        ring = ImageDraw.Draw(frame)
        rr = d / 2 + 2
        ring.ellipse((c - rr, c - 18 - rr + bob, c + rr, c - 18 + rr + bob), outline=(*ACCENT, 255), width=5)
        # equaliser
        bw, gap, base = 10, 7, BOX - 22
        x0 = c - (bars * bw + (bars - 1) * gap) / 2
        for k in range(bars):
            hgt = 6 + a * 30 * (0.55 + 0.45 * math.sin(t * 13 + phases[k]))
            x = x0 + k * (bw + gap)
            ring.rounded_rectangle((x, base - hgt, x + bw, base), radius=4, fill=(*ACCENT, int(120 + 135 * a)))
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise SystemExit("avatar encode failed")
    return out

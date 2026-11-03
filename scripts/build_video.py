"""Build the 3-minute demo video: slides + full-screen recording + your voice-over.

    python scripts/build_video.py [voice_dir]      ->  out/video/paycheck_committee_demo.mp4

voice_dir (default docs/_private/voice) holds one file per segment, any of .m4a/.mp3/.wav:
  01_cover 02_problem 03_arch 04_scene1 05_scene2 06_scene3 07_meta 08_close
Slides come from docs/slides/*.html (rendered with Playwright); scenes come from the recording made
by scripts/record_demo.py (out/video/markers.json). Waiting-for-the-model parts of each scene are sped
up so the scene matches the length of its voice clip; clicks stay at normal speed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avatar  # noqa: E402
import transcribe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SLIDES = ROOT / "docs" / "slides"
VIDEO = ROOT / "out" / "video"
WORK = VIDEO / "build"
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONTS = ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700"
         "&family=IBM+Plex+Sans:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap")
PLAN = [  # (voice file stem, slide id or scene name)
    ("01_cover", "cover"), ("02_problem", "problem"), ("03_arch", "committee"),
    ("04_scene1", "s1"), ("05_scene2", "s2"), ("06_scene3", "s3"),
    ("07_meta", "meta"), ("08_close", "close"),
]
ENC = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-ar", "48000", "-ac", "2"]
MAX_SPEED = 12.0
BUDGET = 178.0        # seconds for the whole video
PAD = 0.6             # silence around each clip
MAX_TEMPO = 1.6       # fastest the voice may be sped up and stay clear
SUBS = {  # what each clip says (subtitles use this text, timed to the real voice)
    1: "Hi, I’m Ming-An, a grad student in Taiwan. This is Paycheck Committee — a finance agent for people "
       "who live paycheck to paycheck. Bills first, then a committee of Muse Spark agents debates the rest.",
    2: "Every month people ask two things: can I pay every bill on time, and how much can I safely invest? "
       "Robo-advisors ignore next week’s rent. Chatbots give advice nobody is accountable for.",
    3: "Each box is a live Muse Spark call through the Meta Model API: researchers, five investor personas, "
       "a devil’s advocate. The risk officer is plain code that can veto them. Let’s watch it run.",
    4: "First, a user whose card bill and rent land before payday. The engine simulates every day: they hit "
       "minus 10,600 on November 12th. It tells them to move 9,000 from the emergency fund — and the committee "
       "gets zero to invest. Bills always come first.",
    5: "Now a student who can invest 8,700. Watch the decision chain. Four researcher agents read the market data "
       "in parallel — each one is a Muse Spark call, and they may only cite numbers we gave them. Then five "
       "investor personas — Buffett, Lynch, Bogle, Dalio and Kostolany — score three proposals, also in parallel. "
       "On the right you see every call live: model, latency, tokens — and most of them are reasoning tokens. "
       "Muse Spark is actually thinking. The devil’s advocate attacks the leading plan and says what would prove "
       "it wrong. Then the risk officer — which is code, not an LLM — vetoes A and B: they would put most of the "
       "portfolio in a single fund. The models can argue. They can’t argue past the rules. And every node is "
       "auditable: click it and you see the exact prompt we sent to the Meta Model API and the exact JSON that "
       "came back.",
    6: "Life changes. I type one sentence: a dentist bill of 9,000 on the 9th. Muse Spark turns it into a "
       "structured bill, the whole plan reruns, and this month’s investment drops to zero — the committee is "
       "told to sit this one out.",
    7: "One key, nine Meta models. 96% of Muse Spark’s output is visible reasoning. Parallel agents run three "
       "times faster. Every call is logged — and zero LLM calls in the risk officer, on purpose.",
    8: "Bills first, then a debate, then a veto. It’s open source — thanks for watching.",
}


def ff(*args: str) -> str:
    r = subprocess.run([FF, "-hide_banner", "-y", *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])
    return r.stderr


def duration(path: Path) -> float:
    err = subprocess.run([FF, "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def render_portrait(src: Path) -> Path:
    """Crop the photo to a transparent circle with an accent ring."""
    out = WORK / "portrait_circle.png"
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 420, "height": 420})
        page.set_content(f"<body style='margin:0;background:transparent'><div style='width:400px;height:400px;"
                         f"margin:10px;border-radius:50%;border:8px solid #F0A35E;box-sizing:border-box;"
                         f"background:url(\"data:image/jpeg;base64,{base64.b64encode(src.read_bytes()).decode()}\") "
                         f"50% 12%/125% no-repeat'></div></body>")
        page.screenshot(path=str(out), omit_background=True)
        b.close()
    return out


def render_slides() -> dict[str, Path]:
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        for f in sorted(SLIDES.glob("*.html")):
            html = (f"<!doctype html><meta charset='utf-8'><link rel='stylesheet' href='{FONTS}'>"
                    "<style>html,body{margin:0}section{width:1920px;height:1080px;position:relative;"
                    "overflow:hidden;box-sizing:border-box}h1,h2,h3,p,ul{margin:0}aside{display:none}</style>"
                    + f.read_text(encoding="utf-8"))
            page.set_content(html, wait_until="networkidle")
            png = WORK / f"slide_{f.stem}.png"
            page.screenshot(path=str(png))
            out[f.stem] = png
        b.close()
    return out


def tighten_voice(src: Path) -> tuple[Path, float]:
    """Trim the ends, shorten every pause to 0.25 s, normalise loudness."""
    dst = WORK / f"voice_{src.stem}.wav"
    af = ("silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.1:"
          "stop_periods=-1:stop_duration=0.35:stop_threshold=-42dB:stop_silence=0.25,"
          "loudnorm=I=-16:TP=-1.5")
    ff("-i", str(src), "-af", af, "-ar", "48000", "-ac", "2", str(dst))
    return dst, duration(dst)


def speed_voice(src: Path, tempo: float) -> tuple[Path, float]:
    if tempo <= 1.001:
        return src, duration(src)
    dst = src.with_name(src.stem + "_fast.wav")
    ff("-i", str(src), "-af", f"atempo={tempo:.3f}", str(dst))
    return dst, duration(dst)


def _ts(t: float) -> str:
    h, rem = divmod(max(t, 0.0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _chunks(text: str, limit: int = 78) -> list[str]:
    """Sentences, then split long ones at commas/dashes so each cue fits two lines."""
    out = []
    for sent in re.split(r"(?<=[.?!])\s+", text.strip()):
        parts, cur = re.split(r"(?<=[,:;—])\s+", sent), ""
        for p in parts:
            if cur and len(cur) + len(p) + 1 > limit:
                out.append(cur)
                cur = p
            else:
                cur = f"{cur} {p}".strip()
        if cur:
            out.append(cur)
    return out


def write_subs(cues: list[tuple[float, float, str]], path: Path) -> None:
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,46,&H00F3EFE6,&H00F3EFE6,&H00000000,&H9C1A0F0B,0,0,0,0,100,100,0,0,3,14,0,2,"
            "400,400,120,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = [f"Dialogue: 0,{_ts(a)},{_ts(b)},Default,,0,0,0,,{t}" for a, b, t in cues]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def _asr_turns(voice: Path) -> list[tuple[float, float, int]]:
    """(start s, end s, characters) per spoken turn, from Meta's muse-voice-transcribe-1.0; cached."""
    cache = voice.with_name(f"{voice.stem}.{hashlib.sha1(voice.read_bytes()).hexdigest()[:10]}.asr.json")
    if not cache.exists():
        try:
            cache.write_text(json.dumps(transcribe.transcribe(voice)), encoding="utf-8")
        except (SystemExit, Exception) as e:  # no key / API down: fall back to even spreading
            print(f"  ASR unavailable for {voice.name}: {e}")
            return []
    res = json.loads(cache.read_text(encoding="utf-8"))
    return [(t["startMs"] / 1000, t["endMs"] / 1000, max(len(t.get("transcript", "")), 1))
            for t in res.get("turns", []) if t.get("endMs", 0) > t.get("startMs", 0)]


def cues_for(n: int, start: float, speech: float, voice: Path) -> list[tuple[float, float, str]]:
    """Time the clip's script text to the real voice: characters map onto the ASR turns, pauses included."""
    chunks = _chunks(SUBS[n])
    turns = _asr_turns(voice) or [(0.0, speech, 1)]
    asr_total = sum(c for *_, c in turns)
    # piecewise map: fraction of text spoken -> time in the clip
    knots, acc = [(0.0, turns[0][0])], 0
    for a, b, c in turns:
        knots.append((acc / asr_total, a))
        acc += c
        knots.append((acc / asr_total, b))

    def at(f: float) -> float:
        for (f0, t0), (f1, t1) in zip(knots, knots[1:]):
            if f <= f1:
                return t0 if f1 == f0 else t0 + (t1 - t0) * (f - f0) / (f1 - f0)
        return knots[-1][1]

    total = sum(len(c) for c in chunks)
    cues, done = [], 0
    for c in chunks:
        a, b = at(done / total), at((done + len(c)) / total)
        cues.append((start + a, start + max(b, a + 0.6) - 0.05, c))
        done += len(c)
    return cues


def find_voice(voice_dir: Path, n: int, stem: str) -> Path:
    for f in voice_dir.iterdir():
        if f.suffix.lower() in (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".webm") and \
                (f.stem == stem or f.stem.lower() in (f"slide{n:02d}", f"slide{n}", f"{n:02d}")):
            return f
    raise SystemExit(f"missing voice file {stem}.* or Slide{n:02d}.* in {voice_dir}")


def slide_segment(png: Path, voice: Path, dur: float, out: Path) -> None:
    total = dur + PAD
    ff("-loop", "1", "-t", f"{total:.2f}", "-i", str(png), "-i", str(voice),
       "-filter_complex", f"[0:v]scale=1920:1080,fps=30[v];[1:a]adelay=300|300,apad,atrim=0:{total:.2f}[a]",
       "-map", "[v]", "-map", "[a]", *ENC, str(out))


def scene_segment(webm: Path, marks: dict, scene: str, voice: Path, dur: float, out: Path) -> None:
    start, done, end = marks[f"{scene}_start"], marks[f"{scene}_done"], marks[f"{scene}_end"]
    wait, tail = done - start, end - done
    target = dur + PAD
    room = target - tail
    if room > 0.5:
        s_wait, s_tail = max(wait / room, 1.0), 1.0
        s_wait = min(s_wait, MAX_SPEED)
    else:  # voice shorter than the clicks themselves: speed everything evenly
        s_wait = s_tail = min(max((wait + tail) / target, 1.0), MAX_SPEED)
    vf = (f"[0:v]trim={start}:{done},setpts=(PTS-STARTPTS)/{s_wait:.3f}[w];"
          f"[0:v]trim={done}:{end},setpts=(PTS-STARTPTS)/{s_tail:.3f}[t];"
          f"[w][t]concat=n=2:v=1:a=0,scale=1920:1080:flags=lanczos,fps=30,"
          f"tpad=stop_mode=clone:stop_duration=30,trim=0:{target:.2f}[v];"
          f"[1:a]adelay=300|300,apad,atrim=0:{target:.2f}[a]")
    ff("-i", str(webm), "-i", str(voice), "-filter_complex", vf, "-map", "[v]", "-map", "[a]", *ENC, str(out))
    print(f"  {scene}: waiting {wait:.0f}s at {s_wait:.1f}x, clicks {tail:.0f}s at {s_tail:.1f}x -> {target:.1f}s")


def main() -> None:
    voice_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "_private" / "voice"
    WORK.mkdir(parents=True, exist_ok=True)
    marks = json.loads((VIDEO / "markers.json").read_text(encoding="utf-8"))
    webm = Path(marks["video"])
    # markers start when the page opens; the video starts a moment later
    lag = max(0.0, marks["s3_end"] - duration(webm))
    marks = {k: (max(0.0, v - lag) if isinstance(v, float) else v) for k, v in marks.items()}
    slides = render_slides()

    tight = [tighten_voice(find_voice(voice_dir, n, stem)) for n, (stem, _) in enumerate(PLAN, 1)]
    raw_total = sum(d for _, d in tight)
    tempo = max(1.0, raw_total / (BUDGET - PAD * len(PLAN)))
    if tempo > MAX_TEMPO:
        print(f"WARNING: voice needs {tempo:.2f}x to fit {BUDGET:.0f}s; capped at {MAX_TEMPO}x — re-record shorter")
        tempo = MAX_TEMPO
    print(f"voice {raw_total:.1f}s after pause trimming -> tempo {tempo:.2f}x")

    parts, cues, spans, t = [], [], [], 0.0
    for n, ((stem, what), (v, _)) in enumerate(zip(PLAN, tight), 1):
        voice, dur = speed_voice(v, tempo)
        seg = WORK / f"seg_{stem}.mp4"
        if what in slides:
            slide_segment(slides[what], voice, dur, seg)
        else:
            scene_segment(webm, marks, what, voice, dur, seg)
        cues += cues_for(n, t + 0.3, dur, voice)  # clips start after a 0.3 s delay
        spans.append((what, t, t + dur + PAD))
        parts.append(seg)
        t += dur + PAD
        print(f"{stem}: {dur:.1f}s voice")

    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    joined = WORK / "joined.mp4"
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined))
    write_subs(cues, WORK / "subs.ass")
    final = VIDEO / "paycheck_committee_demo.mp4"
    # speaking avatar: large on the cover, small bottom-right on slides, small bottom-left over the demo;
    # every spot is empty space on its screen, and subtitles keep 300 px side margins
    photo = ROOT / "docs" / "_private" / "portrait_hd.jpg"
    inputs, vf = ["-i", "joined.mp4"], "[0:v]subtitles=subs.ass[s]"
    if photo.exists():
        voice_track = WORK / "voice_track.wav"
        ff("-i", str(joined), "-vn", "-ac", "1", "-ar", "16000", str(voice_track))
        track = avatar.render_track(photo, voice_track, WORK / "avatar.mov")
        inputs += ["-i", track.name]
        en = lambda kinds: "+".join(f"between(t,{a:.2f},{b:.2f})" for w, a, b in spans if kinds(w)) or "0"
        vf = ("[1:v]split=3[p1][p2][p3];[p1]scale=360:360[big];[p2]scale=250:250[sm1];[p3]scale=200:200[sm2];"
              "[0:v]subtitles=subs.ass[v0];"
              f"[v0][big]overlay=x=1530:y=570:enable='{en(lambda w: w == 'cover')}'[v1];"
              f"[v1][sm1]overlay=x=1650:y=800:enable='{en(lambda w: w in slides and w != 'cover')}'[v2];"
              f"[v2][sm2]overlay=x=40:y=872:enable='{en(lambda w: w not in slides)}'[s]")
    # subtitles filter paths are awkward on Windows: run from WORK with a bare file name
    r = subprocess.run([FF, "-hide_banner", "-y", *inputs, "-filter_complex", vf, "-map", "[s]", "-map", "0:a",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "copy",
                        "-movflags", "+faststart", str(final)], cwd=WORK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])
    print(f"\n{final}  ({t:.0f}s{' — OVER 3:00' if t > 180 else ''})")


if __name__ == "__main__":
    main()

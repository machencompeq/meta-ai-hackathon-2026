"""Record the demo with Playwright: python scripts/record_demo.py  ->  out/video/*.webm

Start the server first (python -m finagent.web, with MODEL_API_KEY set for a live run).
Video has no audio: add the voice-over from docs/demo講稿.md in any editor.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = Path(__file__).resolve().parent.parent / "out" / "video"
SIZE = {"width": 1600, "height": 900}

# Playwright videos have no cursor; draw one so viewers can follow the clicks.
CURSOR = """
const c = document.createElement('div');
c.style.cssText = 'position:fixed;width:22px;height:22px;border-radius:50%;background:rgba(240,163,94,.55);'
  + 'border:2px solid #F0A35E;pointer-events:none;z-index:99999;transform:translate(-50%,-50%);transition:transform .1s';
document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; });
document.addEventListener('mousedown', () => c.style.transform = 'translate(-50%,-50%) scale(.7)');
document.addEventListener('mouseup', () => c.style.transform = 'translate(-50%,-50%)');
window.addEventListener('DOMContentLoaded', () => document.body.appendChild(c));
"""


def click(page, selector: str, pause: int = 900) -> None:
    box = page.locator(selector).first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=20)
    page.wait_for_timeout(250)
    page.locator(selector).first.click()
    page.wait_for_timeout(pause)


def runs(page) -> int:
    return page.evaluate("window.__runs || 0")


def wait_done(page, before: int) -> None:
    page.wait_for_function(f"(window.__runs || 0) > {before}", timeout=300_000)
    page.wait_for_timeout(1500)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=SIZE, record_video_dir=str(OUT), record_video_size=SIZE)
        ctx.add_init_script(CURSOR)
        page = ctx.new_page()
        t0 = time.monotonic()
        marks: dict[str, float] = {}

        def mark(name: str) -> None:
            marks[name] = round(time.monotonic() - t0, 2)

        page.goto(URL)
        page.wait_for_timeout(2000)

        # Scene 1: bills come first — short on cash, the committee never gets money
        mark("s1_start")
        page.select_option("#persona", "short_on_cash")
        page.wait_for_timeout(600)
        n = runs(page)
        click(page, "#run")
        wait_done(page, n)
        mark("s1_done")
        click(page, '.node[data-id="cash"]', 3500)
        mark("s1_end")

        # Scene 2: full decision chain for the student
        mark("s2_start")
        page.select_option("#persona", "student")
        page.wait_for_timeout(600)
        n = runs(page)
        click(page, "#run")
        wait_done(page, n)
        mark("s2_done")
        click(page, '.node[data-id="A"]', 3000)      # vetoed proposal
        click(page, '.node[data-id="risk"]', 3000)   # rules, no LLM
        click(page, '.node[data-id="devil"]', 2500)  # model attacks the leader
        click(page, "#detail summary", 1000)          # exact API request & response
        page.locator("#detail pre").first.evaluate("e => e.scrollTo({top: e.scrollHeight, behavior: 'smooth'})")
        page.wait_for_timeout(3500)
        click(page, '.node[data-id="buffett"]', 2500)
        page.locator("#calls").evaluate("e => e.scrollTo({top: e.scrollHeight, behavior: 'smooth'})")
        page.wait_for_timeout(2500)
        mark("s2_end")

        # Scene 3: one sentence changes the plan
        mark("s3_start")
        click(page, "#say", 300)
        page.keyboard.type("dentist bill 9,000 due on the 9th", delay=55)
        page.wait_for_timeout(500)
        n = runs(page)
        click(page, "#sayBtn", 200)
        wait_done(page, n)
        mark("s3_done")
        click(page, '.node[data-id="cash"]', 4000)
        mark("s3_end")

        video = page.video.path()
        (OUT / "markers.json").write_text(json.dumps({"video": str(video), **marks}, indent=1), encoding="utf-8")
        ctx.close()
        browser.close()
    print(f"video: {video}")


if __name__ == "__main__":
    main()

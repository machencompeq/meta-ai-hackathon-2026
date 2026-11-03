"""Live committee room: python -m finagent.web  ->  http://127.0.0.1:8765

Streams every step (cash plan, each agent's Meta Model API call, risk vetoes, decision) as NDJSON.
Standard library only.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from . import committee, engine, intake, llm, market
from .models import IncomeRule, Obligation, Profile

ROOT = Path(__file__).resolve().parent.parent
PERSONAS = ROOT / "examples" / "personas"
STATIC = Path(__file__).with_name("static")
OUT = ROOT / "out"
_models_cache: list[str] | None = None


def _available_models() -> list[str]:
    global _models_cache
    if _models_cache is None:
        if llm.is_mock():
            _models_cache = []
        else:
            try:
                r = requests.get(f"{os.getenv('META_API_BASE', llm.DEFAULT_BASE).rstrip('/')}/models",
                                 headers={"Authorization": f"Bearer {llm._key()}"}, timeout=20)
                _models_cache = [m["id"] for m in r.json().get("data", [])]
            except (requests.RequestException, ValueError):
                _models_cache = []
    return _models_cache


def _load(persona: str, extras: list[dict]) -> Profile:
    p = Profile.model_validate_json((PERSONAS / f"{Path(persona).stem}.json").read_text(encoding="utf-8"))
    for x in extras:
        item = {k: v for k, v in x.items() if k != "kind"}
        if x.get("kind") == "income":
            p.incomes.append(IncomeRule(**item))
        else:
            p.obligations.append(Obligation(**item))
    return p


def run_pipeline(persona: str, extras: list[dict], emit) -> None:
    llm.reset_trace()
    t0 = time.perf_counter()
    profile = _load(persona, extras)
    plan = engine.simulate_cash(profile, 60)
    alloc = engine.investable_amount(profile, plan)
    emit({"type": "cash", "start": profile.liquid_balance, "buffer": profile.policy.min_cash_buffer,
          "days": [{"d": d.day.isoformat(), "bal": d.balance, "events": d.events} for d in plan.days],
          "lowest": plan.lowest_balance, "lowest_day": plan.lowest_day.isoformat(),
          "shortfall_days": [d.isoformat() for d in plan.shortfall_days], "transfers": plan.transfers})
    emit({"type": "alloc", **alloc.__dict__})
    feats = {s: market.features(c) for s, c in market.load_sample().items()}
    emit({"type": "market", "features": feats})
    meeting = committee.run(profile, alloc, feats, emit)
    wall = round((time.perf_counter() - t0) * 1000)
    trace = list(llm.TRACE)
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT / f"trace_{Path(persona).stem}_{stamp}.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in trace), encoding="utf-8")
    emit({"type": "done", "wall_ms": wall, "calls": len(trace), "sum_call_ms": sum(r["ms"] for r in trace),
          "trace_file": str(path.relative_to(ROOT)), "mock": meeting.mock})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/info":
            self._json({"mock": llm.is_mock(), "models": llm.MODELS,
                        "base": os.getenv("META_API_BASE", llm.DEFAULT_BASE),
                        "available": _available_models(),
                        "personas": sorted(p.stem for p in PERSONAS.glob("*.json"))})
        elif self.path == "/api/trace":
            self._json(list(llm.TRACE))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path == "/api/parse":
            item, rec = intake.parse(self._body().get("text", ""))
            kind = "income" if isinstance(item, IncomeRule) else "obligation"
            self._json({"kind": kind, "item": {"kind": kind, **item.model_dump()},
                        "call": committee._call_meta(rec), "raw": committee._raw(rec)})
        elif self.path == "/api/run":
            req = self._body()
            q: queue.Queue = queue.Queue()

            def emit(ev: dict) -> None:
                q.put(ev)

            def work() -> None:
                try:
                    run_pipeline(req.get("persona", "student"), req.get("extras", []), emit)
                except Exception as e:  # surface to UI instead of hanging the stream
                    q.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
                q.put(None)

            threading.Thread(target=work, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while (ev := q.get()) is not None:
                self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
        else:
            self._json({"error": "not found"}, 404)


def main() -> None:
    port = int(os.getenv("PORT", "8765"))
    if llm.is_mock():
        os.environ.setdefault("MOCK_DELAY", "0.8")
    print(f"Paycheck Committee live room: http://127.0.0.1:{port}  ({'MOCK' if llm.is_mock() else 'Meta Model API'})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

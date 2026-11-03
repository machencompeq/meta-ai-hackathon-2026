"""Meta Model API client (OpenAI-compatible chat completions) with an offline mock.

Every call is recorded in TRACE (prompt, raw reply, tokens, latency) so a run can prove
exactly what the Meta models did.

Env vars (never commit keys):
  MODEL_API_KEY   - key from https://dev.meta.ai (format LLM|<id>|<secret>); unset -> mock mode
  META_API_BASE   - default https://api.meta.ai/v1
  META_MODEL_CHIEF / META_MODEL_SMALL - default muse-spark-1.3
    (muse-spark-1.3-contributor is discounted; see dev.meta.ai docs for its data terms)
  MOCK_DELAY      - seconds each mock call pretends to take (UI demo only), default 0
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime

import requests

DEFAULT_BASE = "https://api.meta.ai/v1"
MODELS = {
    "chief": os.getenv("META_MODEL_CHIEF", "muse-spark-1.3"),
    "small": os.getenv("META_MODEL_SMALL", "muse-spark-1.3"),
}

TRACE: list[dict] = []
_lock = threading.Lock()


def _key() -> str | None:
    return os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY")


def is_mock() -> bool:
    return not _key()


def reset_trace() -> None:
    with _lock:
        TRACE.clear()


def call(tier: str, system: str, user: str, mock: dict | None = None, label: str = "",
         timeout: int = 180, retries: int = 2) -> tuple[dict, dict]:
    """Ask for one JSON object. Returns (parsed, trace record)."""
    system = system + "\nReply with ONE JSON object only."
    rec = {"label": label, "tier": tier, "model": "mock" if is_mock() else MODELS[tier],
           "at": datetime.now().isoformat(timespec="seconds"), "system": system, "user": user}
    t0 = time.perf_counter()
    if is_mock():
        time.sleep(float(os.getenv("MOCK_DELAY", "0")))
        parsed, rec["reply"], rec["usage"] = dict(mock or {}), json.dumps(mock or {}), {}
    else:
        base = os.getenv("META_API_BASE", DEFAULT_BASE).rstrip("/")
        err = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {_key()}"},
                    json={"model": MODELS[tier], "temperature": 0.2,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": user}]},
                    timeout=timeout,
                )
                resp.raise_for_status()
                body = resp.json()
                rec["reply"] = body["choices"][0]["message"]["content"]
                rec["usage"] = body.get("usage", {})
                parsed = _extract_json(rec["reply"])
                break
            except (requests.RequestException, ValueError, KeyError) as e:
                err = e
                rec["retries"] = attempt + 1
        else:
            rec["error"] = str(err)
            parsed = dict(mock or {})
            parsed["_fallback"] = True
    rec["ms"] = round((time.perf_counter() - t0) * 1000)
    with _lock:
        TRACE.append(rec)
    return parsed, rec


def chat_json(tier: str, system: str, user: str, mock: dict | None = None, label: str = "") -> dict:
    return call(tier, system, user, mock, label)[0]


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"model returned no JSON: {text[:200]}")
    return json.loads(m.group(0))

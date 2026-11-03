"""Meta Model API client (OpenAI-compatible chat completions) with an offline mock.

Env vars (never commit keys):
  MODEL_API_KEY   - key from https://dev.meta.ai (format LLM|<id>|<secret>); unset -> mock mode
  META_API_BASE   - default https://api.meta.ai/v1
  META_MODEL_CHIEF / META_MODEL_SMALL - default muse-spark-1.3
    (muse-spark-1.3-contributor is discounted; see dev.meta.ai docs for its data terms)
"""
from __future__ import annotations

import json
import os
import re

import requests

DEFAULT_BASE = "https://api.meta.ai/v1"
MODELS = {
    "chief": os.getenv("META_MODEL_CHIEF", "muse-spark-1.3"),
    "small": os.getenv("META_MODEL_SMALL", "muse-spark-1.3"),
}


def _key() -> str | None:
    return os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY")


def is_mock() -> bool:
    return not _key()


def chat_json(tier: str, system: str, user: str, mock: dict | None = None, timeout: int = 90) -> dict:
    """Ask for a JSON object. In mock mode return `mock` so the demo runs offline."""
    if is_mock():
        return dict(mock or {})
    base = os.getenv("META_API_BASE", DEFAULT_BASE).rstrip("/")
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {_key()}"},
        json={
            "model": MODELS[tier],
            "messages": [
                {"role": "system", "content": system + "\nReply with ONE JSON object only."},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"model returned no JSON: {text[:200]}")
    return json.loads(m.group(0))

"""Meta Model API client (OpenAI-compatible chat completions) with an offline mock.

Env vars (never commit keys):
  META_API_KEY    - key from the Meta Model API console; unset -> mock mode
  META_API_BASE   - default https://api.llama.com/compat/v1  (TODO: confirm for Muse models)
  META_MODEL_CHIEF / META_MODEL_SMALL - model ids (TODO: confirm exact Muse Spark ids)
"""
from __future__ import annotations

import json
import os
import re

import requests

DEFAULT_BASE = "https://api.llama.com/compat/v1"
MODELS = {
    "chief": os.getenv("META_MODEL_CHIEF", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
    "small": os.getenv("META_MODEL_SMALL", "Llama-4-Scout-17B-16E-Instruct-FP8"),
}


def is_mock() -> bool:
    return not os.getenv("META_API_KEY")


def chat_json(tier: str, system: str, user: str, mock: dict | None = None, timeout: int = 90) -> dict:
    """Ask for a JSON object. In mock mode return `mock` so the demo runs offline."""
    if is_mock():
        return dict(mock or {})
    base = os.getenv("META_API_BASE", DEFAULT_BASE).rstrip("/")
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['META_API_KEY']}"},
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

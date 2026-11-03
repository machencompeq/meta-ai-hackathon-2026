"""Pluggable market data. Offline sample by default; TWSE open data when online."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import requests

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "market_sample.csv"


def load_sample(path: Path = SAMPLE) -> dict[str, list[float]]:
    """symbol -> closes (oldest first)."""
    out: dict[str, list[float]] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["symbol"], []).append(float(row["close"]))
    return out


def fetch_twse_month(symbol: str, month: date) -> list[float]:
    """TWSE STOCK_DAY: daily closes for one month."""
    r = requests.get(
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
        params={"response": "json", "date": month.strftime("%Y%m01"), "stockNo": symbol},
        timeout=20,
    )
    r.raise_for_status()
    return [float(row[6].replace(",", "")) for row in r.json().get("data", [])]


def features(closes: list[float]) -> dict:
    """Facts the researcher agents are allowed to cite."""
    last = closes[-1]
    ma60 = sum(closes[-60:]) / min(len(closes), 60)
    ma20 = sum(closes[-20:]) / min(len(closes), 20)
    chg20 = last / closes[-21] - 1 if len(closes) > 20 else 0.0
    return {
        "last": round(last, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "pct_vs_ma60": round(last / ma60 - 1, 4),
        "chg_20d": round(chg20, 4),
    }

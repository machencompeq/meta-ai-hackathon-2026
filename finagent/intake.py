"""Natural-language intake: "phone bill 1,200 due on the 9th" -> Obligation / IncomeRule via Muse Spark."""
from __future__ import annotations

import re

from . import llm
from .models import IncomeRule, Obligation


def _mock_parse(text: str) -> dict:
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)]
    amount = max(nums) if nums else 0
    day = next((n for n in nums if 1 <= n <= 31 and n != amount), 1)
    income = bool(re.search(r"salary|paid|income|bonus|refund|薪|收入|入帳", text, re.I))
    return {"kind": "income" if income else "obligation", "name": text[:40], "amount": amount,
            "day_of_month": day, "months_left": 1}


def parse(text: str, account_id: str = "bank") -> tuple[Obligation | IncomeRule, dict]:
    out, rec = llm.call(
        "small",
        "You turn one sentence about money into a cash-flow item. Output: {\"kind\": \"obligation\"|\"income\", "
        "\"name\": short English label, \"amount\": positive number, \"day_of_month\": 1-31, "
        "\"months_left\": integer or null for recurring}. A one-off item has months_left 1.",
        text,
        mock=_mock_parse(text),
        label="intake",
    )
    common = {"name": str(out.get("name") or text[:40]), "amount": abs(float(out["amount"])),
              "day_of_month": int(out["day_of_month"]), "account_id": account_id}
    if out.get("kind") == "income":
        return IncomeRule(**common), rec
    return Obligation(**common, months_left=out.get("months_left")), rec

"""Orchestrator: researchers -> chair drafts proposals -> masters score -> devil -> risk veto -> chair.

`emit(event)` streams every step (used by the live web UI); researchers and masters run in parallel.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from . import llm, risk
from .engine import Allocation
from .models import Profile

ROLES = Path(__file__).with_name("roles.yaml")
Emit = Callable[[dict], None]


@dataclass
class Meeting:
    signal_cards: list[dict] = field(default_factory=list)
    proposals: list[risk.Proposal] = field(default_factory=list)
    scores: dict[str, dict[str, int]] = field(default_factory=dict)  # master -> proposal -> 1..5
    reasons: dict[str, str] = field(default_factory=dict)  # master -> one-line reason
    devil: dict = field(default_factory=dict)
    verdicts: list[risk.Verdict] = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    mock: bool = True


def _call_meta(rec: dict) -> dict:
    u = rec.get("usage") or {}
    return {"model": rec["model"], "ms": rec["ms"], "prompt_tokens": u.get("prompt_tokens"),
            "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "fallback": "error" in rec, "label": rec["label"]}


def _raw(rec: dict) -> dict:
    return {"system": rec["system"], "user": rec["user"], "reply": rec.get("reply"), "error": rec.get("error")}


def _mock_card(role: dict, feats: dict[str, dict]) -> dict:
    f = feats.get("0050") or next(iter(feats.values()))
    gap = f["pct_vs_ma60"]
    direction = "bullish" if gap < -0.03 else "bearish" if gap > 0.08 else "neutral"
    return {
        "role": role["id"],
        "direction": direction,
        "strength": 3,
        "evidence": f"0050 last {f['last']} vs MA60 {f['ma60']} ({gap:+.1%}); 20d {f['chg_20d']:+.1%}",
    }


def _draft_proposals(investable: float, prices: dict[str, float]) -> list[risk.Proposal]:
    """Candidate plans. Amounts come from code; the chair LLM only writes the rationale."""
    def buy(sym: str, amt: float) -> risk.Order:
        return risk.Order(symbol=sym, side="buy", amount=round(amt), price=prices.get(sym, 0.0))

    return [
        risk.Proposal(id="A", title="All core index (0050)", orders=[buy("0050", investable)]),
        risk.Proposal(id="B", title="Index + dividend split", orders=[buy("0050", investable * 0.6), buy("00878", investable * 0.4)]),
        risk.Proposal(id="C", title="Split buy: half now, half next week", orders=[buy("006208", investable * 0.5)]),
    ]


def _mock_scores(master: str) -> dict:
    table = {
        "buffett": {"A": 4, "B": 4, "C": 3},
        "lynch": {"A": 3, "B": 3, "C": 3},
        "bogle": {"A": 5, "B": 4, "C": 4},
        "dalio": {"A": 4, "B": 5, "C": 4},
        "kostolany": {"A": 3, "B": 3, "C": 4},
    }
    return {"scores": table.get(master, {"A": 3, "B": 3, "C": 3}), "reason": "Mock score."}


def run(profile: Profile, alloc: Allocation, feats: dict[str, dict], emit: Emit | None = None) -> Meeting:
    emit = emit or (lambda e: None)
    roles = yaml.safe_load(ROLES.read_text(encoding="utf-8"))
    m = Meeting(mock=llm.is_mock())
    prices = {s: f["last"] for s, f in feats.items()}
    facts = json.dumps(feats, ensure_ascii=False)

    def researcher(r: dict) -> dict:
        emit({"type": "agent_start", "id": r["id"], "name": r["name"], "layer": "researcher"})
        card, rec = llm.call(
            r["tier"],
            f"You are the '{r['name']}' researcher on a Taiwan-stock committee. Focus: {r['focus']} "
            "Cite ONLY the numbers given. Output keys: role, direction (bullish|neutral|bearish), strength (1-5), "
            "evidence (max 40 words).",
            f"Market facts: {facts}",
            mock=_mock_card(r, feats),
            label=f"researcher:{r['id']}",
        )
        card["role"] = r["id"]
        emit({"type": "agent_done", "id": r["id"], "name": r["name"], "layer": "researcher",
              "output": card, "call": _call_meta(rec), "raw": _raw(rec)})
        return card

    emit({"type": "stage", "stage": "research"})
    with ThreadPoolExecutor(max_workers=len(roles["researchers"])) as ex:
        m.signal_cards = list(ex.map(researcher, roles["researchers"]))

    if alloc.investable <= 0:
        m.decision = {"choice": None, "summary": "No investing this month. " + " ".join(alloc.reasons)}
        emit({"type": "decision", "decision": m.decision})
        return m

    m.proposals = _draft_proposals(alloc.investable, prices)
    emit({"type": "stage", "stage": "proposals"})
    emit({"type": "proposals", "proposals": [p.model_dump() for p in m.proposals]})
    plist = json.dumps([p.model_dump() for p in m.proposals], ensure_ascii=False)
    cards = json.dumps(m.signal_cards, ensure_ascii=False)

    def master(ms: dict) -> tuple[str, dict, str]:
        emit({"type": "agent_start", "id": ms["id"], "name": ms["name"], "layer": "master"})
        out, rec = llm.call(
            "small",
            f"You are {ms['name']}. Check: {ms['checks']} Score each proposal 1-5 from your philosophy and cite "
            "a signal card. Output: {\"scores\": {\"A\": n, \"B\": n, \"C\": n}, \"reason\": \"max 30 words\"}",
            f"Proposals: {plist}\nSignal cards: {cards}",
            mock=_mock_scores(ms["id"]),
            label=f"master:{ms['id']}",
        )
        scores = {k: int(v) for k, v in out.get("scores", {}).items()}
        reason = str(out.get("reason", ""))
        emit({"type": "agent_done", "id": ms["id"], "name": ms["name"], "layer": "master",
              "output": {"scores": scores, "reason": reason}, "call": _call_meta(rec), "raw": _raw(rec)})
        return ms["id"], scores, reason

    emit({"type": "stage", "stage": "scoring"})
    with ThreadPoolExecutor(max_workers=len(roles["masters"])) as ex:
        for mid, scores, reason in ex.map(master, roles["masters"]):
            m.scores[mid], m.reasons[mid] = scores, reason

    totals = {p.id: sum(s.get(p.id, 0) for s in m.scores.values()) for p in m.proposals}
    # tie -> earlier (more conservative) proposal wins; proposals are ordered conservative-first
    best = max(m.proposals, key=lambda p: (totals[p.id], -m.proposals.index(p)))
    emit({"type": "totals", "totals": totals, "leader": best.id})

    emit({"type": "stage", "stage": "devil"})
    emit({"type": "agent_start", "id": "devil", "name": roles["devil"]["name"], "layer": "devil"})
    m.devil, rec = llm.call(
        "chief",
        "You are the devil's advocate. Attack the leading proposal. Output: "
        "{\"attack\": \"strongest counter-argument, max 50 words, cite numbers\", \"falsifier\": \"what would prove you wrong\"}",
        f"Leader: {best.model_dump_json()}\nSignal cards: {cards}",
        mock={"attack": f"{best.title}: if 0050 keeps rising above MA60 you buy the top; split the buy instead.",
              "falsifier": "3 months later return below a 2-tranche split buy."},
        label="devil",
    )
    emit({"type": "agent_done", "id": "devil", "name": roles["devil"]["name"], "layer": "devil",
          "output": m.devil, "call": _call_meta(rec), "raw": _raw(rec)})

    emit({"type": "stage", "stage": "risk"})
    m.verdicts = [risk.check(profile, p, alloc.investable, prices) for p in m.proposals]
    emit({"type": "risk", "verdicts": [v.model_dump() for v in m.verdicts]})
    ok = {v.proposal_id for v in m.verdicts if v.approved}
    ranked = sorted(m.proposals, key=lambda p: (-totals[p.id], m.proposals.index(p)))
    choice = next((p for p in ranked if p.id in ok), None)

    emit({"type": "stage", "stage": "chair"})
    emit({"type": "agent_start", "id": "chief", "name": roles["chief"]["name"], "layer": "chair"})
    summary, rec = llm.call(
        "chief",
        "You chair the committee. Explain the final choice in 3 short sentences for a student; mention any veto. "
        "Output: {\"summary\": str}",
        f"Totals: {totals}\nChoice: {choice.model_dump_json() if choice else None}\nDevil: {m.devil}\n"
        f"Risk: {[v.model_dump() for v in m.verdicts]}",
        mock={"summary": f"Chose {choice.title if choice else 'nothing'} (score {totals.get(choice.id) if choice else '-'}). "
                         "Bills and emergency fund are covered first; the risk officer approved it."},
        label="chair",
    )
    emit({"type": "agent_done", "id": "chief", "name": roles["chief"]["name"], "layer": "chair",
          "output": summary, "call": _call_meta(rec), "raw": _raw(rec)})
    m.decision = {"choice": choice.model_dump() if choice else None, "totals": totals, **summary}
    emit({"type": "decision", "decision": m.decision})
    return m

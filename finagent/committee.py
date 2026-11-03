"""Orchestrator: researchers -> chair drafts proposals -> masters score -> devil -> risk veto -> chair."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import llm, risk
from .engine import Allocation
from .models import Profile

ROLES = Path(__file__).with_name("roles.yaml")


@dataclass
class Meeting:
    signal_cards: list[dict] = field(default_factory=list)
    proposals: list[risk.Proposal] = field(default_factory=list)
    scores: dict[str, dict[str, int]] = field(default_factory=dict)  # master -> proposal -> 1..5
    devil: dict = field(default_factory=dict)
    verdicts: list[risk.Verdict] = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    mock: bool = True


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


def _mock_scores(master: str) -> dict[str, int]:
    table = {
        "buffett": {"A": 4, "B": 4, "C": 3},
        "lynch": {"A": 3, "B": 3, "C": 3},
        "bogle": {"A": 5, "B": 4, "C": 4},
        "dalio": {"A": 4, "B": 5, "C": 4},
        "kostolany": {"A": 3, "B": 3, "C": 4},
    }
    return table.get(master, {"A": 3, "B": 3, "C": 3})


def run(profile: Profile, alloc: Allocation, feats: dict[str, dict]) -> Meeting:
    roles = yaml.safe_load(ROLES.read_text(encoding="utf-8"))
    m = Meeting(mock=llm.is_mock())
    prices = {s: f["last"] for s, f in feats.items()}
    facts = json.dumps(feats, ensure_ascii=False)

    for r in roles["researchers"]:
        card = llm.chat_json(
            r["tier"],
            f"You are the '{r['name']}' researcher on a Taiwan-stock committee. Focus: {r['focus']} "
            "Cite ONLY the numbers given. Output keys: role, direction (bullish|neutral|bearish), strength (1-5), evidence.",
            f"Market facts: {facts}",
            mock=_mock_card(r, feats),
        )
        card.setdefault("role", r["id"])
        m.signal_cards.append(card)

    if alloc.investable <= 0:
        m.decision = {"choice": None, "summary": "No investing this month. " + " ".join(alloc.reasons)}
        return m

    m.proposals = _draft_proposals(alloc.investable, prices)
    plist = json.dumps([p.model_dump() for p in m.proposals], ensure_ascii=False)
    cards = json.dumps(m.signal_cards, ensure_ascii=False)

    for ms in roles["masters"]:
        out = llm.chat_json(
            "small",
            f"You are {ms['name']}. Check: {ms['checks']} Score each proposal 1-5. Output: {{\"scores\": {{\"A\": n, ...}}}}",
            f"Proposals: {plist}\nSignal cards: {cards}",
            mock={"scores": _mock_scores(ms["id"])},
        )
        m.scores[ms["id"]] = {k: int(v) for k, v in out.get("scores", {}).items()}

    totals = {p.id: sum(s.get(p.id, 0) for s in m.scores.values()) for p in m.proposals}
    # tie -> earlier (more conservative) proposal wins; proposals are ordered conservative-first
    best = max(m.proposals, key=lambda p: (totals[p.id], -m.proposals.index(p)))

    m.devil = llm.chat_json(
        "chief",
        "You are the devil's advocate. Attack the winning proposal: strongest counter-argument and what would prove it wrong.",
        f"Winner: {best.model_dump_json()}\nSignal cards: {cards}",
        mock={"attack": f"{best.title}: if 0050 keeps rising above MA60 you buy the top; split the buy instead.",
              "falsifier": "3 months later return below a 2-tranche split buy."},
    )

    m.verdicts = [risk.check(profile, p, alloc.investable, prices) for p in m.proposals]
    ok = {v.proposal_id for v in m.verdicts if v.approved}
    ranked = sorted(m.proposals, key=lambda p: (-totals[p.id], m.proposals.index(p)))
    choice = next((p for p in ranked if p.id in ok), None)

    summary = llm.chat_json(
        "chief",
        "You chair the committee. Explain the final choice in 3 short sentences for a student. Output: {\"summary\": str}",
        f"Totals: {totals}\nChoice: {choice.model_dump_json() if choice else None}\nDevil: {m.devil}\nRisk: {[v.model_dump() for v in m.verdicts]}",
        mock={"summary": f"Chose {choice.title if choice else 'nothing'} (score {totals.get(choice.id) if choice else '-'}). "
                         "Bills and emergency fund are covered first; the risk officer approved it."},
    )
    m.decision = {"choice": choice.model_dump() if choice else None, "totals": totals, **summary}
    return m

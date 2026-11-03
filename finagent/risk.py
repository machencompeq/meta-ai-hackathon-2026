"""Risk officer = rule engine. LLMs can explain a veto, never override it."""
from __future__ import annotations

from pydantic import BaseModel

from .models import Profile


class Order(BaseModel):
    symbol: str
    side: str  # "buy" | "sell"
    amount: float  # TWD
    price: float
    margin: bool = False


class Proposal(BaseModel):
    id: str
    title: str
    orders: list[Order]
    rationale: str = ""


class Verdict(BaseModel):
    proposal_id: str
    approved: bool
    violations: list[str]


def check(profile: Profile, proposal: Proposal, investable: float, prices: dict[str, float]) -> Verdict:
    pol = profile.policy
    v: list[str] = []
    held = {h.symbol: h for h in profile.holdings}

    buy_total = sum(o.amount for o in proposal.orders if o.side == "buy")
    if buy_total > investable + 1e-6:
        v.append(f"Buys {buy_total:,.0f} exceed investable {investable:,.0f} (bills/emergency fund first).")

    for o in proposal.orders:
        if o.margin and not pol.allow_margin:
            v.append(f"{o.symbol}: margin / borrowing is forbidden.")
        h = held.get(o.symbol)
        if o.side == "sell" and h and pol.sell_only_above_cost and o.price < h.avg_cost:
            v.append(f"{o.symbol}: selling below cost ({o.price} < {h.avg_cost}) is forbidden.")
        if o.side == "buy" and h and (h.high_risk or h.leveraged):
            v.append(f"{o.symbol}: user flagged as high-risk/leveraged, no adding.")

    # post-trade concentration
    value = {h.symbol: h.shares * prices.get(h.symbol, h.avg_cost) for h in profile.holdings}
    lev = {h.symbol for h in profile.holdings if h.leveraged}
    for o in proposal.orders:
        value[o.symbol] = value.get(o.symbol, 0.0) + (o.amount if o.side == "buy" else -o.amount)
    total = sum(max(x, 0.0) for x in value.values())
    if total > 0:
        for sym, x in value.items():
            if x / total > pol.max_single_holding_pct + 1e-9 and any(o.symbol == sym and o.side == "buy" for o in proposal.orders):
                v.append(f"{sym}: would be {x / total:.0%} of portfolio (> {pol.max_single_holding_pct:.0%}).")
        lev_pct = sum(value.get(s, 0.0) for s in lev) / total
        if lev_pct > pol.max_leveraged_pct and any(o.symbol in lev and o.side == "buy" for o in proposal.orders):
            v.append(f"Leveraged ETFs would be {lev_pct:.0%} (> {pol.max_leveraged_pct:.0%}).")

    return Verdict(proposal_id=proposal.id, approved=not v, violations=v)

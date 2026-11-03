"""Deterministic money math. No LLM here: everything is unit-tested."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Profile


@dataclass
class CashDay:
    day: date
    balance: float
    events: list[str] = field(default_factory=list)


@dataclass
class CashPlan:
    days: list[CashDay]
    lowest_balance: float
    lowest_day: date
    shortfall_days: list[date]
    transfers: list[str]  # human-readable fixes, e.g. "Move 3,000 from emergency fund before 11/10"


def _hits(d: date, day_of_month: int) -> bool:
    last = calendar.monthrange(d.year, d.month)[1]
    return d.day == min(day_of_month, last)


def simulate_cash(profile: Profile, horizon_days: int = 60) -> CashPlan:
    """Walk day by day over liquid accounts, applying incomes and obligations."""
    balance = profile.liquid_balance
    months_used: dict[str, set[tuple[int, int]]] = {}
    days: list[CashDay] = []
    shortfalls: list[date] = []
    buffer = profile.policy.min_cash_buffer

    for i in range(1, horizon_days + 1):
        d = profile.today + timedelta(days=i)
        events: list[str] = []
        for inc in profile.incomes:
            if _hits(d, inc.day_of_month):
                balance += inc.amount
                events.append(f"+{inc.amount:,.0f} {inc.name}")
        for ob in profile.obligations:
            if not _hits(d, ob.day_of_month):
                continue
            seen = months_used.setdefault(ob.name, set())
            if ob.months_left is not None and len(seen) >= ob.months_left:
                continue
            seen.add((d.year, d.month))
            balance -= ob.amount
            events.append(f"-{ob.amount:,.0f} {ob.name}")
        days.append(CashDay(d, round(balance, 2), events))
        if balance < buffer:
            shortfalls.append(d)

    low = min(days, key=lambda x: x.balance) if days else CashDay(profile.today, balance)
    transfers: list[str] = []
    gap = buffer - low.balance
    if gap > 0:
        first = shortfalls[0]
        from_ef = min(profile.emergency_fund, gap)
        if from_ef > 0:
            transfers.append(f"Move {from_ef:,.0f} from emergency fund before {first.isoformat()}")
        if gap - from_ef > 0:
            transfers.append(f"Still short {gap - from_ef:,.0f}: extra income or cut spending before {first.isoformat()}")
    return CashPlan(days, low.balance, low.day, shortfalls, transfers)


@dataclass
class Allocation:
    bills_covered: bool
    to_emergency_fund: float
    investable: float
    reasons: list[str]


def investable_amount(profile: Profile, plan: CashPlan) -> Allocation:
    """Order: bills first -> emergency fund to target -> only then invest."""
    reasons: list[str] = []
    if plan.shortfall_days:
        reasons.append(f"Cash goes below buffer on {plan.shortfall_days[0]}: invest 0, fix bills first.")
        return Allocation(False, 0.0, 0.0, reasons)

    surplus = plan.lowest_balance - profile.policy.min_cash_buffer - profile.policy.reserved_short_term
    surplus = max(surplus, 0.0)
    reasons.append(f"Lowest projected balance {plan.lowest_balance:,.0f}; spare above buffer {surplus:,.0f}.")

    ef_gap = max(profile.policy.emergency_fund_target - profile.emergency_fund, 0.0)
    to_ef = min(ef_gap, surplus)
    if to_ef:
        reasons.append(f"Emergency fund short by {ef_gap:,.0f}: put {to_ef:,.0f} there first.")
    investable = round(surplus - to_ef, 2)
    reasons.append(f"Investable this month: {investable:,.0f}.")
    return Allocation(True, round(to_ef, 2), investable, reasons)

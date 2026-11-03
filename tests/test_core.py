from datetime import date
from pathlib import Path

from finagent import committee, engine, market, risk
from finagent.models import Account, Holding, Obligation, IncomeRule, Policy, Profile

EX = Path(__file__).resolve().parent.parent / "examples" / "personas"


def load(name: str) -> Profile:
    return Profile.model_validate_json((EX / name).read_text(encoding="utf-8"))


def tiny(balance: float, bill: float, ef: float = 0, target: float = 0) -> Profile:
    return Profile(
        name="t", today=date(2026, 11, 3),
        accounts=[Account(id="b", name="b", kind="bank", balance=balance),
                  Account(id="e", name="e", kind="savings_goal", balance=ef)],
        obligations=[Obligation(name="bill", amount=bill, day_of_month=10, account_id="b", months_left=1)],
        incomes=[IncomeRule(name="pay", amount=10000, day_of_month=15, account_id="b")],
        holdings=[Holding(symbol="0050", shares=10, avg_cost=200)],
        policy=Policy(emergency_fund_target=target, min_cash_buffer=1000, max_single_holding_pct=1.0),
    )


def test_shortfall_detected_and_transfer_suggested():
    p = load("short_on_cash.json")
    plan = engine.simulate_cash(p, 30)
    assert plan.shortfall_days[0] == date(2026, 11, 8)
    assert plan.lowest_balance == 4200 - 8800 - 6000  # card bill and rent both land before payday
    assert plan.transfers[0].startswith("Move 9,000 from emergency fund")
    assert plan.transfers[1].startswith("Still short 2,600")
    assert engine.investable_amount(p, plan).investable == 0


def test_emergency_fund_before_investing():
    p = tiny(balance=9000, bill=2000, ef=1000, target=4000)
    plan = engine.simulate_cash(p, 20)
    a = engine.investable_amount(p, plan)
    assert plan.lowest_balance == 7000
    assert a.to_emergency_fund == 3000          # gap 3000 filled first
    assert a.investable == 7000 - 1000 - 3000   # minus buffer, minus EF


def test_month_end_due_day_clamps():
    p = tiny(5000, 100)
    p.obligations[0].day_of_month = 31
    plan = engine.simulate_cash(p, 30)
    assert any("bill" in e for d in plan.days if d.day == date(2026, 11, 30) for e in d.events)


def test_risk_vetoes():
    p = tiny(10000, 0)
    p.holdings.append(Holding(symbol="LEV", shares=100, avg_cost=10, leveraged=True, high_risk=True))
    prices = {"0050": 150, "LEV": 8}
    sell_loss = risk.Proposal(id="s", title="", orders=[risk.Order(symbol="0050", side="sell", amount=1500, price=150)])
    add_lev = risk.Proposal(id="l", title="", orders=[risk.Order(symbol="LEV", side="buy", amount=100, price=8)])
    too_big = risk.Proposal(id="b", title="", orders=[risk.Order(symbol="0050", side="buy", amount=5000, price=150)])
    margin = risk.Proposal(id="m", title="", orders=[risk.Order(symbol="0050", side="buy", amount=10, price=150, margin=True)])
    assert not risk.check(p, sell_loss, 1000, prices).approved
    assert not risk.check(p, add_lev, 1000, prices).approved
    assert not risk.check(p, too_big, 1000, prices).approved
    assert not risk.check(p, margin, 1000, prices).approved
    ok = risk.Proposal(id="ok", title="", orders=[risk.Order(symbol="0050", side="buy", amount=900, price=150)])
    assert risk.check(p, ok, 1000, prices).approved


def test_full_meeting_offline(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    p = load("student.json")
    plan = engine.simulate_cash(p, 60)
    alloc = engine.investable_amount(p, plan)
    feats = {s: market.features(c) for s, c in market.load_sample().items()}
    m = committee.run(p, alloc, feats)
    assert len(m.signal_cards) == 4
    assert set(m.scores) == {"buffett", "lynch", "bogle", "dalio", "kostolany"}
    choice = m.decision["choice"]
    if alloc.investable > 0:
        assert choice is not None
        assert sum(o["amount"] for o in choice["orders"]) <= alloc.investable + 1

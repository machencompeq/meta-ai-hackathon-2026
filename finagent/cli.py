"""python -m finagent.cli examples/personas/student.json  ->  out/<name>_report.html + decision log JSON"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path

from . import committee, engine, market
from .models import Profile


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--out", default="out")
    ap.add_argument("--days", type=int, default=60)
    a = ap.parse_args()

    profile = Profile.model_validate_json(Path(a.profile).read_text(encoding="utf-8"))
    plan = engine.simulate_cash(profile, a.days)
    alloc = engine.investable_amount(profile, plan)
    feats = {s: market.features(c) for s, c in market.load_sample().items()}
    meeting = committee.run(profile, alloc, feats)

    out = Path(a.out)
    out.mkdir(exist_ok=True)
    stem = profile.name.lower().replace(" ", "_")
    log = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mock_llm": meeting.mock,
        "profile": profile.name,
        "cash": {"lowest": plan.lowest_balance, "lowest_day": plan.lowest_day.isoformat(),
                 "shortfall_days": [d.isoformat() for d in plan.shortfall_days], "transfers": plan.transfers},
        "allocation": alloc.__dict__,
        "signal_cards": meeting.signal_cards,
        "proposals": [p.model_dump() for p in meeting.proposals],
        "scores": meeting.scores,
        "devil": meeting.devil,
        "risk": [v.model_dump() for v in meeting.verdicts],
        "decision": meeting.decision,
    }
    (out / f"{stem}_decision.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{stem}_report.html").write_text(render(profile, plan, log), encoding="utf-8")
    print(json.dumps(log["decision"], ensure_ascii=False, indent=2))
    print(f"report: {out / (stem + '_report.html')}")


def render(profile: Profile, plan: engine.CashPlan, log: dict) -> str:
    e = html.escape
    rows = "".join(
        f"<tr class='{'bad' if d.balance < profile.policy.min_cash_buffer else ''}'><td>{d.day}</td>"
        f"<td>{d.balance:,.0f}</td><td>{e('; '.join(d.events))}</td></tr>"
        for d in plan.days if d.events
    )
    cards = "".join(f"<li><b>{e(str(c.get('role')))}</b> {e(str(c.get('direction')))} ({c.get('strength')}): {e(str(c.get('evidence')))}</li>"
                    for c in log["signal_cards"])
    risk_rows = "".join(f"<li>{v['proposal_id']}: {'APPROVED' if v['approved'] else 'VETO — ' + e('; '.join(v['violations']))}</li>"
                        for v in log["risk"])
    return f"""<!doctype html><meta charset="utf-8"><title>{e(profile.name)} monthly plan</title>
<style>body{{font-family:system-ui;max-width:860px;margin:2em auto;padding:0 16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #ddd;padding:4px}}.bad{{background:#fdd}}</style>
<h1>{e(profile.name)} — monthly plan</h1>
<p>LLM mode: {'offline mock' if log['mock_llm'] else 'Meta Model API'}</p>
<h2>1. Can I pay every bill?</h2>
<p>Lowest balance {plan.lowest_balance:,.0f} on {plan.lowest_day}. {e(' '.join(plan.transfers) or 'No shortfall.')}</p>
<table>{rows}</table>
<h2>2. How much can I invest?</h2><ul>{''.join(f'<li>{e(r)}</li>' for r in log['allocation']['reasons'])}</ul>
<h2>3. Committee</h2><h3>Signal cards</h3><ul>{cards}</ul>
<h3>Scores</h3><pre>{e(json.dumps(log['scores'], indent=1))}</pre>
<h3>Devil's advocate</h3><pre>{e(json.dumps(log['devil'], ensure_ascii=False, indent=1))}</pre>
<h3>Risk officer (rules, not LLM)</h3><ul>{risk_rows}</ul>
<h2>Decision</h2><p>{e(str(log['decision'].get('summary', '')))}</p>
<p><small>AI role-play, not financial advice. Never places orders.</small></p>"""


if __name__ == "__main__":
    main()

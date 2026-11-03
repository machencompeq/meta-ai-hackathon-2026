# Paycheck Committee — a Meta-model finance agent for people living paycheck to paycheck

Meta Global AI Developer Hackathon 2026 · Indie Dev Track

Every month it answers two questions:

1. **Can I pay every bill on time?** A day-by-day cash simulation finds the lowest balance and any shortfall, then lists the exact transfers to make.
2. **How much can I safely invest, and in what?** Bills come first, then the emergency fund. Whatever is left goes to an **investment committee of agents**: researcher agents write signal cards from market data, "master" personas (Buffett, Lynch, Bogle, Dalio, Kostolany) score 2–3 proposals, a devil's advocate attacks the winner, and a **risk officer that is a rule engine, not an LLM**, vetoes anything that breaks hard rules.

> All money math and rules are deterministic Python with unit tests. LLMs only interpret, argue and explain. The agent never places orders.

## Architecture

```
profile JSON / CSV ─► models.py (pydantic unified model)
                          │
                          ▼
                    engine.py ── simulate_cash() ─► shortfalls + transfers
                          │      investable_amount(): bills → emergency fund → invest
                          ▼
market.py (TWSE open data / offline sample) ─► features (MA20, MA60, 20d change)
                          │
                          ▼
committee.py  (roles.yaml, config-driven)
   4 researchers ──► signal cards        [Meta model, small tier]
   code drafts proposals (amounts from engine, never from LLM)
   5 masters ──► 1–5 scores              [Meta model, small tier]
   devil's advocate ──► attack           [Meta model, chief tier]
   risk.py ──► APPROVED / VETO           [rules only]
   chair ──► plain-language summary      [Meta model, chief tier]
                          │
                          ▼
cli.py ─► out/<name>_report.html + out/<name>_decision.json (decision log)
```

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
python -m finagent.cli examples/personas/student.json        # can invest
python -m finagent.cli examples/personas/short_on_cash.json  # shortfall -> invest 0
```

Without `META_API_KEY` it runs in **offline mock mode**, so the demo works anywhere. To use Meta models:

```bash
cp .env.example .env   # fill in, never commit
export META_API_KEY=...            # Meta Model API key
export META_MODEL_CHIEF=...        # e.g. Muse Spark model id
export META_MODEL_SMALL=...        # smaller / cheaper model id
```

## Meta models used

| Role | Tier | Model |
|---|---|---|
| Researchers, masters | small | `META_MODEL_SMALL` (smaller Meta model or open weights run locally) |
| Chair, devil's advocate | chief | `META_MODEL_CHIEF` (Muse Spark) |

## Hard rules (risk officer)

- Buys never exceed this month's investable amount (bills and emergency fund first)
- No selling below average cost
- No adding to positions the user flagged high-risk or leveraged
- Single-holding cap and leveraged-ETF cap after the trade
- No margin, no borrowing

## Data and privacy

All personas and market prices in `examples/` are **synthetic**. No real ledgers, accounts or keys are in this repo.

## Disclaimer

AI role-play for education, not licensed financial advice.

"""Unified data model. Every importer (CSV, natural-language, PDF) produces a Profile."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Account(BaseModel):
    id: str
    name: str
    kind: Literal["cash", "bank", "credit_card", "brokerage", "savings_goal"]
    balance: float = 0.0
    # credit cards only
    statement_day: int | None = None
    due_day: int | None = None
    credit_limit: float | None = None


class Transaction(BaseModel):
    date: date
    account_id: str
    amount: float  # +income / -expense
    category: str = "other"
    note: str = ""


class Obligation(BaseModel):
    """A recurring or one-off bill: rent, phone, card bill, installment."""

    name: str
    amount: float
    day_of_month: int
    account_id: str
    months_left: int | None = None  # None = indefinite


class IncomeRule(BaseModel):
    name: str
    amount: float
    day_of_month: int
    account_id: str


class Holding(BaseModel):
    symbol: str
    name: str = ""
    shares: float
    avg_cost: float
    leveraged: bool = False
    high_risk: bool = False  # user-flagged: no adding


class Policy(BaseModel):
    emergency_fund_target: float
    min_cash_buffer: float = 0.0
    max_single_holding_pct: float = 0.30
    max_leveraged_pct: float = 0.10
    sell_only_above_cost: bool = True
    allow_margin: bool = False
    reserved_short_term: float = 0.0  # money needed within 3 years, never invested
    watchlist: list[str] = Field(default_factory=lambda: ["0050", "006208", "0056", "00878"])


class Profile(BaseModel):
    name: str
    persona: str = ""
    today: date
    accounts: list[Account]
    obligations: list[Obligation] = Field(default_factory=list)
    incomes: list[IncomeRule] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    holdings: list[Holding] = Field(default_factory=list)
    policy: Policy

    @property
    def liquid_balance(self) -> float:
        return sum(a.balance for a in self.accounts if a.kind in ("cash", "bank"))

    @property
    def emergency_fund(self) -> float:
        return sum(a.balance for a in self.accounts if a.kind == "savings_goal")

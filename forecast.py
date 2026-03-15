from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from calendar import monthrange

from db import get_account_by_name, get_latest_account_snapshot, get_transaction_rules, is_rule_expired


@dataclass(frozen=True)
class ForecastEvent:
    event_date: date
    account_name: str
    description: str
    amount: float
    event_type: str
    source_rule_id: int | None = None
    related_descriptions: list[str] | None = None
    related_count: int = 0


@dataclass(frozen=True)
class ForecastResult:
    account_name: str
    start_date: date
    end_date: date
    opening_balance: float
    closing_balance: float
    min_balance: float
    min_balance_date: date
    max_balance: float
    max_balance_date: date
    events: list[ForecastEvent]


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _last_day_of_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _add_months(base_date: date, months: int) -> date:
    month_index = (base_date.month - 1) + months
    year = base_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base_date.day, _last_day_of_month(year, month))
    return date(year, month, day)


def _build_event_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, _last_day_of_month(year, month)))


def _rule_is_effective(rule: dict, target_date: date) -> bool:
    if not rule["active"]:
        return False
    if is_rule_expired(rule["end_date"], today=target_date):
        return False

    start_date = _parse_iso_date(rule["start_date"])
    end_date = _parse_iso_date(rule["end_date"])

    if start_date and target_date < start_date:
        return False
    if end_date and target_date > end_date:
        return False
    return True


def _iter_rule_dates(rule: dict, start_date: date, end_date: date) -> list[date]:
    dates: list[date] = []

    if rule["frequency"] == "monthly":
        current = date(start_date.year, start_date.month, 1)
        while current <= end_date:
            due_date = _build_event_date(current.year, current.month, int(rule["day_of_month"]))
            if start_date <= due_date <= end_date and _rule_is_effective(rule, due_date):
                dates.append(due_date)
            current = _add_months(current, 1)
        return dates

    for year in range(start_date.year, end_date.year + 1):
        due_date = _build_event_date(year, int(rule["month_of_year"]), int(rule["day_of_month"]))
        if start_date <= due_date <= end_date and _rule_is_effective(rule, due_date):
            dates.append(due_date)
    return dates


def _next_settlement_date(event_date: date, settlement_day: int) -> date:
    next_month = _add_months(date(event_date.year, event_date.month, 1), 1)
    return _build_event_date(next_month.year, next_month.month, settlement_day)


def build_account_forecast(
    account_name: str,
    start_date: date,
    end_date: date,
    opening_balance: float | None = None,
) -> ForecastResult:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    account = get_account_by_name(account_name)
    if account is None:
        raise ValueError(f"Unknown account: {account_name}")

    if opening_balance is None:
        snapshot = get_latest_account_snapshot(account["id"], start_date.isoformat())
        if snapshot is None:
            raise ValueError(
                f"No snapshot available for {account_name} on or before {start_date.isoformat()}"
            )
        opening_balance = float(snapshot["balance"])

    rules = [dict(row) for row in get_transaction_rules() if row["account_name"] == account_name]

    direct_events: list[ForecastEvent] = []
    card_buckets: dict[date, list[ForecastEvent]] = defaultdict(list)

    for rule in rules:
        for due_date in _iter_rule_dates(rule, start_date, end_date):
            payment_method = (rule["payment_method"] or "conto").lower()
            if payment_method == "carta":
                settlement_day = int(rule["card_settlement_day"] or 10)
                settlement_date = _next_settlement_date(due_date, settlement_day)
                if settlement_date <= end_date:
                    card_buckets[settlement_date].append(
                        ForecastEvent(
                            event_date=due_date,
                            account_name=account_name,
                            description=rule["description"],
                            amount=float(rule["amount"]),
                            event_type="card_spend",
                            source_rule_id=int(rule["id"]),
                        )
                    )
                continue

            direct_events.append(
                ForecastEvent(
                    event_date=due_date,
                    account_name=account_name,
                    description=rule["description"],
                    amount=float(rule["amount"]),
                    event_type="direct",
                    source_rule_id=int(rule["id"]),
                )
            )

    settlement_events: list[ForecastEvent] = []
    for settlement_date, spends in sorted(card_buckets.items()):
        total_amount = sum(event.amount for event in spends)
        description = "Carta di credito"
        if len(spends) == 1:
            description = f"Carta di credito ({spends[0].description})"
        settlement_events.append(
            ForecastEvent(
                event_date=settlement_date,
                account_name=account_name,
                description=description,
                amount=total_amount,
                event_type="card_settlement",
                source_rule_id=None,
                related_descriptions=[event.description for event in spends],
                related_count=len(spends),
            )
        )

    events = sorted(
        direct_events + settlement_events,
        key=lambda event: (event.event_date, event.event_type, event.description),
    )

    closing_balance = opening_balance
    min_balance = opening_balance
    min_balance_date = start_date
    max_balance = opening_balance
    max_balance_date = start_date

    for event in events:
        closing_balance += event.amount
        if closing_balance < min_balance:
            min_balance = closing_balance
            min_balance_date = event.event_date
        if closing_balance > max_balance:
            max_balance = closing_balance
            max_balance_date = event.event_date

    return ForecastResult(
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        min_balance=min_balance,
        min_balance_date=min_balance_date,
        max_balance=max_balance,
        max_balance_date=max_balance_date,
        events=events,
    )

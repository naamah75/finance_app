from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from calendar import monthrange

from db import (
    get_account_by_name,
    get_forecast_event_overrides,
    get_latest_account_snapshot,
    get_manual_events,
    get_transaction_rules,
    is_rule_expired,
)


@dataclass(frozen=True)
class ForecastEvent:
    event_date: date
    ledger_date: date
    original_event_date: date
    account_name: str
    description: str
    original_description: str
    amount: float
    original_amount: float
    event_type: str
    source_rule_id: int | None = None
    source_manual_event_id: int | None = None
    account_id: int | None = None
    payment_method: str | None = None
    note: str | None = None
    override_id: int | None = None
    override_status: str | None = None
    override_resolution_mode: str | None = None
    override_description: str | None = None
    override_event_date: date | None = None
    override_amount: float | None = None
    carried_overdue: bool = False
    related_descriptions: list[str] | None = None
    related_count: int = 0


@dataclass(frozen=True)
class ForecastResult:
    account_name: str
    start_date: date
    end_date: date
    opening_balance: float
    closing_balance: float
    overdraft_limit: float
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
            due_date = _build_event_date(
                current.year, current.month, int(rule["day_of_month"])
            )
            if start_date <= due_date <= end_date and _rule_is_effective(
                rule, due_date
            ):
                dates.append(due_date)
            current = _add_months(current, 1)
        return dates

    for year in range(start_date.year, end_date.year + 1):
        due_date = _build_event_date(
            year, int(rule["month_of_year"]), int(rule["day_of_month"])
        )
        if start_date <= due_date <= end_date and _rule_is_effective(rule, due_date):
            dates.append(due_date)
    return dates


def _next_settlement_date(event_date: date, settlement_day: int) -> date:
    next_month = _add_months(date(event_date.year, event_date.month, 1), 1)
    return _build_event_date(next_month.year, next_month.month, settlement_day)


def _is_planned_credit_card_rule(event: ForecastEvent) -> bool:
    return event.description.strip().lower() == "carta di credito"


def _format_description_amount(value: float) -> str:
    text = f"{abs(value):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _build_override_map(account_id: int) -> dict[tuple[int, date], dict]:
    overrides = [dict(row) for row in get_forecast_event_overrides(account_id)]
    return {
        (int(item["rule_id"]), date.fromisoformat(item["original_event_date"])): item
        for item in overrides
    }


def _earliest_open_override_date(
    overrides: dict[tuple[int, date], dict],
) -> date | None:
    open_dates = [
        key[1] for key, value in overrides.items() if value["status"] == "open"
    ]
    return min(open_dates) if open_dates else None


def _apply_override(
    event: ForecastEvent,
    override_map: dict[tuple[int, date], dict],
    start_date: date,
) -> ForecastEvent | None:
    if event.source_rule_id is None:
        return event

    override = override_map.get((int(event.source_rule_id), event.original_event_date))
    if override is None:
        return event

    status = override["status"] or "open"
    if status in {"resolved", "cancelled"}:
        return None

    override_event_date = (
        date.fromisoformat(override["override_event_date"])
        if override["override_event_date"]
        else None
    )
    override_amount = (
        float(override["override_amount"])
        if override["override_amount"] is not None
        else None
    )
    resolution_mode = override.get("resolution_mode") or "auto"
    effective_date = override_event_date or event.event_date
    override_description = override.get("override_description")
    carried_overdue = (
        resolution_mode == "manual" and effective_date < start_date and status == "open"
    )

    return ForecastEvent(
        event_date=effective_date,
        ledger_date=start_date if carried_overdue else effective_date,
        original_event_date=event.original_event_date,
        account_name=event.account_name,
        description=override_description or event.description,
        original_description=event.original_description,
        amount=override_amount if override_amount is not None else event.amount,
        original_amount=event.original_amount,
        event_type=event.event_type,
        source_rule_id=event.source_rule_id,
        source_manual_event_id=event.source_manual_event_id,
        account_id=event.account_id,
        payment_method=event.payment_method,
        note=event.note,
        override_id=int(override["id"]),
        override_status=status,
        override_resolution_mode=resolution_mode,
        override_description=override_description,
        override_event_date=override_event_date,
        override_amount=override_amount,
        carried_overdue=carried_overdue,
        related_descriptions=event.related_descriptions,
        related_count=event.related_count,
    )


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

    overdraft_limit = float(account["overdraft_limit"] or 0)
    account_id = int(account["id"])

    rules = [
        dict(row)
        for row in get_transaction_rules()
        if row["account_name"] == account_name
    ]
    override_map = _build_override_map(account_id)
    earliest_override_date = _earliest_open_override_date(override_map)
    generation_start = (
        min(start_date, earliest_override_date)
        if earliest_override_date
        else start_date
    )

    direct_events: list[ForecastEvent] = []
    planned_card_events: dict[date, list[ForecastEvent]] = defaultdict(list)
    card_buckets: dict[date, list[ForecastEvent]] = defaultdict(list)

    for rule in rules:
        for due_date in _iter_rule_dates(rule, generation_start, end_date):
            payment_method = (rule["payment_method"] or "conto").lower()
            base_event = ForecastEvent(
                event_date=due_date,
                ledger_date=due_date,
                original_event_date=due_date,
                account_name=account_name,
                description=rule["description"],
                original_description=rule["description"],
                amount=float(rule["amount"]),
                original_amount=float(rule["amount"]),
                event_type="card_spend" if payment_method == "carta" else "direct",
                source_rule_id=int(rule["id"]),
                account_id=account_id,
                payment_method=rule["payment_method"],
            )
            event = _apply_override(base_event, override_map, start_date)
            if event is None or not (start_date <= event.ledger_date <= end_date):
                continue

            if payment_method == "carta":
                settlement_day = int(rule["card_settlement_day"] or 10)
                settlement_date = _next_settlement_date(
                    event.event_date, settlement_day
                )
                if settlement_date <= end_date:
                    card_buckets[settlement_date].append(event)
                continue

            if _is_planned_credit_card_rule(event):
                planned_card_events[event.event_date].append(event)
                continue

            direct_events.append(event)

    settlement_events: list[ForecastEvent] = []
    for settlement_date in sorted(
        set(card_buckets.keys()) | set(planned_card_events.keys())
    ):
        spends = card_buckets.get(settlement_date, [])
        planned = planned_card_events.get(settlement_date, [])
        total_amount = sum(event.amount for event in spends)
        planned_amount = sum(event.amount for event in planned)
        description = "Carta di credito"
        if spends and planned:
            description = (
                "Carta di credito "
                f"({_format_description_amount(total_amount)}+{_format_description_amount(planned_amount)})"
            )
        elif len(spends) == 1 and not planned:
            description = f"Carta di credito ({spends[0].description})"
        settlement_events.append(
            ForecastEvent(
                event_date=settlement_date,
                ledger_date=settlement_date,
                original_event_date=settlement_date,
                account_name=account_name,
                description=description,
                original_description=description,
                amount=total_amount + planned_amount,
                original_amount=total_amount + planned_amount,
                event_type="card_settlement",
                source_rule_id=None,
                account_id=account_id,
                related_descriptions=[event.description for event in spends]
                + [event.description for event in planned],
                related_count=len(spends) + len(planned),
            )
        )

    manual_events = [
        dict(row)
        for row in get_manual_events(
            account_id, start_date.isoformat(), end_date.isoformat()
        )
    ]
    extra_events: list[ForecastEvent] = []
    for manual_event in manual_events:
        if (manual_event["status"] or "open") != "open":
            continue
        event_date = date.fromisoformat(manual_event["event_date"])
        extra_events.append(
            ForecastEvent(
                event_date=event_date,
                ledger_date=event_date,
                original_event_date=event_date,
                account_name=account_name,
                description=manual_event["description"],
                original_description=manual_event["description"],
                amount=float(manual_event["amount"]),
                original_amount=float(manual_event["amount"]),
                event_type="manual",
                source_rule_id=None,
                source_manual_event_id=int(manual_event["id"]),
                account_id=account_id,
                payment_method=manual_event["payment_method"],
                note=manual_event["note"],
            )
        )

    events = sorted(
        direct_events + settlement_events + extra_events,
        key=lambda event: (
            event.ledger_date,
            event.event_date,
            event.event_type,
            event.description,
        ),
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
            min_balance_date = event.ledger_date
        if closing_balance > max_balance:
            max_balance = closing_balance
            max_balance_date = event.ledger_date

    return ForecastResult(
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        overdraft_limit=overdraft_limit,
        min_balance=min_balance,
        min_balance_date=min_balance_date,
        max_balance=max_balance,
        max_balance_date=max_balance_date,
        events=events,
    )

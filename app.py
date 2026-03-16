from datetime import date, datetime

from nicegui import ui

from db import (
    add_manual_event,
    delete_forecast_event_override,
    get_account_by_name,
    get_accounts,
    get_forecast_event_override,
    get_latest_account_snapshot,
    get_setting,
    get_transaction_rules,
    init_db,
    is_rule_expired,
    set_account_overdraft_limit,
    set_manual_event_status,
    set_setting,
    set_transaction_rule_active,
    update_manual_event,
    upsert_forecast_event_override,
    upsert_account_snapshot,
)
from forecast import build_account_forecast


def format_balance(balance: float | None) -> str:
    if balance is None:
        return "nessuno snapshot"
    return f"{balance:.2f}"


def format_currency(amount: float | None) -> str:
    if amount is None:
        return "0.00"
    return f"{amount:.2f}"


def format_ui_date(value: date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d-%m-%Y")


def parse_ui_date(value: str) -> date:
    return datetime.strptime(value, "%d-%m-%Y").date()


def format_overdraft_limit(value: float | None) -> str:
    if not value:
        return "nessun fido"
    return f"fido € {value:.2f}"


def get_warning_margin() -> float:
    raw_value = get_setting("warning_margin", "300") or "300"
    try:
        margin = float(raw_value)
    except ValueError:
        margin = 300.0
    return max(0.0, margin)


def month_background(month: int) -> str:
    palette = {
        1: "#f3d9cf",
        2: "#efe0b8",
        3: "#d9e8bc",
        4: "#c9ead6",
        5: "#c4ebe4",
        6: "#cbe0ef",
        7: "#d4d8f3",
        8: "#dfd2f3",
        9: "#eccff0",
        10: "#f0d2c3",
        11: "#e8dcc7",
        12: "#d9d6df",
    }
    return palette.get(month, "#fcf8f4")


def add_months(base_date: date, months: int) -> date:
    month_index = (base_date.month - 1) + months
    year = base_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base_date.day, 28)
    return date(year, month, day)


def get_forecast_window_months() -> int:
    raw_value = get_setting("forecast_window_months", "3") or "3"
    try:
        months = int(raw_value)
    except ValueError:
        months = 3
    return max(1, months)


def format_cadence(rule: dict) -> str:
    if rule["frequency"] == "yearly" and rule["month_of_year"]:
        return f"{rule['day_of_month']}/{rule['month_of_year']}"
    return f"giorno {rule['day_of_month']}"


def get_rule_status(rule: dict) -> tuple[str, str]:
    if is_rule_expired(rule["end_date"]):
        return "Scaduta", "#8b5e00"
    if rule["active"]:
        return "Attiva", "#1f7a1f"
    return "Disattivata", "#8a1c1c"


def load_rules(account_filter: str) -> list[dict]:
    rules = [dict(row) for row in get_transaction_rules()]
    if account_filter == "Tutti":
        return rules
    return [rule for rule in rules if rule["account_name"] == account_filter]


def get_dashboard_status(min_balance: float, overdraft_limit: float) -> tuple[str, str]:
    warning_margin = get_warning_margin()
    if min_balance < -overdraft_limit:
        return "Critico", "#8a1c1c"
    if min_balance < (-overdraft_limit + warning_margin):
        return "Attenzione", "#8b5e00"
    return "Stabile", "#1f7a1f"


def sync_snapshot_form(account_name: str) -> None:
    account = get_account_by_name(account_name)
    if account is None:
        return

    snapshot = get_latest_account_snapshot(account["id"])
    snapshot_state["account_name"] = account_name
    if snapshot:
        snapshot_state["snapshot_date"] = format_ui_date(snapshot["snapshot_date"])
        snapshot_state["balance"] = f"{snapshot['balance']:.2f}"
        snapshot_state["note"] = snapshot["note"] or ""
    else:
        snapshot_state["snapshot_date"] = format_ui_date(date.today())
        snapshot_state["balance"] = ""
        snapshot_state["note"] = ""


def select_active_account(account_name: str) -> None:
    dashboard_state["account_name"] = account_name
    forecast_state["account_name"] = account_name
    override_state["selected_key"] = ""
    sync_snapshot_form(account_name)
    refresh_forecast_defaults()
    render_dashboard_header.refresh()
    render_forecast.refresh()
    render_override_editor.refresh()


def refresh_all_rule_views() -> None:
    render_rule_stats.refresh(rule_state["account_filter"])
    render_rules.refresh(rule_state["account_filter"])


def refresh_snapshot_views() -> None:
    render_dashboard_header.refresh()
    refresh_forecast_defaults()
    render_settings.refresh()
    render_forecast.refresh()
    render_override_editor.refresh()


def refresh_forecast_defaults() -> None:
    account_name = forecast_state["account_name"]
    if not account_name:
        return

    account = get_account_by_name(account_name)
    if account is None:
        return

    snapshot = get_latest_account_snapshot(account["id"])
    forecast_window_months = get_forecast_window_months()
    if snapshot:
        forecast_state["start_date"] = format_ui_date(snapshot["snapshot_date"])
        forecast_state["opening_balance"] = f"{snapshot['balance']:.2f}"
        forecast_state["end_date"] = format_ui_date(
            add_months(
                date.fromisoformat(snapshot["snapshot_date"]), forecast_window_months
            )
        )
    else:
        forecast_state["start_date"] = format_ui_date(date.today())
        forecast_state["end_date"] = format_ui_date(
            add_months(date.today(), forecast_window_months)
        )
        forecast_state["opening_balance"] = ""

    try_run_default_forecast()


def try_run_default_forecast() -> None:
    account_name = forecast_state["account_name"]
    start_date_text = forecast_state["start_date"]
    end_date_text = forecast_state["end_date"]
    opening_balance_text = forecast_state["opening_balance"].strip()

    if not account_name or not start_date_text or not end_date_text:
        forecast_state["result"] = None
        return

    try:
        opening_balance = None
        if opening_balance_text:
            opening_balance = float(opening_balance_text.replace(",", "."))

        forecast_state["result"] = build_account_forecast(
            account_name,
            parse_ui_date(start_date_text),
            parse_ui_date(end_date_text),
            opening_balance,
        )
    except Exception:
        forecast_state["result"] = None


def toggle_rule(rule_id: int, active: bool) -> None:
    set_transaction_rule_active(rule_id, active)
    refresh_all_rule_views()


def save_snapshot() -> None:
    account_name = snapshot_state["account_name"]
    snapshot_date = snapshot_state["snapshot_date"]
    balance_text = snapshot_state["balance"]
    note = snapshot_state["note"].strip() or None

    if not account_name or not snapshot_date or not balance_text:
        ui.notify("Compila conto, data e saldo.", color="negative")
        return

    account = get_account_by_name(account_name)
    if account is None:
        ui.notify("Conto non trovato.", color="negative")
        return

    try:
        snapshot_date_value = parse_ui_date(snapshot_date)
        balance = float(balance_text.replace(",", "."))
    except ValueError:
        ui.notify(
            "Controlla data e saldo: usa DD-MM-YYYY e un numero valido.",
            color="negative",
        )
        return

    upsert_account_snapshot(
        account["id"], snapshot_date_value.isoformat(), balance, note
    )
    ui.notify("Snapshot salvato.", color="positive")
    sync_snapshot_form(account_name)
    refresh_snapshot_views()


def save_overdraft_limit(account_name: str, overdraft_text: str) -> None:
    account = get_account_by_name(account_name)
    if account is None:
        ui.notify("Conto non trovato.", color="negative")
        return

    raw_value = overdraft_text.strip()
    try:
        overdraft_limit = 0.0 if raw_value == "" else float(raw_value.replace(",", "."))
    except ValueError:
        ui.notify("Fido non valido.", color="negative")
        return

    set_account_overdraft_limit(account["id"], overdraft_limit)
    ui.notify("Fido aggiornato.", color="positive")
    render_settings.refresh()
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()


def save_forecast_window_months(value_text: str) -> None:
    try:
        months = int(value_text.strip())
    except ValueError:
        ui.notify("La finestra deve essere un numero intero.", color="negative")
        return

    if months < 1:
        ui.notify("La finestra deve essere almeno di 1 mese.", color="negative")
        return

    set_setting("forecast_window_months", str(months))
    settings_state["forecast_window_months"] = str(months)
    refresh_forecast_defaults()
    render_settings.refresh()
    ui.notify("Finestra previsione aggiornata.", color="positive")


def save_warning_margin(value_text: str) -> None:
    try:
        margin = float(value_text.strip().replace(",", "."))
    except ValueError:
        ui.notify("La soglia attenzione deve essere un numero.", color="negative")
        return

    if margin < 0:
        ui.notify("La soglia attenzione non puo essere negativa.", color="negative")
        return

    set_setting("warning_margin", str(margin))
    settings_state["warning_margin"] = str(
        int(margin) if margin.is_integer() else margin
    )
    try_run_default_forecast()
    render_settings.refresh()
    render_forecast.refresh()
    render_override_editor.refresh()
    ui.notify("Soglia attenzione aggiornata.", color="positive")


def run_forecast() -> None:
    account_name = forecast_state["account_name"]
    start_date_text = forecast_state["start_date"]
    end_date_text = forecast_state["end_date"]
    opening_balance_text = forecast_state["opening_balance"].strip()

    if not account_name or not start_date_text or not end_date_text:
        ui.notify("Compila conto, data iniziale e data finale.", color="negative")
        return

    try:
        start_date_value = parse_ui_date(start_date_text)
        end_date_value = parse_ui_date(end_date_text)
    except ValueError:
        ui.notify("Le date devono essere nel formato DD-MM-YYYY.", color="negative")
        return

    try:
        opening_balance = None
        if opening_balance_text:
            opening_balance = float(opening_balance_text.replace(",", "."))

        forecast_state["result"] = build_account_forecast(
            account_name,
            start_date_value,
            end_date_value,
            opening_balance,
        )
        render_forecast.refresh()
        render_override_editor.refresh()
    except Exception as exc:
        forecast_state["result"] = None
        render_forecast.refresh()
        render_override_editor.refresh()
        ui.notify(str(exc), color="negative")


def save_manual_event() -> None:
    account = get_account_by_name(dashboard_state["account_name"])
    if account is None:
        ui.notify("Conto non trovato.", color="negative")
        return

    try:
        event_date = parse_ui_date(manual_event_state["event_date"]).isoformat()
        amount = float(manual_event_state["amount"].replace(",", "."))
    except ValueError:
        ui.notify("Controlla data e importo del movimento manuale.", color="negative")
        return

    description = manual_event_state["description"].strip()
    if not description:
        ui.notify(
            "Inserisci una descrizione per il movimento manuale.", color="negative"
        )
        return

    if manual_event_state["selected_event_id"] is None:
        add_manual_event(
            account_id=account["id"],
            event_date=event_date,
            description=description,
            amount=amount,
            payment_method=manual_event_state["payment_method"] or None,
            note=manual_event_state["note"].strip() or None,
        )
        ui.notify("Movimento manuale aggiunto.", color="positive")
    else:
        update_manual_event(
            event_id=manual_event_state["selected_event_id"],
            event_date=event_date,
            description=description,
            amount=amount,
            payment_method=manual_event_state["payment_method"] or None,
            note=manual_event_state["note"].strip() or None,
        )
        ui.notify("Movimento manuale aggiornato.", color="positive")

    clear_manual_event_selection(refresh_editor=False)
    manual_event_state["description"] = ""
    manual_event_state["amount"] = ""
    manual_event_state["note"] = ""
    try_run_default_forecast()
    render_forecast.refresh()
    render_manual_event_editor.refresh()


def clear_manual_event_selection(refresh_editor: bool = True) -> None:
    manual_event_state["selected_event_id"] = None
    manual_event_state["selected_key"] = ""
    manual_event_state["event_date"] = format_ui_date(date.today())
    manual_event_state["description"] = ""
    manual_event_state["amount"] = ""
    manual_event_state["payment_method"] = "Conto"
    manual_event_state["note"] = ""
    if refresh_editor:
        render_manual_event_editor.refresh()


def get_selected_forecast_key() -> str:
    return manual_event_state["selected_key"] or override_state["selected_key"]


def select_forecast_row(value: str | None) -> None:
    selected_key = value or ""
    selected_row = next(
        (row for row in override_state["rows"] if row["selection_key"] == selected_key),
        None,
    )

    if selected_row is None:
        clear_manual_event_selection(refresh_editor=False)
        select_override_event(None, refresh_editor=False)
    elif selected_row["is_manual_event"]:
        manual_event_state["selected_event_id"] = selected_row["source_manual_event_id"]
        manual_event_state["selected_key"] = selected_row["selection_key"]
        manual_event_state["event_date"] = selected_row["date"]
        manual_event_state["description"] = selected_row["description"]
        manual_event_state["amount"] = selected_row["amount"]
        manual_event_state["payment_method"] = selected_row["payment_method"] or "Conto"
        manual_event_state["note"] = selected_row["note"] or ""
        select_override_event(None, refresh_editor=False)
    else:
        clear_manual_event_selection(refresh_editor=False)
        if selected_row["editable"]:
            select_override_event(selected_row["selection_key"], refresh_editor=False)
        else:
            select_override_event(None, refresh_editor=False)

    render_manual_event_editor.refresh()
    render_override_editor.refresh()


def delete_manual_event() -> None:
    selected_event_id = manual_event_state["selected_event_id"]
    if selected_event_id is None:
        ui.notify("Seleziona prima un movimento manuale.", color="negative")
        return

    set_manual_event_status(selected_event_id, "cancelled")
    ui.notify("Movimento manuale annullato.", color="positive")
    clear_manual_event_selection(refresh_editor=False)
    try_run_default_forecast()
    render_forecast.refresh()
    render_manual_event_editor.refresh()


def select_override_event(value: str | None, refresh_editor: bool = True) -> None:
    override_state["selected_key"] = value or ""
    selected_row = next(
        (
            row
            for row in override_state["rows"]
            if row["selection_key"] == override_state["selected_key"]
        ),
        None,
    )

    if selected_row is None:
        override_state["rule_id"] = None
        override_state["original_event_date"] = ""
        override_state["override_description"] = ""
        override_state["override_event_date"] = ""
        override_state["override_amount"] = ""
        override_state["resolution_mode"] = "auto"
        override_state["status"] = "open"
    elif not selected_row["editable"]:
        override_state["selected_key"] = ""
        override_state["rule_id"] = None
        override_state["original_event_date"] = ""
        override_state["override_description"] = ""
        override_state["override_event_date"] = ""
        override_state["override_amount"] = ""
        override_state["resolution_mode"] = "auto"
        override_state["status"] = "open"
    else:
        override_state["rule_id"] = selected_row["source_rule_id"]
        override_state["original_event_date"] = selected_row["original_event_date"]
        override_state["override_description"] = (
            selected_row["override_description"] or selected_row["description"]
        )
        override_state["override_event_date"] = (
            selected_row["override_event_date"] or selected_row["date"]
        )
        override_state["override_amount"] = (
            f"{selected_row['override_amount']:.2f}"
            if selected_row["override_amount"] is not None
            else ""
        )
        override_state["resolution_mode"] = (
            selected_row["override_resolution_mode"] or "auto"
        )
        override_state["status"] = selected_row["override_status"] or "open"

    if refresh_editor:
        render_override_editor.refresh()


def save_event_override() -> None:
    account = get_account_by_name(dashboard_state["account_name"])
    rule_id = override_state["rule_id"]
    original_event_date = override_state["original_event_date"]
    if account is None or rule_id is None or not original_event_date:
        ui.notify("Seleziona prima un movimento modificabile.", color="negative")
        return

    override_description = override_state["override_description"].strip()
    override_event_date = override_state["override_event_date"].strip()
    override_amount_text = override_state["override_amount"].strip()
    resolution_mode = override_state["resolution_mode"]
    status = override_state["status"]

    try:
        parsed_override_date = (
            parse_ui_date(override_event_date).isoformat()
            if override_event_date
            else None
        )
        parsed_override_amount = (
            float(override_amount_text.replace(",", "."))
            if override_amount_text
            else None
        )
    except ValueError:
        ui.notify("Controlla data e importo override.", color="negative")
        return

    if status == "open" and parsed_override_date is None:
        ui.notify("Per un override aperto serve una data prevista.", color="negative")
        return

    upsert_forecast_event_override(
        rule_id=rule_id,
        account_id=account["id"],
        original_event_date=original_event_date,
        override_description=override_description or None,
        override_event_date=parsed_override_date,
        override_amount=parsed_override_amount,
        resolution_mode=resolution_mode,
        status=status,
    )
    ui.notify("Override salvato.", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()


def clear_event_override() -> None:
    account = get_account_by_name(dashboard_state["account_name"])
    rule_id = override_state["rule_id"]
    original_event_date = override_state["original_event_date"]
    if account is None or rule_id is None or not original_event_date:
        ui.notify("Seleziona prima un movimento modificabile.", color="negative")
        return

    delete_forecast_event_override(rule_id, account["id"], original_event_date)
    ui.notify("Override rimosso.", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()


init_db()

rule_state = {"account_filter": "Tutti"}
snapshot_state = {
    "account_name": "Fineco",
    "snapshot_date": format_ui_date(date.today()),
    "balance": "",
    "note": "",
    "account_filter": "Tutti",
}
forecast_state = {
    "account_name": "Fineco",
    "start_date": format_ui_date(date.today()),
    "end_date": format_ui_date(add_months(date.today(), get_forecast_window_months())),
    "opening_balance": "",
    "result": None,
}
dashboard_state = {
    "account_name": "Fineco",
}
settings_state = {
    "forecast_window_months": str(get_forecast_window_months()),
    "warning_margin": str(int(get_warning_margin())),
}
manual_event_state = {
    "selected_event_id": None,
    "selected_key": "",
    "event_date": format_ui_date(date.today()),
    "description": "",
    "amount": "",
    "payment_method": "Conto",
    "note": "",
}
override_state = {
    "rows": [],
    "selected_key": "",
    "rule_id": None,
    "original_event_date": "",
    "override_description": "",
    "override_event_date": "",
    "override_amount": "",
    "resolution_mode": "auto",
    "status": "open",
}

if get_account_by_name("Fineco") is None and get_accounts():
    default_name = get_accounts()[0]["name"]
    dashboard_state["account_name"] = default_name

sync_snapshot_form(dashboard_state["account_name"])
forecast_state["account_name"] = dashboard_state["account_name"]
refresh_forecast_defaults()

ui.query("body").style("background: linear-gradient(180deg, #f3efe5 0%, #fbf8f2 100%);")
ui.add_head_html(
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">'
)

with ui.column().classes("w-full max-w-7xl mx-auto gap-4 p-6"):
    with ui.tabs().classes("w-full") as tabs:
        dashboard_tab = ui.tab("Movimenti")
        rules_tab = ui.tab("Regole")
        settings_tab = ui.tab("Impostazioni")

    @ui.refreshable
    def render_rule_stats(account_filter: str) -> None:
        rules = load_rules(account_filter)
        active_rules = [
            rule
            for rule in rules
            if rule["active"] and not is_rule_expired(rule["end_date"])
        ]
        expired_rules = [rule for rule in rules if is_rule_expired(rule["end_date"])]
        disabled_rules = [
            rule
            for rule in rules
            if not rule["active"] and not is_rule_expired(rule["end_date"])
        ]

        with ui.row().classes("w-full gap-4"):
            for title, value in (
                ("Regole visibili", len(rules)),
                ("Attive effettive", len(active_rules)),
                ("Disattivate manualmente", len(disabled_rules)),
                ("Scadute", len(expired_rules)),
            ):
                with ui.card().classes("min-w-[180px] flex-1"):
                    ui.label(title).style("color: #6b5b53; font-size: 14px")
                    ui.label(str(value)).style(
                        "font-size: 28px; font-weight: 700; color: #2f241f"
                    )

    @ui.refreshable
    def render_rules(account_filter: str) -> None:
        rules = load_rules(account_filter)

        with ui.column().classes("w-full gap-3"):
            if not rules:
                with ui.card().classes("w-full"):
                    ui.label("Nessuna regola disponibile per il filtro selezionato.")
                return

            for rule in rules:
                status_text, status_color = get_rule_status(rule)
                payment_method = (rule["payment_method"] or "n/d").capitalize()
                provider = rule["provider"] or "-"
                date_range = rule["start_date"] or "-"
                if rule["end_date"]:
                    date_range = f"{date_range} -> {rule['end_date']}"

                with ui.card().classes("w-full"):
                    with ui.row().classes(
                        "w-full items-center justify-between gap-4 no-wrap"
                    ):
                        with ui.column().classes("gap-1"):
                            ui.label(rule["description"]).style(
                                "font-size: 18px; font-weight: 600"
                            )
                            ui.label(
                                f"{rule['account_name']} | {rule['amount']:.2f} EUR | {rule['frequency']} | {format_cadence(rule)}"
                            ).style("color: #5f5048")
                            ui.label(
                                f"Pagamento: {payment_method} | Provider: {provider} | Validita: {date_range}"
                            ).style("color: #7a6a62; font-size: 13px")

                        with ui.column().classes("items-end gap-1"):
                            ui.label(status_text).style(
                                f"color: {status_color}; font-weight: 700; font-size: 14px"
                            )
                            ui.switch(
                                text="Abilitata manualmente",
                                value=bool(rule["active"]),
                                on_change=lambda event, rule_id=rule["id"]: toggle_rule(
                                    rule_id, bool(event.value)
                                ),
                            )

    @ui.refreshable
    def render_forecast() -> None:
        result = forecast_state["result"]

        with ui.column().classes("w-full gap-3"):
            if result is None:
                with ui.card().classes("w-full"):
                    ui.label("Nessuna previsione calcolata.")
                    ui.label(
                        "Se il saldo iniziale non e compilato, verra usato l'ultimo snapshot disponibile fino alla data iniziale."
                    ).style("color: #7a6a62")
                return

            forecast_rows = []
            running_balance = result.opening_balance
            previous_month_key = None
            for index, event in enumerate(result.events, start=1):
                running_balance += event.amount
                month_key = event.event_date.strftime("%Y-%m")
                type_icon = (
                    "credit_card"
                    if event.event_type == "card_settlement"
                    else ("south_west" if event.amount < 0 else "north_east")
                )
                floor_value = -result.overdraft_limit
                balance_status = "check_circle"
                if running_balance < floor_value:
                    balance_status = "dangerous"
                elif running_balance < floor_value + get_warning_margin():
                    balance_status = "warning"

                forecast_rows.append(
                    {
                        "id": index,
                        "selection_key": f"{event.source_rule_id or 'settlement'}|{event.original_event_date.isoformat()}|{index}",
                        "is_selected": False,
                        "row_bg": month_background(event.event_date.month),
                        "month_break": previous_month_key is not None
                        and month_key != previous_month_key,
                        "date": format_ui_date(event.event_date),
                        "type": type_icon,
                        "description": event.description,
                        "original_description": event.original_description,
                        "source_rule_id": event.source_rule_id,
                        "source_manual_event_id": event.source_manual_event_id,
                        "editable": event.source_rule_id is not None,
                        "is_manual_event": event.source_manual_event_id is not None,
                        "payment_method": getattr(event, "payment_method", None),
                        "note": getattr(event, "note", None),
                        "original_event_date": event.original_event_date.isoformat(),
                        "original_event_date_label": format_ui_date(
                            event.original_event_date
                        ),
                        "original_amount": event.original_amount,
                        "override_id": event.override_id,
                        "override_status": event.override_status,
                        "override_resolution_mode": event.override_resolution_mode,
                        "override_description": event.override_description,
                        "override_event_date": format_ui_date(event.override_event_date)
                        if event.override_event_date
                        else "",
                        "override_amount": event.override_amount,
                        "carried_overdue": event.carried_overdue,
                        "has_override": event.override_id is not None,
                        "description_changed": bool(event.override_description),
                        "date_changed": event.override_event_date is not None,
                        "amount_changed": event.override_amount is not None,
                        "amount_value": round(event.amount, 2),
                        "amount": format_currency(event.amount),
                        "balance_value": round(running_balance, 2),
                        "balance": format_currency(running_balance),
                        "status": balance_status,
                    }
                )
                previous_month_key = month_key

            table = ui.table(
                columns=[
                    {"name": "date", "label": "Data", "field": "date", "align": "left"},
                    {
                        "name": "schedule",
                        "label": "Programma",
                        "field": "override_status",
                        "align": "center",
                    },
                    {
                        "name": "type",
                        "label": "Tipo",
                        "field": "type",
                        "align": "center",
                    },
                    {
                        "name": "description",
                        "label": "Descrizione",
                        "field": "description",
                        "align": "left",
                    },
                    {
                        "name": "amount",
                        "label": "Importo",
                        "field": "amount",
                        "align": "right",
                    },
                    {
                        "name": "balance",
                        "label": "Saldo",
                        "field": "balance",
                        "align": "right",
                    },
                    {
                        "name": "status",
                        "label": "Stato",
                        "field": "status",
                        "align": "center",
                    },
                ],
                rows=forecast_rows,
                row_key="id",
                pagination=34,
            ).classes("w-full rounded-xl overflow-hidden")
            table.style("font-family: 'IBM Plex Mono', monospace; font-size: 11px")
            override_state["rows"] = forecast_rows
            selected_forecast_key = get_selected_forecast_key()
            available_rows = [row for row in forecast_rows if row["editable"]]
            if override_state["selected_key"] and not any(
                row["selection_key"] == override_state["selected_key"]
                for row in available_rows
            ):
                override_state["selected_key"] = ""
            if not override_state["selected_key"] and available_rows:
                select_override_event(
                    available_rows[0]["selection_key"], refresh_editor=False
                )
            selected_forecast_key = get_selected_forecast_key()
            for row in forecast_rows:
                row["is_selected"] = row["selection_key"] == selected_forecast_key
            table.add_slot(
                "body",
                r"""
                <q-tr :props="props" @click="() => $parent.$emit('select_override_row', props.row.selection_key)" class="cursor-pointer" :style="'background-color:' + props.row.row_bg + '; border-top:' + (props.row.month_break ? '4px solid #8f7f73' : '0') + '; box-shadow:' + (props.row.is_selected ? 'inset 0 0 0 2px #2f241f' : 'none')">
                    <q-td key="date" :props="props" style="padding-top: 4px; padding-bottom: 4px">{{ props.row.date }}</q-td>
                    <q-td key="schedule" :props="props" class="text-center">
                        <q-icon v-if="props.row.is_manual_event" name="add_task" color="teal" size="sm">
                            <q-tooltip>Movimento manuale una tantum</q-tooltip>
                        </q-icon>
                        <template v-else-if="props.row.has_override">
                            <q-icon v-if="props.row.override_resolution_mode === 'manual' && props.row.override_status === 'open'" name="push_pin" color="warning" size="xs" class="q-mr-xs">
                                <q-tooltip>Override manuale aperto. Originale: {{ props.row.original_event_date_label }} | {{ props.row.original_description }} | {{ props.row.original_amount.toFixed(2) }}</q-tooltip>
                            </q-icon>
                            <q-icon v-if="props.row.date_changed" name="event_repeat" color="secondary" size="xs" class="q-mr-xs">
                                <q-tooltip>Data modificata. Originale: {{ props.row.original_event_date_label }}</q-tooltip>
                            </q-icon>
                            <q-icon v-if="props.row.amount_changed" name="euro" color="secondary" size="xs" class="q-mr-xs">
                                <q-tooltip>Importo modificato. Originale: {{ props.row.original_amount.toFixed(2) }}</q-tooltip>
                            </q-icon>
                            <q-icon v-if="props.row.description_changed" name="edit_note" color="secondary" size="xs">
                                <q-tooltip>Descrizione modificata. Originale: {{ props.row.original_description }}</q-tooltip>
                            </q-icon>
                        </template>
                        <q-icon v-else name="radio_button_unchecked" color="grey-5" size="xs" />
                    </q-td>
                    <q-td key="type" :props="props" class="text-center">
                        <q-icon :name="props.row.type" :color="props.row.amount_value < 0 ? 'negative' : 'positive'" size="sm" />
                    </q-td>
                    <q-td key="description" :props="props" style="padding-top: 4px; padding-bottom: 4px">
                        <div class="row items-center no-wrap">
                            <q-icon v-if="props.row.carried_overdue" name="history" color="warning" size="xs" class="q-mr-xs" />
                            <span>{{ props.row.description }}</span>
                        </div>
                    </q-td>
                    <q-td key="amount" :props="props" style="padding-top: 4px; padding-bottom: 4px" :class="props.row.amount_value < 0 ? 'text-[#8a1c1c]' : 'text-[#1f7a1f]'">{{ props.row.amount }}</q-td>
                    <q-td key="balance" :props="props" style="padding-top: 4px; padding-bottom: 4px" :class="props.row.balance_value < 0 ? 'text-[#8a1c1c] font-semibold' : 'text-[#2f241f] font-semibold'">{{ props.row.balance }}</q-td>
                    <q-td key="status" :props="props" class="text-center">
                        <q-icon :name="props.row.status" :color="props.row.status === 'dangerous' ? 'negative' : (props.row.status === 'warning' ? 'warning' : 'positive')" size="sm" />
                    </q-td>
                </q-tr>
                """,
            )
            table.on("select_override_row", lambda event: select_forecast_row(event.args))

    @ui.refreshable
    def render_manual_event_editor() -> None:
        with ui.card().classes("w-full"):
            title = (
                "Modifica movimento una tantum"
                if manual_event_state["selected_event_id"] is not None
                else "Aggiungi movimento una tantum"
            )
            ui.label(title).style(
                "font-size: 18px; font-weight: 600"
            )
            if manual_event_state["selected_event_id"] is not None:
                ui.label(
                    "Hai selezionato un movimento manuale dalla tabella: puoi aggiornarlo o annullarlo."
                ).style("color: #6b5b53; font-size: 13px")
            with ui.row().classes("w-full items-end gap-4"):
                ui.input(
                    label="Data movimento",
                    value=manual_event_state["event_date"],
                    on_change=lambda event: manual_event_state.__setitem__(
                        "event_date", event.value
                    ),
                ).classes("min-w-[170px]")
                ui.input(
                    label="Descrizione una tantum",
                    value=manual_event_state["description"],
                    on_change=lambda event: manual_event_state.__setitem__(
                        "description", event.value
                    ),
                ).classes("min-w-[260px]")
                ui.input(
                    label="Importo",
                    value=manual_event_state["amount"],
                    on_change=lambda event: manual_event_state.__setitem__(
                        "amount", event.value
                    ),
                ).classes("min-w-[140px]")
                ui.select(
                    options=["Conto", "Carta"],
                    value=manual_event_state["payment_method"],
                    on_change=lambda event: manual_event_state.__setitem__(
                        "payment_method", event.value
                    ),
                ).classes("min-w-[140px]")
                ui.button(
                    icon=("save" if manual_event_state["selected_event_id"] is not None else "add"),
                    on_click=save_manual_event,
                ).props("round flat")
                if manual_event_state["selected_event_id"] is not None:
                    ui.button(icon="close", on_click=clear_manual_event_selection).props(
                        "round flat"
                    )
                    ui.button(icon="delete", on_click=delete_manual_event).props(
                        "round flat"
                    )

    @ui.refreshable
    def render_override_editor() -> None:
        editable_rows = [row for row in override_state["rows"] if row["editable"]]

        with ui.card().classes("w-full"):
            ui.label("Personalizzazione movimento").style(
                "font-size: 18px; font-weight: 600"
            )
            if not editable_rows:
                ui.label(
                    "Nessun movimento modificabile nella finestra di previsione."
                ).style("color: #6b5b53")
                return

            event_options = {
                row[
                    "selection_key"
                ]: f"{row['date']} | {row['description']} | {row['amount']}"
                for row in editable_rows
            }
            ui.select(
                options=event_options,
                value=override_state["selected_key"] or next(iter(event_options)),
                label="Movimento da modificare",
                on_change=lambda event: select_override_event(event.value),
            ).classes("w-full")

            ui.label(
                "Auto: l'override segue la normale pianificazione. Manuale: resta pendente finche non lo segni come risolto o annullato."
            ).style("color: #6b5b53; font-size: 13px")

            with ui.row().classes("w-full items-end gap-4 mt-3"):
                ui.input(
                    label="Nuova descrizione",
                    value=override_state["override_description"],
                    on_change=lambda event: override_state.__setitem__(
                        "override_description", event.value
                    ),
                ).classes("min-w-[260px]")
                ui.input(
                    label="Nuova data",
                    value=override_state["override_event_date"],
                    on_change=lambda event: override_state.__setitem__(
                        "override_event_date", event.value
                    ),
                ).classes("min-w-[170px]")
                ui.input(
                    label="Nuovo importo",
                    value=override_state["override_amount"],
                    on_change=lambda event: override_state.__setitem__(
                        "override_amount", event.value
                    ),
                ).classes("min-w-[150px]")
                ui.select(
                    options={"auto": "Auto", "manual": "Manuale"},
                    value=override_state["resolution_mode"],
                    label="Risoluzione",
                    on_change=lambda event: override_state.__setitem__(
                        "resolution_mode", event.value
                    ),
                ).classes("min-w-[150px]")
                ui.select(
                    options={
                        "open": "Aperto",
                        "resolved": "Risolto",
                        "cancelled": "Annullato",
                    },
                    value=override_state["status"],
                    label="Stato",
                    on_change=lambda event: override_state.__setitem__(
                        "status", event.value
                    ),
                ).classes("min-w-[150px]")
                ui.button(icon="save", on_click=save_event_override).props("round flat")
                ui.button(icon="delete", on_click=clear_event_override).props(
                    "round flat"
                )

    @ui.refreshable
    def render_dashboard_header() -> None:
        with ui.card().classes("w-full"):
            with ui.column().classes("w-full gap-3"):
                with ui.row().classes("items-center gap-3"):
                    ui.select(
                        options=[account_row["name"] for account_row in get_accounts()],
                        value=dashboard_state["account_name"],
                        on_change=lambda event: select_active_account(event.value),
                    ).classes("min-w-[240px]").style(
                        "font-family: 'IBM Plex Mono', monospace; font-size: 28px; text-transform: uppercase; letter-spacing: 0.08em"
                    )
                    ui.button(
                        icon="refresh",
                        on_click=lambda: (
                            try_run_default_forecast(),
                            render_forecast.refresh(),
                        ),
                    ).props("round flat")

            with ui.row().classes("w-full items-end gap-4"):
                ui.input(
                    label="Data aggiornamento",
                    value=snapshot_state["snapshot_date"],
                    on_change=lambda event: snapshot_state.__setitem__(
                        "snapshot_date", event.value
                    ),
                ).classes("min-w-[180px]")
                ui.input(
                    label="Saldo",
                    value=snapshot_state["balance"],
                    on_change=lambda event: snapshot_state.__setitem__(
                        "balance", event.value
                    ),
                ).classes("min-w-[160px]")
                ui.input(
                    label="Nota",
                    value=snapshot_state["note"],
                    on_change=lambda event: snapshot_state.__setitem__(
                        "note", event.value
                    ),
                ).classes("min-w-[260px]")
                ui.button(icon="save", on_click=save_snapshot).props("round flat")

    @ui.refreshable
    def render_settings() -> None:
        accounts = get_accounts()

        with ui.column().classes("w-full gap-3"):
            with ui.card().classes("w-full"):
                ui.label("Impostazioni previsione").style(
                    "font-size: 22px; font-weight: 600"
                )
                ui.label(
                    "Definisci la finestra predefinita usata dalla previsione."
                ).style("color: #6b5b53")
                with ui.row().classes("items-end gap-3"):
                    forecast_window_input = ui.input(
                        label="Finestra previsione (mesi)",
                        value=settings_state["forecast_window_months"],
                    ).classes("min-w-[220px]")
                    ui.button(
                        "Salva finestra",
                        on_click=lambda _: save_forecast_window_months(
                            forecast_window_input.value
                        ),
                    )

                with ui.row().classes("items-end gap-3 mt-3"):
                    warning_margin_input = ui.input(
                        label="Soglia attenzione (€)",
                        value=settings_state["warning_margin"],
                    ).classes("min-w-[220px]")
                    ui.button(
                        "Salva soglia",
                        on_click=lambda _: save_warning_margin(
                            warning_margin_input.value
                        ),
                    )

            with ui.card().classes("w-full"):
                ui.label("Fido conti").style("font-size: 22px; font-weight: 600")
                ui.label("Imposta il fido disponibile per ogni conto.").style(
                    "color: #6b5b53"
                )

                for account in accounts:
                    with ui.row().classes("w-full items-end gap-3"):
                        ui.label(account["name"]).classes("min-w-[140px]")
                        overdraft_input = ui.input(
                            label="Fido",
                            value=str(account["overdraft_limit"] or 0),
                        ).classes("min-w-[180px]")
                        ui.button(
                            "Salva",
                            on_click=lambda _, acc_name=account["name"], field=overdraft_input: (
                                save_overdraft_limit(acc_name, field.value)
                            ),
                        )

    with ui.tab_panels(tabs, value=dashboard_tab).classes("w-full"):
        with ui.tab_panel(dashboard_tab).classes("gap-4"):
            render_dashboard_header()
            render_forecast()
            render_manual_event_editor()
            render_override_editor()

        with ui.tab_panel(rules_tab).classes("gap-4"):
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between gap-4"):
                    with ui.column().classes("gap-1"):
                        ui.label("Regole").style("font-size: 22px; font-weight: 600")
                        ui.label(
                            "Le regole scadute restano storiche ma non sono piu attive nella previsione."
                        ).style("color: #6b5b53")

                    account_options = ["Tutti"] + [
                        account["name"] for account in get_accounts()
                    ]
                    ui.select(
                        options=account_options,
                        value=rule_state["account_filter"],
                        label="Filtra per conto",
                        on_change=lambda event: (
                            rule_state.__setitem__("account_filter", event.value),
                            render_rule_stats.refresh(event.value),
                            render_rules.refresh(event.value),
                        ),
                    ).classes("min-w-[220px]")

            render_rule_stats(rule_state["account_filter"])
            render_rules(rule_state["account_filter"])

        with ui.tab_panel(settings_tab).classes("gap-4"):
            render_settings()

ui.run()

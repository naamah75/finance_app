import tempfile
from datetime import date, datetime
from pathlib import Path

from nicegui import ui

from db import (
    add_transaction_rule,
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
    replace_transaction_rules,
    set_account_overdraft_limit,
    set_manual_event_status,
    set_setting,
    set_transaction_rule_active,
    update_manual_event,
    update_transaction_rule,
    upsert_forecast_event_override,
    upsert_account_snapshot,
)
from forecast import build_account_forecast
from import_excel import extract_rules


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


def format_ui_date_long(value: date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            value = parse_ui_date(value)
    weekdays = [
        "Lunedi",
        "Martedi",
        "Mercoledi",
        "Giovedi",
        "Venerdi",
        "Sabato",
        "Domenica",
    ]
    months = [
        "Gennaio",
        "Febbraio",
        "Marzo",
        "Aprile",
        "Maggio",
        "Giugno",
        "Luglio",
        "Agosto",
        "Settembre",
        "Ottobre",
        "Novembre",
        "Dicembre",
    ]
    return f"{weekdays[value.weekday()]} {value.day} {months[value.month - 1]} {value.year}"


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


def month_selected_background(month: int) -> str:
    return month_background(month)


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


def get_helper_tooltips_enabled() -> bool:
    raw_value = (get_setting("helper_tooltips_enabled", "1") or "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def add_tooltip(element, text: str):
    if settings_state["helper_tooltips_enabled"]:
        element.tooltip(text)
    return element


def format_cadence(rule: dict) -> str:
    if rule["frequency"] == "yearly" and rule["month_of_year"]:
        return f"{rule['day_of_month']}/{rule['month_of_year']}"
    return f"giorno {rule['day_of_month']}"


def format_rule_frequency(rule: dict) -> str:
    return "Annuale" if rule["frequency"] == "yearly" else "Mensile"


def format_rule_validity(start_date: str | None, end_date: str | None) -> str:
    if start_date and end_date:
        return f"da {format_ui_date(start_date)} a {format_ui_date(end_date)}"
    if start_date:
        return f"da {format_ui_date(start_date)}"
    if end_date:
        return f"fino al {format_ui_date(end_date)}"
    return "sempre attiva"


def get_rule_status(rule: dict) -> tuple[str, str]:
    if is_rule_expired(rule["end_date"]):
        return "Scaduta", "#8b5e00"
    if rule["active"]:
        return "Attiva", "#1f7a1f"
    return "Disattivata", "#8a1c1c"


def get_rule_card_style(is_selected: bool, status_color: str) -> str:
    base = (
        f"border-left: 7px solid {status_color}; border-top: 1px solid rgba(47, 36, 31, 0.08); "
        f"border-right: 1px solid rgba(47, 36, 31, 0.08); border-bottom: 1px solid rgba(47, 36, 31, 0.08); padding: 6px 10px; "
    )
    if is_selected:
        return (
            base
            + "background-color: #f3e7d4 !important; box-shadow: 0 6px 14px rgba(143, 106, 70, 0.12);"
        )
    return base + "background-color: #ffffff !important;"


def get_rule_frequency_tint(rule: dict) -> str:
    return "#f4efe2" if rule["frequency"] == "yearly" else "#eef4ea"


def get_provider_options() -> list[str]:
    providers = {
        (dict(row)["provider"] or "").strip()
        for row in get_transaction_rules()
        if (dict(row)["provider"] or "").strip()
    }
    return sorted(providers)


def load_rules(account_filter: str, show_expired: bool = False) -> list[dict]:
    rules = [dict(row) for row in get_transaction_rules()]
    if account_filter != "Tutti":
        rules = [rule for rule in rules if rule["account_name"] == account_filter]
    if not show_expired:
        rules = [rule for rule in rules if not is_rule_expired(rule["end_date"])]
    return rules


def clear_rule_selection(refresh_editor: bool = True) -> None:
    rule_state["selected_rule_id"] = None
    rule_state["account_name"] = dashboard_state["account_name"]
    rule_state["description"] = ""
    rule_state["amount"] = ""
    rule_state["frequency"] = "monthly"
    rule_state["day_of_month"] = ""
    rule_state["month_of_year"] = ""
    rule_state["payment_method"] = "Conto"
    rule_state["provider"] = ""
    rule_state["start_date"] = ""
    rule_state["end_date"] = ""
    rule_state["installments_total"] = ""
    rule_state["active"] = True
    rule_state["source_sheet"] = ""
    refresh_all_rule_views()
    if refresh_editor:
        refresh_rule_editor()


def start_new_rule() -> None:
    clear_rule_selection(refresh_editor=False)
    rule_state["account_name"] = str(rule_state["account_filter"])
    rule_state["active"] = True
    refresh_all_rule_views()
    refresh_rule_editor()


def select_rule(rule_id: int | None, refresh_editor: bool = True) -> None:
    if rule_id is None:
        clear_rule_selection(refresh_editor=refresh_editor)
        return
    if rule_state["selected_rule_id"] == int(rule_id):
        clear_rule_selection(refresh_editor=refresh_editor)
        return

    selected_rule = next(
        (dict(row) for row in get_transaction_rules() if int(row["id"]) == int(rule_id)),
        None,
    )
    if selected_rule is None:
        clear_rule_selection(refresh_editor=refresh_editor)
        return

    rule_state["selected_rule_id"] = int(selected_rule["id"])
    rule_state["account_name"] = selected_rule["account_name"]
    rule_state["description"] = selected_rule["description"]
    rule_state["amount"] = f"{float(selected_rule['amount']):.2f}"
    rule_state["frequency"] = selected_rule["frequency"]
    rule_state["day_of_month"] = str(selected_rule["day_of_month"] or "")
    rule_state["month_of_year"] = str(selected_rule["month_of_year"] or "")
    rule_state["payment_method"] = (selected_rule["payment_method"] or "Conto").capitalize()
    rule_state["provider"] = selected_rule["provider"] or ""
    rule_state["start_date"] = (
        format_ui_date(selected_rule["start_date"]) if selected_rule["start_date"] else ""
    )
    rule_state["end_date"] = (
        format_ui_date(selected_rule["end_date"]) if selected_rule["end_date"] else ""
    )
    rule_state["installments_total"] = str(selected_rule["installments_total"] or "")
    rule_state["active"] = bool(selected_rule["active"])
    rule_state["source_sheet"] = selected_rule["source_sheet"] or ""
    refresh_all_rule_views()
    if refresh_editor:
        refresh_rule_editor()


def save_rule_changes() -> None:
    rule_id = rule_state["selected_rule_id"]
    is_new_rule = rule_id is None
    if rule_id is not None:
        rule_id = int(str(rule_id))

    account_name = str(rule_state["account_name"])
    description = str(rule_state["description"]).strip()
    amount_text = str(rule_state["amount"]).strip()
    frequency = str(rule_state["frequency"])
    day_of_month_text = str(rule_state["day_of_month"]).strip()
    month_of_year_text = str(rule_state["month_of_year"]).strip()
    start_date_text = str(rule_state["start_date"]).strip()
    end_date_text = str(rule_state["end_date"]).strip()
    installments_total_text = str(rule_state["installments_total"]).strip()
    provider_text = str(rule_state["provider"]).strip()
    payment_method_text = str(rule_state["payment_method"] or "").strip().lower()
    active = bool(rule_state["active"])

    account = get_account_by_name(account_name)
    if account is None:
        ui.notify("Conto non trovato per la regola selezionata.", color="negative")
        return

    if not description:
        ui.notify("Inserisci una descrizione per la regola.", color="negative")
        return

    try:
        amount = float(amount_text.replace(",", "."))
        day_of_month = int(day_of_month_text)
        month_of_year = (
            int(month_of_year_text)
            if frequency == "yearly" and month_of_year_text
            else None
        )
        start_date = (
            parse_ui_date(start_date_text).isoformat()
            if start_date_text
            else None
        )
        end_date = (
            parse_ui_date(end_date_text).isoformat()
            if end_date_text
            else None
        )
        installments_total = (
            int(installments_total_text)
            if installments_total_text
            else None
        )
    except ValueError:
        ui.notify("Controlla i campi numerici e le date della regola.", color="negative")
        return

    if not 1 <= day_of_month <= 31:
        ui.notify("Il giorno della regola deve essere tra 1 e 31.", color="negative")
        return
    if frequency == "yearly" and month_of_year is None:
        ui.notify("Per una regola annuale serve anche il mese.", color="negative")
        return
    if month_of_year is not None and not 1 <= month_of_year <= 12:
        ui.notify("Il mese della regola deve essere tra 1 e 12.", color="negative")
        return
    if installments_total is not None and installments_total < 1:
        ui.notify("Il numero rate deve essere almeno 1.", color="negative")
        return
    if start_date and end_date and end_date < start_date:
        ui.notify("La data fine non puo essere precedente alla data inizio.", color="negative")
        return

    payment_method = payment_method_text or None

    if is_new_rule:
        rule_id = add_transaction_rule(
            account_id=int(account["id"]),
            description=description,
            amount=amount,
            frequency=frequency,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            payment_method=payment_method,
            provider=provider_text or None,
            start_date=start_date,
            end_date=end_date,
            installments_total=installments_total,
            active=active,
        )
        ui.notify("Nuova regola aggiunta.", color="positive")
    else:
        update_transaction_rule(
            rule_id=rule_id,
            account_id=int(account["id"]),
            description=description,
            amount=amount,
            frequency=frequency,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            payment_method=payment_method,
            provider=provider_text or None,
            start_date=start_date,
            end_date=end_date,
            installments_total=installments_total,
            active=active,
        )
        ui.notify("Regola aggiornata.", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()
    refresh_all_rule_views()
    select_rule(int(rule_id), refresh_editor=False)
    refresh_rule_editor()


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
    forecast_state["selected_key"] = ""
    override_state["selected_key"] = ""
    sync_snapshot_form(account_name)
    refresh_forecast_defaults()
    render_dashboard_header.refresh()
    render_forecast.refresh()
    render_override_editor.refresh()


def refresh_all_rule_views() -> None:
    render_rule_stats.refresh(str(rule_state["account_filter"]))
    render_rules.refresh(str(rule_state["account_filter"]))


def refresh_rule_editor() -> None:
    editor = globals().get("render_rule_editor")
    if editor is not None:
        editor.refresh()


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
    if rule_state["selected_rule_id"] == rule_id:
        rule_state["active"] = active
        refresh_rule_editor()
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()
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


def save_helper_tooltips_enabled(enabled: bool) -> None:
    set_setting("helper_tooltips_enabled", "1" if enabled else "0")
    settings_state["helper_tooltips_enabled"] = enabled
    render_dashboard_header.refresh()
    render_forecast.refresh()
    render_manual_event_editor.refresh()
    render_override_editor.refresh()
    refresh_all_rule_views()
    render_settings.refresh()
    ui.notify(
        "Tooltip guida attivati." if enabled else "Tooltip guida disattivati.",
        color="positive",
    )


def import_workbook(upload_event) -> None:
    filename = (upload_event.name or "").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        ui.notify("Importa un file Excel .xlsx o .xlsm.", color="negative")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(upload_event.content.read())

    try:
        rules = extract_rules(temp_path)
        replace_transaction_rules(rules)
    except Exception as exc:
        ui.notify(f"Import Excel non riuscito: {exc}", color="negative")
        return
    finally:
        temp_path.unlink(missing_ok=True)

    refresh_all_rule_views()
    clear_rule_selection(refresh_editor=False)
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()
    render_manual_event_editor.refresh()
    ui.notify(f"Importate {len(rules)} regole da {filename}.", color="positive")


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

    manual_event_state["expanded"] = False
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
    manual_event_state["expanded"] = False
    manual_event_state["event_date"] = format_ui_date(date.today())
    manual_event_state["description"] = ""
    manual_event_state["amount"] = ""
    manual_event_state["payment_method"] = "Conto"
    manual_event_state["note"] = ""
    if refresh_editor:
        render_manual_event_editor.refresh()


def get_selected_forecast_key() -> str:
    return str(forecast_state.get("selected_key") or "")


def select_forecast_row(value: str | None) -> None:
    selected_key = value or ""
    if selected_key and selected_key == get_selected_forecast_key():
        forecast_state["selected_key"] = ""
        clear_manual_event_selection(refresh_editor=False)
        select_override_event(None, refresh_editor=False)
        render_forecast.refresh()
        render_manual_event_editor.refresh()
        render_override_editor.refresh()
        return

    selected_row = next(
        (row for row in override_state["rows"] if row["selection_key"] == selected_key),
        None,
    )
    if selected_row is None:
        forecast_state["selected_key"] = ""
        clear_manual_event_selection(refresh_editor=False)
        select_override_event(None, refresh_editor=False)
    elif selected_row["description"].strip().lower() == "carta di credito calcolata":
        forecast_state["selected_key"] = selected_row["selection_key"]
        clear_manual_event_selection(refresh_editor=False)
        select_override_event(None, refresh_editor=False)
    elif selected_row["is_manual_event"]:
        forecast_state["selected_key"] = selected_row["selection_key"]
        manual_event_state["selected_event_id"] = selected_row["source_manual_event_id"]
        manual_event_state["selected_key"] = selected_row["selection_key"]
        manual_event_state["expanded"] = True
        manual_event_state["event_date"] = selected_row["date"]
        manual_event_state["description"] = selected_row["description"]
        manual_event_state["amount"] = selected_row["amount"]
        manual_event_state["payment_method"] = selected_row["payment_method"] or "Conto"
        manual_event_state["note"] = selected_row["note"] or ""
        select_override_event(None, refresh_editor=False)
    else:
        forecast_state["selected_key"] = selected_row["selection_key"]
        clear_manual_event_selection(refresh_editor=False)
        if selected_row["editable"]:
            select_override_event(selected_row["selection_key"], refresh_editor=False)
        else:
            select_override_event(None, refresh_editor=False)

    render_forecast.refresh()
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


def toggle_manual_event_editor() -> None:
    manual_event_state["expanded"] = not bool(manual_event_state["expanded"])
    render_manual_event_editor.refresh()


def cancel_manual_event_editor() -> None:
    clear_manual_event_selection(refresh_editor=False)
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
            else f"{selected_row['amount_value']:.2f}"
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

rule_state: dict[str, object] = {
    "account_filter": "Fineco",
    "show_expired": False,
    "selected_rule_id": None,
    "account_name": "Fineco",
    "description": "",
    "amount": "",
    "frequency": "monthly",
    "day_of_month": "",
    "month_of_year": "",
    "payment_method": "Conto",
    "provider": "",
    "start_date": "",
    "end_date": "",
    "installments_total": "",
    "active": True,
    "source_sheet": "",
}
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
    "selected_key": "",
}
dashboard_state = {
    "account_name": "Fineco",
}
settings_state = {
    "forecast_window_months": str(get_forecast_window_months()),
    "warning_margin": str(int(get_warning_margin())),
    "helper_tooltips_enabled": get_helper_tooltips_enabled(),
}
manual_event_state = {
    "selected_event_id": None,
    "selected_key": "",
    "expanded": False,
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
    rule_state["account_filter"] = default_name

sync_snapshot_form(dashboard_state["account_name"])
forecast_state["account_name"] = dashboard_state["account_name"]
refresh_forecast_defaults()

ui.query("body").style("background: linear-gradient(180deg, #f3efe5 0%, #fbf8f2 100%);")
ui.add_head_html(
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">'
)
ui.add_head_html(
    """
    <style>
    .forecast-table .q-table__middle {
        max-height: 990px;
    }
    .forecast-table thead tr th {
        position: sticky;
        top: 0;
        z-index: 2;
        background: #f6f1e8;
    }
    .forecast-table .q-table__bottom {
        position: sticky;
        bottom: 0;
        z-index: 2;
        background: #fffdf8;
        border-top: 1px solid rgba(47, 36, 31, 0.08);
    }
    .forecast-table .selected-marker-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        color: #607d8b;
        font-size: 16px;
        visibility: hidden;
    }
    .forecast-table .selected-marker-icon.active {
        visibility: visible;
    }
    </style>
    """
)

with ui.column().classes("w-full max-w-7xl mx-auto gap-4 p-6"):
    with ui.tabs().classes("w-full") as tabs:
        dashboard_tab = ui.tab("Movimenti")
        rules_tab = ui.tab("Regole")
        settings_tab = ui.tab("Impostazioni")

    @ui.refreshable
    def render_rule_stats(account_filter: str) -> None:
        rules = load_rules(account_filter, show_expired=bool(rule_state["show_expired"]))
        all_rules = load_rules(account_filter, show_expired=True)
        active_rules = [
            rule
            for rule in all_rules
            if rule["active"] and not is_rule_expired(rule["end_date"])
        ]
        expired_rules = [rule for rule in all_rules if is_rule_expired(rule["end_date"])]
        disabled_rules = [
            rule
            for rule in all_rules
            if not rule["active"] and not is_rule_expired(rule["end_date"])
        ]

        with ui.card().classes("w-full").style("padding-top: 8px; padding-bottom: 6px;"):
            with ui.column().classes("w-full gap-0"):
                with ui.row().classes("w-full items-center justify-between gap-4"):
                    ui.label("Riepilogo regole").style(
                        "color: #6b5b53; font-size: 12px; line-height: 1; text-transform: uppercase; letter-spacing: 0.08em"
                    )
                with ui.row().classes("w-full items-center justify-between gap-4 no-wrap"):
                    for title, value in (
                        ("Visibili", len(rules)),
                        ("Attive effettive", len(active_rules)),
                        ("Disattivate manualmente", len(disabled_rules)),
                        ("Scadute", len(expired_rules)),
                    ):
                        with ui.row().classes("items-baseline gap-2"):
                            ui.label(f"{title}:").style(
                                "color: #5f5048; font-size: 13px; line-height: 1"
                            )
                            ui.label(str(value)).style(
                                "font-size: 15px; line-height: 1; font-weight: 700; color: #2f241f"
                            )
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Mostra scadute:").style(
                            "color: #5f5048; font-size: 13px; line-height: 1"
                        )
                        add_tooltip(
                            ui.switch(
                                value=bool(rule_state["show_expired"]),
                                on_change=lambda event: (
                                    rule_state.__setitem__("show_expired", bool(event.value)),
                                    refresh_all_rule_views(),
                                ),
                            ),
                            "Mostra anche le regole scadute, cosi puoi modificarle o estenderne la validita.",
                        )

    @ui.refreshable
    def render_rules(account_filter: str) -> None:
        rules = load_rules(account_filter, show_expired=bool(rule_state["show_expired"]))

        with ui.column().classes("w-full gap-3"):
            if not rules:
                with ui.card().classes("w-full"):
                    ui.label("Nessuna regola disponibile per il filtro selezionato.")
                return

            for rule in rules:
                _, status_color = get_rule_status(rule)
                supplier = rule["provider"] or "-"
                date_range = format_rule_validity(rule["start_date"], rule["end_date"])
                is_selected = rule_state["selected_rule_id"] == int(rule["id"])
                payment_icon = (
                    "credit_card"
                    if (rule["payment_method"] or "").lower() == "carta"
                    else "account_balance_wallet"
                )

                card = ui.card().classes("w-full cursor-pointer transition-all")
                card.style(
                    get_rule_card_style(is_selected, status_color)
                    + f" background-color: {get_rule_frequency_tint(rule)} !important;"
                )
                card.on("click", lambda _, rule_id=rule["id"]: select_rule(int(rule_id)))
                with card:
                    with ui.row().classes("w-full items-center justify-between gap-3 no-wrap"):
                        with ui.row().classes("items-center gap-2 min-w-[220px] no-wrap"):
                            ui.icon(payment_icon).style(
                                f"font-size: 26px; color: {status_color}; margin-top: 4px; margin-right: 6px"
                            )
                            with ui.column().classes("gap-0"):
                                ui.label(rule["description"]).style(
                                    f"font-size: 15px; line-height: 1.1; font-weight: 600; color: {'#2f241f' if is_selected else '#4f4540'}"
                                )
                                ui.label(
                                    f"{rule['amount']:.2f} EUR"
                                ).style("color: #72665f; font-size: 13px; line-height: 1.1; font-weight: 600")
                        with ui.column().classes("gap-0 items-end"):
                            ui.label(
                                f"{format_rule_frequency(rule)} | {format_cadence(rule)}"
                            ).style("color: #72665f; font-size: 12px; line-height: 1.1")
                            ui.label(supplier).style(
                                "color: #8b817c; font-size: 11px; line-height: 1.1"
                            )
                            ui.label(date_range).style(
                                "color: #8b817c; font-size: 11px; line-height: 1.1"
                            )

    @ui.refreshable
    def render_rule_editor() -> None:
        account_options = [account["name"] for account in get_accounts()]
        selected_rule_id = rule_state["selected_rule_id"]
        account_name = str(rule_state["account_name"])
        description = str(rule_state["description"])
        amount = str(rule_state["amount"])
        frequency = str(rule_state["frequency"])
        day_of_month = str(rule_state["day_of_month"])
        month_of_year = str(rule_state["month_of_year"])
        payment_method = str(rule_state["payment_method"])
        supplier = str(rule_state["provider"])
        start_date = str(rule_state["start_date"])
        end_date = str(rule_state["end_date"])
        installments_total = str(rule_state["installments_total"])
        active = bool(rule_state["active"])

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between gap-3").style("margin-top: -10px;"):
                ui.label(
                    "Modifica regola" if selected_rule_id is not None else "Nuova regola"
                ).style("font-size: 18px; font-weight: 600")
                if selected_rule_id is None:
                    add_tooltip(
                        ui.button(icon="add", on_click=start_new_rule).props("round flat"),
                        "Prepara il form per inserire una nuova regola.",
                    )
                if selected_rule_id is not None:
                    add_tooltip(
                        ui.switch(
                            text="Abilitata",
                            value=active,
                            on_change=lambda event: rule_state.__setitem__(
                                "active", bool(event.value)
                            ),
                        ),
                        "Attiva o disattiva manualmente questa regola senza cancellarla.",
                    )
            if selected_rule_id is None:
                return

            with ui.column().classes("w-full gap-1"):
                add_tooltip(
                    ui.select(
                        options=account_options,
                        value=account_name,
                        label="Conto",
                        on_change=lambda event: rule_state.__setitem__(
                            "account_name", event.value
                        ),
                    ),
                    "Conto su cui la regola impatta la previsione.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Descrizione",
                        value=description,
                        on_change=lambda event: rule_state.__setitem__(
                            "description", event.value
                        ),
                    ),
                    "Descrizione mostrata nei movimenti generati dalla regola.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Importo",
                        value=amount,
                        on_change=lambda event: rule_state.__setitem__(
                            "amount", event.value
                        ),
                    ),
                    "Importo della regola: negativo per uscite, positivo per entrate.",
                ).classes("w-full")
                add_tooltip(
                    ui.select(
                        options={"monthly": "Mensile", "yearly": "Annuale"},
                        value=frequency,
                        label="Frequenza",
                        on_change=lambda event: rule_state.__setitem__(
                            "frequency", event.value
                        ),
                    ),
                    "Scegli se la regola si ripete ogni mese o una volta l'anno.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Giorno",
                        value=day_of_month,
                        on_change=lambda event: rule_state.__setitem__(
                            "day_of_month", event.value
                        ),
                    ),
                    "Giorno del mese in cui la regola genera il movimento.",
                ).classes("w-full")
                if frequency == "yearly":
                    add_tooltip(
                        ui.input(
                            label="Mese",
                            value=month_of_year,
                            on_change=lambda event: rule_state.__setitem__(
                                "month_of_year", event.value
                            ),
                        ),
                        "Mese dell'anno per le regole annuali.",
                    ).classes("w-full")
                add_tooltip(
                    ui.select(
                        options=["Conto", "Carta"],
                        value=payment_method,
                        label="Pagamento",
                        on_change=lambda event: rule_state.__setitem__(
                            "payment_method", event.value
                        ),
                    ),
                    "Conto applica il movimento subito; Carta lo porta al saldo carta del mese successivo.",
                ).classes("w-full")
                add_tooltip(
                    ui.select(
                        label="Fornitore",
                        with_input=True,
                        new_value_mode="add-unique",
                        options=get_provider_options(),
                        value=supplier,
                        on_change=lambda event: rule_state.__setitem__(
                            "provider", event.value
                        ),
                    ),
                    "Campo facoltativo per banca, finanziaria o altro fornitore collegato alla regola.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Data inizio",
                        value=start_date,
                        on_change=lambda event: rule_state.__setitem__(
                            "start_date", event.value
                        ),
                    ),
                    "Data da cui la regola inizia a produrre movimenti, formato DD-MM-YYYY.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Data fine",
                        value=end_date,
                        on_change=lambda event: rule_state.__setitem__(
                            "end_date", event.value
                        ),
                    ),
                    "Data oltre la quale la regola e considerata scaduta; svuota il campo per riattivarla nel tempo.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Numero rate",
                        value=installments_total,
                        on_change=lambda event: rule_state.__setitem__(
                            "installments_total", event.value
                        ),
                    ),
                    "Numero totale rate, se la regola rappresenta un pagamento rateale.",
                ).classes("w-full")
                with ui.row().classes("w-full justify-end gap-2 pt-0"):
                    add_tooltip(
                        ui.button(icon="close", on_click=clear_rule_selection).props(
                            "round flat"
                        ),
                        "Deseleziona la regola e svuota il pannello di modifica.",
                    )
                    add_tooltip(
                        ui.button(icon="save", on_click=save_rule_changes).props(
                            "round flat"
                        ),
                        "Salva i cambiamenti fatti alla regola selezionata.",
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

            selected_forecast_key = get_selected_forecast_key()

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
                        "selected_bg": month_selected_background(event.event_date.month),
                        "selected_border": "#2f241f",
                        "month_break": previous_month_key is not None
                        and month_key != previous_month_key,
                        "date": format_ui_date(event.event_date),
                        "type": type_icon,
                        "description": event.description,
                        "description_label": event.description,
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
                        "related_descriptions": list(getattr(event, "related_descriptions", []) or []),
                    }
                )
                previous_month_key = month_key

            for row in forecast_rows:
                row["is_selected"] = row["selection_key"] == selected_forecast_key

            selected_forecast_row = next(
                (row for row in forecast_rows if row["is_selected"]),
                None,
            )

            with ui.card().classes("w-full"):
                if selected_forecast_row is None:
                    ui.label("Nessun movimento selezionato.").style(
                        "color: #9a9089; font-size: 13px"
                    )
                else:
                    amount_text = selected_forecast_row["amount"]
                    clean_amount = amount_text[1:] if amount_text.startswith("-") else amount_text
                    amount_with_symbol = f"€{clean_amount}"
                    movement_label = (
                        "addebito"
                        if selected_forecast_row["amount_value"] < 0
                        else "accredito"
                    )
                    ui.label(
                        f"{format_ui_date_long(selected_forecast_row['date'])}, {movement_label} di {amount_with_symbol} per {selected_forecast_row['description']}"
                    ).style("font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; color: #2f241f")
                    if selected_forecast_row["description"].strip().lower() == "carta di credito calcolata":
                        details = selected_forecast_row["related_descriptions"]
                        if details:
                            ui.label("Componenti: " + " | ".join(details)).style(
                                "font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b5b53"
                            )

            table = ui.table(
                columns=[
                    {
                        "name": "status",
                        "label": "Stato",
                        "field": "status",
                        "align": "center",
                    },
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
                ],
                rows=forecast_rows,
                row_key="id",
                pagination=34,
            ).classes("w-full rounded-xl overflow-hidden forecast-table")
            table.props('table-style="max-height: 990px"')
            table.style("font-family: 'IBM Plex Mono', monospace; font-size: 11px")
            override_state["rows"] = forecast_rows
            available_rows = [row for row in forecast_rows if row["editable"]]
            if override_state["selected_key"] and not any(
                row["selection_key"] == override_state["selected_key"]
                for row in available_rows
            ):
                override_state["selected_key"] = ""
            table.add_slot(
                "body",
                r"""
                <q-tr :props="props" @click="() => $parent.$emit('select_override_row', props.row.selection_key)" :class="props.row.is_selected ? 'cursor-pointer forecast-selected-row' : 'cursor-pointer'" :style="'background-color:' + props.row.row_bg + '; border-top:' + (props.row.month_break ? '4px solid #8f7f73' : '0')">
                    <q-td key="status" :props="props" class="text-center" :style="'background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">
                        <q-icon v-if="props.row.is_selected" name="edit" color="blue-grey-6" size="sm" />
                        <q-icon v-else :name="props.row.status" :color="props.row.status === 'dangerous' ? 'negative' : (props.row.status === 'warning' ? 'warning' : 'positive')" size="sm" />
                    </q-td>
                    <q-td key="date" :props="props" :style="'padding-top: 2px; padding-bottom: 2px; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">{{ props.row.date }}</q-td>
                    <q-td key="schedule" :props="props" class="text-center" :style="'background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">
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
                    <q-td key="type" :props="props" class="text-center" :style="'background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">
                        <q-icon :name="props.row.type" :color="props.row.amount_value < 0 ? 'negative' : 'positive'" size="sm" />
                    </q-td>
                    <q-td key="description" :props="props" :style="'padding-top: 2px; padding-bottom: 2px; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">
                        <div class="row items-center no-wrap">
                            <q-icon v-if="props.row.carried_overdue" name="history" color="warning" size="xs" class="q-mr-xs" />
                            <span>{{ props.row.description_label }}</span>
                        </div>
                    </q-td>
                    <q-td key="amount" :props="props" :style="'padding-top: 2px; padding-bottom: 2px; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)" :class="props.row.amount_value < 0 ? 'text-[#8a1c1c]' : 'text-[#1f7a1f]'">{{ props.row.amount }}</q-td>
                    <q-td key="balance" :props="props" :style="'padding-top: 2px; padding-bottom: 2px; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)" :class="props.row.balance_value < 0 ? 'text-[#8a1c1c] font-semibold' : 'text-[#2f241f] font-semibold'">{{ props.row.balance }}</q-td>
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
                else "Movimento una tantum"
            )
            with ui.row().classes("w-full items-center justify-between gap-2").style("margin-top: -10px;"):
                ui.label(title).style("font-size: 18px; font-weight: 600")
                if manual_event_state["selected_event_id"] is None:
                    add_tooltip(
                        ui.button(icon="add", on_click=toggle_manual_event_editor).props(
                            "round flat"
                        ),
                        "Apri o chiudi il riquadro del movimento una tantum.",
                    )
                if manual_event_state["selected_event_id"] is not None:
                    add_tooltip(
                        ui.button(
                            icon=("expand_less" if manual_event_state["expanded"] else "expand_more"),
                            on_click=toggle_manual_event_editor,
                        ).props("round flat"),
                        "Apri o chiudi il riquadro del movimento una tantum.",
                    )
            if not manual_event_state["expanded"] and manual_event_state["selected_event_id"] is None:
                return
            if manual_event_state["selected_event_id"] is not None:
                ui.label(
                    "Hai selezionato un movimento manuale dalla tabella: puoi aggiornarlo o annullarlo."
                ).style("color: #6b5b53; font-size: 13px")
            with ui.column().classes("w-full gap-1"):
                add_tooltip(
                    ui.input(
                        label="Data movimento",
                        value=manual_event_state["event_date"],
                        on_change=lambda event: manual_event_state.__setitem__(
                            "event_date", event.value
                        ),
                    ),
                    "Data del movimento una tantum, nel formato DD-MM-YYYY.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Descrizione una tantum",
                        value=manual_event_state["description"],
                        on_change=lambda event: manual_event_state.__setitem__(
                            "description", event.value
                        ),
                    ),
                    "Nome breve del movimento manuale che vuoi aggiungere o modificare.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Importo",
                        value=manual_event_state["amount"],
                        on_change=lambda event: manual_event_state.__setitem__(
                            "amount", event.value
                        ),
                    ),
                    "Importo del movimento: usa un valore negativo per un'uscita e positivo per un'entrata.",
                ).classes("w-full")
                add_tooltip(
                    ui.select(
                        options=["Conto", "Carta"],
                        value=manual_event_state["payment_method"],
                        on_change=lambda event: manual_event_state.__setitem__(
                            "payment_method", event.value
                        ),
                    ),
                    "Indica se il movimento impatta il conto direttamente o passa dalla carta.",
                ).classes("w-full")
                with ui.row().classes("w-full justify-end gap-2 pt-0"):
                    if manual_event_state["selected_event_id"] is not None:
                        add_tooltip(
                            ui.button(icon="close", on_click=clear_manual_event_selection),
                            "Esci dalla modifica e svuota il form senza cancellare il movimento.",
                        ).props("round flat")
                        add_tooltip(
                            ui.button(icon="delete", on_click=delete_manual_event),
                            "Annulla il movimento manuale selezionato e toglilo dalla previsione.",
                        ).props("round flat")
                    else:
                        add_tooltip(
                            ui.button(icon="close", on_click=cancel_manual_event_editor),
                            "Chiudi il riquadro senza salvare il movimento.",
                        ).props("round flat")
                    add_tooltip(
                        ui.button(
                            icon="save",
                            on_click=save_manual_event,
                        ),
                        "Salva questo movimento manuale oppure aggiorna quello selezionato.",
                    ).props("round flat")

    @ui.refreshable
    def render_override_editor() -> None:
        editable_rows = [row for row in override_state["rows"] if row["editable"]]
        selected_editable_row = next(
            (
                row
                for row in editable_rows
                if row["selection_key"] == override_state["selected_key"]
            ),
            None,
        )

        with ui.card().classes("w-full"):
            ui.label("Personalizzazione movimento").style(
                "margin-top: -6px; "
                "font-size: 18px; font-weight: 600"
            )
            if not editable_rows:
                ui.label(
                    "Nessun movimento modificabile nella finestra di previsione."
                ).style("color: #6b5b53")
                return

            if not override_state["selected_key"]:
                ui.label("Nessun movimento selezionato.").style(
                    "color: #9a9089; font-size: 13px"
                )
                return

            event_options = {
                row[
                    "selection_key"
                ]: f"{row['date']} | {row['description']} | {row['amount']}"
                for row in editable_rows
            }
            add_tooltip(
                ui.select(
                    options=event_options,
                    value=override_state["selected_key"] or next(iter(event_options)),
                    label="Movimento da modificare",
                    on_change=lambda event: select_override_event(event.value),
                ),
                "Seleziona un movimento generato da regola per personalizzarne data, importo o descrizione.",
            ).classes("w-full")

            with ui.column().classes("w-full gap-0 mt-1"):
                add_tooltip(
                    ui.input(
                        label="Nuova descrizione",
                        value=override_state["override_description"],
                        on_change=lambda event: override_state.__setitem__(
                            "override_description", event.value
                        ),
                    ),
                    "Descrizione sostitutiva per questa singola occorrenza della regola.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Nuova data",
                        value=override_state["override_event_date"],
                        on_change=lambda event: override_state.__setitem__(
                            "override_event_date", event.value
                        ),
                    ),
                    "Nuova data pianificata per questo solo movimento, nel formato DD-MM-YYYY.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Nuovo importo",
                        value=override_state["override_amount"],
                        on_change=lambda event: override_state.__setitem__(
                            "override_amount", event.value
                        ),
                    ),
                    "Nuovo importo per questa singola occorrenza della regola.",
                ).classes("w-full")
                add_tooltip(
                    ui.select(
                        options={"auto": "Auto", "manual": "Manuale"},
                        value=override_state["resolution_mode"],
                        label="Risoluzione",
                        on_change=lambda event: override_state.__setitem__(
                            "resolution_mode", event.value
                        ),
                    ),
                    "Auto segue la pianificazione; Manuale lascia il movimento pendente finche non lo chiudi.",
                ).classes("w-full")
                add_tooltip(
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
                    ),
                    "Stato operativo dell'override selezionato.",
                ).classes("w-full")
                with ui.row().classes("w-full justify-end gap-2 pt-0"):
                    if selected_editable_row and selected_editable_row["has_override"]:
                        add_tooltip(
                            ui.button(icon="restore_page", on_click=clear_event_override),
                            "Ripristina il movimento originale dal database rimuovendo l'override.",
                        ).props("round flat")
                    add_tooltip(
                        ui.button(icon="save", on_click=save_event_override),
                        "Salva la personalizzazione del movimento selezionato.",
                    ).props("round flat")

    @ui.refreshable
    def render_dashboard_header() -> None:
        with ui.card().classes("w-full"):
            with ui.column().classes("w-full gap-3"):
                with ui.row().classes("items-center gap-3").style("margin-top: -10px;"):
                    add_tooltip(
                        ui.select(
                        options=[account_row["name"] for account_row in get_accounts()],
                        value=dashboard_state["account_name"],
                        on_change=lambda event: select_active_account(event.value),
                        ),
                        "Scegli il conto su cui lavorare nella vista Movimenti.",
                    ).classes("min-w-[240px]").style(
                        "font-family: 'IBM Plex Mono', monospace; font-size: 28px; text-transform: uppercase; letter-spacing: 0.08em"
                    )
                    add_tooltip(
                        ui.button(
                            icon="refresh",
                            on_click=lambda: (
                                try_run_default_forecast(),
                                render_forecast.refresh(),
                            ),
                        ),
                        "Ricalcola la previsione usando i dati correnti del conto selezionato.",
                    ).props("round flat")

            with ui.row().classes("w-full items-end gap-4"):
                add_tooltip(
                    ui.input(
                        label="Data aggiornamento",
                        value=snapshot_state["snapshot_date"],
                        on_change=lambda event: snapshot_state.__setitem__(
                            "snapshot_date", event.value
                        ),
                    ),
                    "Data del saldo reale verificato, nel formato DD-MM-YYYY.",
                ).classes("min-w-[180px]")
                add_tooltip(
                    ui.input(
                        label="Saldo",
                        value=snapshot_state["balance"],
                        on_change=lambda event: snapshot_state.__setitem__(
                            "balance", event.value
                        ),
                    ),
                    "Saldo reale del conto alla data indicata; diventa la base della previsione.",
                ).classes("min-w-[160px]")
                add_tooltip(
                    ui.input(
                        label="Nota",
                        value=snapshot_state["note"],
                        on_change=lambda event: snapshot_state.__setitem__(
                            "note", event.value
                        ),
                    ),
                    "Nota facoltativa per ricordare come hai verificato o riconciliato il saldo.",
                ).classes("min-w-[260px]")
                add_tooltip(
                    ui.button(icon="save", on_click=save_snapshot),
                    "Salva o aggiorna lo snapshot del saldo reale per il conto attivo.",
                ).props("round flat")

    @ui.refreshable
    def render_settings() -> None:
        accounts = get_accounts()

        with ui.column().classes("w-full gap-3"):
            with ui.card().classes("w-full"):
                ui.label("Opzioni movimenti").style(
                    "margin-top: -6px; "
                    "font-size: 22px; font-weight: 600"
                )
                with ui.row().classes("items-end gap-3"):
                    forecast_window_input = add_tooltip(
                        ui.input(
                            label="Finestra previsione (mesi)",
                            value=settings_state["forecast_window_months"],
                        ),
                        "Numero di mesi mostrati di default nella previsione del conto.",
                    ).classes("min-w-[220px]")
                    add_tooltip(
                        ui.button(
                            "Salva finestra",
                            on_click=lambda _: save_forecast_window_months(
                                forecast_window_input.value
                            ),
                        ),
                        "Applica la nuova durata predefinita della previsione.",
                    )

                with ui.row().classes("items-end gap-3 mt-3"):
                    warning_margin_input = add_tooltip(
                        ui.input(
                            label="Soglia attenzione (€)",
                            value=settings_state["warning_margin"],
                        ),
                        "Margine sopra il fido entro cui la previsione segnala una situazione di attenzione.",
                    ).classes("min-w-[220px]")
                    add_tooltip(
                        ui.button(
                            "Salva soglia",
                            on_click=lambda _: save_warning_margin(
                                warning_margin_input.value
                            ),
                        ),
                        "Salva la soglia usata per evidenziare i periodi a rischio.",
                    )

            with ui.card().classes("w-full"):
                ui.label("Impostazioni generali").style(
                    "margin-top: -6px; "
                    "font-size: 22px; font-weight: 600"
                )
                ui.label("Preferenze dell'interfaccia e del progetto.").style(
                    "color: #6b5b53"
                )

                with ui.row().classes("items-center gap-3").style("margin-top: -10px;"):
                    add_tooltip(
                        ui.switch(
                            text="Mostra tooltip guida",
                            value=settings_state["helper_tooltips_enabled"],
                            on_change=lambda event: save_helper_tooltips_enabled(
                                bool(event.value)
                            ),
                        ),
                        "Attiva o disattiva i suggerimenti contestuali sui controlli dell'interfaccia.",
                    )

            with ui.card().classes("w-full"):
                ui.label("Importazione Excel").style(
                    "margin-top: -6px; "
                    "font-size: 22px; font-weight: 600"
                )
                ui.label("Importa regole da un file Excel del piano economico.").style(
                    "color: #6b5b53"
                )

                with ui.row().classes("items-center gap-3"):
                    add_tooltip(
                        ui.upload(
                            label="Importa file Excel",
                            auto_upload=True,
                            on_upload=import_workbook,
                        ).props('accept=".xlsx,.xlsm"'),
                        "Importa regole da un file Excel .xlsx o .xlsm e aggiorna il database.",
                    ).classes("min-w-[260px]")

            with ui.card().classes("w-full"):
                ui.label("Fido conti").style("margin-top: -6px; font-size: 22px; font-weight: 600")
                ui.label("Imposta il fido disponibile per ogni conto.").style(
                    "color: #6b5b53"
                )

                for account in accounts:
                    with ui.row().classes("w-full items-end gap-3"):
                        ui.label(account["name"]).classes("min-w-[140px]")
                        overdraft_input = add_tooltip(
                            ui.input(
                                label="Fido",
                                value=str(account["overdraft_limit"] or 0),
                            ),
                            f"Imposta il fido disponibile per il conto {account['name']}.",
                        ).classes("min-w-[180px]")
                        add_tooltip(
                            ui.button(
                                "Salva",
                                on_click=lambda _, acc_name=account["name"], field=overdraft_input: (
                                    save_overdraft_limit(acc_name, field.value)
                                ),
                            ),
                            f"Salva il nuovo fido del conto {account['name']}.",
                        )

    with ui.tab_panels(tabs, value=dashboard_tab).classes("w-full"):
        with ui.tab_panel(dashboard_tab).classes("gap-4"):
            render_dashboard_header()
            with ui.row().classes("w-full items-start gap-4 no-wrap"):
                with ui.column().classes("min-w-0").style("flex: 1 1 0;"):
                    render_forecast()
                with ui.column().classes("gap-4").style("width: 320px; flex: 0 0 320px;"):
                    with ui.column().classes("w-full sticky top-4 gap-4"):
                        render_manual_event_editor()
                        render_override_editor()

        with ui.tab_panel(rules_tab).classes("gap-4"):
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center gap-3"):
                    add_tooltip(
                        ui.select(
                            options=[account_row["name"] for account_row in get_accounts()],
                            value=str(rule_state["account_filter"]),
                            on_change=lambda event: (
                                rule_state.__setitem__("account_filter", event.value),
                                render_rule_stats.refresh(event.value),
                                render_rules.refresh(event.value),
                                refresh_rule_editor(),
                            ),
                        ),
                        "Scegli il conto di cui vuoi visualizzare le regole oppure tutte le regole.",
                    ).classes("min-w-[240px]").style(
                        "font-family: 'IBM Plex Mono', monospace; font-size: 28px; text-transform: uppercase; letter-spacing: 0.08em"
                    )

            render_rule_stats(str(rule_state["account_filter"]))
            with ui.row().classes("w-full items-start gap-4 no-wrap"):
                with ui.column().classes("min-w-0 gap-2").style("flex: 1 1 0;"):
                    with ui.scroll_area().classes("w-full h-[68vh] pr-2"):
                        render_rules(str(rule_state["account_filter"]))
                with ui.column().classes("min-w-0").style("width: 400px; flex: 0 0 400px;"):
                    with ui.column().classes("w-full sticky top-0"):
                        render_rule_editor()

        with ui.tab_panel(settings_tab).classes("gap-4"):
            render_settings()

ui.run()

import tempfile
import inspect
from datetime import date, datetime
from pathlib import Path

from nicegui import app, ui

from db import (
    add_transaction_rule,
    add_app_log,
    add_manual_event,
    cleanup_cancelled_manual_events,
    cleanup_closed_overrides,
    cleanup_obsolete_rules,
    clear_app_logs,
    delete_transaction_rule,
    delete_forecast_event_override,
    get_account_by_name,
    get_accounts,
    get_app_logs,
    get_bool_setting,
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


APP_VERSION = "0.1.0"
ACCOUNT_LOGO_DIR = Path("account_logos")
ASSET_DIR = Path("assets")

ACCOUNT_LOGO_DIR.mkdir(exist_ok=True)
ASSET_DIR.mkdir(exist_ok=True)
app.add_static_files("/account_logos", str(ACCOUNT_LOGO_DIR.resolve()))
app.add_static_files("/assets", str(ASSET_DIR.resolve()))


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


def format_month_label(value: date) -> str:
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
    return f"{months[value.month - 1]} {value.year}"


def format_html_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return parse_ui_date(value).isoformat()
    except ValueError:
        return value


def parse_ui_date(value: str) -> date:
    return datetime.strptime(value, "%d-%m-%Y").date()


def format_overdraft_limit(value: float | None) -> str:
    if not value:
        return "nessun fido"
    return f"fido € {value:.2f}"


def currency_input_style(direction: str) -> str:
    return f"color: {'#8a1c1c' if direction == 'Uscita' else '#1f7a1f'};"


def positive_amount_validation(value: str) -> bool:
    cleaned = (value or "").replace("€", "").replace(" ", "")
    if cleaned == "":
        return True
    if cleaned.startswith("-"):
        return False
    try:
        numeric = float(cleaned.replace(",", "."))
    except ValueError:
        return False
    return numeric >= 0


def normalize_positive_amount_input(value: str) -> str:
    cleaned = (value or "").replace("€", "").replace("-", "").replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    filtered = ""
    dot_seen = False
    for char in cleaned:
        if char.isdigit():
            filtered += char
        elif char == "." and not dot_seen:
            filtered += char
            dot_seen = True
    if "." in filtered:
        head, tail = filtered.split(".", 1)
        filtered = head + "." + tail[:2]
    return filtered.replace(".", ",")


def log_action(category: str, message: str, details: str | None = None, level: str = "info") -> None:
    add_app_log(category=category, message=message, details=details, level=level)


def get_database_file_info() -> list[dict[str, str]]:
    file_info: list[dict[str, str]] = []
    for path in [Path("finance.db")]:
        if path.exists():
            file_info.append(
                {
                    "name": path.name,
                    "size": f"{path.stat().st_size / 1024:.1f} KB",
                    "path": str(path.resolve()),
                }
            )
    return file_info


def account_logo_setting_key(account_name: str) -> str:
    return f"account_logo::{account_name}"


def get_account_logo_path(account_name: str) -> Path | None:
    raw_value = get_setting(account_logo_setting_key(account_name), None)
    if not raw_value:
        return None
    path = Path(raw_value)
    return path if path.exists() else None


def get_account_logo_src(account_name: str) -> str | None:
    path = get_account_logo_path(account_name)
    if path is None:
        return None
    return f"/account_logos/{path.name}"


def render_account_selector_cards(selected_account: str, on_select, min_width: int = 170) -> None:
    accounts = get_accounts()
    with ui.row().classes("items-center gap-3 flex-wrap"):
        for account in accounts:
            account_name = account["name"]
            logo_src = get_account_logo_src(account_name)
            card = ui.card().classes("cursor-pointer").style(
                f"padding: 8px 12px; min-width: {min_width}px; border: 2px solid #2f241f;"
                if account_name == selected_account
                else f"padding: 8px 12px; min-width: {min_width}px; border: 1px solid rgba(47, 36, 31, 0.12);"
            )
            card.on("click", lambda _, value=account_name: on_select(value))
            with card:
                if logo_src:
                    with ui.column().classes("items-center gap-1"):
                        with ui.element("div").style(
                            "width:150px;height:48px;background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:8px;"
                        ):
                            ui.element("img").props(
                                f'src="{logo_src}" alt="{account_name}"'
                            ).style(
                                "display:block;max-width:140px;max-height:40px;width:auto;height:auto;object-fit:contain;"
                            )
                else:
                    ui.label(account_name).style(
                        "font-family: 'IBM Plex Mono', monospace; font-size: 24px; text-transform: uppercase; letter-spacing: 0.08em"
                    )


async def upload_account_logo(account_name: str, upload_event) -> None:
    file_obj = getattr(upload_event, "file", None) or getattr(upload_event, "content", None)
    if file_obj is None:
        ui.notify("Upload logo non riuscito.", color="negative")
        return
    filename = getattr(file_obj, "name", None) or getattr(upload_event, "name", None) or f"{account_name}.png"
    suffix = Path(str(filename)).suffix.lower() or ".png"
    safe_name = account_name.lower().replace(" ", "_")
    target_path = ACCOUNT_LOGO_DIR / f"{safe_name}{suffix}"
    content = file_obj.read() if hasattr(file_obj, "read") else file_obj
    if inspect.isawaitable(content):
        content = await content
    target_path.write_bytes(content)
    set_setting(account_logo_setting_key(account_name), str(target_path))
    log_action("app", "Logo conto aggiornato", account_name)
    render_dashboard_header.refresh()
    render_settings.refresh()
    ui.notify(f"Logo aggiornato per {account_name}.", color="positive")


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


def movement_status_background(status: str) -> str:
    palette = {
        "check_circle": "#eef7ee",
        "warning": "#fbf1d9",
        "dangerous": "#f7e2e2",
    }
    return palette.get(status, "#fcf8f4")


def month_accent_color(month: int) -> str:
    palette = {
        1: "#cf9a86",
        2: "#c9b27a",
        3: "#9eb97c",
        4: "#82b49d",
        5: "#7eb6b0",
        6: "#84a7c2",
        7: "#919dc8",
        8: "#a393c8",
        9: "#bc97bf",
        10: "#c89a84",
        11: "#bba487",
        12: "#a8a0b5",
    }
    return palette.get(month, "#b7ada2")


def month_selected_background(month: int) -> str:
    return month_background(month)


def add_months(base_date: date, months: int) -> date:
    month_index = (base_date.month - 1) + months
    year = base_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base_date.day, 28)
    return date(year, month, day)


def add_years(base_date: date, years: int) -> date:
    target_year = base_date.year + years
    day = min(base_date.day, 28) if base_date.month == 2 else base_date.day
    return date(target_year, base_date.month, day)


def sync_rule_schedule_fields(changed_field: str) -> None:
    start_date_text = str(rule_state["start_date"] or "").strip()
    end_date_text = str(rule_state["end_date"] or "").strip()
    installments_text = str(rule_state["installments_total"] or "").strip()
    frequency = str(rule_state["frequency"])

    if not start_date_text:
        return

    try:
        start_dt = parse_ui_date(start_date_text)
    except ValueError:
        return

    if changed_field == "installments_total" and installments_text:
        try:
            installments = int(installments_text)
        except ValueError:
            return
        if installments < 1:
            return
        end_dt = (
            add_months(start_dt, installments - 1)
            if frequency == "monthly"
            else add_years(start_dt, installments - 1)
        )
        rule_state["end_date"] = format_ui_date(end_dt)
        return

    if changed_field == "end_date" and end_date_text:
        try:
            end_dt = parse_ui_date(end_date_text)
        except ValueError:
            return
        if end_dt < start_dt:
            return
        if frequency == "monthly":
            months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
            rule_state["installments_total"] = str(months + 1)
        else:
            rule_state["installments_total"] = str((end_dt.year - start_dt.year) + 1)
        return

    if changed_field == "start_date":
        if installments_text and not end_date_text:
            sync_rule_schedule_fields("installments_total")
        elif end_date_text and not installments_text:
            sync_rule_schedule_fields("end_date")


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


def get_rule_amount_color(rule: dict) -> str:
    return "#1f7a1f" if float(rule["amount"]) >= 0 else "#8a1c1c"


def get_rule_amount_background(rule: dict) -> str:
    return "#edf7ed" if float(rule["amount"]) >= 0 else "#f8e7e7"


def get_rule_frequency_icon(rule: dict) -> str:
    return "calendar_month" if rule["frequency"] == "yearly" else "date_range"


def get_rule_expiry_icon(rule: dict) -> str:
    return "event_repeat" if rule["end_date"] else "calendar_today"


def get_rule_card_style(rule: dict, is_selected: bool) -> str:
    amount_color = get_rule_amount_color(rule)
    background = "#efefef" if not rule["active"] else get_rule_amount_background(rule)
    if is_rule_expired(rule["end_date"]):
        background = "#f3efe8"
    base = (
        f"border-left: 7px solid {amount_color}; border-top: 1px solid rgba(47, 36, 31, 0.08); "
        f"border-right: 1px solid rgba(47, 36, 31, 0.08); border-bottom: 1px solid rgba(47, 36, 31, 0.08); padding: 6px 10px; "
    )
    if is_selected:
        return (
            base
            + f"background-color: {background} !important; box-shadow: 0 0 0 2px rgba(47, 36, 31, 0.12);"
        )
    return base + f"background-color: {background} !important;"


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
    rule_state["creating_new"] = False
    rule_state["account_name"] = dashboard_state["account_name"]
    rule_state["description"] = ""
    rule_state["amount"] = ""
    rule_state["frequency"] = "monthly"
    rule_state["day_of_month"] = ""
    rule_state["month_of_year"] = ""
    rule_state["payment_method"] = "Conto"
    rule_state["provider"] = ""
    rule_state["start_date"] = format_ui_date(date.today())
    rule_state["end_date"] = ""
    rule_state["installments_total"] = ""
    rule_state["active"] = True
    rule_state["source_sheet"] = ""
    refresh_all_rule_views()
    if refresh_editor:
        refresh_rule_editor()


def start_new_rule() -> None:
    clear_rule_selection(refresh_editor=False)
    rule_state["creating_new"] = True
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
    rule_state["creating_new"] = False
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
    is_new_rule = bool(rule_state.get("creating_new")) and rule_id is None
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
        log_action("db", "Nuova regola aggiunta", description)
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
        log_action("db", "Regola aggiornata", description)
        ui.notify("Regola aggiornata.", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()
    refresh_all_rule_views()
    clear_rule_selection(refresh_editor=False)
    refresh_rule_editor()


def delete_selected_rule() -> None:
    rule_id = rule_state["selected_rule_id"]
    if rule_id is None:
        ui.notify("Seleziona prima una regola da eliminare.", color="negative")
        return

    delete_transaction_rule(int(rule_id))
    log_action("db", "Regola eliminata", f"rule_id={rule_id}")
    ui.notify("Regola eliminata.", color="positive")
    clear_rule_selection(refresh_editor=False)
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()
    refresh_all_rule_views()
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
    log_action("db", "Snapshot salvato", f"{account_name} {snapshot_date_value.isoformat()} {balance:.2f}")
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


def save_show_calculated_card_settlement(enabled: bool) -> None:
    set_setting("show_calculated_card_settlement", "1" if enabled else "0")
    settings_state["show_calculated_card_settlement"] = enabled
    try_run_default_forecast()
    render_settings.refresh()
    render_forecast.refresh()
    render_override_editor.refresh()
    ui.notify(
        "Carta di credito calcolata attivata."
        if enabled
        else "Carta di credito calcolata disattivata.",
        color="positive",
    )


def save_credit_card_keyword(value_text: str) -> None:
    keyword = value_text.strip() or "Carta di credito"
    set_setting("credit_card_keyword", keyword)
    settings_state["credit_card_keyword"] = keyword
    try_run_default_forecast()
    render_settings.refresh()
    render_forecast.refresh()
    render_override_editor.refresh()
    ui.notify("Parola chiave Carta di credito aggiornata.", color="positive")


def run_cleanup_manual_events() -> None:
    deleted = cleanup_cancelled_manual_events()
    log_action("db", "Pulizia movimenti manuali", f"eliminati={deleted}")
    ui.notify(f"Movimenti manuali rimossi: {deleted}", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_settings.refresh()


def run_cleanup_overrides() -> None:
    deleted = cleanup_closed_overrides()
    log_action("db", "Pulizia override chiusi", f"eliminati={deleted}")
    ui.notify(f"Override rimossi: {deleted}", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()
    render_settings.refresh()


def run_cleanup_rules() -> None:
    deleted = cleanup_obsolete_rules()
    log_action("db", "Pulizia regole obsolete", f"eliminate={deleted}")
    ui.notify(f"Regole obsolete rimosse: {deleted}", color="positive")
    refresh_all_rule_views()
    refresh_rule_editor()
    render_settings.refresh()


def run_clear_logs() -> None:
    clear_app_logs()
    add_app_log("app", "Log ripuliti", None)
    render_settings.refresh()


async def import_workbook(upload_event) -> None:
    print("[upload-debug] attrs:", sorted(dir(upload_event)))
    filename = (
        getattr(upload_event, "name", None)
        or getattr(upload_event, "filename", None)
        or getattr(getattr(upload_event, "content", None), "name", None)
        or getattr(getattr(upload_event, "sender", None), "value", None)
        or "uploaded.xlsx"
    )
    filename = str(filename).strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        ui.notify("Importa un file Excel .xlsx o .xlsm.", color="negative")
        return

    file_obj = (
        getattr(upload_event, "content", None)
        or getattr(upload_event, "file", None)
        or getattr(upload_event, "data", None)
    )
    if file_obj is None:
        ui.notify("Upload non riuscito: file non disponibile nell'evento.", color="negative")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        if hasattr(file_obj, "read"):
            content = file_obj.read()
            if inspect.isawaitable(content):
                content = await content
            temp_file.write(content)
        else:
            temp_file.write(file_obj)

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
    log_action("db", "Import Excel completato", f"{filename} -> {len(rules)} regole")
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
        amount_text = (
            manual_event_state["amount"]
            .replace("€", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        if amount_text.startswith("-"):
            raise ValueError
        amount = float(amount_text)
    except ValueError:
        ui.notify("Controlla data e importo del movimento manuale.", color="negative")
        return

    amount = abs(amount)
    if manual_event_state["direction"] == "Uscita":
        amount = -amount

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
        log_action("db", "Movimento manuale aggiunto", description)
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
        log_action("db", "Movimento manuale aggiornato", description)
        ui.notify("Movimento manuale aggiornato.", color="positive")

    manual_event_state["expanded"] = False
    clear_manual_event_selection(refresh_editor=False)
    manual_event_state["description"] = ""
    manual_event_state["amount"] = ""
    manual_event_state["note"] = ""
    forecast_state["selected_key"] = ""
    ui.run_javascript(
        "document.querySelectorAll('.forecast-table tr[data-selection-key]').forEach(row => row.classList.remove('forecast-selected-row'))"
    )
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
    manual_event_state["direction"] = "Uscita"
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
        ui.run_javascript(
            "document.querySelectorAll('.forecast-table tr[data-selection-key]').forEach(row => row.classList.remove('forecast-selected-row'))"
        )
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
        manual_event_state["amount"] = f"{abs(float(selected_row['amount_value'])):.2f}"
        manual_event_state["direction"] = (
            "Uscita" if float(selected_row["amount_value"]) < 0 else "Entrata"
        )
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

    ui.run_javascript(
        f"document.querySelectorAll('.forecast-table tr[data-selection-key]').forEach(row => row.classList.toggle('forecast-selected-row', row.dataset.selectionKey === {selected_key!r}))"
    )
    render_manual_event_editor.refresh()
    render_override_editor.refresh()


def delete_manual_event() -> None:
    selected_event_id = manual_event_state["selected_event_id"]
    if selected_event_id is None:
        ui.notify("Seleziona prima un movimento manuale.", color="negative")
        return

    set_manual_event_status(selected_event_id, "cancelled")
    log_action("db", "Movimento manuale annullato", f"event_id={selected_event_id}")
    ui.notify("Movimento manuale annullato.", color="positive")
    clear_manual_event_selection(refresh_editor=False)
    try_run_default_forecast()
    render_forecast.refresh()
    render_manual_event_editor.refresh()


def duplicate_manual_event_next_month() -> None:
    selected_event_id = manual_event_state["selected_event_id"]
    account = get_account_by_name(dashboard_state["account_name"])
    if selected_event_id is None or account is None:
        ui.notify("Seleziona prima un movimento manuale da duplicare.", color="negative")
        return

    description = manual_event_state["description"].strip()
    amount_text = str(manual_event_state["amount"] or "").replace("€", "").replace(" ", "")
    if not description or not amount_text:
        ui.notify("Compila descrizione e importo prima di duplicare.", color="negative")
        return

    try:
        event_date = parse_ui_date(manual_event_state["event_date"])
        amount = float(amount_text.replace(",", "."))
    except ValueError:
        ui.notify("Controlla data e importo del movimento manuale.", color="negative")
        return

    amount = abs(amount)
    if manual_event_state["direction"] == "Uscita":
        amount = -amount

    add_manual_event(
        account_id=account["id"],
        event_date=add_months(event_date, 1).isoformat(),
        description=description,
        amount=amount,
        payment_method=manual_event_state["payment_method"] or None,
        note=manual_event_state["note"].strip() or None,
    )
    log_action("db", "Movimento manuale duplicato", description)
    ui.notify("Movimento duplicato al mese successivo.", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_manual_event_editor.refresh()


def toggle_manual_event_editor() -> None:
    manual_event_state["expanded"] = not bool(manual_event_state["expanded"])
    render_manual_event_editor.refresh()


def cancel_manual_event_editor() -> None:
    forecast_state["selected_key"] = ""
    clear_manual_event_selection(refresh_editor=False)
    ui.run_javascript(
        "document.querySelectorAll('.forecast-table tr[data-selection-key]').forEach(row => row.classList.remove('forecast-selected-row'))"
    )
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
        override_state["direction"] = "Uscita"
        override_state["resolution_mode"] = "auto"
        override_state["status"] = "open"
    elif not selected_row["editable"]:
        override_state["selected_key"] = ""
        override_state["rule_id"] = None
        override_state["original_event_date"] = ""
        override_state["override_description"] = ""
        override_state["override_event_date"] = ""
        override_state["override_amount"] = ""
        override_state["direction"] = "Uscita"
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
            f"{abs(float(selected_row['override_amount'])):.2f}"
            if selected_row["override_amount"] is not None
            else f"{abs(float(selected_row['amount_value'])):.2f}"
        )
        override_state["direction"] = (
            "Uscita" if float(selected_row["amount_value"]) < 0 else "Entrata"
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
    selected_row = next(
        (
            row
            for row in override_state["rows"]
            if row["selection_key"] == override_state["selected_key"]
        ),
        None,
    )
    if account is None or rule_id is None or not original_event_date:
        ui.notify("Seleziona prima un movimento modificabile.", color="negative")
        return

    override_description = override_state["override_description"].strip()
    override_event_date = override_state["override_event_date"].strip()
    override_amount_text = override_state["override_amount"].strip()
    direction = override_state["direction"]
    resolution_mode = override_state["resolution_mode"]
    status = override_state["status"]

    try:
        parsed_override_date = (
            parse_ui_date(override_event_date).isoformat()
            if override_event_date
            else None
        )
        parsed_override_amount = (
            float(
                override_amount_text.replace("€", "").replace(" ", "").replace(",", ".")
            )
            if override_amount_text
            else None
        )
        if override_amount_text.startswith("-"):
            raise ValueError
    except ValueError:
        ui.notify("Controlla data e importo override.", color="negative")
        return

    if parsed_override_amount is not None:
        parsed_override_amount = abs(parsed_override_amount)
        if direction == "Uscita":
            parsed_override_amount = -parsed_override_amount

    if status == "open" and parsed_override_date is None:
        ui.notify("Per un override aperto serve una data prevista.", color="negative")
        return

    latest_snapshot = get_latest_account_snapshot(account["id"])
    if (
        latest_snapshot
        and parsed_override_date is not None
        and date.fromisoformat(parsed_override_date)
        < date.fromisoformat(latest_snapshot["snapshot_date"])
        and resolution_mode == "auto"
    ):
        resolution_mode = "manual"
        override_state["resolution_mode"] = "manual"
        ui.notify(
            "La nuova data e precedente alla riconciliazione: l'override passa in modalita Manuale.",
            color="warning",
        )

    if selected_row is not None:
        original_description = selected_row["original_description"] or ""
        original_date = selected_row["original_event_date"]
        original_amount = round(float(selected_row["original_amount"]), 2)

        if override_description == original_description:
            override_description = ""
        if parsed_override_date == original_date:
            parsed_override_date = None
        if (
            parsed_override_amount is not None
            and round(float(parsed_override_amount), 2) == original_amount
        ):
            parsed_override_amount = None

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
    log_action("db", "Override salvato", f"rule_id={rule_id} event={original_event_date}")
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
    log_action("db", "Override ripristinato", f"rule_id={rule_id} event={original_event_date}")
    ui.notify("Override rimosso.", color="positive")
    try_run_default_forecast()
    render_forecast.refresh()
    render_override_editor.refresh()


init_db()

rule_state: dict[str, object] = {
    "account_filter": "Fineco",
    "show_expired": False,
    "selected_rule_id": None,
    "creating_new": False,
    "account_name": "Fineco",
    "description": "",
    "amount": "",
    "frequency": "monthly",
    "day_of_month": "",
    "month_of_year": "",
    "payment_method": "Conto",
    "provider": "",
    "start_date": format_ui_date(date.today()),
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
    "show_calculated_card_settlement": get_bool_setting(
        "show_calculated_card_settlement", True
    ),
    "credit_card_keyword": get_setting("credit_card_keyword", "Carta di credito")
    or "Carta di credito",
    "log_category": "all",
}
manual_event_state = {
    "selected_event_id": None,
    "selected_key": "",
    "expanded": False,
    "event_date": format_ui_date(date.today()),
    "description": "",
    "amount": "",
    "direction": "Uscita",
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
    "direction": "Uscita",
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
    '<link rel="icon" type="image/svg+xml" href="/assets/finance_app_icon_v2.svg">'
    '<meta name="theme-color" content="#12372a">'
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
    .forecast-table .row-edit-icon {
        display: none;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        color: #607d8b;
        font-size: 16px;
    }
    .forecast-table .forecast-selected-row .row-edit-icon {
        display: inline-flex;
    }
    .forecast-table .forecast-selected-row .row-state-icon {
        display: none;
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
                frequency_icon = get_rule_frequency_icon(rule)

                card = ui.card().classes("w-full cursor-pointer transition-all")
                card.style(get_rule_card_style(rule, is_selected))
                card.on("click", lambda _, rule_id=rule["id"]: select_rule(int(rule_id)))
                with card:
                    with ui.row().classes("w-full items-center justify-between gap-3 no-wrap"):
                        with ui.row().classes("items-center gap-3 min-w-[220px] no-wrap"):
                            with ui.row().classes("items-center gap-1"):
                                ui.icon(payment_icon).style(
                                    "font-size: 22px; color: #607d8b"
                                )
                                ui.icon(frequency_icon).style(
                                    "font-size: 22px; color: #607d8b"
                                )
                                ui.icon(
                                    get_rule_expiry_icon(rule)
                                ).style("font-size: 22px; color: #607d8b")
                            with ui.column().classes("gap-0"):
                                ui.label(rule["description"]).style(
                                    f"font-size: 15px; line-height: 1.1; font-weight: 600; color: {'#2f241f' if is_selected else '#4f4540'}"
                                )
                                ui.label(
                                    f"€{abs(float(rule['amount'])):.2f}"
                                ).style("color: #2f241f; font-size: 13px; line-height: 1.1; font-weight: 600")
                        with ui.column().classes("gap-0 items-end"):
                            ui.label(
                                format_cadence(rule)
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
        creating_new = bool(rule_state["creating_new"])

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between gap-3").style("margin-top: -10px;"):
                title_text = (
                    "Modifica regola"
                    if selected_rule_id is not None
                    else "Nuova regola"
                )
                ui.label(
                    title_text
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
            if selected_rule_id is None and not creating_new:
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
                        on_change=lambda event: (
                            rule_state.__setitem__("frequency", event.value),
                            sync_rule_schedule_fields(
                                "installments_total"
                                if str(rule_state["installments_total"] or "").strip()
                                else "end_date"
                            ),
                            refresh_rule_editor(),
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
                        options=[""] + get_provider_options(),
                        value=supplier or None,
                        on_change=lambda event: rule_state.__setitem__(
                            "provider", event.value or ""
                        ),
                    ),
                    "Campo facoltativo per banca, finanziaria o altro fornitore collegato alla regola; puoi anche scrivere un nuovo valore.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Data inizio",
                        value=format_html_date(start_date),
                        on_change=lambda event: (
                            rule_state.__setitem__(
                                "start_date",
                                format_ui_date(event.value) if event.value else "",
                            ),
                            sync_rule_schedule_fields("start_date"),
                            refresh_rule_editor(),
                        ),
                    ).props('type="date"'),
                    "Data da cui la regola inizia a produrre movimenti.",
                ).classes("w-full")

                add_tooltip(
                    ui.input(
                        label="Data fine",
                        value=format_html_date(end_date),
                        on_change=lambda event: (
                            rule_state.__setitem__(
                                "end_date",
                                format_ui_date(event.value) if event.value else "",
                            ),
                            sync_rule_schedule_fields("end_date"),
                            refresh_rule_editor(),
                        ),
                    ).props('type="date"'),
                    "Data oltre la quale la regola e considerata scaduta; svuota il campo per riattivarla nel tempo.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Numero rate",
                        value=installments_total,
                        on_change=lambda event: (
                            rule_state.__setitem__("installments_total", event.value),
                            sync_rule_schedule_fields("installments_total"),
                            refresh_rule_editor(),
                        ),
                    ),
                    "Numero totale rate, se la regola rappresenta un pagamento rateale.",
                ).classes("w-full")
                with ui.row().classes("w-full justify-end gap-2 pt-0"):
                    if selected_rule_id is not None:
                        add_tooltip(
                            ui.button(icon="delete", on_click=delete_selected_rule).props(
                                "round flat"
                            ),
                            "Elimina completamente la regola selezionata.",
                        )
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
                    "south_west" if event.amount < 0 else "north_east"
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
                        "row_bg": movement_status_background(balance_status),
                        "selected_bg": month_selected_background(event.event_date.month),
                        "selected_border": "#2f241f",
                        "month_accent": month_accent_color(event.event_date.month),
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
                        "is_calculated_card": event.description.strip().lower()
                        == "carta di credito calcolata",
                        "month_label": format_month_label(event.event_date),
                    }
                )
                previous_month_key = month_key

            for row in forecast_rows:
                row["is_selected"] = row["selection_key"] == selected_forecast_key

            selected_forecast_row = next(
                (row for row in forecast_rows if row["is_selected"]),
                None,
            )

            table = ui.table(
                columns=[
                    {
                        "name": "status",
                        "label": "",
                        "field": "status",
                        "align": "center",
                    },
                    {"name": "date", "label": "Data", "field": "date", "align": "left"},
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
                pagination=30,
            ).classes("w-full rounded-xl overflow-hidden forecast-table")
            table.props('dense table-style="max-height: 990px"')
            table.style("font-family: 'IBM Plex Mono', monospace; font-size: 11px")
            override_state["rows"] = forecast_rows
            available_rows = [row for row in forecast_rows if row["editable"]]
            if override_state["selected_key"] and not any(
                row["selection_key"] == override_state["selected_key"]
                for row in available_rows
            ):
                override_state["selected_key"] = ""
            table.add_slot(
                "top-row",
                r"""
                <q-tr v-if="props.rows.length" class="bg-[#f6f1e8]">
                    <q-td colspan="6" class="text-left text-[11px] font-semibold tracking-[0.08em] text-[#2f241f]" :style="'padding-top: 4px; padding-bottom: 4px; background-color:' + props.rows[0].month_accent">
                        {{ props.rows[0].month_label }}
                    </q-td>
                </q-tr>
                """,
            )
            table.add_slot(
                "body",
                r"""
                <q-tr v-if="props.row.month_break">
                    <q-td colspan="6" class="text-left text-[11px] font-semibold tracking-[0.08em] text-[#2f241f]" :style="'padding-top: 4px; padding-bottom: 4px; background-color:' + props.row.month_accent">
                        {{ props.row.month_label }}
                    </q-td>
                </q-tr>
                <q-tr :props="props" @click="() => $parent.$emit('select_override_row', props.row.selection_key)" :class="props.row.is_selected ? 'cursor-pointer forecast-selected-row' : 'cursor-pointer'" :data-selection-key="props.row.selection_key" :style="'background-color:' + props.row.row_bg">
                    <q-td key="status" :props="props" class="text-center" :style="'padding-top: 0px; padding-bottom: 0px; line-height: 1; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg) + '; border-left: 8px solid ' + props.row.month_accent">
                        <div class="row items-center justify-center no-wrap q-gutter-xs">
                            <q-icon name="edit" color="blue-grey-6" size="sm" class="row-edit-icon" />
                            <q-icon v-if="props.row.is_calculated_card" name="calculate" color="blue-grey-4" size="sm" class="row-state-icon" />
                            <q-icon v-if="props.row.is_manual_event" name="add_task" color="teal" size="xs">
                                <q-tooltip>Movimento manuale una tantum</q-tooltip>
                            </q-icon>
                            <template v-else-if="props.row.has_override">
                                <q-icon v-if="props.row.override_resolution_mode === 'manual' && props.row.override_status === 'open'" name="push_pin" color="warning" size="xs">
                                    <q-tooltip>Override manuale aperto. Originale: {{ props.row.original_event_date_label }} | {{ props.row.original_description }} | {{ props.row.original_amount.toFixed(2) }}</q-tooltip>
                                </q-icon>
                                <q-icon v-if="props.row.date_changed" name="event_repeat" color="secondary" size="xs">
                                    <q-tooltip>Data modificata. Originale: {{ props.row.original_event_date_label }}</q-tooltip>
                                </q-icon>
                                <q-icon v-if="props.row.amount_changed" name="euro" color="secondary" size="xs">
                                    <q-tooltip>Importo modificato. Originale: {{ props.row.original_amount.toFixed(2) }}</q-tooltip>
                                </q-icon>
                                <q-icon v-if="props.row.description_changed" name="edit_note" color="secondary" size="xs">
                                    <q-tooltip>Descrizione modificata. Originale: {{ props.row.original_description }}</q-tooltip>
                                </q-icon>
                            </template>
                        </div>
                    </q-td>
                    <q-td key="date" :props="props" :style="'padding-top: 0px; padding-bottom: 0px; line-height: 1; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">{{ props.row.date }}</q-td>
                    <q-td key="type" :props="props" class="text-center" :style="'padding-top: 0px; padding-bottom: 0px; line-height: 1; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">
                        <q-icon :name="props.row.type" :color="props.row.amount_value < 0 ? 'negative' : 'positive'" size="sm" />
                    </q-td>
                    <q-td key="description" :props="props" :style="'padding-top: 0px; padding-bottom: 0px; line-height: 1; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)">
                        <div class="row items-center no-wrap">
                            <q-icon v-if="props.row.carried_overdue" name="history" color="warning" size="xs" class="q-mr-xs" />
                            <span>{{ props.row.description_label }}</span>
                        </div>
                    </q-td>
                    <q-td key="amount" :props="props" :style="'padding-top: 0px; padding-bottom: 0px; line-height: 1; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)" :class="props.row.amount_value < 0 ? 'text-[#8a1c1c]' : 'text-[#1f7a1f]'">{{ props.row.amount }}</q-td>
                    <q-td key="balance" :props="props" :style="'padding-top: 0px; padding-bottom: 0px; line-height: 1; background-color:' + (props.row.is_selected ? props.row.selected_bg : props.row.row_bg)" :class="props.row.balance_value < 0 ? 'text-[#8a1c1c] font-semibold' : 'text-[#2f241f] font-semibold'">{{ props.row.balance }}</q-td>
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
                        value=format_html_date(manual_event_state["event_date"]),
                        on_change=lambda event: manual_event_state.__setitem__(
                            "event_date",
                            format_ui_date(event.value) if event.value else "",
                        ),
                    ).props('type="date"'),
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
                    ui.select(
                        options=["Uscita", "Entrata"],
                        value=manual_event_state["direction"],
                        on_change=lambda event: manual_event_state.__setitem__(
                            "direction", event.value
                        ),
                    ),
                    "Specifica se il movimento e un addebito oppure un accredito.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Importo",
                        value=manual_event_state["amount"],
                        prefix="€",
                        on_change=lambda event: manual_event_state.__setitem__(
                            "amount", normalize_positive_amount_input(event.value)
                        ),
                    ),
                    "Importo del movimento: inserisci solo il valore positivo, senza segno.",
                ).classes("w-full").style(currency_input_style(manual_event_state["direction"]))
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
                            ui.button(
                                icon="content_copy",
                                on_click=duplicate_manual_event_next_month,
                            ),
                            "Duplica questo movimento al mese successivo mantenendo gli stessi dati.",
                        ).props("round flat")
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
                        value=format_html_date(override_state["override_event_date"]),
                        on_change=lambda event: override_state.__setitem__(
                            "override_event_date",
                            format_ui_date(event.value) if event.value else "",
                        ),
                    ).props('type="date"'),
                    "Nuova data pianificata per questo solo movimento, nel formato DD-MM-YYYY.",
                ).classes("w-full")
                add_tooltip(
                    ui.select(
                        options=["Uscita", "Entrata"],
                        value=override_state["direction"],
                        label="Direzione",
                        on_change=lambda event: override_state.__setitem__(
                            "direction", event.value
                        ),
                    ),
                    "Specifica se il movimento personalizzato e un addebito oppure un accredito.",
                ).classes("w-full")
                add_tooltip(
                    ui.input(
                        label="Nuovo importo",
                        value=override_state["override_amount"],
                        prefix="€",
                        on_change=lambda event: override_state.__setitem__(
                            "override_amount", normalize_positive_amount_input(event.value)
                        ),
                    ),
                    "Nuovo importo per questa singola occorrenza della regola, senza segno.",
                ).classes("w-full").style(currency_input_style(override_state["direction"]))
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
                    add_tooltip(
                        ui.button(icon="close", on_click=lambda: select_override_event(None)).props(
                            "round flat"
                        ),
                        "Chiudi la personalizzazione senza salvare modifiche.",
                    )
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
        with ui.row().classes("w-full gap-4 items-stretch flex-wrap"):
            with ui.card().classes("w-full lg:w-[40%]"):
                    with ui.column().classes("gap-2"):
                        ui.label("Selezione conto").style("font-size: 18px; font-weight: 600")
                        render_account_selector_cards(
                            dashboard_state["account_name"], select_active_account, min_width=140
                        )

            with ui.card().classes("w-full lg:w-[58%]"):
                ui.label("Riconciliazione conto").style(
                    "margin-top: -6px; font-size: 18px; font-weight: 600"
                )
                with ui.row().classes("w-full items-end gap-4 flex-wrap"):
                    add_tooltip(
                        ui.input(
                            label="Data aggiornamento",
                            value=format_html_date(snapshot_state["snapshot_date"]),
                            on_change=lambda event: snapshot_state.__setitem__(
                                "snapshot_date",
                                format_ui_date(event.value) if event.value else "",
                            ),
                        ).props('type="date"'),
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
                    ).classes("min-w-[160px] flex-1")
                    add_tooltip(
                        ui.button(icon="save", on_click=save_snapshot),
                        "Salva o aggiorna lo snapshot del saldo reale per il conto attivo.",
                    ).props("round flat")

    @ui.refreshable
    def render_settings() -> None:
        accounts = get_accounts()

        with ui.row().classes("w-full gap-4 items-stretch flex-wrap"):
            with ui.card().classes("w-full lg:w-[calc(50%-0.5rem)]"):
                ui.label("Opzioni movimenti").style(
                    "margin-top: -6px; "
                    "font-size: 22px; font-weight: 600"
                )
                with ui.column().classes("gap-3"):
                    with ui.row().classes("items-end gap-3 flex-wrap"):
                        forecast_window_input = add_tooltip(
                            ui.input(
                                label="Finestra previsione (mesi)",
                                value=settings_state["forecast_window_months"],
                            ),
                            "Numero di mesi mostrati di default nella previsione del conto.",
                        ).classes("min-w-[220px] flex-1")
                        add_tooltip(
                            ui.button(
                                "Salva finestra",
                                on_click=lambda _: save_forecast_window_months(
                                    forecast_window_input.value
                                ),
                            ),
                            "Applica la nuova durata predefinita della previsione.",
                        )
                    with ui.row().classes("items-end gap-3 flex-wrap"):
                        warning_margin_input = add_tooltip(
                            ui.input(
                                label="Soglia attenzione (€)",
                                value=settings_state["warning_margin"],
                            ),
                            "Margine sopra il fido entro cui la previsione segnala una situazione di attenzione.",
                        ).classes("min-w-[220px] flex-1")
                        add_tooltip(
                            ui.button(
                                "Salva soglia",
                                on_click=lambda _: save_warning_margin(
                                    warning_margin_input.value
                                ),
                            ),
                            "Salva la soglia usata per evidenziare i periodi a rischio.",
                        )

            with ui.card().classes("w-full lg:w-[calc(50%-0.5rem)]"):
                ui.label("Fido conti").style("margin-top: -6px; font-size: 22px; font-weight: 600")

                with ui.column().classes("gap-3"):
                    for account in accounts:
                        with ui.row().classes("items-end gap-2 flex-wrap"):
                            ui.label(account["name"]).classes("min-w-[90px]")
                            overdraft_input = add_tooltip(
                                ui.input(
                                    label="Fido",
                                    value=str(account["overdraft_limit"] or 0),
                                ),
                                f"Imposta il fido disponibile per il conto {account['name']}.",
                            ).classes("min-w-[160px] flex-1")
                            add_tooltip(
                                ui.button(
                                    "Salva",
                                    on_click=lambda _, acc_name=account["name"], field=overdraft_input: (
                                        save_overdraft_limit(acc_name, field.value)
                                    ),
                                ),
                                f"Salva il nuovo fido del conto {account['name']}.",
                            )

            with ui.card().classes("w-full lg:w-[calc(50%-0.5rem)]"):
                ui.label("Impostazioni generali").style(
                    "margin-top: -6px; "
                    "font-size: 22px; font-weight: 600"
                )
                with ui.column().classes("gap-3").style("margin-top: -10px;"):
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
                    add_tooltip(
                        ui.switch(
                            text="Mostra Carta di credito calcolata",
                            value=settings_state["show_calculated_card_settlement"],
                            on_change=lambda event: save_show_calculated_card_settlement(
                                bool(event.value)
                            ),
                        ),
                        "Attiva o disattiva il calcolo e la visualizzazione della riga Carta di credito calcolata.",
                    )
                    with ui.row().classes("items-end gap-3 flex-wrap"):
                        credit_card_keyword_input = add_tooltip(
                            ui.input(
                                label="Parola chiave Carta di credito",
                                value=settings_state["credit_card_keyword"],
                            ),
                            "Testo usato per riconoscere il movimento pianificato della carta di credito nel forecast.",
                        ).classes("min-w-[240px] flex-1")
                        add_tooltip(
                            ui.button(
                                "Salva parola chiave",
                                on_click=lambda: save_credit_card_keyword(
                                    credit_card_keyword_input.value
                                ),
                            ),
                            "Salva la parola chiave usata per il movimento Carta di credito.",
                        )

            with ui.card().classes("w-full lg:w-[calc(50%-0.5rem)]"):
                ui.label("Importazioni").style(
                    "margin-top: -6px; "
                    "font-size: 22px; font-weight: 600"
                )
                with ui.column().classes("gap-3"):
                    add_tooltip(
                        ui.upload(
                            label="Importa file Excel",
                            auto_upload=True,
                            on_upload=import_workbook,
                        ).props('accept=".xlsx,.xlsm"'),
                        "Importa regole da un file Excel .xlsx o .xlsm e aggiorna il database.",
                    ).classes("min-w-[260px]")
                    for account in accounts:
                        add_tooltip(
                            ui.upload(
                                label=f"Logo {account['name']}",
                                auto_upload=True,
                                on_upload=lambda event, name=account["name"]: upload_account_logo(name, event),
                            ).props('accept=".png,.jpg,.jpeg,.webp,.svg"'),
                            f"Carica il logo da associare al conto {account['name']}.",
                        ).classes("min-w-[220px]")

            with ui.card().classes("w-full lg:w-[calc(50%-0.5rem)]"):
                ui.label("Eventi").style("margin-top: -6px; font-size: 22px; font-weight: 600")
                with ui.scroll_area().classes("w-full h-[220px] pr-2"):
                    for entry in get_app_logs(150, "all"):
                        details = f" | {entry['details']}" if entry["details"] else ""
                        ui.label(
                            f"{entry['created_at']} [{entry['category']}] {entry['message']}{details}"
                        ).style("font-family: 'IBM Plex Mono', monospace; font-size: 9px; line-height: 0.9")
                with ui.row().classes("w-full justify-end"):
                    add_tooltip(
                        ui.button("Pulisci log", on_click=run_clear_logs),
                        "Cancella lo storico dei log visibili in questo pannello.",
                    )

            with ui.card().classes("w-full lg:w-[calc(50%-0.5rem)]"):
                ui.label("Banca dati").style("margin-top: -6px; font-size: 22px; font-weight: 600")
                for file_info in get_database_file_info():
                    with ui.column().classes("gap-0"):
                        ui.label(file_info["name"]).style("font-weight: 600")
                        ui.label(f"Dimensione: {file_info['size']}").style("color: #6b5b53")
                        ui.label(file_info["path"]).style(
                            "font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #6b5b53"
                        )
                with ui.row().classes("w-full justify-start gap-2 mt-3 flex-wrap"):
                    add_tooltip(
                        ui.button("Pulisci movimenti", on_click=run_cleanup_manual_events),
                        "Rimuove dal database i movimenti manuali annullati.",
                    )
                    add_tooltip(
                        ui.button("Pulisci override", on_click=run_cleanup_overrides),
                        "Rimuove gli override chiusi o annullati dal database.",
                    )
                    add_tooltip(
                        ui.button("Pulisci regole", on_click=run_cleanup_rules),
                        "Rimuove le regole disattivate e gia scadute.",
                    )

            with ui.card().classes("w-full"):
                ui.label(f"Versione applicazione: {APP_VERSION}").style(
                    "margin-top: -6px; color: #6b5b53; font-size: 12px"
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
                with ui.column().classes("gap-2"):
                    ui.label("Selezione conto").style("font-size: 18px; font-weight: 600")
                    render_account_selector_cards(
                        str(rule_state["account_filter"]),
                        lambda value: (
                            rule_state.__setitem__("account_filter", value),
                            render_rule_stats.refresh(value),
                            render_rules.refresh(value),
                            refresh_rule_editor(),
                        ),
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

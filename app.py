from datetime import date

from nicegui import ui

from db import (
    get_account_by_name,
    get_account_snapshots,
    get_accounts,
    get_latest_account_snapshot,
    get_transaction_rules,
    init_db,
    is_rule_expired,
    set_transaction_rule_active,
    upsert_account_snapshot,
)
from forecast import build_account_forecast


def format_balance(balance: float | None) -> str:
    if balance is None:
        return "saldo non impostato"
    return f"{balance:.2f} EUR"


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


def refresh_all_rule_views() -> None:
    render_accounts.refresh()
    render_rule_stats.refresh(rule_state["account_filter"])
    render_rules.refresh(rule_state["account_filter"])


def refresh_snapshot_views() -> None:
    render_accounts.refresh()
    render_snapshots.refresh(snapshot_state["account_filter"])
    refresh_forecast_defaults()


def refresh_forecast_defaults() -> None:
    account_name = forecast_state["account_name"]
    if not account_name:
        return

    account = get_account_by_name(account_name)
    if account is None:
        return

    snapshot = get_latest_account_snapshot(account["id"])
    if snapshot:
        forecast_state["start_date"] = snapshot["snapshot_date"]
        forecast_state["opening_balance"] = f"{snapshot['balance']:.2f}"
    else:
        forecast_state["start_date"] = date.today().isoformat()
        forecast_state["opening_balance"] = ""


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
        balance = float(balance_text.replace(",", "."))
    except ValueError:
        ui.notify("Saldo non valido.", color="negative")
        return

    upsert_account_snapshot(account["id"], snapshot_date, balance, note)
    ui.notify("Snapshot salvato.", color="positive")
    refresh_snapshot_views()
    render_forecast.refresh()


def run_forecast() -> None:
    account_name = forecast_state["account_name"]
    start_date_text = forecast_state["start_date"]
    end_date_text = forecast_state["end_date"]
    opening_balance_text = forecast_state["opening_balance"].strip()

    if not account_name or not start_date_text or not end_date_text:
        ui.notify("Compila conto, data iniziale e data finale.", color="negative")
        return

    try:
        start_date_value = date.fromisoformat(start_date_text)
        end_date_value = date.fromisoformat(end_date_text)
    except ValueError:
        ui.notify("Le date devono essere nel formato YYYY-MM-DD.", color="negative")
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
    except Exception as exc:
        forecast_state["result"] = None
        render_forecast.refresh()
        ui.notify(str(exc), color="negative")


init_db()

rule_state = {"account_filter": "Tutti"}
snapshot_state = {
    "account_name": "Fineco",
    "snapshot_date": date.today().isoformat(),
    "balance": "",
    "note": "",
    "account_filter": "Tutti",
}
forecast_state = {
    "account_name": "Fineco",
    "start_date": date.today().isoformat(),
    "end_date": date(date.today().year, 12, 31).isoformat(),
    "opening_balance": "",
    "result": None,
}

if get_account_by_name("Fineco") is None and get_accounts():
    default_name = get_accounts()[0]["name"]
    snapshot_state["account_name"] = default_name
    forecast_state["account_name"] = default_name

refresh_forecast_defaults()

ui.query("body").style("background: linear-gradient(180deg, #f3efe5 0%, #fbf8f2 100%);")

with ui.column().classes("w-full max-w-7xl mx-auto gap-4 p-6"):
    ui.label("Finance App").style("font-size: 30px; font-weight: 700; color: #2f241f")
    ui.label("Conti, regole, snapshot riconciliati e prima bozza del forecast.").style(
        "color: #6b5b53; font-size: 15px"
    )

    @ui.refreshable
    def render_accounts() -> None:
        accounts = get_accounts()

        with ui.row().classes("w-full gap-4"):
            for account in accounts:
                latest_snapshot = get_latest_account_snapshot(account["id"])
                with ui.card().classes("min-w-[240px] flex-1"):
                    ui.label(account["name"]).style("font-size: 20px; font-weight: 600")
                    ui.label(format_balance(account["balance"])).style("color: #5f5048")
                    if latest_snapshot:
                        ui.label(
                            f"Ultimo snapshot: {latest_snapshot['snapshot_date']} | {latest_snapshot['balance']:.2f} EUR"
                        ).style("color: #7a6a62; font-size: 13px")
                    else:
                        ui.label("Nessuno snapshot salvato").style("color: #7a6a62; font-size: 13px")

    @ui.refreshable
    def render_rule_stats(account_filter: str) -> None:
        rules = load_rules(account_filter)
        active_rules = [rule for rule in rules if rule["active"] and not is_rule_expired(rule["end_date"])]
        expired_rules = [rule for rule in rules if is_rule_expired(rule["end_date"])]
        disabled_rules = [rule for rule in rules if not rule["active"] and not is_rule_expired(rule["end_date"])]

        with ui.row().classes("w-full gap-4"):
            for title, value in (
                ("Regole visibili", len(rules)),
                ("Attive effettive", len(active_rules)),
                ("Disattivate manualmente", len(disabled_rules)),
                ("Scadute", len(expired_rules)),
            ):
                with ui.card().classes("min-w-[180px] flex-1"):
                    ui.label(title).style("color: #6b5b53; font-size: 14px")
                    ui.label(str(value)).style("font-size: 28px; font-weight: 700; color: #2f241f")

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
                    with ui.row().classes("w-full items-center justify-between gap-4 no-wrap"):
                        with ui.column().classes("gap-1"):
                            ui.label(rule["description"]).style("font-size: 18px; font-weight: 600")
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
                                on_change=lambda event, rule_id=rule["id"]: toggle_rule(rule_id, bool(event.value)),
                            )

    @ui.refreshable
    def render_snapshots(account_filter: str) -> None:
        account_id = None
        if account_filter != "Tutti":
            account = get_account_by_name(account_filter)
            account_id = account["id"] if account else None

        snapshots = [dict(row) for row in get_account_snapshots(account_id)]

        with ui.column().classes("w-full gap-3"):
            if not snapshots:
                with ui.card().classes("w-full"):
                    ui.label("Nessuno snapshot disponibile.")
                return

            for snapshot in snapshots:
                with ui.card().classes("w-full"):
                    ui.label(
                        f"{snapshot['account_name']} | {snapshot['snapshot_date']} | {snapshot['balance']:.2f} EUR"
                    ).style("font-size: 17px; font-weight: 600")
                    ui.label(snapshot["note"] or "Nessuna nota").style("color: #7a6a62; font-size: 13px")

    @ui.refreshable
    def render_forecast() -> None:
        result = forecast_state["result"]

        with ui.column().classes("w-full gap-3"):
            if result is None:
                with ui.card().classes("w-full"):
                    ui.label("Nessun forecast calcolato.")
                    ui.label(
                        "Se il saldo iniziale non e compilato, verra usato l'ultimo snapshot disponibile fino alla data iniziale."
                    ).style("color: #7a6a62")
                return

            with ui.row().classes("w-full gap-4"):
                for title, value in (
                    ("Saldo iniziale", f"{result.opening_balance:.2f} EUR"),
                    ("Saldo finale", f"{result.closing_balance:.2f} EUR"),
                    ("Eventi", str(len(result.events))),
                ):
                    with ui.card().classes("min-w-[180px] flex-1"):
                        ui.label(title).style("color: #6b5b53; font-size: 14px")
                        ui.label(value).style("font-size: 26px; font-weight: 700; color: #2f241f")

            running_balance = result.opening_balance
            for event in result.events:
                running_balance += event.amount
                label = "Addebito carta" if event.event_type == "card_settlement" else "Movimento"
                with ui.card().classes("w-full"):
                    ui.label(
                        f"{event.event_date.isoformat()} | {event.description} | {event.amount:.2f} EUR"
                    ).style("font-size: 17px; font-weight: 600")
                    ui.label(f"{label} | saldo progressivo {running_balance:.2f} EUR").style(
                        "color: #7a6a62; font-size: 13px"
                    )

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Regole").style("font-size: 22px; font-weight: 600")
                ui.label(
                    "Le regole scadute restano storiche ma non sono piu attive nella previsione."
                ).style("color: #6b5b53")

            account_options = ["Tutti"] + [account["name"] for account in get_accounts()]
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

    with ui.card().classes("w-full"):
        ui.label("Snapshot conti").style("font-size: 22px; font-weight: 600")
        ui.label(
            "Uno snapshot dice che in quella data il saldo reale del conto e stato controllato o riconciliato manualmente."
        ).style("color: #6b5b53")

        account_names = [account["name"] for account in get_accounts()]
        with ui.row().classes("w-full items-end gap-4"):
            ui.select(
                options=account_names,
                value=snapshot_state["account_name"],
                label="Conto",
                on_change=lambda event: snapshot_state.__setitem__("account_name", event.value),
            ).classes("min-w-[180px]")
            ui.input(
                label="Data snapshot",
                value=snapshot_state["snapshot_date"],
                on_change=lambda event: snapshot_state.__setitem__("snapshot_date", event.value),
            ).classes("min-w-[180px]")
            ui.input(
                label="Saldo reale",
                value=snapshot_state["balance"],
                on_change=lambda event: snapshot_state.__setitem__("balance", event.value),
            ).classes("min-w-[160px]")
            ui.input(
                label="Nota",
                value=snapshot_state["note"],
                on_change=lambda event: snapshot_state.__setitem__("note", event.value),
            ).classes("min-w-[260px]")
            ui.button("Salva snapshot", on_click=save_snapshot)

        with ui.row().classes("w-full items-center justify-end gap-4"):
            ui.select(
                options=["Tutti"] + account_names,
                value=snapshot_state["account_filter"],
                label="Mostra snapshot",
                on_change=lambda event: (
                    snapshot_state.__setitem__("account_filter", event.value),
                    render_snapshots.refresh(event.value),
                ),
            ).classes("min-w-[220px]")

    with ui.card().classes("w-full"):
        ui.label("Forecast").style("font-size: 22px; font-weight: 600")
        ui.label(
            "Il forecast usa le regole attive e, se disponibile, l'ultimo snapshot come saldo iniziale affidabile."
        ).style("color: #6b5b53")

        account_names = [account["name"] for account in get_accounts()]
        with ui.row().classes("w-full items-end gap-4"):
            ui.select(
                options=account_names,
                value=forecast_state["account_name"],
                label="Conto",
                on_change=lambda event: (
                    forecast_state.__setitem__("account_name", event.value),
                    refresh_forecast_defaults(),
                    render_forecast.refresh(),
                ),
            ).classes("min-w-[180px]")
            ui.input(
                label="Data iniziale",
                value=forecast_state["start_date"],
                on_change=lambda event: forecast_state.__setitem__("start_date", event.value),
            ).classes("min-w-[180px]")
            ui.input(
                label="Data finale",
                value=forecast_state["end_date"],
                on_change=lambda event: forecast_state.__setitem__("end_date", event.value),
            ).classes("min-w-[180px]")
            ui.input(
                label="Saldo iniziale opzionale",
                value=forecast_state["opening_balance"],
                on_change=lambda event: forecast_state.__setitem__("opening_balance", event.value),
            ).classes("min-w-[200px]")
            ui.button("Calcola forecast", on_click=run_forecast)

    render_accounts()
    render_rule_stats(rule_state["account_filter"])
    render_rules(rule_state["account_filter"])
    render_snapshots(snapshot_state["account_filter"])
    render_forecast()

ui.run()

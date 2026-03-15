from db import (
    get_accounts,
    get_transaction_rules,
    init_db,
    is_rule_expired,
    set_transaction_rule_active,
)
from nicegui import ui


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


def toggle_rule(rule_id: int, active: bool) -> None:
    set_transaction_rule_active(rule_id, active)
    render_accounts.refresh()
    render_rule_stats.refresh(account_filter_state["value"])
    render_rules.refresh(account_filter_state["value"])


init_db()
account_filter_state = {"value": "Tutti"}

ui.query("body").style("background: linear-gradient(180deg, #f3efe5 0%, #fbf8f2 100%);")

with ui.column().classes("w-full max-w-7xl mx-auto gap-4 p-6"):
    ui.label("Finance App").style("font-size: 30px; font-weight: 700; color: #2f241f")
    ui.label("Conti, regole importate e stato operativo delle scadenze.").style(
        "color: #6b5b53; font-size: 15px"
    )

    @ui.refreshable
    def render_accounts() -> None:
        accounts = get_accounts()

        with ui.row().classes("w-full gap-4"):
            for account in accounts:
                with ui.card().classes("min-w-[240px] flex-1"):
                    ui.label(account["name"]).style("font-size: 20px; font-weight: 600")
                    ui.label(format_balance(account["balance"])).style("color: #5f5048")

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

    def handle_filter_change(value: str) -> None:
        account_filter_state["value"] = value
        render_rule_stats.refresh(value)
        render_rules.refresh(value)

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
                value=account_filter_state["value"],
                label="Filtra per conto",
                on_change=lambda event: handle_filter_change(event.value),
            ).classes("min-w-[220px]")

    render_accounts()
    render_rule_stats(account_filter_state["value"])
    render_rules(account_filter_state["value"])

ui.run()

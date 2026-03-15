from nicegui import ui

from db import get_accounts, get_transaction_rules, init_db


init_db()

accounts = get_accounts()
rules = get_transaction_rules()

ui.label("Finance App").style("font-size: 24px; font-weight: 600")

with ui.row().classes("w-full items-start gap-4"):
    with ui.card().classes("min-w-[320px]"):
        ui.label("Conti correnti").style("font-size: 20px")

        if not accounts:
            ui.label("Nessun conto presente nel database.")
        else:
            for account in accounts:
                if account["balance"] is None:
                    ui.label(f"{account['name']}: saldo non impostato")
                else:
                    ui.label(f"{account['name']}: {account['balance']:.2f} EUR")

    with ui.card().classes("min-w-[520px]"):
        ui.label("Regole importate").style("font-size: 20px")

        if not rules:
            ui.label("Nessuna regola importata. Esegui import_excel.py con il file xlsx.")
        else:
            for rule in rules:
                cadence = f"giorno {rule['day_of_month']}"
                if rule["frequency"] == "yearly" and rule["month_of_year"]:
                    cadence = f"{rule['day_of_month']}/{rule['month_of_year']}"

                payment_method = rule["payment_method"] or "n/d"
                ui.label(
                    f"{rule['account_name']} | {rule['description']} | {rule['amount']:.2f} EUR | "
                    f"{rule['frequency']} | {cadence} | {payment_method}"
                )

ui.run()

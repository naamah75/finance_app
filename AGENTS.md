# AGENTS.md

## Project goal

Build a simple personal finance app that starts local-first, stays easy to run, and gradually evolves from a minimal prototype into a useful planning tool.

## Current state

- The app is a working prototype in `app.py`
- UI uses NiceGUI
- Data uses local SQLite in `finance.db`
- The data model now includes `accounts`, `transaction_rules`, and `account_snapshots`
- Excel import currently reads compact rules from `xlsx` via `import_excel.py`
- A first forecast engine draft lives in `forecast.py`

## Main principles

- Prefer small, safe, incremental changes
- Keep the project easy to run locally
- Avoid unnecessary architectural complexity
- Preserve readability over cleverness
- Favor simple SQLite-based solutions unless requirements clearly justify more

## Development conventions

- Use Python 3 and keep dependencies listed in `requirements.txt`
- If a new package is added, update `requirements.txt`
- Keep database access simple and explicit
- Prefer small functions over large abstractions
- Follow the existing style unless there is a clear improvement
- Avoid large refactors unless they unlock the next feature directly

## Files and data

- Treat `finance.db` as local runtime data unless the user explicitly wants it versioned
- Do not commit secrets or local environment files
- Keep `.gitignore` updated when new local/generated files appear
- Treat the personal planning workbook as local input data; do not commit the real `Piano economico.xlsx`

## How to run

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the app:

```bash
python app.py
```

Import the workbook:

```bash
python import_excel.py "Piano economico.xlsx"
```

Default local URL:

- `http://localhost:8080`

## Near-term roadmap

- improve the `accounts` area
- add transactions
- add recurring transactions/rules
- import data from Excel/XLSX
- compute future balance projections
- add charts and dashboard views

## Agreed planning model

- Keep the system reusable for future years by importing compact transaction rules, not pre-generated future occurrences
- Use the Excel workbook as an import source, with the main sheets currently being `OperazioniRicorrenti` and `OperazioniSingole`
- Ignore unrelated sheets such as `WindTre` and `Estinzione` unless future requirements explicitly need them
- Store bank accounts such as `Unicredit` and `Fineco` in `accounts`
- Store planned rules in a single table such as `transaction_rules`, with monthly and yearly frequencies instead of separate tables per sheet
- Store manual or reconciled balances as dated snapshots in a table such as `account_snapshots`
- Future balance projections should start from a manually entered or reconciled account balance and apply the imported rules dynamically
- A snapshot means: on that exact date, the real account balance has been manually checked or reconciled and should be trusted as the forecasting starting point

## Payment handling rules

- The Excel column `Pagamento` determines how a rule impacts the account forecast
- If `Pagamento` is `Conto`, the movement is applied directly to the referenced bank account on its natural due date
- If `Pagamento` is `Carta`, the movement is first accumulated as card spending for the referenced bank account
- Card spending is not charged immediately to the account balance; it is aggregated and charged on day `10` of the following month as the credit card debit
- This card-settlement behavior should be modeled in forecasting logic, while the imported rule should preserve the original payment method and target account

## Current implementation notes

- `db.py` owns schema creation and basic SQLite helpers
- `import_excel.py` is intended to be safe to rerun; for now it replaces imported `transaction_rules` from the latest workbook contents
- `app.py` already includes a rule management view with filter by account, manual enable/disable, and automatic expired-state detection from `end_date`
- Keep manual disable (`active`) separate from automatic expiry; do not overwrite manual intent when a rule becomes expired
- `forecast.py` is the first draft of the projection engine and expands compact rules into dated forecast events
- In the current forecast draft, `Conto` rules generate direct account events and `Carta` rules are aggregated into a single debit on day `10` of the following month
- When the workbook changes over time, re-run the import instead of editing imported rules manually in the database unless a future feature explicitly supports local overrides

## Agent instructions

- Read the repository before making structural changes
- Keep commits focused and atomic
- Prefer changes that preserve the working prototype
- If database schema changes, keep migration/init logic straightforward
- When adding features, explain the why briefly in commits and summaries
- If work begins from another PC, check Git status and pull latest changes first
- Prefer small modules such as `db.py` and `import_excel.py` when they keep `app.py` simple
- When importing from Excel, prefer `xlsx` support and keep the importer safe to rerun
- Preserve enough imported metadata to support later forecasting and reconciliation work
- Prefer forecast logic in dedicated modules such as `forecast.py` instead of embedding it directly in the UI layer

## Context from the initial setup

The first milestone was intentionally simple: prove that Python, NiceGUI, and SQLite work together in a local app. The current code was created as a first visible prototype before designing the fuller finance data model.

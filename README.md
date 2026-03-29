# Finance App

Simple local-first personal finance app built with Python, NiceGUI, and SQLite.

## Current status

The project is no longer just a prototype. It now includes:

- local NiceGUI web app in `app.py`
- local SQLite database in `finance.db`
- reusable compact planning rules in `transaction_rules`
- dated balance checkpoints in `account_snapshots`
- per-event overrides in `forecast_event_overrides`
- one-off planned movements in `manual_events`
- app settings in SQLite for forecast behavior
- Excel import from `.xlsx` and `.xlsm` via `import_excel.py` and from the UI
- first forecast engine in `forecast.py`

## Current UI

The app currently has three main tabs:

- `Movimenti`: one account at a time, with snapshot editing, one-off movement entry, event customization, and a movement-by-movement forecast table with month separators, month accent bars, status-based row colors, compact rows, and a fixed 30-row page
- `Regole`: filtered rules per account, manual create/edit/delete, enable/disable, expired-state handling, provider suggestions, native date pickers, and schedule auto-fill
- `Impostazioni`: a 2x2 grid with movement options, account overdrafts, general settings, Excel import, logs, and technical info

The `Movimenti` tab is currently the main operational view.

## Planning model

- Accounts such as `Fineco` and `Unicredit` are stored in `accounts`
- Excel rules are imported as compact rules, not pre-generated future rows
- `OperazioniRicorrenti` becomes monthly rules
- `OperazioniSingole` becomes yearly rules
- Real balances are stored as snapshots with a date
- Forecasts start from a manual or reconciled balance snapshot
- Single generated occurrences can be customized without changing the base rule
- One-off user-entered planned movements are stored separately from imported rules

## Payment behavior

- If `Pagamento` is `Conto`, the movement hits the account directly on its due date
- If `Pagamento` is `Carta`, spending is accumulated and charged to the account on day `10` of the following month
- Planned `Carta di credito` rules and calculated card settlements are shown as separate movements

## Overrides and one-off movements

- Overrides apply to one specific generated occurrence only
- An override is identified by `rule_id + account_id + original_event_date`
- An override can change description, date, or amount for that single event
- Override resolution modes:
  - `auto`: behaves like a normal planned change
  - `manual`: stays visible until marked resolved or cancelled
- One-off movements are not stored as overrides; they are stored separately in `manual_events`

## Main files

- `app.py`: NiceGUI interface
- `db.py`: SQLite schema and helpers
- `import_excel.py`: imports rules from `.xlsx` and `.xlsm`
- `forecast.py`: expands compact rules into forecast events
- `AGENTS.md`: project notes and guidance for future sessions

## Setup and run

### Windows PowerShell

Create a virtual environment if needed:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

This installs the UI dependency (`nicegui`) and the Excel import dependency (`openpyxl`).

Start the app:

```powershell
python app.py
```

Open `http://localhost:8080`.

## Import the workbook

Put the planning workbook in the project folder and run:

```powershell
python import_excel.py "Piano economico.xlsx"
```

You can also import the workbook from the `Impostazioni` tab.

Note:

- the real workbook is treated as local input data and should not be committed
- while Excel is still the source of truth, rerun the import whenever the workbook changes
- the UI importer accepts `.xlsx` and `.xlsm`
- if a row omits the day column, the importer can fall back to the start date

## Snapshot and forecast flow

Typical workflow:

1. Select the account in `Movimenti`
2. Enter or update the real checked balance with date
3. Save the snapshot
4. Review the projected movement table for the next months
5. Add one-off movements if needed
6. Customize single generated events when a rule needs an exception for one specific occurrence

The movement table highlights the selected row for editing, keeps manual movements separate, shows calculated credit-card settlements as dedicated rows, and uses compact fixed pagination. Manual one-off movements and event overrides now use native date pickers, explicit `Entrata/Uscita` selectors, and positive-only currency inputs.

The settings area also includes:

- log viewer for application and database actions
- cleanup actions for cancelled manual movements, closed overrides, and obsolete rules
- technical info such as app version and database file size

A snapshot means: on that exact date, the real account balance has been checked manually and should be trusted as the forecast starting point.

## Working from another PC

Recommended flow:

1. Open the repository folder
2. Run `git pull`
3. Activate `.venv` if it works, otherwise recreate it
4. Run `pip install -r requirements.txt`
5. Start OpenCode from the repository root
6. Work normally, then `git add`, `git commit`, and `git push`

OneDrive is useful for having the folder available across machines, but Git should handle project history and synchronization.

## Near-term next steps

- improve the one-account-at-a-time `Movimenti` workflow
- add clearer reconciliation flows around snapshots
- improve forecast presentation with charts and timeline views
- prepare the eventual switch from Excel-managed rules to app-managed rules

# AGENTS.md

## Project goal

Build a simple personal finance app that starts local-first, stays easy to run, and gradually evolves from a minimal prototype into a useful planning tool.

## Current state

- The app is a working prototype in `app.py`
- UI uses NiceGUI
- Data uses local SQLite in `finance.db`
- The current schema only contains an `accounts` table

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

## How to run

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the app:

```bash
python app.py
```

Default local URL:

- `http://localhost:8080`

## Near-term roadmap

- improve the `accounts` area
- add transactions
- add recurring transactions/rules
- import data from Excel/XLSM
- compute future balance projections
- add charts and dashboard views

## Agent instructions

- Read the repository before making structural changes
- Keep commits focused and atomic
- Prefer changes that preserve the working prototype
- If database schema changes, keep migration/init logic straightforward
- When adding features, explain the why briefly in commits and summaries
- If work begins from another PC, check Git status and pull latest changes first

## Context from the initial setup

The first milestone was intentionally simple: prove that Python, NiceGUI, and SQLite work together in a local app. The current code was created as a first visible prototype before designing the fuller finance data model.

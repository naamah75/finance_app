# Finance App

Simple local personal finance app built with Python, NiceGUI, and SQLite.

## Current status

The project currently includes a first working prototype:

- local web UI with NiceGUI
- local SQLite database in `finance.db`
- `accounts` table auto-created at startup
- account list rendered in the page

This is the "prototype zero": the goal is to confirm that the environment works end to end before adding business logic.

## Tech stack

- Python 3
- NiceGUI
- SQLite

## Project files

- `app.py`: starts the app, initializes the database, and shows accounts
- `requirements.txt`: Python dependencies
- `.gitignore`: ignores local and generated files

## How to run

1. Create and activate a virtual environment
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python app.py
```

4. Open the browser at `http://localhost:8080`

## Current behavior

At startup the app creates this table if it does not exist:

- `accounts(id, name, balance)`

Then it reads all accounts and shows them in the UI.

## Manual test data

You can add sample rows with Python:

```python
import sqlite3

conn = sqlite3.connect("finance.db")
cur = conn.cursor()

cur.execute("INSERT INTO accounts (name, balance) VALUES ('Fineco', 3500)")
cur.execute("INSERT INTO accounts (name, balance) VALUES ('Unicredit', 1200)")

conn.commit()
conn.close()
```

Refresh the page to see the accounts.

## Next steps

- expand the data model beyond `accounts`
- add transaction and recurring rule support
- import data from Excel/XLSM
- calculate projected balances over time
- add charts and a more complete dashboard

## Working from another PC

- open the same repository folder
- run `git pull` before starting work
- activate the local virtual environment or create a new one
- install dependencies if needed
- start OpenCode from the repository root so it can read project context

OneDrive can help keep the folder available across machines, but Git should remain the source of truth for code history and synchronization.

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
- `requirements.txt`: Python dependencies needed to run the app
- `.gitignore`: ignores local and generated files
- `AGENTS.md`: working instructions for OpenCode and future sessions

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

Start the app:

```powershell
python app.py
```

Open the browser at `http://localhost:8080`.

### If `.venv` is already in OneDrive

You may already see the `.venv` folder on another PC because OneDrive syncs the files, but it is not guaranteed to be reusable.

Why:

- virtual environments often contain absolute paths tied to the machine where they were created
- they can break if Python is installed in a different location
- they can break if the Python version differs between PCs

So the safe rule is:

- if the synced `.venv` works, fine
- if activation or imports fail, delete and recreate `.venv` locally with `python -m venv .venv`

Git remains the source of truth for code. The virtual environment is just a local convenience.

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

## Working from another PC

Recommended flow:

1. Open the repository folder
2. Run `git pull`
3. Activate `.venv` if it works, otherwise recreate it
4. Run `pip install -r requirements.txt`
5. Start OpenCode from the repository root
6. Work normally, then `git add`, `git commit`, and `git push`

OneDrive is useful for having the folder available across machines, but Git should handle project history and synchronization.

## Next steps

- expand the data model beyond `accounts`
- add transaction and recurring rule support
- import data from Excel/XLSM
- calculate projected balances over time
- add charts and a more complete dashboard

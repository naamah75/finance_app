from nicegui import ui
import sqlite3
from pathlib import Path

DB_PATH = Path("finance.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        balance REAL
    )
    """)

    conn.commit()
    conn.close()


def get_accounts():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name, balance FROM accounts")
    rows = cur.fetchall()

    conn.close()
    return rows


init_db()

ui.label("Finance App").style("font-size: 24px")

with ui.card():
    ui.label("Conti correnti")

    for name, balance in get_accounts():
        ui.label(f"{name}: {balance:.2f} €")

ui.run()
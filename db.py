import sqlite3
from pathlib import Path


DB_PATH = Path("finance.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            balance REAL
        )
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_name
        ON accounts(name)
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transaction_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            frequency TEXT NOT NULL,
            day_of_month INTEGER NOT NULL,
            month_of_year INTEGER,
            payment_method TEXT,
            provider TEXT,
            start_date TEXT,
            end_date TEXT,
            installments_total INTEGER,
            card_settlement_day INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            source_sheet TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS account_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            balance REAL NOT NULL,
            note TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_account_snapshots_unique
        ON account_snapshots(account_id, snapshot_date)
        """
    )

    conn.commit()
    conn.close()


def upsert_account(name: str, balance: float | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO accounts(name, balance) VALUES (?, ?)",
        (name, balance),
    )

    if balance is not None:
        cur.execute(
            "UPDATE accounts SET balance = ? WHERE name = ?",
            (balance, name),
        )

    cur.execute("SELECT id FROM accounts WHERE name = ?", (name,))
    account_id = cur.fetchone()["id"]

    conn.commit()
    conn.close()
    return account_id


def replace_transaction_rules(rules: list[dict]) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM transaction_rules")

    cur.executemany(
        """
        INSERT INTO transaction_rules (
            account_id,
            description,
            amount,
            frequency,
            day_of_month,
            month_of_year,
            payment_method,
            provider,
            start_date,
            end_date,
            installments_total,
            card_settlement_day,
            source_sheet
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                rule["account_id"],
                rule["description"],
                rule["amount"],
                rule["frequency"],
                rule["day_of_month"],
                rule["month_of_year"],
                rule["payment_method"],
                rule["provider"],
                rule["start_date"],
                rule["end_date"],
                rule["installments_total"],
                rule["card_settlement_day"],
                rule["source_sheet"],
            )
            for rule in rules
        ],
    )

    conn.commit()
    conn.close()


def get_accounts() -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, balance FROM accounts ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_transaction_rules() -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            transaction_rules.id,
            accounts.name AS account_name,
            transaction_rules.description,
            transaction_rules.amount,
            transaction_rules.frequency,
            transaction_rules.day_of_month,
            transaction_rules.month_of_year,
            transaction_rules.payment_method,
            transaction_rules.provider,
            transaction_rules.start_date,
            transaction_rules.end_date,
            transaction_rules.installments_total,
            transaction_rules.card_settlement_day,
            transaction_rules.source_sheet
        FROM transaction_rules
        JOIN accounts ON accounts.id = transaction_rules.account_id
        WHERE transaction_rules.active = 1
        ORDER BY accounts.name, transaction_rules.frequency, transaction_rules.day_of_month, transaction_rules.description
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows

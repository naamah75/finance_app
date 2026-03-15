import sqlite3
from datetime import date
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
            balance REAL,
            overdraft_limit REAL
        )
        """
    )

    cur.execute("PRAGMA table_info(accounts)")
    account_columns = {row[1] for row in cur.fetchall()}
    if "overdraft_limit" not in account_columns:
        cur.execute("ALTER TABLE accounts ADD COLUMN overdraft_limit REAL")

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_name
        ON accounts(name)
        """
    )

    cur.execute(
        """
        UPDATE accounts
        SET overdraft_limit = 1500
        WHERE name = 'Unicredit' AND overdraft_limit IS NULL
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
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
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


def upsert_account(name: str, balance: float | None = None, overdraft_limit: float | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO accounts(name, balance, overdraft_limit) VALUES (?, ?, ?)",
        (name, balance, overdraft_limit),
    )

    if balance is not None:
        cur.execute(
            "UPDATE accounts SET balance = ? WHERE name = ?",
            (balance, name),
        )

    if overdraft_limit is not None:
        cur.execute(
            "UPDATE accounts SET overdraft_limit = ? WHERE name = ?",
            (overdraft_limit, name),
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
    cur.execute("SELECT id, name, balance, overdraft_limit FROM accounts ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_account_by_name(name: str) -> sqlite3.Row | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, balance, overdraft_limit FROM accounts WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row


def set_account_overdraft_limit(account_id: int, overdraft_limit: float) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE accounts SET overdraft_limit = ? WHERE id = ?",
        (overdraft_limit, account_id),
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO app_settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def get_transaction_rules(active_only: bool = False) -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    filters = "WHERE transaction_rules.active = 1" if active_only else ""
    cur.execute(
        f"""
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
            transaction_rules.active,
            transaction_rules.source_sheet
        FROM transaction_rules
        JOIN accounts ON accounts.id = transaction_rules.account_id
        {filters}
        ORDER BY accounts.name, transaction_rules.frequency, transaction_rules.day_of_month, transaction_rules.description
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def set_transaction_rule_active(rule_id: int, active: bool) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE transaction_rules SET active = ? WHERE id = ?",
        (1 if active else 0, rule_id),
    )
    conn.commit()
    conn.close()


def upsert_account_snapshot(account_id: int, snapshot_date: str, balance: float, note: str | None = None) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO account_snapshots(account_id, snapshot_date, balance, note)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(account_id, snapshot_date)
        DO UPDATE SET balance = excluded.balance, note = excluded.note
        """,
        (account_id, snapshot_date, balance, note),
    )
    conn.commit()
    conn.close()


def get_latest_account_snapshot(account_id: int, on_or_before: str | None = None) -> sqlite3.Row | None:
    conn = get_connection()
    cur = conn.cursor()

    if on_or_before:
        cur.execute(
            """
            SELECT id, account_id, snapshot_date, balance, note
            FROM account_snapshots
            WHERE account_id = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (account_id, on_or_before),
        )
    else:
        cur.execute(
            """
            SELECT id, account_id, snapshot_date, balance, note
            FROM account_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (account_id,),
        )

    row = cur.fetchone()
    conn.close()
    return row


def get_account_snapshots(account_id: int | None = None) -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    if account_id is None:
        cur.execute(
            """
            SELECT
                account_snapshots.id,
                account_snapshots.account_id,
                accounts.name AS account_name,
                account_snapshots.snapshot_date,
                account_snapshots.balance,
                account_snapshots.note
            FROM account_snapshots
            JOIN accounts ON accounts.id = account_snapshots.account_id
            ORDER BY account_snapshots.snapshot_date DESC, accounts.name
            """
        )
    else:
        cur.execute(
            """
            SELECT
                account_snapshots.id,
                account_snapshots.account_id,
                accounts.name AS account_name,
                account_snapshots.snapshot_date,
                account_snapshots.balance,
                account_snapshots.note
            FROM account_snapshots
            JOIN accounts ON accounts.id = account_snapshots.account_id
            WHERE account_snapshots.account_id = ?
            ORDER BY account_snapshots.snapshot_date DESC
            """,
            (account_id,),
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def is_rule_expired(end_date: str | None, today: date | None = None) -> bool:
    if not end_date:
        return False

    reference_date = today or date.today()
    return date.fromisoformat(end_date) < reference_date

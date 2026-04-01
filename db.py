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
        CREATE TABLE IF NOT EXISTS forecast_event_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            original_event_date TEXT NOT NULL,
            override_description TEXT,
            override_event_date TEXT,
            override_amount REAL,
            resolution_mode TEXT NOT NULL DEFAULT 'auto',
            status TEXT NOT NULL DEFAULT 'open',
            FOREIGN KEY (rule_id) REFERENCES transaction_rules(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            event_date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            note TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT,
            level TEXT NOT NULL DEFAULT 'info'
        )
        """
    )

    cur.execute("PRAGMA table_info(forecast_event_overrides)")
    override_columns = {row[1] for row in cur.fetchall()}
    if "override_description" not in override_columns:
        cur.execute(
            "ALTER TABLE forecast_event_overrides ADD COLUMN override_description TEXT"
        )
    if "resolution_mode" not in override_columns:
        cur.execute(
            "ALTER TABLE forecast_event_overrides ADD COLUMN resolution_mode TEXT NOT NULL DEFAULT 'auto'"
        )

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_account_snapshots_unique
        ON account_snapshots(account_id, snapshot_date)
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_forecast_event_overrides_unique
        ON forecast_event_overrides(rule_id, account_id, original_event_date)
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_manual_events_account_date
        ON manual_events(account_id, event_date)
        """
    )

    conn.commit()
    conn.close()


def upsert_account(
    name: str, balance: float | None = None, overdraft_limit: float | None = None
) -> int:
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


def add_transaction_rule(
    account_id: int,
    description: str,
    amount: float,
    frequency: str,
    day_of_month: int,
    month_of_year: int | None,
    payment_method: str | None,
    provider: str | None,
    start_date: str | None,
    end_date: str | None,
    installments_total: int | None,
    active: bool,
    source_sheet: str | None = None,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
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
            source_sheet,
            active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
            10 if payment_method == "carta" else None,
            source_sheet,
            1 if active else 0,
        ),
    )
    new_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return new_id


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
    cur.execute(
        "SELECT id, name, balance, overdraft_limit FROM accounts WHERE name = ?",
        (name,),
    )
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


def get_bool_setting(key: str, default: bool = True) -> bool:
    raw_value = (get_setting(key, "1" if default else "0") or "").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


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


def add_app_log(
    category: str,
    message: str,
    details: str | None = None,
    level: str = "info",
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_logs(category, message, details, level) VALUES (?, ?, ?, ?)",
        (category, message, details, level),
    )
    conn.commit()
    conn.close()


def get_app_logs(limit: int = 200, category: str | None = None) -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    if category and category != "all":
        cur.execute(
            """
            SELECT id, created_at, category, message, details, level
            FROM app_logs
            WHERE category = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (category, limit),
        )
    else:
        cur.execute(
            """
            SELECT id, created_at, category, message, details, level
            FROM app_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def clear_app_logs() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM app_logs")
    conn.commit()
    conn.close()


def cleanup_cancelled_manual_events() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM manual_events WHERE status = 'cancelled'")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def cleanup_closed_overrides() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM forecast_event_overrides WHERE status IN ('resolved', 'cancelled')"
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def cleanup_obsolete_rules(today: str | None = None) -> int:
    current = today or date.today().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM transaction_rules WHERE active = 0 AND end_date IS NOT NULL AND end_date < ?",
        (current,),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_forecast_event_overrides(account_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            rule_id,
            account_id,
            original_event_date,
            override_description,
            override_event_date,
            override_amount,
            resolution_mode,
            status
        FROM forecast_event_overrides
        WHERE account_id = ?
        ORDER BY original_event_date, id
        """,
        (account_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_forecast_event_override(
    rule_id: int, account_id: int, original_event_date: str
) -> sqlite3.Row | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            rule_id,
            account_id,
            original_event_date,
            override_description,
            override_event_date,
            override_amount,
            resolution_mode,
            status
        FROM forecast_event_overrides
        WHERE rule_id = ? AND account_id = ? AND original_event_date = ?
        """,
        (rule_id, account_id, original_event_date),
    )
    row = cur.fetchone()
    conn.close()
    return row


def upsert_forecast_event_override(
    rule_id: int,
    account_id: int,
    original_event_date: str,
    override_description: str | None = None,
    override_event_date: str | None = None,
    override_amount: float | None = None,
    resolution_mode: str = "auto",
    status: str = "open",
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO forecast_event_overrides(
            rule_id,
            account_id,
            original_event_date,
            override_description,
            override_event_date,
            override_amount,
            resolution_mode,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rule_id, account_id, original_event_date)
        DO UPDATE SET
            override_description = excluded.override_description,
            override_event_date = excluded.override_event_date,
            override_amount = excluded.override_amount,
            resolution_mode = excluded.resolution_mode,
            status = excluded.status
        """,
        (
            rule_id,
            account_id,
            original_event_date,
            override_description,
            override_event_date,
            override_amount,
            resolution_mode,
            status,
        ),
    )
    conn.commit()
    conn.close()


def delete_forecast_event_override(
    rule_id: int, account_id: int, original_event_date: str
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM forecast_event_overrides WHERE rule_id = ? AND account_id = ? AND original_event_date = ?",
        (rule_id, account_id, original_event_date),
    )
    conn.commit()
    conn.close()


def get_manual_events(
    account_id: int, start_date: str | None = None, end_date: str | None = None
) -> list[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT id, account_id, event_date, description, amount, payment_method, status, note
        FROM manual_events
        WHERE account_id = ?
    """
    params: list[object] = [account_id]

    if start_date is not None:
        query += " AND event_date >= ?"
        params.append(start_date)
    if end_date is not None:
        query += " AND event_date <= ?"
        params.append(end_date)

    query += " ORDER BY event_date, id"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def add_manual_event(
    account_id: int,
    event_date: str,
    description: str,
    amount: float,
    payment_method: str | None = None,
    status: str = "open",
    note: str | None = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO manual_events(account_id, event_date, description, amount, payment_method, status, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, event_date, description, amount, payment_method, status, note),
    )
    conn.commit()
    conn.close()


def update_manual_event(
    event_id: int,
    event_date: str,
    description: str,
    amount: float,
    payment_method: str | None = None,
    note: str | None = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE manual_events
        SET event_date = ?, description = ?, amount = ?, payment_method = ?, note = ?
        WHERE id = ?
        """,
        (event_date, description, amount, payment_method, note, event_id),
    )
    conn.commit()
    conn.close()


def set_manual_event_status(event_id: int, status: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE manual_events SET status = ? WHERE id = ?", (status, event_id))
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
            transaction_rules.account_id,
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


def delete_transaction_rule(rule_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM forecast_event_overrides WHERE rule_id = ?", (rule_id,))
    cur.execute("DELETE FROM transaction_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()


def update_transaction_rule(
    rule_id: int,
    account_id: int,
    description: str,
    amount: float,
    frequency: str,
    day_of_month: int,
    month_of_year: int | None,
    payment_method: str | None,
    provider: str | None,
    start_date: str | None,
    end_date: str | None,
    installments_total: int | None,
    active: bool,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE transaction_rules
        SET
            account_id = ?,
            description = ?,
            amount = ?,
            frequency = ?,
            day_of_month = ?,
            month_of_year = ?,
            payment_method = ?,
            provider = ?,
            start_date = ?,
            end_date = ?,
            installments_total = ?,
            card_settlement_day = ?,
            active = ?
        WHERE id = ?
        """,
        (
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
            10 if payment_method == "carta" else None,
            1 if active else 0,
            rule_id,
        ),
    )
    conn.commit()
    conn.close()


def upsert_account_snapshot(
    account_id: int, snapshot_date: str, balance: float, note: str | None = None
) -> None:
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


def get_latest_account_snapshot(
    account_id: int, on_or_before: str | None = None
) -> sqlite3.Row | None:
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

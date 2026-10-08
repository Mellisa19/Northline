"""SQLite persistence for the Northline demo portfolio."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "northline.db"

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS borrowers (
    id                 INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    sector             TEXT NOT NULL,
    city               TEXT NOT NULL,
    state              TEXT NOT NULL,
    cac_number         TEXT NOT NULL,
    contact_name       TEXT NOT NULL,
    contact_phone      TEXT NOT NULL,
    contact_email      TEXT NOT NULL,
    relationship_manager TEXT NOT NULL,
    onboarded_date     TEXT NOT NULL,
    years_trading      INTEGER NOT NULL,
    employees          INTEGER NOT NULL,
    monthly_inflow_base INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id                  INTEGER PRIMARY KEY,
    ref                 TEXT NOT NULL UNIQUE,
    borrower_id         INTEGER NOT NULL REFERENCES borrowers(id),
    product_code        TEXT NOT NULL,
    product_name        TEXT NOT NULL,
    principal           INTEGER NOT NULL,
    monthly_rate        REAL NOT NULL,
    tenor_months        INTEGER NOT NULL,
    instalment          INTEGER NOT NULL,
    disbursed_date      TEXT NOT NULL,
    first_due_date      TEXT NOT NULL,
    maturity_date       TEXT NOT NULL,
    outstanding_principal INTEGER NOT NULL,
    arrears_amount      INTEGER NOT NULL,
    dpd                 INTEGER NOT NULL,
    band                INTEGER NOT NULL,
    status              TEXT NOT NULL,
    collateral          TEXT NOT NULL,
    officer             TEXT NOT NULL,
    cohort_month        TEXT NOT NULL,
    monitoring_tier     TEXT NOT NULL,
    monitoring_consent  TEXT NOT NULL,
    consent_granted_at  TEXT,
    consent_expires_at  TEXT,
    control_group       INTEGER NOT NULL DEFAULT 0,
    written_off_date    TEXT,
    recovery_to_date    INTEGER NOT NULL DEFAULT 0,
    instalments_paid    INTEGER NOT NULL DEFAULT 0,
    instalments_due     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS installments (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    seq         INTEGER NOT NULL,
    due_date    TEXT NOT NULL,
    amount_due  INTEGER NOT NULL,
    amount_paid INTEGER NOT NULL DEFAULT 0,
    paid_date   TEXT,
    status      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY,
    account_id     INTEGER NOT NULL REFERENCES accounts(id),
    installment_id INTEGER,
    paid_date      TEXT NOT NULL,
    amount         INTEGER NOT NULL,
    channel        TEXT NOT NULL,
    source         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cashflow_months (
    id                    INTEGER PRIMARY KEY,
    borrower_id           INTEGER NOT NULL REFERENCES borrowers(id),
    account_id            INTEGER NOT NULL REFERENCES accounts(id),
    month                 TEXT NOT NULL,
    inflow                INTEGER NOT NULL,
    outflow               INTEGER NOT NULL,
    closing_balance       INTEGER NOT NULL,
    pos_inflow            INTEGER NOT NULL,
    transfer_inflow       INTEGER NOT NULL,
    new_recurring_debits  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signal_events (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    code        TEXT NOT NULL,
    label       TEXT NOT NULL,
    severity    INTEGER NOT NULL,
    detected_at TEXT NOT NULL,
    headline    TEXT NOT NULL,
    evidence    TEXT NOT NULL,
    lead_days   INTEGER,
    actionable  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS actions (
    id            INTEGER NOT NULL,
    account_id    INTEGER NOT NULL REFERENCES accounts(id),
    occurred_at   TEXT NOT NULL,
    channel       TEXT NOT NULL,
    disposition   TEXT NOT NULL,
    officer       TEXT NOT NULL,
    playbook_code TEXT,
    notes         TEXT NOT NULL DEFAULT '',
    cost          INTEGER NOT NULL DEFAULT 0,
    effect        TEXT NOT NULL DEFAULT 'no_effect',
    promise_id    INTEGER,
    PRIMARY KEY (account_id, id)
);

CREATE TABLE IF NOT EXISTS promises (
    id             INTEGER NOT NULL,
    account_id     INTEGER NOT NULL REFERENCES accounts(id),
    made_at        TEXT NOT NULL,
    promised_date  TEXT NOT NULL,
    amount         INTEGER NOT NULL,
    status         TEXT NOT NULL,
    resolved_at    TEXT,
    action_id      INTEGER,
    PRIMARY KEY (account_id, id)
);

CREATE TABLE IF NOT EXISTS recovery_events (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    occurred_at TEXT NOT NULL,
    kind        TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS band_history (
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    month_end   TEXT NOT NULL,
    dpd         INTEGER NOT NULL,
    band        INTEGER NOT NULL,
    arrears     INTEGER NOT NULL,
    outstanding INTEGER NOT NULL,
    PRIMARY KEY (account_id, month_end)
);

-- ---------------------------------------------------------------------------
-- Access control. Kept in the same database as the book so a fresh checkout is
-- one file, and so organisation-scoped queries stay trivial.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS organisations (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    slug       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organisations(id),
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    tone          TEXT NOT NULL DEFAULT 'clay',
    title         TEXT,
    created_at    TEXT NOT NULL,
    last_seen_at  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- Single-use handshakes for the Google sign-in flow.
CREATE TABLE IF NOT EXISTS oauth_states (
    state       TEXT PRIMARY KEY,
    redirect_to TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_codes (
    code       TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_borrower ON accounts(borrower_id);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_dpd ON accounts(dpd);
CREATE INDEX IF NOT EXISTS idx_installments_account ON installments(account_id);
CREATE INDEX IF NOT EXISTS idx_payments_account ON payments(account_id);
CREATE INDEX IF NOT EXISTS idx_cashflow_borrower ON cashflow_months(borrower_id, month);
CREATE INDEX IF NOT EXISTS idx_signals_account ON signal_events(account_id);
CREATE INDEX IF NOT EXISTS idx_actions_account ON actions(account_id);
CREATE INDEX IF NOT EXISTS idx_promises_account ON promises(account_id);
CREATE INDEX IF NOT EXISTS idx_band_history_month ON band_history(month_end, band);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_user ON oauth_codes(user_id);
"""

# Columns added after the first release. ``CREATE TABLE IF NOT EXISTS`` will not
# touch a table that already exists, so new columns are applied explicitly and an
# existing database upgrades in place rather than needing a reseed.
ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "google_sub": "TEXT",
        "avatar_url": "TEXT",
        "email_verified": "INTEGER NOT NULL DEFAULT 0",
        "auth_provider": "TEXT NOT NULL DEFAULT 'password'",
    },
}


def _migrate(connection: sqlite3.Connection) -> None:
    for table, columns in ADDED_COLUMNS.items():
        existing = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if not existing:
            continue
        for name, declaration in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    # Partial unique index: most users have no Google identity, but no two may
    # share one.
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub "
        "ON users(google_sub) WHERE google_sub IS NOT NULL"
    )


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with row access by column name."""
    target = Path(path) if path is not None else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    _migrate(connection)
    connection.commit()


def reset(path: Path | str | None = None) -> sqlite3.Connection:
    """Drop the database file and return a fresh, empty connection."""
    target = Path(path) if path is not None else DB_PATH
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(target) + suffix)
        if candidate.exists():
            candidate.unlink()
    connection = connect(target)
    create_schema(connection)
    return connection


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(connection: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default

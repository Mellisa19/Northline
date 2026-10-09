"""Accounts, organisations, roles and sessions.

Passwords are hashed with PBKDF2-HMAC-SHA256 from the standard library so the
backend keeps its single dependency surface. Sessions are opaque bearer tokens
stored server-side, which means signing out actually revokes access rather than
just asking the browser to forget something.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone

from fastapi import Header, HTTPException

from . import env

PBKDF2_ROUNDS = 240_000
SESSION_DAYS = 14


def utcnow() -> datetime:
    """Timezone-aware UTC; naive datetimes are on their way out."""
    return datetime.now(timezone.utc)


def stamp() -> str:
    return utcnow().isoformat(timespec="seconds")

ROLES = [
    {
        "code": "admin",
        "label": "Administrator",
        "description": "Full access, including the team and workspace settings.",
    },
    {
        "code": "risk",
        "label": "Risk Manager",
        "description": "Portfolio oversight, signals and the model card.",
    },
    {
        "code": "analyst",
        "label": "Credit Analyst",
        "description": "Assessment, borrower records and portfolio reporting.",
    },
    {
        "code": "collections",
        "label": "Collections Officer",
        "description": "Works the queue, records contact and captures promises.",
    },
    {
        "code": "field",
        "label": "Field Recovery",
        "description": "Visits and secures repayment on aged accounts.",
    },
]

ROLE_BY_CODE = {role["code"]: role for role in ROLES}

# Avatar tints, drawn from the warm end of the palette.
TONES = ["clay", "ochre", "sage", "plum", "marine", "rust"]


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
    )
    return digest.hex()


def new_salt() -> str:
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected)


def password_problem(password: str) -> str | None:
    if len(password) < 8:
        return "Use at least 8 characters."
    if password.lower() in {"password", "12345678", "northline", "qwertyui"}:
        return "That password is too easy to guess."
    return None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def create_session(connection: sqlite3.Connection, user_id: int) -> dict:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(days=SESSION_DAYS)
    connection.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")),
    )
    connection.execute(
        "UPDATE users SET last_seen_at = ? WHERE id = ?",
        (now.isoformat(timespec="seconds"), user_id),
    )
    connection.commit()
    return {"token": token, "expires_at": expires.isoformat(timespec="seconds")}


def revoke_session(connection: sqlite3.Connection, token: str) -> None:
    connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
    connection.commit()


def user_for_token(connection: sqlite3.Connection, token: str) -> dict | None:
    row = connection.execute(
        "SELECT u.*, o.name AS org_name, o.slug AS org_slug, s.expires_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "JOIN organisations o ON o.id = u.org_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    if row is None:
        return None
    if date.fromisoformat(row["expires_at"][:10]) < date.today():
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        connection.commit()
        return None
    return public_user(row)


def public_user(row) -> dict:
    return {
        "id": row["id"],
        "org_id": row["org_id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "role_label": ROLE_BY_CODE.get(row["role"], {}).get("label", row["role"]),
        "title": row["title"],
        "tone": row["tone"],
        "org_name": row["org_name"],
        "org_slug": row["org_slug"],
        "last_seen_at": row["last_seen_at"],
        # Present on rows read after the Google migration; guarded so an older
        # row shape cannot break the endpoint.
        "avatar_url": row["avatar_url"] if "avatar_url" in row.keys() else None,
        "auth_provider": (
            row["auth_provider"] if "auth_provider" in row.keys() else "password"
        ),
        "google_linked": bool(row["google_sub"]) if "google_sub" in row.keys() else False,
    }


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def require_user(authorization: str | None = Header(default=None)) -> dict:
    """Dependency for any route that needs a signed-in person."""
    # Imported here to avoid a circular import with the app package.
    from .db import connect, create_schema

    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")

    connection = connect()
    try:
        create_schema(connection)
        user = user_for_token(connection, token)
    finally:
        connection.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    return user


def require_admin(user: dict) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrators only.")
    return user


# ---------------------------------------------------------------------------
# Demo access
# ---------------------------------------------------------------------------
# Northline ships with a synthetic book. Letting a visitor walk straight in is the
# whole point of a demonstration, so demo access is on unless it is explicitly
# turned off — but it is a named, documented switch rather than an accident, and
# it is refused the moment DEMO_MODE is anything falsy.
DEMO_PASSWORD = "northline2026"

DEMO_NOTICE = (
    "These are shared credentials for a demonstration organisation. The portfolio "
    "behind them is generated, not real borrower data."
)

DEMO_TEAM = [
    ("admin@northline.ng", "Ade Balogun", "admin", "Head of Credit", "clay"),
    ("risk@northline.ng", "Ngozi Eze", "risk", "Risk Manager", "sage"),
    ("analyst@northline.ng", "Tunde Salami", "analyst", "Credit Analyst", "ochre"),
    ("collections@northline.ng", "Bola Adeyemi", "collections", "Collections Officer", "plum"),
    ("field@northline.ng", "Musa Ibrahim", "field", "Field Recovery", "marine"),
]


def demo_mode_enabled() -> bool:
    raw = env.get("DEMO_MODE", "true") or "true"
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def seed_demo_team(connection: sqlite3.Connection) -> dict:
    """Create the demo organisation and its team, if they are not there yet."""
    if not demo_mode_enabled():
        return {"created": 0, "existing": 0, "disabled": True}

    existing = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if existing:
        return {"created": 0, "existing": existing}

    now = stamp()
    cursor = connection.execute(
        "INSERT INTO organisations (name, slug, created_at) VALUES (?,?,?)",
        ("Northline Demo Lending", "northline-demo", now),
    )
    org_id = cursor.lastrowid

    for email, name, role, title, tone in DEMO_TEAM:
        salt = new_salt()
        connection.execute(
            "INSERT INTO users (org_id, email, name, role, password_hash, password_salt, tone, "
            "title, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (org_id, email, name, role, hash_password(DEMO_PASSWORD, salt), salt, tone, title, now),
        )
    connection.commit()
    return {"created": len(DEMO_TEAM), "existing": 0, "org_id": org_id, "password": DEMO_PASSWORD}

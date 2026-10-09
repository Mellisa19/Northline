"""Authentication and organisation endpoints."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import auth, google
from .db import connect, create_schema

log = logging.getLogger("northline.auth")

router = APIRouter(prefix="/api", tags=["access"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _connection() -> sqlite3.Connection:
    connection = connect()
    create_schema(connection)
    return connection


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "workspace"


class SignUpRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=200)
    title: str | None = Field(default=None, max_length=80)


class SignInRequest(BaseModel):
    email: str
    password: str


class InviteRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=160)
    role: str
    title: str | None = Field(default=None, max_length=80)


@router.get("/auth/roles")
def roles() -> dict:
    return {"roles": auth.ROLES}


@router.get("/auth/demo")
def demo_credentials() -> dict:
    """Shared credentials for the demonstration organisation.

    On by default, because walking straight into a synthetic portfolio is the point
    of a demonstration. Set ``DEMO_MODE=false`` and this returns 404 and no demo
    team is created — which is what a real deployment holding real borrower data
    would do.
    """
    if not auth.demo_mode_enabled():
        raise HTTPException(status_code=404, detail="Demo access is turned off on this server.")
    return {
        "organisation": "Northline Demo Lending",
        "password": auth.DEMO_PASSWORD,
        "notice": auth.DEMO_NOTICE,
        "accounts": [
            {"email": email, "name": name, "role": role, "role_label": auth.ROLE_BY_CODE[role]["label"]}
            for email, name, role, _title, _tone in auth.DEMO_TEAM
        ],
    }


@router.post("/auth/signup", status_code=201)
def sign_up(body: SignUpRequest) -> dict:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="That email address does not look right.")
    problem = auth.password_problem(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    connection = _connection()
    try:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with that email already exists.")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        slug = _slugify(body.org_name)
        suffix = 1
        while connection.execute(
            "SELECT 1 FROM organisations WHERE slug = ?", (slug,)
        ).fetchone():
            suffix += 1
            slug = f"{_slugify(body.org_name)}-{suffix}"

        cursor = connection.execute(
            "INSERT INTO organisations (name, slug, created_at) VALUES (?,?,?)",
            (body.org_name.strip(), slug, now),
        )
        org_id = cursor.lastrowid

        salt = auth.new_salt()
        cursor = connection.execute(
            "INSERT INTO users (org_id, email, name, role, password_hash, password_salt, tone, "
            "title, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                org_id,
                email,
                body.name.strip(),
                "admin",
                auth.hash_password(body.password, salt),
                salt,
                auth.TONES[0],
                body.title or "Administrator",
                now,
            ),
        )
        user_id = cursor.lastrowid
        connection.commit()

        session = auth.create_session(connection, user_id)
        user = connection.execute(
            "SELECT u.*, o.name AS org_name, o.slug AS org_slug FROM users u "
            "JOIN organisations o ON o.id = u.org_id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        return {"token": session["token"], "expires_at": session["expires_at"],
                "user": auth.public_user(user)}
    finally:
        connection.close()


@router.post("/auth/signin")
def sign_in(body: SignInRequest) -> dict:
    email = body.email.strip().lower()
    connection = _connection()
    try:
        row = connection.execute(
            "SELECT u.*, o.name AS org_name, o.slug AS org_slug FROM users u "
            "JOIN organisations o ON o.id = u.org_id WHERE u.email = ?",
            (email,),
        ).fetchone()

        # Same message either way: never reveal which emails exist.
        if row is None or not auth.verify_password(
            body.password, row["password_salt"], row["password_hash"]
        ):
            raise HTTPException(status_code=401, detail="That email and password do not match.")

        session = auth.create_session(connection, row["id"])
        return {"token": session["token"], "expires_at": session["expires_at"],
                "user": auth.public_user(row)}
    finally:
        connection.close()


@router.get("/auth/me")
def me(user: dict = Depends(auth.require_user)) -> dict:
    """Who am I. Authenticates through the dependency rather than route state, so
    it works whether or not the request passed through the gating middleware."""
    return {"user": user}


@router.post("/auth/signout")
def sign_out(request: Request) -> dict:
    token = auth.bearer_token(request.headers.get("authorization"))
    if token:
        connection = _connection()
        try:
            auth.revoke_session(connection, token)
        finally:
            connection.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Team management
# ---------------------------------------------------------------------------
@router.get("/auth/providers")
def providers() -> dict:
    """Which sign-in methods this server can actually offer.

    The interface uses this so it never shows a button that cannot work.
    """
    status = google.status()
    return {
        "google": status["enabled"],
        "password": True,
    }


# ---------------------------------------------------------------------------
# Google sign-in
# ---------------------------------------------------------------------------
@router.get("/auth/google/start")
def google_start(redirect: str | None = Query(default=None)) -> RedirectResponse:
    config = google.load_config()
    if not config.configured:
        log.warning("Google sign-in requested but not configured: %s", config.problems)
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on this server.",
        )

    connection = _connection()
    try:
        state = google.create_state(connection, google.safe_redirect(redirect))
    finally:
        connection.close()

    return RedirectResponse(google.authorization_url(config, state), status_code=302)


@router.get("/auth/google/callback")
def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    config = google.load_config()

    def back(message: str) -> RedirectResponse:
        return RedirectResponse(
            f"{config.app_base_url}/sign-in?error={quote(message)}", status_code=302
        )

    if error:
        # Google sends error=access_denied when somebody closes the consent screen.
        log.info("Google returned error=%s", error)
        return back("Sign-in with Google was cancelled.")

    if not code or not state:
        return back("That sign-in link was incomplete. Please try again.")

    if not config.configured:
        return back("Google sign-in is not configured on this server.")

    connection = _connection()
    try:
        destination = google.consume_state(connection, state)
        if destination is None:
            return back("That sign-in link has expired. Please try again.")

        try:
            tokens = google.exchange_code(config, code)
            profile = google.fetch_profile(tokens["access_token"])
            user = google.upsert_user(connection, profile)
        except google.GoogleAuthError as failure:
            return back(str(failure))

        exchange_code = google.issue_exchange_code(connection, user["id"])
    finally:
        connection.close()

    target = (
        f"{config.app_base_url}/auth/callback"
        f"?code={quote(exchange_code)}&next={quote(destination)}"
    )
    return RedirectResponse(target, status_code=302)


class GoogleSessionRequest(BaseModel):
    code: str = Field(min_length=10, max_length=200)


@router.post("/auth/google/session")
def google_session(body: GoogleSessionRequest) -> dict:
    """Trade the one-time code for a real session.

    The session token is returned in a response body rather than a URL, so it never
    lands in browser history, a referrer header or a server access log.
    """
    connection = _connection()
    try:
        user_id = google.redeem_exchange_code(connection, body.code)
        if user_id is None:
            raise HTTPException(
                status_code=401, detail="That sign-in link has expired. Please try again."
            )

        row = connection.execute(
            "SELECT u.*, o.name AS org_name, o.slug AS org_slug FROM users u "
            "JOIN organisations o ON o.id = u.org_id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="That account no longer exists.")

        session = auth.create_session(connection, user_id)
        return {
            "token": session["token"],
            "expires_at": session["expires_at"],
            "user": auth.public_user(row),
        }
    finally:
        connection.close()


@router.get("/org/sso-status")
def sso_status(user: dict = Depends(auth.require_user)) -> dict:
    """Setup detail for an administrator: what to register with Google, and what
    is still missing. Never exposes the client secret."""
    auth.require_admin(user)
    status = google.status()
    return {
        "enabled": status["enabled"],
        "problems": status["problems"],
        "redirect_uri_to_register": status["redirect_uri"],
        "app_base_url": status["app_base_url"],
    }


@router.get("/org/team")
def team(user: dict = Depends(auth.require_user)) -> dict:
    connection = _connection()
    try:
        rows = connection.execute(
            "SELECT id, name, email, role, title, tone, created_at, last_seen_at FROM users "
            "WHERE org_id = ? ORDER BY CASE role WHEN 'admin' THEN 0 WHEN 'risk' THEN 1 "
            "WHEN 'analyst' THEN 2 WHEN 'collections' THEN 3 ELSE 4 END, name",
            (user["org_id"],),
        ).fetchall()

        members = [
            {
                **{key: row[key] for key in row.keys()},
                "role_label": auth.ROLE_BY_CODE.get(row["role"], {}).get("label", row["role"]),
                "is_you": row["id"] == user["id"],
            }
            for row in rows
        ]

        workload = connection.execute(
            "SELECT officer, COUNT(*) AS attempts FROM actions GROUP BY officer"
        ).fetchall()
        return {
            "organisation": {"name": user["org_name"], "slug": user["org_slug"]},
            "members": members,
            "roles": auth.ROLES,
            "may_manage": user["role"] == "admin",
            "attempts_logged": sum(row["attempts"] for row in workload),
        }
    finally:
        connection.close()


@router.post("/org/team", status_code=201)
def invite(body: InviteRequest, user: dict = Depends(auth.require_user)) -> dict:
    auth.require_admin(user)
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="That email address does not look right.")
    if body.role not in auth.ROLE_BY_CODE:
        raise HTTPException(status_code=400, detail="Unknown role.")

    connection = _connection()
    try:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="That person is already on the team.")

        salt = auth.new_salt()
        tone = auth.TONES[
            connection.execute("SELECT COUNT(*) AS n FROM users WHERE org_id = ?",
                               (user["org_id"],)).fetchone()["n"] % len(auth.TONES)
        ]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        temporary = "northline2026"
        cursor = connection.execute(
            "INSERT INTO users (org_id, email, name, role, password_hash, password_salt, tone, "
            "title, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                user["org_id"],
                email,
                body.name.strip(),
                body.role,
                auth.hash_password(temporary, salt),
                salt,
                tone,
                body.title or auth.ROLE_BY_CODE[body.role]["label"],
                now,
            ),
        )
        connection.commit()
        return {
            "id": cursor.lastrowid,
            "temporary_password": temporary,
            "note": "Share this once and ask them to change it.",
        }
    finally:
        connection.close()


@router.delete("/org/team/{member_id}")
def remove_member(member_id: int, user: dict = Depends(auth.require_user)) -> dict:
    auth.require_admin(user)
    if member_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot remove your own access.")
    connection = _connection()
    try:
        target = connection.execute(
            "SELECT id FROM users WHERE id = ? AND org_id = ?", (member_id, user["org_id"])
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="That person is not on your team.")
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (member_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (member_id,))
        connection.commit()
        return {"removed": member_id}
    finally:
        connection.close()

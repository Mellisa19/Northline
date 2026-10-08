"""Google sign-in.

The authorisation-code flow, run entirely on the server:

1.  The browser is sent to Google with a single-use ``state`` we stored.
2.  Google returns the person to our callback with a code.
3.  We exchange that code for tokens server-to-server, using the client secret
    that never leaves the backend.
4.  We read the profile from Google's userinfo endpoint using the access token we
    just received *directly from Google over TLS*. That is why the identity can be
    trusted without separately verifying a JWT signature: the token was not
    supplied by the browser, it was fetched by us with the client secret.
5.  We hand the browser a single-use exchange code, not the session token, so the
    long-lived credential never appears in a URL, a referrer header or browser
    history.

Nothing here is simulated. If the credentials are absent the endpoints report
that clearly instead of pretending to sign anybody in.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from . import auth, env

log = logging.getLogger("northline.google")

# Taken from Google's OpenID Connect discovery document, which is authoritative
# and worth re-checking if these ever stop working:
#   https://accounts.google.com/.well-known/openid-configuration
#
# It also confirms the rest of what this module assumes:
#   scopes_supported      = openid, email, profile
#   response_types        = code
#   grant_types           = authorization_code
#   token auth methods    = client_secret_post   (the secret goes in the POST body)
#   claims                = sub, email, email_verified, name, picture
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

SCOPES = "openid email profile"
HTTP_TIMEOUT = 15.0

STATE_TTL = timedelta(minutes=10)
EXCHANGE_CODE_TTL = timedelta(minutes=2)


class GoogleAuthError(Exception):
    """A failure that is safe to show the person who tried to sign in."""


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    app_base_url: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @property
    def problems(self) -> list[str]:
        missing = []
        if not self.client_id:
            missing.append("GOOGLE_CLIENT_ID is not set")
        if not self.client_secret:
            missing.append("GOOGLE_CLIENT_SECRET is not set")
        if not self.redirect_uri:
            missing.append("GOOGLE_REDIRECT_URI is not set")
        return missing


def load_config() -> GoogleConfig:
    """Read configuration at call time, so a restart is all that is needed."""
    app_base_url = (env.get("APP_BASE_URL") or "http://localhost:5180").rstrip("/")
    redirect_uri = env.get("GOOGLE_REDIRECT_URI") or f"{app_base_url}/api/auth/google/callback"
    return GoogleConfig(
        client_id=(env.get("GOOGLE_CLIENT_ID") or "").strip(),
        client_secret=(env.get("GOOGLE_CLIENT_SECRET") or "").strip(),
        redirect_uri=redirect_uri.strip(),
        app_base_url=app_base_url,
    )


def authorization_url(config: GoogleConfig, state: str) -> str:
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        # Let people pick which Google account to use rather than silently
        # reusing whichever one the browser is already signed into.
        "prompt": "select_account",
        "access_type": "online",
        "include_granted_scopes": "true",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Talking to Google
# ---------------------------------------------------------------------------
def exchange_code(config: GoogleConfig, code: str) -> dict:
    payload = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config.redirect_uri,
    }
    try:
        response = httpx.post(TOKEN_ENDPOINT, data=payload, timeout=HTTP_TIMEOUT)
    except httpx.HTTPError as error:
        log.warning("token exchange could not reach Google: %s", error)
        raise GoogleAuthError("We could not reach Google just now. Please try again.") from error

    if response.status_code != 200:
        # The body often says why; keep it in the server log, never in the reply.
        log.warning(
            "token exchange rejected (%s): %s", response.status_code, response.text[:400]
        )
        raise GoogleAuthError("Google rejected that sign-in attempt. Please try again.")

    data = response.json()
    if not data.get("access_token"):
        log.warning("token exchange returned no access token: %s", list(data))
        raise GoogleAuthError("Google did not complete the sign-in. Please try again.")
    return data


def fetch_profile(access_token: str) -> dict:
    try:
        response = httpx.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT,
        )
    except httpx.HTTPError as error:
        log.warning("userinfo could not reach Google: %s", error)
        raise GoogleAuthError("We could not read your Google profile. Please try again.") from error

    if response.status_code != 200:
        log.warning("userinfo rejected (%s): %s", response.status_code, response.text[:400])
        raise GoogleAuthError("We could not read your Google profile. Please try again.")

    profile = response.json()
    if not profile.get("sub"):
        log.warning("userinfo returned no subject: %s", list(profile))
        raise GoogleAuthError("Google did not identify that account. Please try again.")
    return profile


# ---------------------------------------------------------------------------
# Single-use state and exchange codes
# ---------------------------------------------------------------------------
def _purge(connection: sqlite3.Connection) -> None:
    now = auth.utcnow().isoformat()
    connection.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now,))
    connection.execute("DELETE FROM oauth_codes WHERE expires_at < ?", (now,))


def create_state(connection: sqlite3.Connection, redirect_to: str) -> str:
    _purge(connection)
    state = secrets.token_urlsafe(32)
    now = auth.utcnow()
    connection.execute(
        "INSERT INTO oauth_states (state, redirect_to, created_at, expires_at) VALUES (?,?,?,?)",
        (state, redirect_to, now.isoformat(), (now + STATE_TTL).isoformat()),
    )
    connection.commit()
    return state


def consume_state(connection: sqlite3.Connection, state: str) -> str | None:
    """Return the stored destination, or None. Always deletes, so it cannot replay."""
    row = connection.execute(
        "SELECT redirect_to, expires_at FROM oauth_states WHERE state = ?", (state,)
    ).fetchone()
    if row is None:
        return None
    connection.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    connection.commit()

    try:
        if datetime.fromisoformat(row["expires_at"]) < auth.utcnow():
            return None
    except ValueError:
        return None
    return row["redirect_to"] or "/app"


def issue_exchange_code(connection: sqlite3.Connection, user_id: int) -> str:
    _purge(connection)
    code = secrets.token_urlsafe(32)
    now = auth.utcnow()
    connection.execute(
        "INSERT INTO oauth_codes (code, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (code, user_id, now.isoformat(), (now + EXCHANGE_CODE_TTL).isoformat()),
    )
    connection.commit()
    return code


def redeem_exchange_code(connection: sqlite3.Connection, code: str) -> int | None:
    """Single use: the row is deleted before it is trusted."""
    row = connection.execute(
        "SELECT user_id, expires_at FROM oauth_codes WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    connection.execute("DELETE FROM oauth_codes WHERE code = ?", (code,))
    connection.commit()

    try:
        if datetime.fromisoformat(row["expires_at"]) < auth.utcnow():
            return None
    except ValueError:
        return None
    return int(row["user_id"])


def safe_redirect(value: str | None, fallback: str = "/app") -> str:
    """Only ever send people to a path on this site.

    Without this, ``?redirect=//evil.example`` would turn our callback into an
    open redirect that launders a trusted domain.
    """
    if not value:
        return fallback
    candidate = value.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return fallback
    return candidate


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _fetch_user(connection: sqlite3.Connection, user_id: int):
    return connection.execute(
        "SELECT u.*, o.name AS org_name, o.slug AS org_slug FROM users u "
        "JOIN organisations o ON o.id = u.org_id WHERE u.id = ?",
        (user_id,),
    ).fetchone()


def _unique_slug(connection: sqlite3.Connection, name: str) -> str:
    base = "".join(character if character.isalnum() else "-" for character in name.lower())
    base = "-".join(part for part in base.split("-") if part)[:48] or "workspace"
    slug = base
    suffix = 1
    while connection.execute("SELECT 1 FROM organisations WHERE slug = ?", (slug,)).fetchone():
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def upsert_user(connection: sqlite3.Connection, profile: dict):
    """Find or create the person behind a Google profile.

    Matching order matters: the Google subject is the stable identifier, and the
    email is only used to attach a Google identity to an account that already
    exists — and only when Google says that address is verified.
    """
    subject = profile["sub"]
    email = (profile.get("email") or "").strip().lower()
    verified = bool(profile.get("email_verified"))
    provided_name = (profile.get("name") or "").strip()
    name = provided_name or (email.split("@")[0] if email else "Google user")
    avatar = profile.get("picture")
    now = auth.stamp()

    existing = connection.execute(
        "SELECT * FROM users WHERE google_sub = ?", (subject,)
    ).fetchone()
    if existing:
        # Keep the display name in step with Google, but never blank it out if the
        # profile simply did not carry one.
        connection.execute(
            "UPDATE users SET name = ?, avatar_url = ?, last_seen_at = ?, email_verified = ? "
            "WHERE id = ?",
            (
                provided_name or existing["name"],
                avatar,
                now,
                1 if verified else 0,
                existing["id"],
            ),
        )
        connection.commit()
        return _fetch_user(connection, existing["id"])

    if email:
        by_email = connection.execute(
            "SELECT * FROM users WHERE lower(email) = ?", (email,)
        ).fetchone()
        if by_email is not None:
            if not verified:
                raise GoogleAuthError(
                    "Google has not confirmed that email address, so we cannot link it "
                    "to an existing account."
                )
            if by_email["google_sub"] and by_email["google_sub"] != subject:
                raise GoogleAuthError(
                    "That email is already linked to a different Google account."
                )
            provider = "password+google" if by_email["auth_provider"] == "password" else "google"
            connection.execute(
                "UPDATE users SET google_sub = ?, avatar_url = ?, email_verified = 1, "
                "auth_provider = ?, last_seen_at = ? WHERE id = ?",
                (subject, avatar, provider, now, by_email["id"]),
            )
            connection.commit()
            log.info("linked Google identity to existing user %s", by_email["id"])
            return _fetch_user(connection, by_email["id"])

    # A brand new person: give them their own workspace, as the sign-up form does.
    display = name.split()[0] if name.split() else "New"
    org_name = f"{display}'s workspace"
    cursor = connection.execute(
        "INSERT INTO organisations (name, slug, created_at) VALUES (?,?,?)",
        (org_name, _unique_slug(connection, org_name), now),
    )
    org_id = cursor.lastrowid

    salt = auth.new_salt()
    # No password they could ever use; this account signs in with Google only.
    unusable = auth.hash_password(secrets.token_urlsafe(32), salt)
    cursor = connection.execute(
        "INSERT INTO users (org_id, email, name, role, password_hash, password_salt, tone, "
        "title, created_at, last_seen_at, google_sub, avatar_url, email_verified, auth_provider) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'google')",
        (
            org_id,
            email or f"{subject}@google.invalid",
            name,
            "admin",
            unusable,
            salt,
            auth.TONES[0],
            "Administrator",
            now,
            now,
            subject,
            avatar,
            1 if verified else 0,
        ),
    )
    connection.commit()
    log.info("created workspace %s for new Google user %s", org_id, cursor.lastrowid)
    return _fetch_user(connection, cursor.lastrowid)


def status() -> dict:
    config = load_config()
    return {
        "enabled": config.configured,
        "problems": config.problems,
        "redirect_uri": config.redirect_uri,
        "app_base_url": config.app_base_url,
    }

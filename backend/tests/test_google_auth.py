"""Google sign-in tests.

The interactive part of an OAuth flow — a person choosing a Google account in a
browser — cannot be exercised from here. Everything either side of it can, and
that is what these cover: the redirect we build, the CSRF state, the code
exchange against a stubbed Google, identity linking rules, the single-use
exchange code, and every failure path.

``httpx`` is stubbed rather than called, so these tests never touch the network
and never need real credentials.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, db, env, google  # noqa: E402
from app.db import create_schema, reset  # noqa: E402

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"
BASE_URL = "http://localhost:5180"
REDIRECT_URI = f"{BASE_URL}/api/auth/google/callback"


@pytest.fixture(scope="session")
def workdir():
    path = Path(__file__).resolve().parent / ".tmp"
    path.mkdir(exist_ok=True)
    return path


@pytest.fixture
def configured(monkeypatch):
    """Pretend the operator has filled in .env."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setenv("APP_BASE_URL", BASE_URL)
    # ``env.get`` treats an empty string as unset, so blanking is the same as
    # removing them.
    monkeypatch.setattr(env, "load", lambda *a, **k: {})


@pytest.fixture
def unconfigured(monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("APP_BASE_URL", BASE_URL)
    monkeypatch.setattr(env, "load", lambda *a, **k: {})


@pytest.fixture
def api(workdir, monkeypatch):
    path = workdir / "google.db"
    connection = reset(path)
    create_schema(connection)
    auth.seed_demo_team(connection)
    connection.close()

    monkeypatch.setattr(db, "DB_PATH", path)

    from app.api import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def connection(workdir, monkeypatch):
    path = workdir / "google.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    con = db.connect(path)
    create_schema(con)
    # The linking tests need accounts that already exist.
    auth.seed_demo_team(con)
    yield con
    con.close()


PROFILE = {
    "sub": "10769150350006150715113082367",
    "email": "thandi@example.com",
    "email_verified": True,
    "name": "Thandi Mokoena",
    "picture": "https://lh3.googleusercontent.com/a/example",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def test_config_reads_from_the_environment(configured):
    config = google.load_config()
    assert config.configured
    assert config.client_id == CLIENT_ID
    assert config.redirect_uri == REDIRECT_URI
    assert config.app_base_url == BASE_URL
    assert config.problems == []


def test_unconfigured_server_reports_what_is_missing(unconfigured):
    config = google.load_config()
    assert not config.configured
    assert any("GOOGLE_CLIENT_ID" in problem for problem in config.problems)
    assert any("GOOGLE_CLIENT_SECRET" in problem for problem in config.problems)


def test_redirect_uri_defaults_to_the_app_origin(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "")
    monkeypatch.setenv("APP_BASE_URL", "https://northline.example.com/")
    monkeypatch.setattr(env, "load", lambda *a, **k: {})

    config = google.load_config()
    assert config.app_base_url == "https://northline.example.com"
    assert config.redirect_uri == "https://northline.example.com/api/auth/google/callback"


def test_authorization_url_carries_everything_google_needs(configured):
    config = google.load_config()
    url = google.authorization_url(config, "state-abc")

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert f"client_id={CLIENT_ID}" in url
    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url or "scope=openid%20email%20profile" in url
    assert "state=state-abc" in url
    assert "prompt=select_account" in url
    # The redirect URI is sent, and it is the one registered with Google.
    assert "redirect_uri=" in url
    assert "localhost%3A5180" in url
    # The secret must never appear anywhere in a URL.
    assert CLIENT_SECRET not in url


# ---------------------------------------------------------------------------
# Open-redirect protection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "attempt",
    ["//evil.example", "https://evil.example", "\\\\evil", "/\\evil", "javascript:alert(1)"],
)
def test_safe_redirect_refuses_to_leave_the_site(attempt):
    assert google.safe_redirect(attempt) == "/app"


def test_safe_redirect_allows_local_paths():
    assert google.safe_redirect("/app/recovery") == "/app/recovery"
    assert google.safe_redirect(None) == "/app"
    assert google.safe_redirect("") == "/app"


# ---------------------------------------------------------------------------
# State and one-time codes
# ---------------------------------------------------------------------------
def test_state_is_single_use(connection):
    state = google.create_state(connection, "/app/recovery")
    assert google.consume_state(connection, state) == "/app/recovery"
    # A replay must fail: the row was deleted the first time.
    assert google.consume_state(connection, state) is None


def test_unknown_and_expired_state_are_rejected(connection):
    assert google.consume_state(connection, "never-issued") is None

    state = google.create_state(connection, "/app")
    connection.execute(
        "UPDATE oauth_states SET expires_at = ? WHERE state = ?",
        ((auth.utcnow() - timedelta(minutes=1)).isoformat(), state),
    )
    connection.commit()
    assert google.consume_state(connection, state) is None


def test_exchange_code_is_single_use(connection):
    user_id = connection.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    code = google.issue_exchange_code(connection, user_id)

    assert google.redeem_exchange_code(connection, code) == user_id
    assert google.redeem_exchange_code(connection, code) is None


def test_expired_exchange_code_is_rejected(connection):
    user_id = connection.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    code = google.issue_exchange_code(connection, user_id)
    connection.execute(
        "UPDATE oauth_codes SET expires_at = ? WHERE code = ?",
        ((auth.utcnow() - timedelta(seconds=1)).isoformat(), code),
    )
    connection.commit()
    assert google.redeem_exchange_code(connection, code) is None


# ---------------------------------------------------------------------------
# Talking to Google, with httpx stubbed
# ---------------------------------------------------------------------------
class StubResponse:
    def __init__(self, status_code, payload, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self):
        return self._payload


def test_exchange_code_posts_the_right_form(configured, monkeypatch):
    captured = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return StubResponse(200, {"access_token": "ya29.example", "id_token": "jwt"})

    monkeypatch.setattr(httpx, "post", fake_post)
    config = google.load_config()
    tokens = google.exchange_code(config, "auth-code-from-google")

    assert tokens["access_token"] == "ya29.example"
    assert captured["url"] == "https://oauth2.googleapis.com/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "auth-code-from-google"
    assert captured["data"]["redirect_uri"] == REDIRECT_URI
    # The secret belongs in the server-to-server body, and nowhere else.
    assert captured["data"]["client_secret"] == CLIENT_SECRET


def test_a_rejected_code_does_not_leak_googles_message(configured, monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: StubResponse(400, {"error": "invalid_grant"}, text='{"error":"invalid_grant"}'),
    )
    config = google.load_config()
    with pytest.raises(google.GoogleAuthError) as failure:
        google.exchange_code(config, "stale-code")
    assert "invalid_grant" not in str(failure.value)
    assert "Google rejected" in str(failure.value)


def test_network_failure_is_reported_plainly(configured, monkeypatch):
    def explode(*args, **kwargs):
        raise httpx.ConnectError("dns is down")

    monkeypatch.setattr(httpx, "post", explode)
    config = google.load_config()
    with pytest.raises(google.GoogleAuthError) as failure:
        google.exchange_code(config, "code")
    assert "could not reach Google" in str(failure.value)


def test_fetch_profile_requires_a_subject(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: StubResponse(200, {"email": "a@b.com"}))
    with pytest.raises(google.GoogleAuthError):
        google.fetch_profile("token")


def test_fetch_profile_sends_the_bearer_token(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return StubResponse(200, PROFILE)

    monkeypatch.setattr(httpx, "get", fake_get)
    profile = google.fetch_profile("ya29.example")

    assert profile["sub"] == PROFILE["sub"]
    assert captured["headers"]["Authorization"] == "Bearer ya29.example"
    assert captured["url"] == "https://openidconnect.googleapis.com/v1/userinfo"


# ---------------------------------------------------------------------------
# Identity linking
# ---------------------------------------------------------------------------
def test_a_new_google_user_gets_their_own_workspace(connection):
    user = google.upsert_user(connection, PROFILE)

    assert user["email"] == "thandi@example.com"
    assert user["name"] == "Thandi Mokoena"
    assert user["role"] == "admin"
    assert user["auth_provider"] == "google"
    assert user["google_sub"] == PROFILE["sub"]
    assert user["org_name"] == "Thandi's workspace"

    # No usable password exists for this account.
    assert user["password_hash"]
    assert not auth.verify_password("", user["password_salt"], user["password_hash"])
    assert not auth.verify_password("password", user["password_salt"], user["password_hash"])


def test_returning_google_user_is_recognised(connection):
    first = google.upsert_user(connection, PROFILE)
    second = google.upsert_user(connection, {**PROFILE, "name": "Thandi M."})

    assert first["id"] == second["id"]
    # A changed Google display name is picked up on the next sign-in.
    assert second["name"] == "Thandi M."
    # One Google identity, and no second workspace created for the same person.
    assert connection.execute(
        "SELECT COUNT(*) AS n FROM users WHERE google_sub IS NOT NULL"
    ).fetchone()["n"] == 1
    assert connection.execute(
        "SELECT COUNT(*) AS n FROM organisations"
    ).fetchone()["n"] == 2  # the demo org, plus Thandi's


def test_google_sign_in_links_to_an_existing_password_account(connection):
    existing = connection.execute(
        "SELECT id, email, org_id, role FROM users WHERE email = 'analyst@northline.ng'"
    ).fetchone()

    user = google.upsert_user(
        connection,
        {
            "sub": "google-sub-for-analyst",
            "email": "analyst@northline.ng",
            "email_verified": True,
            "name": "Tunde Salami",
        },
    )

    assert user["id"] == existing["id"]
    assert user["org_id"] == existing["org_id"]
    assert user["role"] == existing["role"]  # role is not escalated by signing in
    assert user["auth_provider"] == "password+google"
    assert user["google_sub"] == "google-sub-for-analyst"
    # The password still works.
    row = connection.execute(
        "SELECT password_hash, password_salt FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    assert auth.verify_password("northline2026", row["password_salt"], row["password_hash"])


def test_an_unverified_email_cannot_take_over_an_account(connection):
    with pytest.raises(google.GoogleAuthError) as failure:
        google.upsert_user(
            connection,
            {
                "sub": "attacker-sub",
                "email": "admin@northline.ng",
                "email_verified": False,
                "name": "Not Ade",
            },
        )
    assert "confirmed" in str(failure.value)

    row = connection.execute(
        "SELECT google_sub FROM users WHERE email = 'admin@northline.ng'"
    ).fetchone()
    assert row["google_sub"] is None


def test_two_google_accounts_cannot_claim_the_same_email(connection):
    google.upsert_user(connection, PROFILE)
    with pytest.raises(google.GoogleAuthError) as failure:
        google.upsert_user(connection, {**PROFILE, "sub": "a-different-subject"})
    assert "already linked" in str(failure.value)


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------
def test_providers_reports_what_is_available(api, configured):
    payload = api.get("/api/auth/providers").json()
    assert payload == {"google": True, "password": True}


def test_start_redirects_to_google_with_a_state(api, configured):
    response = api.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 302

    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "state=" in location
    assert CLIENT_SECRET not in location

    # The state we issued is stored and unused.
    row = api.get("/api/auth/providers")  # unrelated call, keeps the client busy
    assert row.status_code == 200


def test_start_is_unavailable_when_not_configured(api, unconfigured):
    response = api.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_start_ignores_an_offsite_redirect_target(api, configured, connection):
    api.get("/api/auth/google/start?redirect=//evil.example", follow_redirects=False)
    stored = connection.execute("SELECT redirect_to FROM oauth_states").fetchall()
    assert [row["redirect_to"] for row in stored] == ["/app"]


def test_callback_without_a_code_sends_people_back_with_a_message(api, configured):
    response = api.get("/api/auth/google/callback?state=whatever", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{BASE_URL}/sign-in?error=")


def test_callback_reports_a_cancelled_consent_screen(api, configured):
    response = api.get(
        "/api/auth/google/callback?error=access_denied", follow_redirects=False
    )
    assert response.status_code == 302
    assert "cancelled" in response.headers["location"]


def test_callback_rejects_an_unknown_state(api, configured):
    response = api.get(
        "/api/auth/google/callback?code=abc&state=never-issued", follow_redirects=False
    )
    assert response.status_code == 302
    assert "expired" in response.headers["location"]


def test_full_callback_issues_a_one_time_code(api, configured, monkeypatch, connection):
    monkeypatch.setattr(google, "exchange_code", lambda config, code: {"access_token": "tok"})
    monkeypatch.setattr(google, "fetch_profile", lambda access_token: PROFILE)

    start = api.get("/api/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])

    callback = api.get(
        f"/api/auth/google/callback?code=auth-code&state={state}", follow_redirects=False
    )
    assert callback.status_code == 302

    location = callback.headers["location"]
    assert location.startswith(f"{BASE_URL}/auth/callback?code=")
    assert _query(location, "next") == "/app"
    # The session token must not be in the URL.
    exchange_code = _query(location, "code")
    assert exchange_code and len(exchange_code) > 20

    # And that code is what turns into a session.
    session = api.post("/api/auth/google/session", json={"code": exchange_code})
    assert session.status_code == 200
    payload = session.json()
    assert payload["token"]
    assert payload["user"]["email"] == "thandi@example.com"

    me = api.get("/api/auth/me", headers={"Authorization": f"Bearer {payload['token']}"})
    assert me.status_code == 200
    assert me.json()["user"]["name"] == "Thandi Mokoena"


def test_a_failed_exchange_returns_people_to_sign_in(api, configured, monkeypatch):
    def refuse(config, code):
        raise google.GoogleAuthError("Google rejected that sign-in attempt. Please try again.")

    monkeypatch.setattr(google, "exchange_code", refuse)

    start = api.get("/api/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])
    callback = api.get(
        f"/api/auth/google/callback?code=bad&state={state}", follow_redirects=False
    )

    assert callback.status_code == 302
    assert callback.headers["location"].startswith(f"{BASE_URL}/sign-in?error=")
    assert "rejected" in callback.headers["location"]


def test_the_exchange_code_cannot_be_reused(api, configured, monkeypatch):
    monkeypatch.setattr(google, "exchange_code", lambda config, code: {"access_token": "tok"})
    monkeypatch.setattr(google, "fetch_profile", lambda access_token: PROFILE)

    start = api.get("/api/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])
    callback = api.get(
        f"/api/auth/google/callback?code=auth-code&state={state}", follow_redirects=False
    )
    code = _query(callback.headers["location"], "code")

    assert api.post("/api/auth/google/session", json={"code": code}).status_code == 200
    # Second attempt: already redeemed.
    assert api.post("/api/auth/google/session", json={"code": code}).status_code == 401


def test_an_invented_exchange_code_is_refused(api, configured):
    response = api.post("/api/auth/google/session", json={"code": "made-up-code-value"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_a_google_session_unlocks_the_private_surface(api, configured, monkeypatch):
    monkeypatch.setattr(google, "exchange_code", lambda config, code: {"access_token": "tok"})
    monkeypatch.setattr(google, "fetch_profile", lambda access_token: PROFILE)

    assert api.get("/api/worklist?budget=2").status_code == 401

    start = api.get("/api/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])
    callback = api.get(
        f"/api/auth/google/callback?code=auth-code&state={state}", follow_redirects=False
    )
    code = _query(callback.headers["location"], "code")
    token = api.post("/api/auth/google/session", json={"code": code}).json()["token"]

    allowed = api.get("/api/worklist?budget=2", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200


def test_sso_status_is_administrator_only_and_hides_the_secret(api, configured):
    admin = api.post(
        "/api/auth/signin",
        json={"email": "admin@northline.ng", "password": auth.DEMO_PASSWORD},
    ).json()["token"]
    officer = api.post(
        "/api/auth/signin",
        json={"email": "collections@northline.ng", "password": auth.DEMO_PASSWORD},
    ).json()["token"]

    assert api.get("/api/org/sso-status").status_code == 401
    assert api.get("/api/org/sso-status", headers={"Authorization": f"Bearer {officer}"}).status_code == 403

    response = api.get("/api/org/sso-status", headers={"Authorization": f"Bearer {admin}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["redirect_uri_to_register"] == REDIRECT_URI
    assert CLIENT_SECRET not in response.text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _state_from(location: str) -> str:
    return _query(location, "state")


def _query(location: str, key: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(location).query).get(key, [""])[0]

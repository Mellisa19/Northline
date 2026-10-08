"""Access control tests.

The API reads its database path from ``db.DB_PATH`` at call time, so pointing that
at a temporary file isolates the whole HTTP layer without patching each module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, db  # noqa: E402
from app.auth import DEMO_PASSWORD  # noqa: E402
from app.db import create_schema, reset  # noqa: E402


@pytest.fixture(scope="session")
def workdir():
    path = Path(__file__).resolve().parent / ".tmp"
    path.mkdir(exist_ok=True)
    return path


@pytest.fixture
def api(workdir, monkeypatch):
    """A TestClient wired to its own database."""
    path = workdir / "auth.db"
    connection = reset(path)
    create_schema(connection)
    auth.seed_demo_team(connection)
    connection.close()

    monkeypatch.setattr(db, "DB_PATH", path)

    from app.api import app

    with TestClient(app) as client:
        yield client


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def test_passwords_are_salted_and_verifiable():
    salt_a, salt_b = auth.new_salt(), auth.new_salt()
    assert salt_a != salt_b

    hash_a = auth.hash_password("correct horse battery", salt_a)
    hash_b = auth.hash_password("correct horse battery", salt_b)

    # Same password, different salts, different digests.
    assert hash_a != hash_b
    assert auth.verify_password("correct horse battery", salt_a, hash_a)
    assert not auth.verify_password("wrong horse battery", salt_a, hash_a)


def test_weak_passwords_are_refused():
    assert auth.password_problem("short")
    assert auth.password_problem("password")
    assert auth.password_problem("northline")
    assert auth.password_problem("a-long-enough-secret") is None


# ---------------------------------------------------------------------------
# Sign up and sign in
# ---------------------------------------------------------------------------
def test_sign_up_creates_an_organisation_with_an_administrator(api):
    response = api.post(
        "/api/auth/signup",
        json={
            "org_name": "Adeola Capital",
            "name": "Kemi Adeyemi",
            "email": "kemi@adeola.ng",
            "password": "a-long-enough-secret",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["role"] == "admin"
    assert payload["user"]["org_name"] == "Adeola Capital"
    assert payload["token"]

    me = api.get("/api/auth/me", headers=bearer(payload["token"]))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "kemi@adeola.ng"


def test_sign_up_rejects_duplicate_email_and_weak_passwords(api):
    body = {
        "org_name": "Second Capital",
        "name": "Bola Sanni",
        "email": "bola@second.ng",
        "password": "a-long-enough-secret",
    }
    assert api.post("/api/auth/signup", json=body).status_code == 201
    assert api.post("/api/auth/signup", json=body).status_code == 409

    weak = {**body, "email": "weak@second.ng", "password": "password"}
    assert api.post("/api/auth/signup", json=weak).status_code == 400

    malformed = {**body, "email": "not-an-email"}
    assert api.post("/api/auth/signup", json=malformed).status_code == 400


def test_sign_in_rejects_the_wrong_password_without_revealing_which_email_exists(api):
    bad_password = api.post(
        "/api/auth/signin", json={"email": "admin@northline.ng", "password": "not-the-password"}
    )
    unknown_email = api.post(
        "/api/auth/signin", json={"email": "nobody@northline.ng", "password": DEMO_PASSWORD}
    )
    assert bad_password.status_code == 401
    assert unknown_email.status_code == 401
    assert bad_password.json()["detail"] == unknown_email.json()["detail"]


def test_session_token_resolves_to_a_user_and_signs_out(api):
    sign_in = api.post(
        "/api/auth/signin", json={"email": "collections@northline.ng", "password": DEMO_PASSWORD}
    ).json()
    token = sign_in["token"]
    assert sign_in["user"]["role"] == "collections"

    assert api.get("/api/auth/me", headers=bearer(token)).status_code == 200
    assert api.post("/api/auth/signout", headers=bearer(token)).status_code == 200
    # Revoked server-side, not merely forgotten by the client.
    assert api.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_a_garbage_token_is_rejected(api):
    assert api.get("/api/auth/me", headers=bearer("not-a-real-token")).status_code == 401
    assert api.get("/api/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert api.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# What is private and what is not
# ---------------------------------------------------------------------------
def test_borrower_records_are_private_but_aggregates_are_not(api):
    # This database has no portfolio in it, so the point is reachability rather
    # than content: these must be answerable without a session.
    for path in (
        "/api/portfolio/summary",
        "/api/portfolio/featured-case",
        "/api/portfolio/ordering-demo?budget=10",
        "/api/playbooks",
        "/api/meta",
    ):
        response = api.get(path)
        assert response.status_code != 401, f"{path} should not require a session"

    # Private: anything that could name an account.
    assert api.get("/api/worklist?budget=5").status_code == 401
    assert api.get("/api/accounts/1").status_code == 401
    assert api.get("/api/org/team").status_code == 401


def test_a_session_unlocks_the_queue(api):
    token = api.post(
        "/api/auth/signin", json={"email": "admin@northline.ng", "password": DEMO_PASSWORD}
    ).json()["token"]
    blocked = api.get("/api/worklist?budget=5")
    allowed = api.get("/api/worklist?budget=5", headers=bearer(token))

    assert blocked.status_code == 401
    assert allowed.status_code == 200
    assert "rows" in allowed.json()


def test_the_public_ordering_demo_never_names_a_borrower(api):
    payload = api.get("/api/portfolio/ordering-demo?budget=10").json()
    assert "rows" in payload and "baseline_rows" in payload
    for row in payload["rows"] + payload["baseline_rows"]:
        assert "borrower_name" not in row
        assert "ref" not in row
        assert "account_id" not in row
        assert " · " in row["label"]  # sector · city, never a company name

    featured = api.get("/api/portfolio/featured-case")
    if featured.status_code == 200:
        assert "borrower_name" not in featured.json()
        assert featured.json()["descriptor"]


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
def test_only_administrators_can_change_the_team(api):
    admin = api.post(
        "/api/auth/signin", json={"email": "admin@northline.ng", "password": DEMO_PASSWORD}
    ).json()["token"]
    officer = api.post(
        "/api/auth/signin", json={"email": "collections@northline.ng", "password": DEMO_PASSWORD}
    ).json()["token"]

    # Everyone can see who they work with.
    assert api.get("/api/org/team", headers=bearer(admin)).status_code == 200
    assert api.get("/api/org/team", headers=bearer(officer)).status_code == 200

    invite = {"name": "New Person", "email": "new@northline.ng", "role": "analyst"}
    assert api.post("/api/org/team", json=invite, headers=bearer(officer)).status_code == 403

    created = api.post("/api/org/team", json=invite, headers=bearer(admin))
    assert created.status_code == 201
    temporary = created.json()["temporary_password"]

    # The invited person can sign in with the password they were given.
    signed_in = api.post(
        "/api/auth/signin", json={"email": "new@northline.ng", "password": temporary}
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["role"] == "analyst"

    # Unknown roles are refused rather than stored.
    assert (
        api.post(
            "/api/org/team",
            json={"name": "Test Person", "email": "x@northline.ng", "role": "ceo"},
            headers=bearer(admin),
        ).status_code
        == 400
    )


def test_an_administrator_cannot_remove_their_own_access(api):
    token = api.post(
        "/api/auth/signin", json={"email": "admin@northline.ng", "password": DEMO_PASSWORD}
    ).json()["token"]
    me = api.get("/api/auth/me", headers=bearer(token)).json()["user"]
    response = api.delete(f"/api/org/team/{me['id']}", headers=bearer(token))
    assert response.status_code == 400


def test_removing_a_member_revokes_their_sessions(api):
    admin = api.post(
        "/api/auth/signin", json={"email": "admin@northline.ng", "password": DEMO_PASSWORD}
    ).json()["token"]

    created = api.post(
        "/api/org/team",
        json={"name": "Temp Person", "email": "temp@northline.ng", "role": "field"},
        headers=bearer(admin),
    ).json()
    member_id = created["id"]

    member_token = api.post(
        "/api/auth/signin",
        json={"email": "temp@northline.ng", "password": created["temporary_password"]},
    ).json()["token"]
    assert api.get("/api/auth/me", headers=bearer(member_token)).status_code == 200

    assert api.delete(f"/api/org/team/{member_id}", headers=bearer(admin)).status_code == 200
    assert api.get("/api/auth/me", headers=bearer(member_token)).status_code == 401


def test_the_demo_team_covers_every_role(api):
    payload = api.get("/api/auth/demo").json()
    codes = {account["role"] for account in payload["accounts"]}
    assert codes == {role["code"] for role in auth.ROLES}
    assert payload["password"] == DEMO_PASSWORD

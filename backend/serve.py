"""Run the Northline API.

    python serve.py --port 8010

Creates and seeds the demo database on first run so a fresh checkout works with a
single command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import env  # noqa: E402

env.load()  # before anything reads configuration

from app import auth, google  # noqa: E402
from app.api import app  # noqa: E402
from app.db import connect, create_schema, get_meta  # noqa: E402
from app.generate import SEED, build_database  # noqa: E402


def report_sign_in() -> None:
    status = google.status()
    if status["enabled"]:
        print("Google sign-in: enabled")
        print(f"  redirect URI registered with Google must be exactly: {status['redirect_uri']}")
    else:
        print("Google sign-in: NOT configured — the button will say so on the sign-in page")
        for problem in status["problems"]:
            print(f"  - {problem}")
        print("  Copy backend/.env.example to backend/.env and fill it in.")


def ensure_seeded() -> None:
    connection = connect()
    try:
        create_schema(connection)
        if get_meta(connection, "generator") is None:
            print("No portfolio found; generating the demo book...")
            build_database(connection, seed=SEED)
        team = auth.seed_demo_team(connection)
        if team.get("created"):
            print(f"Demo team ready: {team['created']} users, password {team['password']}")
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Northline API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    ensure_seeded()
    report_sign_in()

    import uvicorn

    if args.reload:
        uvicorn.run("app.api:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

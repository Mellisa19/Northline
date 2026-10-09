"""Run the Northline API.

    python serve.py                       # http://127.0.0.1:8010
    HOST=0.0.0.0 PORT=8000 python serve.py  # what a container does

Creates and seeds the demonstration book on first run, so a fresh checkout works
with a single command. When ``frontend/dist`` exists the same process also serves
the built interface, which is how a deployment runs: one container, one origin,
no CORS.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import env  # noqa: E402

env.load()  # before anything reads configuration

from app import auth, google  # noqa: E402
from app.api import DIST_DIR, app  # noqa: E402
from app.db import connect, create_schema, get_meta  # noqa: E402
from app.generate import SEED, build_database  # noqa: E402


def report_sign_in() -> None:
    status = google.status()
    if status["enabled"]:
        print("Google sign-in: enabled")
        print(f"  the redirect URI registered with Google must be exactly: {status['redirect_uri']}")
    else:
        print("Google sign-in: not configured — the button is hidden rather than broken")
        for problem in status["problems"]:
            print(f"  - {problem}")
        print("  Copy backend/.env.example to backend/.env and fill it in to enable it.")


def report_demo_access() -> None:
    if auth.demo_mode_enabled():
        print(f"Demo access: ON — {auth.DEMO_TEAM[0][0]} / {auth.DEMO_PASSWORD}")
        print("  Set DEMO_MODE=false to turn this off and create no demo accounts.")
    else:
        print("Demo access: OFF — sign up or sign in with Google instead")


def report_interface() -> None:
    if (DIST_DIR / "index.html").is_file():
        print(f"Interface: serving the build in {DIST_DIR}")
    else:
        print("Interface: not built — run `npm run build` in frontend/, or use `npm run dev`")


def ensure_seeded() -> None:
    connection = connect()
    try:
        create_schema(connection)
        if get_meta(connection, "generator") is None:
            print("No portfolio found; generating the demonstration book...")
            build_database(connection, seed=SEED)
        team = auth.seed_demo_team(connection)
        if team.get("created"):
            print(f"Demo team ready: {team['created']} users")
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Northline application.")
    parser.add_argument("--host", default=env.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(env.get("PORT", "8010")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    ensure_seeded()
    report_sign_in()
    report_demo_access()
    report_interface()
    print(f"Listening on http://{args.host}:{args.port}")

    import uvicorn

    if args.reload:
        uvicorn.run("app.api:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

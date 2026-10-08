"""Build the demo database.

    python seed.py [--force]

The portfolio is deterministic for a given seed, so charts and figures on the
site stay stable between restarts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import auth, config  # noqa: E402
from app.db import connect, create_schema, get_meta, reset  # noqa: E402
from app.generate import SEED, build_database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Northline demo portfolio.")
    parser.add_argument("--force", action="store_true", help="Rebuild even if data exists.")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    existing = None
    if not args.force:
        connection = connect()
        try:
            create_schema(connection)
            existing = get_meta(connection, "generator")
        finally:
            connection.close()

    if existing and not args.force:
        print(f"Portfolio already present ({existing}). Use --force to rebuild.")
        return 0

    connection = reset()
    try:
        summary = build_database(connection, seed=args.seed)
        team = auth.seed_demo_team(connection)
    finally:
        connection.close()

    print(f"Seeded Northline portfolio as of {config.AS_OF.isoformat()} (seed {args.seed})")
    print(f"  accounts        {summary['accounts']:,}")
    print(f"    active        {summary['active']:,}")
    print(f"    written off   {summary['written_off']:,}")
    print(f"    closed        {summary['closed']:,}")
    print(f"  signals         {summary['signals']:,}")
    print(f"  actions         {summary['actions']:,}")
    print(f"  promises        {summary['promises']:,}")
    print(f"  control group   {summary['control_group']:,}")
    if team.get("created"):
        print(f"  demo team       {team['created']} users · password {team['password']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Write operations: the closed loop.

Reading a worklist is not a product. Recording what was done, capturing a dated
commitment, and settling it so the account position actually moves — that is the
part that produces the outcome data everything else learns from.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from . import analytics, config

AS_OF = config.AS_OF


def _successor(account_id: int, ref: str) -> dict:
    return {"account_id": account_id, "ref": ref}


def log_action(
    connection: sqlite3.Connection,
    account_id: int,
    channel: str,
    disposition: str,
    officer: str,
    playbook_code: str | None = None,
    notes: str = "",
    promised_date: str | None = None,
    promised_amount: int | None = None,
    occurred_at: str | None = None,
) -> dict:
    """Record a contact attempt, and the promise that came out of it."""
    account = connection.execute(
        "SELECT id, ref, instalment, arrears_amount FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if account is None:
        raise KeyError(f"Account {account_id} not found")

    if channel not in config.CHANNEL_COST:
        raise ValueError(f"Unknown channel: {channel}")
    if disposition not in config.DISPOSITIONS:
        raise ValueError(f"Unknown disposition: {disposition}")

    when = occurred_at or AS_OF.isoformat()
    next_id = connection.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM actions WHERE account_id = ?", (account_id,)
    ).fetchone()[0]

    promise_id = None
    if disposition == "promise_to_pay" and promised_date and promised_amount:
        promise_id = connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM promises WHERE account_id = ?", (account_id,)
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO promises (id, account_id, made_at, promised_date, amount, status, "
            "resolved_at, action_id) VALUES (?,?,?,?,?,'open',NULL,?)",
            (promise_id, account_id, when, promised_date, int(promised_amount), next_id),
        )

    connection.execute(
        "INSERT INTO actions (id, account_id, occurred_at, channel, disposition, officer, "
        "playbook_code, notes, cost, effect, promise_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            next_id,
            account_id,
            when,
            channel,
            disposition,
            officer,
            playbook_code,
            notes,
            config.CHANNEL_COST[channel],
            "promise" if promise_id else "no_effect",
            promise_id,
        ),
    )
    connection.commit()
    analytics.bump()

    return {
        "action_id": next_id,
        "promise_id": promise_id,
        "cost": config.CHANNEL_COST[channel],
        "occurred_at": when,
        **_successor(account_id, account["ref"]),
    }


def resolve_promise(
    connection: sqlite3.Connection,
    account_id: int,
    promise_id: int,
    kept: bool,
    settled_amount: int | None = None,
) -> dict:
    """Mark a promise kept or broken. A kept promise is cash, and settles the oldest arrears."""
    promise = connection.execute(
        "SELECT * FROM promises WHERE account_id = ? AND id = ?", (account_id, promise_id)
    ).fetchone()
    if promise is None:
        raise KeyError(f"Promise {promise_id} not found on account {account_id}")
    if promise["status"] != "open":
        raise ValueError(f"Promise {promise_id} is already {promise['status']}")

    status = "kept" if kept else "broken"
    connection.execute(
        "UPDATE promises SET status = ?, resolved_at = ? WHERE account_id = ? AND id = ?",
        (status, AS_OF.isoformat(), account_id, promise_id),
    )
    connection.execute(
        "UPDATE actions SET effect = ? WHERE account_id = ? AND promise_id = ?",
        ("promise_kept" if kept else "promise_broken", account_id, promise_id),
    )

    settled = 0
    if kept:
        settled = int(settled_amount or promise["amount"])
        apply_payment(connection, account_id, settled, AS_OF.isoformat(), "collections_promise")

    connection.commit()
    analytics.bump()
    position = recompute_position(connection, account_id)
    return {"promise_id": promise_id, "status": status, "settled": settled, "position": position}


def apply_payment(
    connection: sqlite3.Connection,
    account_id: int,
    amount: int,
    paid_date: str,
    source: str = "collections_promise",
    channel: str = "bank_transfer",
) -> dict:
    connection.execute(
        "INSERT INTO payments (account_id, installment_id, paid_date, amount, channel, source) "
        "VALUES (?,?,?,?,?,?)",
        (account_id, None, paid_date, int(amount), channel, source),
    )
    connection.commit()
    analytics.bump()
    return {"amount": int(amount), "paid_date": paid_date, "source": source}


def recompute_position(connection: sqlite3.Connection, account_id: int) -> dict:
    """Rebuild the account position from the payment record.

    Payments settle the oldest outstanding instalment first, so a cleared backlog
    genuinely restores the account to current and the delinquency band moves.
    """
    rows = connection.execute(
        "SELECT id, seq, due_date, amount_due FROM installments WHERE account_id = ? "
        "ORDER BY due_date, seq",
        (account_id,),
    ).fetchall()
    if not rows:
        raise KeyError(f"No schedule for account {account_id}")

    total_paid = connection.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE account_id = ?",
        (account_id,),
    ).fetchone()["total"]

    remaining = float(total_paid)
    arrears = 0.0
    settled = 0
    first_open: date | None = None

    for row in rows:
        due = date.fromisoformat(row["due_date"])
        amount_due = float(row["amount_due"])
        paid = 0.0
        status = "unpaid"
        if due <= AS_OF:
            if remaining >= amount_due - config.SETTLEMENT_TOLERANCE:
                paid = amount_due
                remaining = max(0.0, remaining - amount_due)
                status = "paid"
                settled += 1
            else:
                paid = max(0.0, remaining)
                remaining = 0.0
                arrears += amount_due - paid
                status = (
                    "paid"
                    if amount_due - paid <= config.SETTLEMENT_TOLERANCE
                    else ("partial" if paid > config.SETTLEMENT_TOLERANCE else "unpaid")
                )
                if first_open is None:
                    first_open = due
        connection.execute(
            "UPDATE installments SET amount_paid = ?, status = ? WHERE id = ?",
            (int(round(paid)), status, row["id"]),
        )

    dpd = max(0, (AS_OF - first_open).days) if first_open else 0
    band = config.band_for_dpd(dpd)
    tenor = len(rows)
    principal = connection.execute(
        "SELECT principal, instalment, status FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    principal_component = principal["principal"] / tenor
    unpaid_count = connection.execute(
        "SELECT COUNT(*) AS n FROM installments WHERE account_id = ? AND status != 'paid'",
        (account_id,),
    ).fetchone()["n"]
    outstanding_principal = int(round(principal_component * unpaid_count, -2))
    instalments_due = connection.execute(
        "SELECT COUNT(*) AS n FROM installments WHERE account_id = ? AND due_date <= ?",
        (account_id, AS_OF.isoformat()),
    ).fetchone()["n"]
    instalments_paid = connection.execute(
        "SELECT COUNT(*) AS n FROM installments WHERE account_id = ? AND status = 'paid'",
        (account_id,),
    ).fetchone()["n"]

    status = principal["status"]
    if status == "active" and band == 0:
        status = "active"
    connection.execute(
        "UPDATE accounts SET arrears_amount = ?, dpd = ?, band = ?, outstanding_principal = ?, "
        "instalments_paid = ?, instalments_due = ? WHERE id = ?",
        (
            int(round(arrears)),
            dpd,
            band,
            outstanding_principal,
            instalments_paid,
            instalments_due,
            account_id,
        ),
    )

    # Keep the current reporting point in the history in step with the account.
    connection.execute(
        "UPDATE band_history SET dpd = ?, band = ?, arrears = ?, outstanding = ? "
        "WHERE account_id = ? AND month_end = ?",
        (dpd, band, int(round(arrears)), outstanding_principal, account_id, AS_OF.isoformat()),
    )
    connection.commit()
    analytics.bump()

    return {
        "dpd": dpd,
        "band": band,
        "band_label": config.BANDS[band]["label"],
        "arrears_amount": int(round(arrears)),
        "outstanding_principal": outstanding_principal,
        "instalments_paid": instalments_paid,
        "instalments_due": instalments_due,
    }


def account_timeline(connection: sqlite3.Connection, account_id: int, limit: int = 60) -> list[dict]:
    """One merged, chronological story of the account."""
    events: list[dict] = []

    for row in connection.execute(
        "SELECT occurred_at, channel, disposition, officer, playbook_code, notes, cost, effect "
        "FROM actions WHERE account_id = ? ORDER BY occurred_at DESC LIMIT ?",
        (account_id, limit),
    ).fetchall():
        events.append(
            {
                "kind": "action",
                "at": row["occurred_at"],
                "title": config.DISPOSITION_LABELS.get(row["disposition"], row["disposition"]),
                "subtitle": f"{row['channel'].replace('_', ' ').title()} by {row['officer']}",
                "detail": row["notes"] or None,
                "playbook_code": row["playbook_code"],
                "effect": row["effect"],
                "cost": row["cost"],
            }
        )

    for row in connection.execute(
        "SELECT made_at, promised_date, amount, status, resolved_at FROM promises "
        "WHERE account_id = ? ORDER BY made_at DESC LIMIT ?",
        (account_id, limit),
    ).fetchall():
        events.append(
            {
                "kind": "promise",
                "at": row["made_at"],
                "title": f"Promise to pay {_naira(row['amount'])} by {row['promised_date']}",
                "subtitle": f"Promise {row['status']}",
                "detail": f"Resolved {row['resolved_at']}" if row["resolved_at"] else None,
                "effect": row["status"],
                "cost": 0,
            }
        )

    for row in connection.execute(
        "SELECT paid_date, amount, channel, source FROM payments WHERE account_id = ? "
        "ORDER BY paid_date DESC LIMIT ?",
        (account_id, limit),
    ).fetchall():
        events.append(
            {
                "kind": "payment",
                "at": row["paid_date"],
                "title": f"Payment received {_naira(row['amount'])}",
                "subtitle": row["channel"].replace("_", " ").title(),
                "detail": f"Source: {row['source'].replace('_', ' ')}",
                "effect": "payment",
                "cost": 0,
            }
        )

    events.sort(key=lambda event: event["at"] or "", reverse=True)
    return events[:limit]


def _naira(amount: float) -> str:
    amount = float(amount or 0)
    if amount >= 1_000_000:
        return f"\u20a6{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"\u20a6{amount / 1_000:.0f}k"
    return f"\u20a6{amount:,.0f}"

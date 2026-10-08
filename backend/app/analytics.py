"""Portfolio analytics: queries, scoring assembly and reporting.

Everything the interface displays is computed here from the seeded book. There are
no hard-coded figures anywhere in the product: if the database changes, the numbers
change with it.

Performance note: the worklist needs each account joined to its signals and its
cash-flow summary. That is ~1,100 accounts and ~20k cash-flow rows, so the built
worklist is cached in-process and invalidated whenever a mutation occurs.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from . import config, playbooks, priority, scoring

AS_OF = config.AS_OF

# --------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------
_CACHE: dict[str, object] = {}


def bump() -> None:
    """Invalidate derived data after a write."""
    _CACHE.clear()


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load_cashflow(connection: sqlite3.Connection) -> dict[int, dict]:
    """Per-account cash-flow summaries built from the monthly series."""
    rows = connection.execute(
        "SELECT account_id, month, inflow, outflow, closing_balance, pos_inflow, "
        "transfer_inflow, new_recurring_debits FROM cashflow_months ORDER BY account_id, month"
    ).fetchall()

    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["account_id"], []).append(row)

    summaries: dict[int, dict] = {}
    for account_id, series in grouped.items():
        if len(series) < 7:
            summaries[account_id] = {"months": series, "change_pct": None}
            continue
        recent = sum(row["inflow"] for row in series[-3:]) / 3.0
        prior = sum(row["inflow"] for row in series[-6:-3]) / 3.0
        balances = [row["closing_balance"] for row in series[-6:]]
        avg_balance = sum(balances[:-1]) / max(1, len(balances) - 1)
        summaries[account_id] = {
            "months": series,
            "recent_3m_avg": round(recent),
            "prior_3m_avg": round(prior),
            "change_pct": round((recent - prior) / prior * 100, 1) if prior else None,
            "latest_balance": balances[-1],
            "six_month_average": round(avg_balance),
        }
    return summaries


def load_signals(connection: sqlite3.Connection) -> dict[int, list[dict]]:
    rows = connection.execute(
        "SELECT id, account_id, code, label, severity, detected_at, headline, evidence, "
        "lead_days, actionable FROM signal_events ORDER BY detected_at DESC"
    ).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["account_id"], []).append(
            {
                "id": row["id"],
                "account_id": row["account_id"],
                "code": row["code"],
                "label": row["label"],
                "severity": row["severity"],
                "detected_at": row["detected_at"],
                "headline": row["headline"],
                "evidence": json.loads(row["evidence"] or "{}"),
                "lead_days": row["lead_days"],
                "actionable": bool(row["actionable"]),
            }
        )
    return grouped


ACCOUNT_SQL = """
SELECT a.*, b.name AS borrower_name, b.sector, b.city, b.state, b.contact_name,
       b.contact_phone, b.contact_email, b.relationship_manager, b.years_trading,
       b.employees, b.monthly_inflow_base, b.cac_number,
       (SELECT COALESCE(SUM(i.amount_due - i.amount_paid), 0) FROM installments i
          WHERE i.account_id = a.id AND i.status != 'paid') AS outstanding_total,
       (SELECT MIN(i.due_date) FROM installments i
          WHERE i.account_id = a.id AND i.due_date <= :as_of AND i.status != 'paid')
          AS oldest_unpaid_due,
       (SELECT MIN(i.due_date) FROM installments i
          WHERE i.account_id = a.id AND i.due_date > :as_of) AS next_due_date,
       (SELECT COALESCE(SUM(p.amount), 0) FROM payments p WHERE p.account_id = a.id)
          AS total_collected,
       (SELECT COALESCE(SUM(p.amount), 0) FROM payments p
          WHERE p.account_id = a.id AND p.paid_date >= :d90) AS collected_90d,
       (SELECT COALESCE(SUM(ac.cost), 0) FROM actions ac
          WHERE ac.account_id = a.id AND ac.occurred_at >= :d90) AS cost_90d,
       (SELECT COUNT(*) FROM actions ac WHERE ac.account_id = a.id) AS action_count,
       (SELECT COUNT(*) FROM promises pr
          WHERE pr.account_id = a.id AND pr.status = 'broken') AS broken_promises,
       (SELECT COUNT(*) FROM promises pr
          WHERE pr.account_id = a.id AND pr.status = 'open') AS open_promises,
       (SELECT MIN(pr.promised_date) FROM promises pr
          WHERE pr.account_id = a.id AND pr.status = 'open') AS next_promised_date
FROM accounts a
JOIN borrowers b ON b.id = a.borrower_id
WHERE a.status IN ('active', 'written_off')
"""


def load_accounts(connection: sqlite3.Connection) -> list[dict]:
    as_of = AS_OF.isoformat()
    rows = connection.execute(
        ACCOUNT_SQL, {"as_of": as_of, "d90": (AS_OF - timedelta(days=90)).isoformat()}
    ).fetchall()

    short_rows = connection.execute(
        "SELECT p.account_id, "
        "SUM(CASE WHEN p.amount < a.instalment * 0.92 THEN 1 ELSE 0 END) AS short_count "
        "FROM (SELECT account_id, amount, ROW_NUMBER() OVER "
        "        (PARTITION BY account_id ORDER BY paid_date DESC, id DESC) AS rn "
        "      FROM payments) p "
        "JOIN accounts a ON a.id = p.account_id WHERE p.rn <= 3 GROUP BY p.account_id"
    ).fetchall()
    short_map = {row["account_id"]: row["short_count"] for row in short_rows}

    accounts: list[dict] = []
    for row in rows:
        account = dict(row)
        account["outstanding_total"] = int(account["outstanding_total"] or 0)
        account["exposure"] = account["outstanding_total"]
        account["short_payments_last_3"] = short_map.get(account["id"], 0)
        account["next_due_in_days"] = (
            (date.fromisoformat(account["next_due_date"]) - AS_OF).days
            if account["next_due_date"]
            else None
        )
        account["dpd"] = int(account["dpd"] or 0)
        accounts.append(account)
    return accounts


def build_book(connection: sqlite3.Connection) -> list[dict]:
    """Every live account, scored, playbooked and priced. Cached in-process."""
    cached = _CACHE.get("book")
    if cached is not None:
        return cached  # type: ignore[return-value]

    accounts = load_accounts(connection)
    signals = load_signals(connection)
    cashflow = load_cashflow(connection)

    book: list[dict] = []
    for account in accounts:
        account_signals = signals.get(account["id"], [])
        actionable = [s for s in account_signals if s["actionable"]]
        summary = cashflow.get(account["id"])
        summary_public = (
            {key: value for key, value in summary.items() if key != "months"} if summary else None
        )

        risk = scoring.score_account(account, account_signals, summary_public)
        recommendation = playbooks.recommend(account, account_signals, risk, summary_public)
        value = priority.evaluate(
            account, risk, recommendation["primary"], float(account["outstanding_total"])
        )

        book.append(
            {
                **account,
                "risk": risk,
                "playbook": recommendation,
                "priority_value": value,
                "signals": account_signals,
                "actionable_signals": actionable,
                "cashflow": summary_public,
            }
        )

    _CACHE["book"] = book
    return book


def get_book_account(connection: sqlite3.Connection, account_id: int) -> dict | None:
    for account in build_book(connection):
        if account["id"] == account_id:
            return account
    return None


# --------------------------------------------------------------------------
# Portfolio reporting
# --------------------------------------------------------------------------
def portfolio_summary(connection: sqlite3.Connection) -> dict:
    book = build_book(connection)
    active = [row for row in book if row["status"] == "active"]

    def pare(rows: list[dict], min_dpd: int) -> dict:
        selected = [row for row in rows if row["dpd"] >= min_dpd]
        return {
            "accounts": len(selected),
            "count_pct": round(len(selected) / len(rows) * 100, 1) if rows else 0.0,
            "value": round(sum(row["outstanding_principal"] for row in selected)),
            "value_pct": round(
                sum(row["outstanding_principal"] for row in selected)
                / max(1, sum(row["outstanding_principal"] for row in rows))
                * 100,
                1,
            ),
        }

    band_distribution = []
    for band in config.BANDS:
        rows = [row for row in active if row["band"] == band["index"]]
        band_distribution.append(
            {
                "band": band["index"],
                "code": band["code"],
                "label": band["label"],
                "accounts": len(rows),
                "value": round(sum(row["outstanding_principal"] for row in rows)),
                "arrears": round(sum(row["arrears_amount"] for row in rows)),
            }
        )

    risk_distribution = []
    for _low, _high, code, label in scoring.BANDS:
        rows = [row for row in active if row["risk"]["band_code"] == code]
        risk_distribution.append(
            {
                "code": code,
                "label": label,
                "accounts": len(rows),
                "value": round(sum(row["outstanding_total"] for row in rows)),
                "expected_recovery": round(
                    sum(row["priority_value"]["expected_recovery"] for row in rows)
                ),
            }
        )

    by_product = []
    for product in config.PRODUCTS:
        rows = [row for row in active if row["product_code"] == product["code"]]
        if not rows:
            continue
        by_product.append(
            {
                "code": product["code"],
                "name": product["name"],
                "accounts": len(rows),
                "value": round(sum(row["outstanding_principal"] for row in rows)),
                "par30_pct": round(
                    sum(1 for row in rows if row["dpd"] >= 1) / len(rows) * 100, 1
                ),
            }
        )

    needs_attention = [
        row
        for row in active
        if row["dpd"] > 0
        or row["risk"]["index"] >= 40
        or any(s["severity"] >= 2 and s["actionable"] for s in row["signals"])
    ]

    return {
        "as_of": AS_OF.isoformat(),
        "borrowers": len({row["borrower_id"] for row in active}),
        "accounts": len(active),
        "written_off_accounts": len(book) - len(active),
        "book_principal": round(sum(row["outstanding_principal"] for row in active)),
        "book_obligation": round(sum(row["outstanding_total"] for row in active)),
        "arrears_total": round(sum(row["arrears_amount"] for row in active)),
        "par30": pare(active, 1),
        "par60": pare(active, 31),
        "par90": pare(active, 61),
        "band_distribution": band_distribution,
        "risk_distribution": risk_distribution,
        "by_product": by_product,
        "needs_attention": {
            "accounts": len(needs_attention),
            "value": round(sum(row["outstanding_total"] for row in needs_attention)),
        },
        "expected_recovery_available": round(
            sum(row["priority_value"]["expected_recovery"] for row in active)
        ),
        "loss_at_risk": round(sum(row["priority_value"]["loss_at_risk"] for row in active)),
        "collected_90d": round(sum(row["collected_90d"] for row in book)),
        "cost_to_collect_90d": round(sum(row["cost_90d"] for row in book)),
        "monitoring": monitoring_coverage(connection, book),
    }


def monitoring_coverage(connection: sqlite3.Connection, book: list[dict] | None = None) -> dict:
    book = book or build_book(connection)
    active = [row for row in book if row["status"] == "active"]

    by_tier: dict[str, dict] = {}
    for tier in ("full", "selective", "none"):
        rows = [row for row in active if row["monitoring_tier"] == tier]
        by_tier[tier] = {
            "accounts": len(rows),
            "value": round(sum(row["outstanding_principal"] for row in rows)),
        }

    consented = [row for row in active if row["monitoring_consent"] == "active"]
    expired = [row for row in active if row["monitoring_consent"] == "expired"]

    all_signals = [signal for row in active for signal in row["signals"]]
    transaction_signals = [s for s in all_signals if not s["actionable"]]
    monitored_accounts = {row["id"] for row in active if row["monitoring_consent"] == "active"}
    blind_spot = [
        row
        for row in active
        if row["id"] not in monitored_accounts and row["risk"]["index"] >= 40
    ]

    return {
        "consented_accounts": len(consented),
        "consented_value": round(sum(row["outstanding_principal"] for row in consented)),
        "coverage_pct": round(len(consented) / len(active) * 100, 1) if active else 0.0,
        "coverage_value_pct": round(
            sum(row["outstanding_principal"] for row in consented)
            / max(1, sum(row["outstanding_principal"] for row in active))
            * 100,
            1,
        ),
        "expired_accounts": len(expired),
        "by_tier": by_tier,
        "signals_total": len(all_signals),
        "signals_requiring_consent": len(transaction_signals),
        "blind_spot_accounts": len(blind_spot),
        "blind_spot_value": round(sum(row["outstanding_principal"] for row in blind_spot)),
    }


def advance_warning(connection: sqlite3.Connection, window_months: int = 15) -> dict:
    """How early the signals fired, measured against the first real delinquency.

    The denominator is every account that actually reached 31+ days past due inside
    the window the transaction history covers, so the detection rate cannot be
    flattered by accounts whose decline happened before the data begins.
    """
    window_start = _shift_months(AS_OF, -window_months).isoformat()

    first_stress = {
        row["account_id"]: row["first_stress"]
        for row in connection.execute(
            "SELECT account_id, MIN(month_end) AS first_stress FROM band_history "
            "WHERE band >= 2 GROUP BY account_id HAVING first_stress >= ?",
            (window_start,),
        ).fetchall()
    }
    first_decline = {
        row["account_id"]: row["first_decline"]
        for row in connection.execute(
            "SELECT account_id, MIN(detected_at) AS first_decline FROM signal_events "
            "WHERE code = 'inflow_decline' GROUP BY account_id"
        ).fetchall()
    }

    leads: list[int] = []
    flagged: set[int] = set()
    for account_id, stress_date in first_stress.items():
        decline = first_decline.get(account_id)
        if not decline:
            continue
        lead = (date.fromisoformat(stress_date) - date.fromisoformat(decline)).days
        if lead > 0:
            leads.append(lead)
            flagged.add(account_id)

    leads.sort()

    def median(values: list[int]) -> float | None:
        if not values:
            return None
        mid = len(values) // 2
        return float(values[mid]) if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    all_detections = connection.execute(
        "SELECT COUNT(*) AS n FROM signal_events WHERE code = 'inflow_decline'"
    ).fetchone()["n"]

    # A signal can only be raised where the feed exists. Measuring detection across
    # the whole book flatters nothing and understates the product, so the rate is
    # reported both ways: the book as a whole, and the accounts actually covered.
    monitored = {
        row["id"]
        for row in connection.execute(
            "SELECT id FROM accounts WHERE monitoring_consent = 'active'"
        ).fetchall()
    }
    monitored_denominator = [a for a in first_stress if a in monitored]
    monitored_flagged = [a for a in monitored_denominator if a in flagged]

    return {
        "window_months": window_months,
        "accounts_reaching_31dpd": len(first_stress),
        "accounts_flagged_in_advance": len(flagged),
        "detection_rate_pct": (
            round(len(flagged) / len(first_stress) * 100, 1) if first_stress else None
        ),
        "monitored_accounts_reaching_31dpd": len(monitored_denominator),
        "monitored_accounts_flagged": len(monitored_flagged),
        "detection_rate_monitored_pct": (
            round(len(monitored_flagged) / len(monitored_denominator) * 100, 1)
            if monitored_denominator
            else None
        ),
        "median_days": median(leads),
        "p25_days": leads[len(leads) // 4] if leads else None,
        "p75_days": leads[(len(leads) * 3) // 4] if leads else None,
        "max_days": leads[-1] if leads else None,
        "min_days": leads[0] if leads else None,
        "declines_detected_total": all_detections,
        "method": (
            "First inflow decline dated at least a day before the account first reached "
            "31 days past due, across accounts that did so within the last "
            f"{window_months} months."
        ),
    }


def _shift_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(value.day, 28)
    return date(year, month, day)


def par_trend(connection: sqlite3.Connection, months: int = 18) -> list[dict]:
    rows = connection.execute(
        "SELECT h.month_end, "
        "COUNT(*) AS accounts, "
        "SUM(h.outstanding) AS book, "
        "SUM(CASE WHEN h.band >= 1 THEN h.outstanding ELSE 0 END) AS par30, "
        "SUM(CASE WHEN h.band >= 2 THEN h.outstanding ELSE 0 END) AS par60, "
        "SUM(CASE WHEN h.band >= 3 THEN h.outstanding ELSE 0 END) AS par90, "
        "SUM(h.arrears) AS arrears "
        "FROM band_history h JOIN accounts a ON a.id = h.account_id "
        "WHERE a.status IN ('active','written_off') "
        "GROUP BY h.month_end ORDER BY h.month_end DESC LIMIT ?",
        (months,),
    ).fetchall()
    series = []
    for row in rows:
        book = max(1, row["book"] or 0)
        series.append(
            {
                "month": row["month_end"][:7],
                "month_end": row["month_end"],
                "accounts": row["accounts"],
                "book": row["book"],
                "par30_pct": round((row["par30"] or 0) / book * 100, 1),
                "par60_pct": round((row["par60"] or 0) / book * 100, 1),
                "par90_pct": round((row["par90"] or 0) / book * 100, 1),
                "arrears": row["arrears"] or 0,
            }
        )
    return list(reversed(series))


def migration_matrix(connection: sqlite3.Connection, since: str = "2026-01-01") -> dict:
    """Month-over-month band migration, with write-off/close as a real exit state."""
    pairs = connection.execute(
        "SELECT a.account_id, a.month_end, a.band AS from_band, "
        "       (SELECT b.band FROM band_history b WHERE b.account_id = a.account_id "
        "        AND b.month_end > a.month_end ORDER BY b.month_end LIMIT 1) AS to_band, "
        "       (SELECT b.month_end FROM band_history b WHERE b.account_id = a.account_id "
        "        AND b.month_end > a.month_end ORDER BY b.month_end LIMIT 1) AS next_month "
        "FROM band_history a WHERE a.month_end >= ?",
        (since,),
    ).fetchall()

    size = len(config.BANDS)
    counts = [[0] * (size + 1) for _ in range(size)]
    month_counts: dict[str, list[list[int]]] = {}

    for row in pairs:
        from_band = row["from_band"]
        if row["to_band"] is None or row["next_month"] != _next_month_end(row["month_end"]):
            to_band = size  # exited: written off or closed out of the book
        else:
            to_band = row["to_band"]
        counts[from_band][to_band] += 1
        bucket = month_counts.setdefault(row["month_end"][:7], [[0] * (size + 1) for _ in range(size)])
        bucket[from_band][to_band] += 1

    def as_rows(matrix: list[list[int]]) -> list[dict]:
        out = []
        for index in range(size):
            total = sum(matrix[index])
            out.append(
                {
                    "from_band": index,
                    "from_label": config.BANDS[index]["label"],
                    "total": total,
                    "transitions": [
                        {
                            "to_band": target,
                            "to_label": (
                                config.BANDS[target]["label"]
                                if target < size
                                else "Written off / closed"
                            ),
                            "count": matrix[index][target],
                            "pct": round(matrix[index][target] / total * 100, 1) if total else 0.0,
                        }
                        for target in range(size + 1)
                    ],
                }
            )
        return out

    return {"since": since, "matrix": as_rows(counts), "by_month": month_counts}


def _next_month_end(month_end: str) -> str:
    current = date.fromisoformat(month_end)
    if current.month == 12:
        nxt = date(current.year + 1, 1, 1)
    else:
        nxt = date(current.year, current.month + 1, 1)
    if nxt.month == 12:
        end = date(nxt.year, 12, 31)
    else:
        end = date(nxt.year, nxt.month + 1, 1) - timedelta(days=1)
    return min(end, AS_OF).isoformat()


def vintage_curves(connection: sqlite3.Connection, min_cohort: str = "2024-06") -> dict:
    """Cumulative share of each disbursement cohort that reached 31+ days past due.

    The denominator is the cohort's own size, fixed at disbursement, and the running
    maximum is taken per cohort. A cumulative default rate that fell would mean the
    denominator moved rather than that the book improved.
    """
    sizes = {
        row["cohort_month"]: row["n"]
        for row in connection.execute(
            "SELECT cohort_month, COUNT(*) AS n FROM accounts WHERE cohort_month >= ? "
            "GROUP BY cohort_month",
            (min_cohort,),
        ).fetchall()
    }

    rows = connection.execute(
        "WITH points AS ("
        "  SELECT a.cohort_month AS cohort, "
        "  CAST((julianday(h.month_end) - julianday(a.disbursed_date)) / 30.44 AS INTEGER) AS mob, "
        "  COUNT(DISTINCT h.account_id) AS observed, "
        "  COUNT(DISTINCT CASE WHEN h.band >= 2 THEN h.account_id END) AS stressed "
        "  FROM band_history h JOIN accounts a ON a.id = h.account_id "
        "  WHERE a.cohort_month >= ? "
        "  GROUP BY cohort, mob HAVING mob BETWEEN 0 AND 20) "
        "SELECT cohort, mob, observed, stressed, "
        "       MAX(stressed) OVER (PARTITION BY cohort ORDER BY mob) AS cumulative "
        "FROM points ORDER BY cohort, mob",
        (min_cohort,),
    ).fetchall()

    cohorts: dict[str, list[dict]] = {}
    for row in rows:
        size = max(1, sizes.get(row["cohort"], 1))
        cohorts.setdefault(row["cohort"], []).append(
            {
                "months_on_book": row["mob"],
                "cohort_size": size,
                "observed": row["observed"],
                "stressed": row["cumulative"],
                "cumulative_pct": round(row["cumulative"] / size * 100, 1),
            }
        )
    return {"cohorts": cohorts}


def recovery_performance(connection: sqlite3.Connection) -> dict:
    by_playbook = connection.execute(
        "SELECT COALESCE(playbook_code, 'UNASSIGNED') AS code, COUNT(*) AS attempts, "
        "SUM(cost) AS cost, "
        "SUM(CASE WHEN effect = 'promise_kept' THEN 1 ELSE 0 END) AS kept, "
        "SUM(CASE WHEN effect = 'promise_broken' THEN 1 ELSE 0 END) AS broken, "
        "SUM(CASE WHEN effect = 'restructured' THEN 1 ELSE 0 END) AS restructured "
        "FROM actions GROUP BY code ORDER BY attempts DESC"
    ).fetchall()

    playbook_rows = []
    for row in by_playbook:
        resolved = (row["kept"] or 0) + (row["broken"] or 0)
        playbook_rows.append(
            {
                "code": row["code"],
                "name": config.PLAYBOOK_BY_CODE.get(row["code"], {}).get("name", row["code"]),
                "attempts": row["attempts"],
                "cost": row["cost"] or 0,
                "promises_kept": row["kept"] or 0,
                "promises_broken": row["broken"] or 0,
                "restructured": row["restructured"] or 0,
                "kept_rate": round((row["kept"] or 0) / resolved * 100, 1) if resolved else None,
                "cost_per_kept": (
                    round((row["cost"] or 0) / row["kept"]) if row["kept"] else None
                ),
            }
        )

    by_channel = connection.execute(
        "SELECT channel, COUNT(*) AS attempts, SUM(cost) AS cost, "
        "SUM(CASE WHEN effect IN ('promise_kept','restructured') THEN 1 ELSE 0 END) AS wins "
        "FROM actions GROUP BY channel ORDER BY attempts DESC"
    ).fetchall()

    by_officer = connection.execute(
        "SELECT officer, COUNT(*) AS attempts, SUM(cost) AS cost, "
        "SUM(CASE WHEN effect IN ('promise_kept','restructured') THEN 1 ELSE 0 END) AS wins "
        "FROM actions GROUP BY officer ORDER BY wins DESC, attempts DESC"
    ).fetchall()

    return {
        "by_playbook": playbook_rows,
        "by_channel": [
            {
                "channel": row["channel"],
                "attempts": row["attempts"],
                "cost": row["cost"] or 0,
                "wins": row["wins"] or 0,
                "win_rate": round((row["wins"] or 0) / row["attempts"] * 100, 1),
                "cost_per_win": round((row["cost"] or 0) / row["wins"]) if row["wins"] else None,
            }
            for row in by_channel
        ],
        "by_officer": [
            {
                "officer": row["officer"],
                "attempts": row["attempts"],
                "cost": row["cost"] or 0,
                "wins": row["wins"] or 0,
                "win_rate": round((row["wins"] or 0) / row["attempts"] * 100, 1),
            }
            for row in by_officer
        ],
    }


def roi_ledger(connection: sqlite3.Connection) -> dict:
    """What was collected, what it cost, and what the holdout slice actually shows.

    Gross collections flatter any collections system, because most of that cash
    would have arrived without a phone call. The defensible estimate of the
    intervention's own effect is the comparison between accounts that were worked
    and the holdout slice that was deliberately not contacted. Both are reported
    here, and the distinction is stated rather than buried in a footnote.
    """
    d90 = (AS_OF - timedelta(days=90)).isoformat()

    gross = connection.execute(
        "SELECT COALESCE(SUM(p.amount), 0) AS total FROM payments p "
        "JOIN accounts a ON a.id = p.account_id "
        "WHERE p.paid_date >= ? AND (a.dpd > 0 OR a.status = 'written_off')",
        (d90,),
    ).fetchone()["total"]

    spend = connection.execute(
        "SELECT COALESCE(SUM(cost), 0) AS total, COUNT(*) AS attempts FROM actions "
        "WHERE occurred_at >= ?",
        (d90,),
    ).fetchone()

    resolved = connection.execute(
        "SELECT SUM(CASE WHEN status = 'kept' THEN 1 ELSE 0 END) AS kept, "
        "SUM(CASE WHEN status IN ('kept','broken') THEN 1 ELSE 0 END) AS resolved, "
        "COALESCE(SUM(CASE WHEN status = 'kept' THEN amount ELSE 0 END), 0) AS kept_value "
        "FROM promises"
    ).fetchone()

    # Holdout slice: accounts already delinquent three months ago, compared on what
    # happened to them since. Uses the last reporting point at or before the window
    # start, because snapshots are month ends rather than arbitrary dates.
    snapshot = connection.execute(
        "SELECT MAX(month_end) AS month_end FROM band_history WHERE month_end <= ?", (d90,)
    ).fetchone()["month_end"]

    comparison: dict[str, dict] = {}
    incremental = None
    sample_note = None
    if snapshot:
        for row in connection.execute(
            "SELECT a.control_group, COUNT(*) AS accounts, "
            "SUM(CASE WHEN a.band = 0 THEN 1 ELSE 0 END) AS cured, "
            "SUM(CASE WHEN a.band >= 4 THEN 1 ELSE 0 END) AS deteriorated, "
            "AVG(a.dpd) AS avg_dpd, SUM(a.arrears_amount) AS arrears "
            "FROM band_history h JOIN accounts a ON a.id = h.account_id "
            "WHERE h.month_end = ? AND h.band >= 1 AND a.status IN ('active','written_off') "
            "GROUP BY a.control_group",
            (snapshot,),
        ).fetchall():
            key = "control" if row["control_group"] else "worked"
            comparison[key] = {
                "accounts": row["accounts"],
                "cured": row["cured"] or 0,
                "cure_rate": round((row["cured"] or 0) / max(1, row["accounts"]) * 100, 1),
                "deteriorated": row["deteriorated"] or 0,
                "avg_dpd": round(row["avg_dpd"] or 0, 1),
                "arrears": round(row["arrears"] or 0),
            }

        worked = comparison.get("worked")
        control = comparison.get("control")
        if worked and control:
            if worked["accounts"] >= 15 and control["accounts"] >= 15:
                average_arrears = worked["arrears"] / max(1, worked["accounts"])
                incremental = round(
                    max(0.0, worked["cure_rate"] - control["cure_rate"]) / 100 * worked["accounts"]
                    * average_arrears
                )
            else:
                sample_note = (
                    f"Holdout slice is too small to measure ({control['accounts']} accounts "
                    "left unworked at the snapshot). No incremental estimate is claimed."
                )
            if worked and control:
                gap = abs(worked["avg_dpd"] - control["avg_dpd"])
                if gap > 45:
                    sample_note = (
                        (sample_note + " " if sample_note else "")
                        + f"The two groups are not balanced on severity (average "
                        f"{worked['avg_dpd']:.0f} vs {control['avg_dpd']:.0f} days past due), "
                        "so treat the difference as indicative rather than causal."
                    )
        elif control:
            sample_note = "No worked group at this snapshot to compare against."

    written_off = connection.execute(
        "SELECT COUNT(*) AS accounts, COALESCE(SUM(recovery_to_date), 0) AS recovered "
        "FROM accounts WHERE status = 'written_off'"
    ).fetchone()

    recovered_after_writeoff = connection.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM recovery_events"
    ).fetchone()["total"]

    return {
        "window_days": 90,
        "snapshot_month": snapshot,
        "collected_on_delinquent_accounts": round(gross),
        "cost": round(spend["total"]),
        "attempts": spend["attempts"],
        "cost_per_attempt": round(spend["total"] / spend["attempts"]) if spend["attempts"] else None,
        "cost_per_naira_collected": (round(spend["total"] / gross, 4) if gross else None),
        "promise_kept": {
            "kept": resolved["kept"] or 0,
            "resolved": resolved["resolved"] or 0,
            "kept_rate": round((resolved["kept"] or 0) / max(1, resolved["resolved"]) * 100, 1),
            "value": round(resolved["kept_value"] or 0),
        },
        "holdout": comparison,
        "incremental_recovery_estimate": incremental,
        "sample_note": sample_note,
        "written_off": {
            "accounts": written_off["accounts"],
            "recovered": round(written_off["recovered"]),
            "recovery_events": round(recovered_after_writeoff),
        },
        "interpretation": (
            "Gross collections include payments that would have been made without "
            "contact. Only the difference between the worked group and the holdout "
            "slice isolates the effect of intervention, and that difference is what "
            "the incremental estimate is based on."
        ),
    }


def worklist(
    connection: sqlite3.Connection,
    budget: int | None = None,
    officer: str | None = None,
    band: int | None = None,
    product: str | None = None,
    search: str | None = None,
    only_actionable: bool = True,
) -> dict:
    book = build_book(connection)
    rows = [row for row in book if row["status"] == "active"]

    if officer:
        rows = [row for row in rows if row["officer"] == officer]
    if band is not None:
        rows = [row for row in rows if row["band"] == band]
    if product:
        rows = [row for row in rows if row["product_code"] == product]
    if search:
        needle = search.lower()
        rows = [
            row
            for row in rows
            if needle in row["borrower_name"].lower()
            or needle in row["ref"].lower()
            or needle in row["city"].lower()
        ]

    ranking = priority.apply_review_budget(rows, budget)

    if only_actionable:
        rows = [
            row
            for row in rows
            if row["dpd"] > 0 or row["risk"]["index"] >= 20 or row["actionable_signals"]
        ]

    ranked = sorted(
        rows,
        key=lambda row: (row["priority_value"]["expected_recovery"], row["exposure"]),
        reverse=True,
    )
    baseline_ranked = sorted(
        rows, key=lambda row: (row["dpd"], row["exposure"]), reverse=True
    )
    selected = ranked[:budget] if budget else ranked

    return {
        "ranking": ranking,
        "rows": [summarise_row(row) for row in selected],
        "baseline_rows": [summarise_row(row) for row in baseline_ranked[: len(selected)]],
        "returned": len(selected),
        "eligible": len(rows),
    }


def summarise_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "ref": row["ref"],
        "borrower_name": row["borrower_name"],
        "sector": row["sector"],
        "city": row["city"],
        "state": row["state"],
        "product_code": row["product_code"],
        "product_name": row["product_name"],
        "officer": row["officer"],
        "status": row["status"],
        "dpd": row["dpd"],
        "band": row["band"],
        "band_label": config.BANDS[row["band"]]["label"],
        "instalment": row["instalment"],
        "arrears_amount": row["arrears_amount"],
        "outstanding_principal": row["outstanding_principal"],
        "exposure": row["exposure"],
        "risk_index": row["risk"]["index"],
        "risk_band": row["risk"]["band_label"],
        "risk_band_code": row["risk"]["band_code"],
        "top_reason": row["risk"]["reasons"][0]["label"] if row["risk"]["reasons"] else None,
        "reasons": row["risk"]["reasons"][:3],
        "playbook_code": row["playbook"]["primary"]["code"],
        "playbook_name": row["playbook"]["primary"]["name"],
        "priority": row["priority_value"]["priority"],
        "expected_recovery": row["priority_value"]["expected_recovery"],
        "loss_at_risk": row["priority_value"]["loss_at_risk"],
        "value_per_attempt": row["priority_value"]["value_per_attempt"],
        "monitoring_consent": row["monitoring_consent"],
        "monitoring_tier": row["monitoring_tier"],
        "control_group": bool(row["control_group"]),
        "open_promises": row["open_promises"],
        "broken_promises": row["broken_promises"],
        "next_promised_date": row["next_promised_date"],
        "next_due_date": row["next_due_date"],
        "action_count": row["action_count"],
        "signal_count": len(row["signals"]),
        "cashflow_change_pct": (row["cashflow"] or {}).get("change_pct"),
    }


def alert_feed(connection: sqlite3.Connection, limit: int = 60) -> list[dict]:
    """Signals worth a person's attention now, newest and most severe first."""
    rows = connection.execute(
        "SELECT s.*, a.ref, a.dpd, a.band, a.outstanding_principal, a.monitoring_consent, "
        "b.name AS borrower_name, b.sector "
        "FROM signal_events s JOIN accounts a ON a.id = s.account_id "
        "JOIN borrowers b ON b.id = a.borrower_id "
        "WHERE a.status IN ('active','written_off') "
        "ORDER BY s.severity DESC, s.detected_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "account_id": row["account_id"],
            "ref": row["ref"],
            "borrower_name": row["borrower_name"],
            "sector": row["sector"],
            "code": row["code"],
            "label": row["label"],
            "severity": row["severity"],
            "headline": row["headline"],
            "detected_at": row["detected_at"],
            "evidence": json.loads(row["evidence"] or "{}"),
            "lead_days": row["lead_days"],
            "actionable": bool(row["actionable"]),
            "dpd": row["dpd"],
            "band": row["band"],
            "band_label": config.BANDS[row["band"]]["label"],
            "outstanding_principal": row["outstanding_principal"],
            "monitoring_consent": row["monitoring_consent"],
        }
        for row in rows
    ]

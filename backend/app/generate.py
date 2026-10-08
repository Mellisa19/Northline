"""Reproducible synthetic loan book.

The demo portfolio is simulated, not scraped and not real. That is stated openly in
the product. What matters is that it is *internally coherent*: repayment behaviour,
cash-flow deterioration, collection actions and recovery outcomes are all driven by
one latent stress process, so every figure the analytics compute is a genuine
consequence of the data rather than a hard-coded number.

Two design decisions worth knowing about:

1.  Cash flow observes stress ``CASHFLOW_LEAD`` months before repayment does. That
    creates a real, measurable advance-warning window instead of an asserted one.
2.  Collection actions are generated *inside* the repayment loop and apply a
    log-odds uplift to the following month's payment probability. Recovery uplift
    is therefore an emergent property of the simulation, and the control group
    (no proactive contact) genuinely performs worse.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import date, timedelta

from . import config
from .db import set_meta

AS_OF = config.AS_OF
SEED = config.SEED

GLOBAL_MONTHS = 42
_first_of_month = date(AS_OF.year, AS_OF.month, 1)
_total_months = _first_of_month.year * 12 + (_first_of_month.month - 1) - (GLOBAL_MONTHS - 1)
_gs_year, _gs_month = divmod(_total_months, 12)
GLOBAL_START = date(_gs_year, _gs_month + 1, 1)

CASHFLOW_LEAD = 4          # months by which cash flow leads repayment stress
CASHFLOW_MONTHS = 18       # history retained per borrower
ACTIVE_ACCOUNTS = 720
CLOSED_ACCOUNTS = 380
CONTROL_GROUP_SHARE = 0.22

# Stress below this level is ordinary trading noise and does not move takings.
# Above it, every unit of stress removes a share of the month's inflows.
NORMAL_STRESS = 0.30
STRESS_DECLINE_SLOPE = 0.62
MIN_INFLOW_MULT = 0.28
DECLINE_THRESHOLD = -0.20   # three-month fall in takings that counts as a signal

# Log-odds uplift applied to the month following a collection action.
CHANNEL_UPLIFT = {
    "call": 0.36,
    "whatsapp": 0.41,
    "sms": 0.18,
    "email": 0.06,
    "field_visit": 0.56,
    "payment_link": 0.31,
    "legal_notice": 0.05,
}

# Signals the lender can raise from its own loan records, with or without a
# monitoring consent on the borrower's account.
LENDER_RECORD_SIGNALS = frozenset(
    {"broken_promise", "partial_payment_pattern", "first_payment_default", "written_off"}
)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _add_months_safe(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(d.day, _days_in_month(year, month)))


def add_months(d: date, n: int) -> date:
    return _add_months_safe(d, n)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def month_index(d: date) -> int:
    return months_between(GLOBAL_START, date(d.year, d.month, 1))


def iso(d: date) -> str:
    return d.isoformat()


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def inflow_multiplier(stress: float) -> float:
    """Share of normal takings the business still receives at this stress level."""
    excess = max(0.0, stress - NORMAL_STRESS)
    return max(MIN_INFLOW_MULT, 1.0 - STRESS_DECLINE_SLOPE * excess)


def weighted_choice(rng: random.Random, options: list[tuple], index: int = -1):
    weights = [option[index] for option in options]
    return rng.choices(options, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
def build_stress_paths(rng: random.Random) -> dict[str, list[float]]:
    """Correlated monthly sector shocks plus a shared market factor."""
    market: list[float] = []
    value = 0.0
    for _ in range(GLOBAL_MONTHS):
        value = 0.80 * value + rng.gauss(0.0, 0.26)
        market.append(value)

    paths: dict[str, list[float]] = {}
    for sector, _weight in config.SECTORS:
        sensitivity = config.SECTOR_CYCLE_SENSITIVITY[sector]
        own = 0.0
        series: list[float] = []
        for m in range(GLOBAL_MONTHS):
            own = 0.74 * own + rng.gauss(0.0, 0.22)
            combined = 0.62 * market[m] + 0.72 * own
            series.append(max(0.0, combined * sensitivity))
        paths[sector] = series
    return paths


def build_borrowers(
    rng: random.Random, count: int, used_names: set[str], start_id: int = 1
) -> list[dict]:
    borrowers: list[dict] = []

    for index in range(count):
        sector, _ = weighted_choice(rng, config.SECTORS, 1)
        state, city, _ = weighted_choice(rng, config.LOCATIONS, 2)

        for _attempt in range(40):
            surname = rng.choice(config.SURNAMES)
            trade = rng.choice(config.TRADE_WORDS)
            suffix, _ = weighted_choice(rng, config.SUFFIXES, 1)
            name = f"{surname} {trade} {suffix}"
            if name not in used_names:
                used_names.add(name)
                break
        else:
            name = f"{surname} {trade} {suffix} {index}"

        contact_first = rng.choice(
            ["Ada", "Bola", "Chidi", "Damilola", "Emeka", "Fatima", "Grace",
             "Hauwa", "Ifeanyi", "Jide", "Kemi", "Lami", "Musa", "Ngozi",
             "Obinna", "Segun", "Tolu", "Uche", "Yemi", "Zara"]
        )
        contact_last = name.split()[0]
        slug = name.split()[0].lower()

        onboarded = AS_OF - timedelta(days=rng.randint(400, 2600))
        years_trading = max(2, round((AS_OF - onboarded).days / 365) + rng.randint(0, 6))

        borrowers.append(
            {
                "id": start_id + index,
                "name": name,
                "sector": sector,
                "city": city,
                "state": state,
                "cac_number": f"RC{rng.randint(100000, 1899999)}",
                "contact_name": f"{contact_first} {contact_last}",
                "contact_phone": f"+234 8{rng.randint(0, 1)} {rng.randint(200, 999)} "
                                 f"{rng.randint(1000, 9999)}",
                "contact_email": f"accounts@{slug}-{rng.randint(10, 99)}.ng",
                "relationship_manager": rng.choice(config.RELATIONSHIP_MANAGERS),
                "onboarded_date": iso(onboarded),
                "years_trading": years_trading,
                "employees": max(3, int(rng.lognormvariate(2.6, 0.9))),
                "monthly_inflow_base": 0,
                "quality": min(0.97, max(0.05, rng.betavariate(5.0, 2.2))),
                "idiosyncratic": [0.0] * GLOBAL_MONTHS,
                "episode_start": None,
                "episode_peak": 0.0,
            }
        )

    # Idiosyncratic stress path per borrower, plus a deterioration episode for
    # roughly a quarter of them — this is the "silent decline" population.
    for borrower in borrowers:
        value = 0.0
        series: list[float] = []
        for _ in range(GLOBAL_MONTHS):
            value = 0.72 * value + rng.gauss(0.0, 0.18)
            series.append(value)
        borrower["idiosyncratic"] = series

        if rng.random() < 0.27:
            start = rng.randint(12, GLOBAL_MONTHS - 3)
            borrower["episode_start"] = start
            borrower["episode_peak"] = rng.uniform(0.55, 1.45)

    return borrowers


def stress_at(borrower: dict, sector_paths: dict[str, list[float]], index: int) -> float:
    index = max(0, min(GLOBAL_MONTHS - 1, index))
    total = sector_paths[borrower["sector"]][index] + borrower["idiosyncratic"][index]
    start = borrower["episode_start"]
    if start is not None and index >= start:
        elapsed = index - start
        # Ramp up over three months, then decay slowly.
        ramp = min(1.0, elapsed / 3.0)
        decay = math.exp(-max(0, elapsed - 3) * 0.055)
        total += borrower["episode_peak"] * ramp * decay
    return max(0.0, total)


# ---------------------------------------------------------------------------
# Account construction
# ---------------------------------------------------------------------------
def build_account_terms(rng: random.Random, borrower: dict, slot: int) -> dict:
    product = weighted_choice(rng, [(p, p["weight"]) for p in config.PRODUCTS], 1)[0]
    if slot == 1:
        # Second facilities skew smaller and shorter.
        product = weighted_choice(
            rng, [(p, p["weight"]) for p in config.PRODUCTS if p["code"] in ("MCA", "WC", "PAY")], 1
        )[0]

    tenor = rng.randint(product["tenor"][0], product["tenor"][1])
    low, high = product["ticket"]
    principal = int(round(rng.triangular(low, high, low + (high - low) * 0.28), -4))
    monthly_rate = rng.uniform(*product["monthly_rate"])

    total_due = principal * (1 + monthly_rate * tenor)
    instalment = int(round(total_due / tenor, -2))
    disbursed = add_months(AS_OF, -rng.randint(1, 34))
    disbursed = date(disbursed.year, disbursed.month, rng.randint(1, 28))
    first_due = add_months(disbursed, 1)

    collateral = {
        "WC": "Stock and receivables debenture",
        "AF": "Asset financed, registered interest",
        "ID": "Assigned invoices with recourse",
        "MCA": "POS terminal flow assignment",
        "PAY": "Irrevocable payroll deduction mandate",
    }[product["code"]]

    return {
        "product_code": product["code"],
        "product_name": product["name"],
        "principal": principal,
        "monthly_rate": monthly_rate,
        "tenor_months": tenor,
        "instalment": instalment,
        "disbursed_date": disbursed,
        "first_due_date": first_due,
        "maturity_date": add_months(first_due, tenor - 1),
        "collateral": collateral,
    }


def simulate_account(
    rng: random.Random,
    borrower: dict,
    terms: dict,
    sector_paths: dict[str, list[float]],
    account_id: int,
    account_ref: str,
    force_closed: bool,
) -> dict:
    """Run one account's repayment history and produce its full record."""
    tenor = terms["tenor_months"]
    instalment = terms["instalment"]
    principal_component = terms["principal"] / tenor

    quality = borrower["quality"]
    if force_closed:
        quality = min(0.98, quality + 0.22)

    due_dates = [add_months(terms["first_due_date"], i) for i in range(tenor)]

    # Target debt-service ratio drives how exposed this borrower is month to month,
    # and headroom sets how much of a fall in takings the business can absorb.
    target_dsr = rng.uniform(0.17, 0.41)
    headroom = rng.uniform(0.15, 0.75)
    inflow_base = max(instalment / target_dsr, instalment * 1.4)
    borrower["monthly_inflow_base"] = int(round(inflow_base, -4))

    is_control = (not force_closed) and rng.random() < CONTROL_GROUP_SHARE

    installments: list[dict] = []
    payments: list[dict] = []
    actions: list[dict] = []
    promises: list[dict] = []
    promise_payments: list[float] = []
    arrears = 0.0
    pending_uplift = 0.0
    uplift_source: str | None = None
    first_missed_due: date | None = None
    action_id = 0
    promise_id = 0

    for seq, due in enumerate(due_dates, start=1):
        row = {
            "seq": seq,
            "due_date": due,
            "amount_due": instalment,
            "amount_paid": 0.0,
            "paid_date": None,
            "status": "unpaid",
        }
        installments.append(row)
        if due > AS_OF:
            continue

        index = month_index(due)
        pay_stress = stress_at(borrower, sector_paths, index)
        # Cash flow leads repayment stress, which is what creates a warning window.
        cf_stress = stress_at(borrower, sector_paths, index + CASHFLOW_LEAD)
        mult = inflow_multiplier(cf_stress)

        # Ability: in ordinary trading the business releases about (1 + headroom)
        # times the instalment. A fall in takings consumes that headroom first, so
        # capacity drops below the instalment and arrears appear — which is exactly
        # the mechanism the monitoring product exists to see early.
        capacity = instalment * (1.0 + headroom) * mult * rng.uniform(0.88, 1.12)

        # Willingness: whether the capacity that exists is actually released to us.
        season = 0.16 * math.sin(2 * math.pi * ((due.month + 1) / 12.0)) - 0.12 * (
            1 if due.month == 1 else 0
        )
        arrears_pressure = min(2.2, arrears / max(1.0, instalment))
        logit = (
            1.75
            + 2.05 * quality
            - 0.92 * pay_stress
            - 1.60 * max(0.0, target_dsr - 0.32)
            + season
            - 0.52 * arrears_pressure
            - (0.28 if seq == 1 else 0.0)
            + pending_uplift
        )
        pending_uplift = 0.0
        uplift_source = None

        owed = instalment + arrears

        # A business whose takings have recovered clears the backlog in one go.
        if arrears > instalment * 0.2 and mult > 0.92 and rng.random() < 0.34:
            capacity = max(capacity, min(owed, instalment * rng.uniform(1.9, 3.1)))

        # A deeply delinquent account can still be restructured rather than lost:
        # the arrears are capitalised and the facility returns to performing.
        restructured = arrears > instalment * 3.0 and rng.random() < 0.045
        if restructured:
            capacity = owed

        willing = rng.random() < sigmoid(logit)
        paid_amount = capacity if willing else capacity * rng.uniform(0.25, 0.85)
        paid_amount = max(0.0, min(owed, paid_amount))
        # Record what will actually be written to the payment ledger, so the
        # schedule and the cash history cannot drift apart by a few naira.
        paid_amount = float(int(round(paid_amount, -2)))
        on_schedule = (
            arrears <= config.SETTLEMENT_TOLERANCE
            and paid_amount >= instalment - config.SETTLEMENT_TOLERANCE
        )

        if paid_amount > 0:
            paid_date = due + timedelta(days=0 if on_schedule else rng.randint(1, 26))
            if paid_date > AS_OF:
                paid_date = AS_OF
            payments.append(
                {
                    "paid_date": paid_date,
                    "amount": int(round(paid_amount, -2)),
                    "channel": rng.choices(
                        ["direct_debit", "bank_transfer", "pos_settlement", "cash_agent", "cheque"],
                        weights=[0.34, 0.31, 0.16, 0.15, 0.04],
                        k=1,
                    )[0],
                    "source": "borrower",
                }
            )

            # Payments settle the oldest outstanding instalment first, so clearing
            # a backlog genuinely restores the account to current.
            remaining = paid_amount
            for target in installments:
                if remaining <= config.SETTLEMENT_TOLERANCE or target["due_date"] > AS_OF:
                    break
                gap = target["amount_due"] - target["amount_paid"]
                if gap <= config.SETTLEMENT_TOLERANCE:
                    continue
                applied = min(gap, remaining)
                target["amount_paid"] += applied
                remaining -= applied
                if target["amount_paid"] >= target["amount_due"] - config.SETTLEMENT_TOLERANCE:
                    target["status"] = "paid"
                    target["paid_date"] = due
                else:
                    target["status"] = "partial"

        arrears = sum(
            r["amount_due"] - r["amount_paid"] for r in installments if r["due_date"] <= AS_OF
        )
        open_rows = [
            r for r in installments
            if r["due_date"] <= AS_OF
            and r["amount_paid"] < r["amount_due"] - config.SETTLEMENT_TOLERANCE
        ]
        if open_rows:
            first_missed_due = min(r["due_date"] for r in open_rows)

        # ---- collections activity for the following month -------------------
        if restructured and not is_control and len(actions) < 9:
            action_id += 1
            actions.append(
                {
                    "id": action_id,
                    "occurred_at": due,
                    "channel": "call",
                    "disposition": "restructure_requested",
                    "officer": rng.choice(config.COLLECTIONS_OFFICERS),
                    "playbook_code": "RESTRUCTURE",
                    "notes": "Arrears capitalised and tenor extended",
                    "cost": config.attempt_cost("call"),
                    "effect": "restructured",
                    "promise_id": None,
                }
            )

        if arrears > 0 and not is_control:
            band = config.band_for_dpd(max(0, (AS_OF - (first_missed_due or due)).days))
            if band == 0:
                band = 1
            probability = {1: 0.42, 2: 0.55, 3: 0.60, 4: 0.48}[band]
            if len(actions) < 9 and rng.random() < probability:
                action_id += 1
                channel = rng.choices(
                    ["call", "whatsapp", "sms", "payment_link", "field_visit", "email"],
                    weights=[0.34, 0.26, 0.16, 0.11, 0.07 if band >= 3 else 0.03, 0.06],
                    k=1,
                )[0]
                makes_promise = False
                occurred = due + timedelta(days=rng.randint(2, 24))
                if occurred > AS_OF:
                    occurred = AS_OF - timedelta(days=rng.randint(0, 6))

                makes_promise = channel in ("call", "whatsapp", "field_visit") and rng.random() < 0.44
                if makes_promise:
                    promise_id += 1
                    # A promise taken on the contact falls due in the weeks after it.
                    promised_date = min(
                        occurred + timedelta(days=rng.randint(5, 30)),
                        AS_OF + timedelta(days=rng.randint(6, 34)),
                    )
                    promises.append(
                        {
                            "id": promise_id,
                            "made_at": occurred,
                            "promised_date": promised_date,
                            "amount": int(round(min(arrears, instalment * rng.uniform(0.6, 2.2)), -2)),
                            "status": "open",
                            "resolved_at": None,
                            "action_id": action_id,
                        }
                    )
                    disposition = "promise_to_pay"
                else:
                    disposition = rng.choices(
                        ["no_answer", "partial_payment", "requested_extension",
                         "not_reachable", "refused_to_pay", "disputed_amount",
                         "restructure_requested"],
                        weights=[0.30, 0.06, 0.16, 0.18, 0.12, 0.08, 0.10],
                        k=1,
                    )[0]

                actions.append(
                    {
                        "id": action_id,
                        "occurred_at": occurred,
                        "channel": channel,
                        "disposition": disposition,
                        "officer": rng.choice(config.COLLECTIONS_OFFICERS),
                        "playbook_code": _playbook_for(band, disposition, channel),
                        "notes": "",
                        "cost": config.attempt_cost(channel),
                        "effect": "promise" if makes_promise else "no_effect",
                        "promise_id": promise_id if makes_promise else None,
                    }
                )
                pending_uplift = CHANNEL_UPLIFT[channel] * rng.uniform(0.7, 1.25)
                uplift_source = channel

    # ---- resolve promises -------------------------------------------------
    for promise in promises:
        if promise["promised_date"] > AS_OF:
            promise["status"] = "open"
            continue
        # A promise is kept when the borrower has capacity at the promised time.
        index = month_index(promise["promised_date"])
        chance = sigmoid(-0.10 + 2.0 * quality - 1.35 * stress_at(borrower, sector_paths, index))
        kept = rng.random() < chance
        promise["status"] = "kept" if kept else "broken"
        promise["resolved_at"] = promise["promised_date"] + timedelta(days=rng.randint(0, 4))
        if kept:
            payments.append(
                {
                    "paid_date": promise["promised_date"],
                    "amount": promise["amount"],
                    "channel": rng.choice(["bank_transfer", "direct_debit", "pos_settlement"]),
                    "source": "collections_promise",
                }
            )
            promise_payments.append(promise["amount"])
        for action in actions:
            if action["promise_id"] == promise["id"]:
                action["effect"] = "promise_kept" if kept else "promise_broken"

    # A kept promise is real cash. Allocate it to the oldest open instalments so the
    # account position genuinely reflects it.
    for amount in promise_payments:
        remaining = float(amount)
        for target in installments:
            if remaining <= config.SETTLEMENT_TOLERANCE or target["due_date"] > AS_OF:
                break
            gap = target["amount_due"] - target["amount_paid"]
            if gap <= config.SETTLEMENT_TOLERANCE:
                continue
            applied = min(gap, remaining)
            target["amount_paid"] += applied
            remaining -= applied
            if target["amount_paid"] >= target["amount_due"] - config.SETTLEMENT_TOLERANCE:
                target["status"] = "paid"
                if target["paid_date"] is None:
                    target["paid_date"] = AS_OF
            else:
                target["status"] = "partial"

    # ---- account position at AS_OF ---------------------------------------
    unpaid = [row for row in installments if row["status"] != "paid"]
    outstanding_principal = int(round(principal_component * len(unpaid), -2))

    past_due = [r for r in unpaid if r["due_date"] <= AS_OF]
    arrears_amount = int(round(sum(r["amount_due"] - r["amount_paid"] for r in past_due), -2))

    dpd = max(0, (AS_OF - min(r["due_date"] for r in past_due)).days) if past_due else 0
    band = config.band_for_dpd(dpd)

    # The book cannot carry hopeless balances for ever. Deep arrears exit to the
    # written-off stock, where recovery continues off-book.
    written_off = False
    written_off_date = None
    recovery_events: list[dict] = []
    if not force_closed and dpd > 180 and arrears_amount > 0:
        exit_chance = 0.35 if dpd <= 270 else (0.70 if dpd <= 360 else 0.95)
        if rng.random() < exit_chance:
            written_off = True
            written_off_date = AS_OF - timedelta(days=rng.randint(5, 240))
            recovered = int(round(arrears_amount * rng.uniform(0.04, 0.26), -3))
            if recovered > 0:
                recovery_events.append(
                    {
                        "occurred_at": written_off_date + timedelta(days=rng.randint(10, 120)),
                        "kind": rng.choice(["legal_recovery", "asset_sale", "settlement"]),
                        "amount": recovered,
                        "notes": "Part recovery after write-off",
                    }
                )

    if force_closed:
        status = "closed"
        outstanding_principal = 0
        arrears_amount = 0
        dpd = 0
        band = 0
    elif written_off:
        status = "written_off"
    else:
        status = "active"

    return {
        "installments": installments,
        "payments": payments,
        "actions": actions,
        "promises": promises,
        "recovery_events": recovery_events,
        "outstanding_principal": outstanding_principal,
        "arrears_amount": arrears_amount,
        "dpd": dpd,
        "band": band,
        "status": status,
        "control_group": 1 if is_control else 0,
        "written_off_date": written_off_date,
        "recovery_to_date": sum(event["amount"] for event in recovery_events),
        "instalments_paid": sum(1 for r in installments if r["status"] == "paid"),
        "instalments_due": sum(1 for r in installments if r["due_date"] <= AS_OF),
        "first_missed_due": first_missed_due,
    }


def build_band_history(
    installments: list[dict],
    payments: list[dict],
    terms: dict,
    written_off_date: date | None = None,
    months: int = 24,
) -> list[dict]:
    """Month-end delinquency snapshots, rebuilt from actual cash movements.

    Roll rates, migration matrices and PAR trends are all read from this history,
    so it is reconstructed from dated payments rather than assumed.
    """
    ordered = sorted(installments, key=lambda row: row["due_date"])
    dated = sorted(
        (p for p in payments if p["paid_date"] is not None), key=lambda p: p["paid_date"]
    )
    principal_component = terms["principal"] / terms["tenor_months"]
    tenor = terms["tenor_months"]
    anchor = date(AS_OF.year, AS_OF.month, 1)

    history: list[dict] = []
    for offset in range(months - 1, -1, -1):
        # The reporting point is never in the future: the current period is reported
        # as of today, not as of a month end that has not happened yet.
        moment = min(_month_end(month_key(add_months(anchor, -offset))), AS_OF)
        if moment < terms["disbursed_date"]:
            continue
        # A written-off balance leaves the delinquency matrix; it is tracked in the
        # recovery book instead.
        if written_off_date is not None and moment > written_off_date:
            continue

        cash = sum(p["amount"] for p in dated if p["paid_date"] <= moment)
        remaining = float(cash)
        arrears = 0.0
        settled = 0
        first_open: date | None = None
        for row in ordered:
            if row["due_date"] > moment:
                break
            gap = row["amount_due"]
            if remaining >= gap - config.SETTLEMENT_TOLERANCE:
                remaining = max(0.0, remaining - gap)
                settled += 1
            else:
                arrears += gap - remaining
                remaining = 0.0
                if first_open is None:
                    first_open = row["due_date"]

        dpd = max(0, (moment - first_open).days) if first_open else 0
        outstanding = int(round(principal_component * max(0, tenor - settled), -2))
        history.append(
            {
                "month_end": moment,
                "dpd": dpd,
                "band": config.band_for_dpd(dpd),
                "arrears": int(round(arrears, -2)),
                "outstanding": outstanding,
            }
        )
    return history


def _playbook_for(band: int, disposition: str, channel: str) -> str:
    if disposition == "restructure_requested":
        return "RESTRUCTURE"
    if channel == "field_visit":
        return "FIELD_VISIT"
    if band >= 4:
        return "LEGAL_REVIEW"
    if band == 3:
        return "FIELD_VISIT"
    if disposition == "promise_to_pay":
        return "PROMISE_CAPTURE"
    if band == 2:
        return "PART_PAYMENT"
    if channel == "payment_link":
        return "REMIND_LINK"
    return "CARE_CALL"


# ---------------------------------------------------------------------------
# Cash flow and signals
# ---------------------------------------------------------------------------
def build_cashflow(
    rng: random.Random, borrower: dict, account_id: int, sector_paths: dict[str, list[float]]
) -> list[dict]:
    base = borrower["monthly_inflow_base"] or 5_000_000
    rows: list[dict] = []
    for offset in range(CASHFLOW_MONTHS - 1, -1, -1):
        moment = add_months(date(AS_OF.year, AS_OF.month, 1), -offset)
        index = month_index(moment)
        cf_stress = stress_at(borrower, sector_paths, index + CASHFLOW_LEAD)
        seasonal = 1.0 + 0.13 * math.sin(2 * math.pi * ((moment.month + 2) / 12.0))
        decline = inflow_multiplier(cf_stress)
        noise = rng.uniform(0.86, 1.16)
        inflow = base * decline * seasonal * noise
        pos_share = rng.uniform(0.18, 0.52)
        pos_inflow = inflow * pos_share * rng.uniform(0.85, 1.15)
        transfer_inflow = inflow - pos_inflow
        outflow = inflow * rng.uniform(0.62, 0.94)
        closing = max(0.0, inflow - outflow + base * rng.uniform(0.05, 0.35))
        rows.append(
            {
                "borrower_id": borrower["id"],
                "account_id": account_id,
                "month": month_key(moment),
                "inflow": int(round(inflow, -2)),
                "outflow": int(round(outflow, -2)),
                "closing_balance": int(round(closing, -2)),
                "pos_inflow": int(round(pos_inflow, -2)),
                "transfer_inflow": int(round(transfer_inflow, -2)),
                "new_recurring_debits": 1 if rng.random() < 0.14 + 0.30 * cf_stress else 0,
            }
        )
    return rows


def derive_signals(
    rng: random.Random,
    cashflow: list[dict],
    account: dict,
    terms: dict,
) -> list[dict]:
    """Turn raw behaviour into the signals the worklist reasons over."""
    signals: list[dict] = []
    # ---- when did the change actually start? -----------------------------
    # Walk the series and date the first sustained break in takings. This is the
    # advance-warning event: dated when it happened, not when someone noticed.
    first_decline = None
    for cursor in range(6, len(cashflow) + 1):
        window = cashflow[cursor - 3:cursor]
        baseline = cashflow[cursor - 6:cursor - 3]
        recent_avg = sum(row["inflow"] for row in window) / 3.0
        prior_avg = sum(row["inflow"] for row in baseline) / 3.0
        if prior_avg <= 0:
            continue
        change = (recent_avg - prior_avg) / prior_avg
        if change <= DECLINE_THRESHOLD:
            first_decline = {
                "detected": _month_end(window[-1]["month"]),
                "recent": recent_avg,
                "prior": prior_avg,
                "change": change,
            }
            break

    if first_decline is not None:
        change = first_decline["change"]
        severity = 3 if change < -0.42 else 2 if change < -0.28 else 1
        signals.append(
            {
                "code": "inflow_decline",
                "label": "Cash inflows falling",
                "severity": severity,
                "detected_at": first_decline["detected"],
                "headline": (
                    f"Average monthly inflows fell {abs(change) * 100:.0f}% "
                    f"across a three-month window"
                ),
                "evidence": {
                    "recent_3m_avg": int(first_decline["recent"]),
                    "prior_3m_avg": int(first_decline["prior"]),
                    "change_pct": round(change * 100, 1),
                },
            }
        )

    if len(cashflow) >= 7:
        balances = [row["closing_balance"] for row in cashflow[-6:]]
        avg_balance = sum(balances[:-1]) / max(1, len(balances) - 1)
        if avg_balance > 0 and balances[-1] < avg_balance * 0.55:
            signals.append(
                {
                    "code": "balance_erosion",
                    "label": "Operating balance eroded",
                    "severity": 2 if balances[-1] < avg_balance * 0.3 else 1,
                    "detected_at": _month_end(cashflow[-1]["month"]),
                    "headline": "Closing balance is well below the six-month average",
                    "evidence": {
                        "latest_balance": balances[-1],
                        "six_month_average": int(avg_balance),
                    },
                }
            )

        pos_recent = sum(row["pos_inflow"] for row in cashflow[-3:]) / 3.0
        pos_prior = sum(row["pos_inflow"] for row in cashflow[-6:-3]) / 3.0
        if pos_prior > 0 and (pos_recent - pos_prior) / pos_prior < -0.30:
            signals.append(
                {
                    "code": "pos_activity_drop",
                    "label": "Card and POS takings down",
                    "severity": 2,
                    "detected_at": _month_end(cashflow[-1]["month"]),
                    "headline": "Settlement inflows are down sharply against the prior quarter",
                    "evidence": {
                        "recent_3m_avg": int(pos_recent),
                        "prior_3m_avg": int(pos_prior),
                    },
                }
            )

        added_debits = sum(row["new_recurring_debits"] for row in cashflow[-3:])
        if added_debits >= 2:
            signals.append(
                {
                    "code": "obligation_creep",
                    "label": "New recurring obligations",
                    "severity": 2 if added_debits >= 3 else 1,
                    "detected_at": _month_end(cashflow[-1]["month"]),
                    "headline": f"{added_debits} new recurring debits detected in three months",
                    "evidence": {"new_recurring_debits": added_debits},
                }
            )

    payments = account["payments"]
    if len(payments) >= 3:
        short = sum(1 for p in payments[-3:] if p["amount"] < terms["instalment"] * 0.92)
        if short >= 2 and account["arrears_amount"] > 0:
            signals.append(
                {
                    "code": "partial_payment_pattern",
                    "label": "Part payments becoming the pattern",
                    "severity": 2,
                    "detected_at": AS_OF - timedelta(days=rng.randint(3, 30)),
                    "headline": f"{short} of the last 3 payments fell short of the instalment",
                    "evidence": {"short_payments_last_3": short},
                }
            )

    broken = [p for p in account["promises"] if p["status"] == "broken"]
    if broken:
        signals.append(
            {
                "code": "broken_promise",
                "label": "Payment promise missed",
                "severity": 3,
                "detected_at": max(p["resolved_at"] for p in broken),
                "headline": f"{len(broken)} recorded payment promise"
                f"{'s' if len(broken) > 1 else ''} not honoured",
                "evidence": {
                    "broken_promises": len(broken),
                    "last_promised_date": max(p["promised_date"] for p in broken).isoformat(),
                },
            }
        )

    if account["instalments_due"] > 0 and account["instalments_paid"] == 0 and account["dpd"] > 0:
        signals.append(
            {
                "code": "first_payment_default",
                "label": "No instalment ever received",
                "severity": 3,
                "detected_at": terms["first_due_date"] + timedelta(days=14),
                "headline": "No payment has been received since disbursement",
                "evidence": {"instalments_due": account["instalments_due"], "paid": 0},
            }
        )

    if rng.random() < 0.021 and account["status"] != "closed":
        signals.append(
            {
                "code": "disbursement_diversion",
                "label": "Facility use not evidenced",
                "severity": 3,
                "detected_at": terms["disbursed_date"] + timedelta(days=rng.randint(2, 9)),
                "headline": "Proceeds left the account within 72 hours of drawdown",
                "evidence": {
                    "disbursed": terms["principal"],
                    "outflow_within_72h": int(round(terms["principal"] * rng.uniform(0.72, 0.97), -4)),
                },
            }
        )

    if account["status"] == "written_off":
        signals.append(
            {
                "code": "written_off",
                "label": "Written off, still recovering",
                "severity": 3,
                "detected_at": account["written_off_date"],
                "headline": "Balance written off; recovery continues",
                "evidence": {"recovered_to_date": account["recovery_to_date"]},
            }
        )

    # Advance warning is measured, not asserted: the gap between the earliest
    # financial signal and the first missed instalment.
    if account["first_missed_due"] is not None and signals:
        for signal in signals:
            if signal["code"] in ("inflow_decline", "balance_erosion", "pos_activity_drop",
                                  "obligation_creep"):
                lead = (account["first_missed_due"] - signal["detected_at"]).days
                if lead > 0:
                    signal["lead_days"] = lead
    return signals


def _month_end(key: str) -> date:
    year, month = (int(part) for part in key.split("-"))
    return date(year, month, _days_in_month(year, month))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def build_database(connection: sqlite3.Connection, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    sector_paths = build_stress_paths(rng)

    needed = ACTIVE_ACCOUNTS + CLOSED_ACCOUNTS
    used_names: set[str] = set()
    borrowers: list[dict] = []
    plan: list[tuple[dict, int]] = []

    # Grow the borrower universe in batches until the book holds enough facilities.
    # Two facilities where the trading history supports it.
    while len(plan) < needed:
        batch = build_borrowers(rng, 200, used_names, start_id=len(borrowers) + 1)
        borrowers.extend(batch)
        for borrower in batch:
            slots = 1
            if borrower["years_trading"] > 7 and rng.random() < 0.62:
                slots = 2
            elif rng.random() < 0.22:
                slots = 2
            for slot in range(slots):
                plan.append((borrower, slot))

    connection.execute("DELETE FROM recovery_events")
    for table in (
        "signal_events", "actions", "promises", "cashflow_months", "band_history",
        "payments", "installments", "accounts", "borrowers", "meta",
    ):
        connection.execute(f"DELETE FROM {table}")

    borrower_rows = [
        {
            key: borrower[key]
            for key in (
                "id", "name", "sector", "city", "state", "cac_number", "contact_name",
                "contact_phone", "contact_email", "relationship_manager", "onboarded_date",
                "years_trading", "employees", "monthly_inflow_base",
            )
        }
        for borrower in borrowers
    ]

    connection.executemany(
        "INSERT INTO borrowers (id, name, sector, city, state, cac_number, contact_name, "
        "contact_phone, contact_email, relationship_manager, onboarded_date, years_trading, "
        "employees, monthly_inflow_base) VALUES (:id, :name, :sector, :city, :state, "
        ":cac_number, :contact_name, :contact_phone, :contact_email, :relationship_manager, "
        ":onboarded_date, :years_trading, :employees, :monthly_inflow_base)",
        borrower_rows,
    )

    rng.shuffle(plan)
    active_plan = [(b, s, False) for b, s in plan[:ACTIVE_ACCOUNTS]]
    closed_plan = [(b, s, True) for b, s in plan[ACTIVE_ACCOUNTS:needed]]

    account_id = 0
    counters: dict[str, int] = {}
    summary = {
        "accounts": 0, "active": 0, "closed": 0, "written_off": 0,
        "signals": 0, "actions": 0, "promises": 0, "control_group": 0,
    }

    for borrower, slot, force_closed in active_plan + closed_plan:
        account_id += 1
        terms = build_account_terms(rng, borrower, slot)
        code = terms["product_code"]
        counters[code] = counters.get(code, 0) + 1
        account_ref = f"NL-{code}-{counters[code]:04d}"

        result = simulate_account(
            rng, borrower, terms, sector_paths, account_id, account_ref, force_closed
        )
        connection.execute(
            "UPDATE borrowers SET monthly_inflow_base = ? WHERE id = ?",
            (borrower["monthly_inflow_base"], borrower["id"]),
        )

        cashflow = build_cashflow(rng, borrower, account_id, sector_paths)

        # Monitoring tier follows the selective-monitoring policy: a live data feed
        # is only paid for where the exposure justifies its cost.
        exposure = result["outstanding_principal"] + result["arrears_amount"]
        if force_closed:
            tier = "none"
        elif exposure > 6_000_000 or result["band"] >= 1:
            tier = "full"
        elif exposure > 1_200_000:
            tier = "selective"
        else:
            tier = "none"

        monitoring_consent = "none"
        consent_granted = None
        consent_expires = None
        if tier != "none":
            draw = rng.random()
            if draw < 0.74:
                monitoring_consent = "active"
                consent_granted = terms["disbursed_date"] + timedelta(days=rng.randint(0, 5))
                consent_expires = consent_granted + timedelta(days=rng.randint(150, 420))
            elif draw < 0.90:
                monitoring_consent = "expired"
                consent_granted = terms["disbursed_date"] - timedelta(days=rng.randint(200, 500))
                consent_expires = AS_OF - timedelta(days=rng.randint(3, 120))
            else:
                monitoring_consent = "declined"

        signals = derive_signals(rng, cashflow, result, terms)

        # Everything detected is kept. Whether it can be acted on depends on
        # monitoring coverage — which is itself a number the risk team needs to see.
        monitoring_ok = monitoring_consent == "active"
        for signal in signals:
            signal["actionable"] = (
                1 if (signal["code"] in LENDER_RECORD_SIGNALS or monitoring_ok) else 0
            )

        connection.execute(
            "INSERT INTO accounts (id, ref, borrower_id, product_code, product_name, principal, "
            "monthly_rate, tenor_months, instalment, disbursed_date, first_due_date, maturity_date, "
            "outstanding_principal, arrears_amount, dpd, band, status, collateral, officer, "
            "cohort_month, monitoring_tier, monitoring_consent, consent_granted_at, "
            "consent_expires_at, control_group, written_off_date, recovery_to_date, "
            "instalments_paid, instalments_due) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?)",
            (
                account_id, account_ref, borrower["id"], terms["product_code"], terms["product_name"],
                terms["principal"], terms["monthly_rate"], terms["tenor_months"], terms["instalment"],
                iso(terms["disbursed_date"]), iso(terms["first_due_date"]), iso(terms["maturity_date"]),
                result["outstanding_principal"], result["arrears_amount"], result["dpd"],
                result["band"], result["status"], terms["collateral"], rng.choice(
                    config.RELATIONSHIP_MANAGERS
                ), month_key(terms["disbursed_date"]), tier, monitoring_consent,
                iso(consent_granted) if consent_granted else None,
                iso(consent_expires) if consent_expires else None,
                result["control_group"],
                iso(result["written_off_date"]) if result["written_off_date"] else None,
                result["recovery_to_date"], result["instalments_paid"], result["instalments_due"],
            ),
        )

        for row in result["installments"]:
            connection.execute(
                "INSERT INTO installments (account_id, seq, due_date, amount_due, amount_paid, "
                "paid_date, status) VALUES (?,?,?,?,?,?,?)",
                (
                    account_id, row["seq"], iso(row["due_date"]), row["amount_due"],
                    int(round(row["amount_paid"])), iso(row["paid_date"]) if row["paid_date"] else None,
                    row["status"],
                ),
            )

        for row in result["payments"]:
            connection.execute(
                "INSERT INTO payments (account_id, installment_id, paid_date, amount, channel, "
                "source) VALUES (?,?,?,?,?,?)",
                (account_id, None, iso(row["paid_date"]), row["amount"], row["channel"], row["source"]),
            )

        for snapshot in build_band_history(
            result["installments"], result["payments"], terms, result["written_off_date"]
        ):
            connection.execute(
                "INSERT INTO band_history (account_id, month_end, dpd, band, arrears, outstanding) "
                "VALUES (?,?,?,?,?,?)",
                (
                    account_id, iso(snapshot["month_end"]), snapshot["dpd"], snapshot["band"],
                    snapshot["arrears"], snapshot["outstanding"],
                ),
            )

        for row in cashflow:
            connection.execute(
                "INSERT INTO cashflow_months (borrower_id, account_id, month, inflow, outflow, "
                "closing_balance, pos_inflow, transfer_inflow, new_recurring_debits) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    row["borrower_id"], row["account_id"], row["month"], row["inflow"], row["outflow"],
                    row["closing_balance"], row["pos_inflow"], row["transfer_inflow"],
                    row["new_recurring_debits"],
                ),
            )

        for promise in result["promises"]:
            connection.execute(
                "INSERT INTO promises (id, account_id, made_at, promised_date, amount, status, "
                "resolved_at, action_id) VALUES (?,?,?,?,?,?,?,?)",
                (
                    promise["id"], account_id, iso(promise["made_at"]),
                    iso(promise["promised_date"]), promise["amount"], promise["status"],
                    iso(promise["resolved_at"]) if promise["resolved_at"] else None,
                    promise["action_id"],
                ),
            )

        for action in result["actions"]:
            connection.execute(
                "INSERT INTO actions (id, account_id, occurred_at, channel, disposition, officer, "
                "playbook_code, notes, cost, effect, promise_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    action["id"], account_id, iso(action["occurred_at"]), action["channel"],
                    action["disposition"], action["officer"], action["playbook_code"],
                    action["notes"], action["cost"], action["effect"], action["promise_id"],
                ),
            )

        for event in result["recovery_events"]:
            connection.execute(
                "INSERT INTO recovery_events (account_id, occurred_at, kind, amount, notes) "
                "VALUES (?,?,?,?,?)",
                (
                    account_id, iso(event["occurred_at"]), event["kind"], event["amount"],
                    event["notes"],
                ),
            )

        for signal in signals:
            connection.execute(
                "INSERT INTO signal_events (account_id, code, label, severity, detected_at, "
                "headline, evidence, lead_days, actionable) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    account_id, signal["code"], signal["label"], signal["severity"],
                    iso(signal["detected_at"]), signal["headline"], json.dumps(signal["evidence"]),
                    signal.get("lead_days"), signal.get("actionable", 1),
                ),
            )

        summary["accounts"] += 1
        summary["signals"] += len(signals)
        summary["actions"] += len(result["actions"])
        summary["promises"] += len(result["promises"])
        summary["control_group"] += result["control_group"]
        if result["status"] == "closed":
            summary["closed"] += 1
        elif result["status"] == "written_off":
            summary["written_off"] += 1
        else:
            summary["active"] += 1

    # Borrowers drawn for the pool but never allocated a facility are dropped, so
    # the borrower count always matches the book.
    connection.execute(
        "DELETE FROM borrowers WHERE id NOT IN (SELECT DISTINCT borrower_id FROM accounts)"
    )

    set_meta(connection, "as_of", iso(AS_OF))
    set_meta(connection, "seed", str(seed))
    set_meta(connection, "generator", "northline-synthetic-portfolio-v1")
    set_meta(connection, "synthetic", "true")
    connection.commit()
    return summary

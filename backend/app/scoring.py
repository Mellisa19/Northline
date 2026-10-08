"""The Northline Risk Index.

A transparent, monotonic, weighted index — deliberately *not* a black box and
deliberately not presented as a calibrated probability of default. Every point is
traceable to a reason a credit officer can argue with, which is what makes the
queue defensible to a committee and to a regulator.

Total weight is exactly 100 points:

    delinquency            39    how far past due the account is
    cash-flow decline      16    material fall in takings
    arrears depth          12    how many instalments behind
    broken promises        10    recorded commitments not honoured
    debt-service load       7    instalment against normal monthly takings
    payment behaviour       6    part payments becoming the pattern
    first-payment default   5    nothing ever received
    obligation creep        3    new recurring debits appearing
    balance erosion         2    operating balance falling away

Every component is separately documented here so the model card writes itself.
"""

from __future__ import annotations

import math

# Maximum points per component. These are the published weights.
WEIGHTS = {
    "delinquency": 39.0,
    "arrears_depth": 12.0,
    "broken_promises": 10.0,
    "cashflow_decline": 16.0,
    "debt_service": 7.0,
    "payment_behaviour": 6.0,
    "first_payment_default": 5.0,
    "obligation_creep": 3.0,
    "balance_erosion": 2.0,
}

BANDS = [
    (0, 19, "low", "Low"),
    (20, 39, "watch", "Watch"),
    (40, 59, "elevated", "Elevated"),
    (60, 79, "high", "High"),
    (80, 100, "severe", "Severe"),
]


def band_for_index(index: float) -> tuple[str, str]:
    for low, high, code, label in BANDS:
        if low <= index <= high:
            return code, label
    return "severe", "Severe"


def _delinquency_points(dpd: int) -> float:
    """Saturating curve: the first missed instalment matters most."""
    if dpd <= 0:
        return 0.0
    return WEIGHTS["delinquency"] * (1.0 - math.exp(-dpd / 70.0))


def _arrears_points(arrears: float, instalment: float) -> float:
    if instalment <= 0 or arrears <= 0:
        return 0.0
    instalments_behind = arrears / instalment
    return WEIGHTS["arrears_depth"] * min(1.0, instalments_behind / 6.0)


def _decline_points(change_pct: float | None) -> float:
    """A 10% drift is noise; a 40% fall is the whole signal.

    Weighted heavily enough that a still-current account with a material fall in
    takings reaches the watch band on the strength of the decline alone — which is
    the entire point of watching accounts before they miss a payment.
    """
    if change_pct is None or change_pct >= -10.0:
        return 0.0
    severity = min(1.0, (abs(change_pct) - 10.0) / 30.0)
    return WEIGHTS["cashflow_decline"] * severity


def _debt_service_points(instalment: float, monthly_inflow: float) -> float:
    """Capacity to service matters more than willingness to."""
    if monthly_inflow <= 0:
        return 0.0
    ratio = instalment / monthly_inflow
    if ratio <= 0.30:
        return 0.0
    return WEIGHTS["debt_service"] * min(1.0, (ratio - 0.30) / 0.20)


def _format_naira(amount: float) -> str:
    amount = float(amount)
    if abs(amount) >= 1_000_000_000:
        return f"\u20a6{amount / 1_000_000_000:.1f}bn"
    if abs(amount) >= 1_000_000:
        return f"\u20a6{amount / 1_000_000:.1f}M"
    if abs(amount) >= 1_000:
        return f"\u20a6{amount / 1_000:.1f}k"
    return f"\u20a6{amount:,.0f}"


def score_account(account: dict, signals: list[dict], cashflow: dict | None) -> dict:
    """Score one account and explain the result in plain language.

    ``account`` needs: dpd, arrears_amount, instalment, monthly_inflow_base,
    instalments_paid, status. ``signals`` are the account's signal rows.
    ``cashflow`` is a summary dict computed from the transaction history.
    """
    reasons: list[dict] = []
    points: dict[str, float] = {}

    # 1. Delinquency ---------------------------------------------------------
    dpd = int(account.get("dpd") or 0)
    value = _delinquency_points(dpd)
    points["delinquency"] = value
    if dpd > 0:
        reasons.append(
            {
                "code": "delinquency",
                "label": f"{dpd} days past due",
                "detail": (
                    f"The instalment due {account.get('oldest_unpaid_due', 'earlier')} "
                    f"remains unsettled."
                ),
                "points": round(value, 1),
                "severity": 3 if dpd > 60 else 2 if dpd > 30 else 1,
                "evidence": {"days_past_due": dpd},
            }
        )

    # 2. Arrears depth -------------------------------------------------------
    arrears = float(account.get("arrears_amount") or 0)
    instalment = float(account.get("instalment") or 0)
    value = _arrears_points(arrears, instalment)
    points["arrears_depth"] = value
    if value > 0:
        behind = arrears / instalment if instalment else 0
        reasons.append(
            {
                "code": "arrears_depth",
                "label": f"{_format_naira(arrears)} overdue",
                "detail": (
                    f"That is {behind:.1f} instalments of "
                    f"{_format_naira(instalment)} behind schedule."
                ),
                "points": round(value, 1),
                "severity": 3 if behind >= 2 else 2,
                "evidence": {"arrears": int(arrears), "instalments_behind": round(behind, 2)},
            }
        )

    # 3. Broken promises -----------------------------------------------------
    broken = sum(1 for s in signals if s["code"] == "broken_promise")
    broken = int(broken or account.get("broken_promises") or 0)
    value = min(WEIGHTS["broken_promises"], WEIGHTS["broken_promises"] * broken / 2.0)
    points["broken_promises"] = value
    if broken:
        reasons.append(
            {
                "code": "broken_promise",
                "label": f"{broken} payment promise{'s' if broken > 1 else ''} missed",
                "detail": "A dated commitment was recorded and not honoured.",
                "points": round(value, 1),
                "severity": 3 if broken >= 2 else 2,
                "evidence": {"broken_promises": broken},
            }
        )

    # 4. Cash-flow decline ---------------------------------------------------
    change = (cashflow or {}).get("change_pct")
    value = _decline_points(change)
    points["cashflow_decline"] = value
    if value > 0:
        reasons.append(
            {
                "code": "cashflow_decline",
                "label": f"Takings down {abs(change):.0f}%",
                "detail": (
                    f"Average monthly inflows fell from "
                    f"{_format_naira((cashflow or {}).get('prior_3m_avg', 0))} to "
                    f"{_format_naira((cashflow or {}).get('recent_3m_avg', 0))}."
                ),
                "points": round(value, 1),
                "severity": 3 if change < -40 else 2,
                "evidence": {
                    "change_pct": change,
                    "recent_3m_avg": (cashflow or {}).get("recent_3m_avg"),
                    "prior_3m_avg": (cashflow or {}).get("prior_3m_avg"),
                },
            }
        )

    # 5. Debt-service load ---------------------------------------------------
    value = _debt_service_points(instalment, float(account.get("monthly_inflow_base") or 0))
    points["debt_service"] = value
    if value > 0:
        inflow = float(account.get("monthly_inflow_base") or 0)
        ratio = instalment / inflow if inflow else 0
        reasons.append(
            {
                "code": "debt_service",
                "label": f"Instalment is {ratio * 100:.0f}% of normal takings",
                "detail": (
                    f"{_format_naira(instalment)} is due each month against ordinary "
                    f"inflows of about {_format_naira(inflow)}."
                ),
                "points": round(value, 1),
                "severity": 2 if ratio > 0.42 else 1,
                "evidence": {"debt_service_ratio": round(ratio, 3)},
            }
        )

    # 6. Payment behaviour ---------------------------------------------------
    short = int(account.get("short_payments_last_3") or 0)
    value = min(WEIGHTS["payment_behaviour"], WEIGHTS["payment_behaviour"] * short / 3.0)
    points["payment_behaviour"] = value
    if short >= 2:
        reasons.append(
            {
                "code": "partial_payment_pattern",
                "label": f"{short} of the last 3 payments were part payments",
                "detail": "Payments are arriving but consistently short of the instalment.",
                "points": round(value, 1),
                "severity": 2,
                "evidence": {"short_payments_last_3": short},
            }
        )

    # 7. First-payment default ----------------------------------------------
    # Only when nothing at all has been received: a large part payment is a very
    # different situation from silence since drawdown.
    collected = float(account.get("total_collected") or 0)
    value = 0.0
    if dpd > 0 and int(account.get("instalments_paid") or 0) == 0 and collected <= 0:
        value = WEIGHTS["first_payment_default"]
        reasons.append(
            {
                "code": "first_payment_default",
                "label": "No instalment ever received",
                "detail": "Nothing has been collected since drawdown.",
                "points": round(value, 1),
                "severity": 3,
                "evidence": {"instalments_paid": 0, "total_collected": 0},
            }
        )
    points["first_payment_default"] = value

    # 8. Obligation creep ----------------------------------------------------
    creep = [s for s in signals if s["code"] == "obligation_creep"]
    value = 0.0
    if creep:
        value = WEIGHTS["obligation_creep"] * (1.0 if max(s["severity"] for s in creep) > 1 else 0.5)
        reasons.append(
            {
                "code": "obligation_creep",
                "label": "New recurring obligations detected",
                "detail": "Additional standing commitments appeared in the account.",
                "points": round(value, 1),
                "severity": 1,
                "evidence": creep[0].get("evidence", {}),
            }
        )
    points["obligation_creep"] = value

    # 9. Balance erosion -----------------------------------------------------
    erosion = [s for s in signals if s["code"] == "balance_erosion"]
    value = WEIGHTS["balance_erosion"] if erosion else 0.0
    points["balance_erosion"] = value
    if erosion:
        reasons.append(
            {
                "code": "balance_erosion",
                "label": "Operating balance eroded",
                "detail": "Closing balances are well below the six-month average.",
                "points": round(value, 1),
                "severity": 1,
                "evidence": erosion[0].get("evidence", {}),
            }
        )

    index = round(min(100.0, sum(points.values())), 1)
    code, label = band_for_index(index)

    reasons.sort(key=lambda reason: reason["points"], reverse=True)

    return {
        "index": index,
        "band_code": code,
        "band_label": label,
        "components": {key: round(val, 1) for key, val in points.items()},
        "weights": WEIGHTS,
        "reasons": reasons,
        "method": (
            "Transparent weighted index over nine documented components. "
            "An index, not a calibrated probability of default."
        ),
    }

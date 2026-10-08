"""Expected-value prioritisation.

A worklist ordered by "risk" is not the same as a worklist ordered by money. A
₦40M asset-finance account with a modest signal is usually worth more attention
than a ₦300k merchant advance that is 45 days late, and a collections manager
with two hundred accounts to review today needs the second question answered:
*which of these is worth a human's time?*

The engine is explicit about its assumptions, and every one of them is exposed in
the UI so a credit committee can disagree with the number rather than distrust it.
"""

from __future__ import annotations

from . import config

# Officer time consumed by one attempt is priced per channel in app.config, so
# there is a single published source for cost-to-collect.

# Recovery thresholds that separate the priority bands, in naira of expected
# incremental recovery from acting today.
PRIORITY_HIGH = 250_000
PRIORITY_MEDIUM = 60_000

# How many future instalments count as reachable when a current account is
# worked. Beyond this the balance is a relationship question, not a queue item.
REACHABLE_INSTALMENTS = 3

# Floor on the probability that an account's reachable value becomes a loss if
# nothing is done, by delinquency band. A current account with no signals scores
# near zero here, which is what keeps healthy accounts off a recovery worklist.
BAND_PROBLEM_FLOOR = {0: 0.0, 1: 0.35, 2: 0.55, 3: 0.70, 4: 0.85}


def problem_probability(band: int, risk_index: float) -> float:
    """Chance the reachable value is lost if the account is left alone."""
    floor = BAND_PROBLEM_FLOOR.get(band, 0.0)
    return max(floor, min(1.0, risk_index / 100.0))


def loss_given_default(product_code: str) -> float:
    return config.LOSS_GIVEN_DEFAULT.get(product_code, 0.55)


def evaluate(
    account: dict,
    risk: dict,
    playbook: dict,
    exposure: float,
) -> dict:
    """Expected incremental recovery from working this account today.

    The value at stake is deliberately *not* the whole remaining balance. Treating
    a three-year facility as fully at risk because one instalment is twenty-six days
    late is how a worklist ends up ranking large loans above urgent ones. What a
    collections team can actually reach this cycle is the overdue balance plus the
    next few instalments, so that is what the engine prices.

    ``loss_at_risk`` applies the product's loss-given-default assumption to that
    reachable amount, and ``expected_recovery`` applies the published playbook
    effectiveness for the account's delinquency band.
    """
    band = int(account.get("band") or 0)
    instalment = float(account.get("instalment") or 0)
    arrears = float(account.get("arrears_amount") or 0)
    lgd = loss_given_default(account.get("product_code", ""))

    reachable = arrears + instalment * REACHABLE_INSTALMENTS
    value_at_stake = max(0.0, min(float(exposure), reachable))

    effectiveness = playbook["effectiveness"]
    probability = problem_probability(band, risk["index"])
    loss_at_risk = value_at_stake * lgd * probability
    expected_recovery = loss_at_risk * effectiveness

    attempt = config.attempt_cost(playbook["channel"])
    value_per_attempt = expected_recovery / attempt if attempt else 0.0

    if expected_recovery >= PRIORITY_HIGH:
        priority = "high"
    elif expected_recovery >= PRIORITY_MEDIUM:
        priority = "medium"
    else:
        priority = "low"

    return {
        "exposure": round(exposure),
        "balance_at_stake": round(exposure),
        "value_at_stake": round(value_at_stake),
        "reachable_basis": "overdue balance plus three instalments, capped at the balance",
        "loss_given_default": lgd,
        "risk_index": risk["index"],
        "probability_of_loss": round(probability, 3),
        "playbook_effectiveness": effectiveness,
        "loss_at_risk": round(loss_at_risk),
        "expected_recovery": round(expected_recovery),
        "attempt_cost": attempt,
        "value_per_attempt": round(value_per_attempt, 1),
        "priority": priority,
        "assumptions": {
            "loss_given_default": lgd,
            "probability_of_loss": round(probability, 3),
            "playbook_effectiveness": effectiveness,
            "channel": playbook["channel"],
            "attempt_cost": attempt,
            "reachable_instalments": REACHABLE_INSTALMENTS,
        },
    }


def apply_review_budget(rows: list[dict], budget: int | None) -> dict:
    """Rank the book and compare Northline's ordering with the existing habit.

    The baseline a lender already has is ``days past due, then size``. If the
    product cannot beat that at the same number of reviews, it has no value — so
    the comparison is returned with every response rather than hidden in a deck.
    """
    actionable = [row for row in rows if row["priority_value"]["expected_recovery"] > 0]
    total_value = sum(row["priority_value"]["expected_recovery"] for row in actionable)
    total_accounts = len(rows)

    ranked = sorted(
        rows,
        key=lambda row: (
            row["priority_value"]["expected_recovery"],
            row["exposure"],
        ),
        reverse=True,
    )
    baseline = sorted(rows, key=lambda row: (row["dpd"], row["exposure"]), reverse=True)

    limit = budget if budget and budget > 0 else len(ranked)
    selected = ranked[:limit]
    baseline_selected = baseline[:limit]

    def summarise(rows_subset: list[dict]) -> dict:
        recovery = sum(row["priority_value"]["expected_recovery"] for row in rows_subset)
        return {
            "accounts": len(rows_subset),
            "expected_recovery": round(recovery),
            "exposure_covered": round(sum(row["exposure"] for row in rows_subset)),
            "value_share_pct": round(recovery / total_value * 100, 1) if total_value else 0.0,
            "delinquent_accounts": sum(1 for row in rows_subset if row["dpd"] > 0),
            "deteriorating_accounts": sum(
                1 for row in rows_subset if row["dpd"] == 0 and row["risk"]["index"] >= 40
            ),
        }

    northline = summarise(selected)
    habit = summarise(baseline_selected)

    lift = (
        northline["expected_recovery"] / habit["expected_recovery"]
        if habit["expected_recovery"]
        else None
    )

    return {
        "budget": limit,
        "total_accounts": total_accounts,
        "actionable_accounts": len(actionable),
        "total_expected_recovery": round(total_value),
        "northline": northline,
        "baseline_dpd_order": habit,
        "lift_vs_dpd_order": round(lift, 2) if lift else None,
    }

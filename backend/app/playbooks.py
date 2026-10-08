"""Playbook selection — the answer to "so what do I do?"

The catalogue itself lives in :mod:`app.config` so that the scripts, the
effectiveness assumptions and the product copy cannot drift apart. This module
only decides which playbook an account should be worked with, and why.
"""

from __future__ import annotations

from . import config

# Which channel a playbook is normally executed through, and therefore what one
# attempt costs the lender.
PLAYBOOK_CHANNEL = {
    "CARE_CALL": "call",
    "REMIND_LINK": "whatsapp",
    "PROMISE_CAPTURE": "call",
    "PART_PAYMENT": "call",
    "RESTRUCTURE": "email",
    "MANDATE_SETUP": "call",
    "DIVERSION_REVIEW": "email",
    "FIELD_VISIT": "field_visit",
    "LEGAL_REVIEW": "legal_notice",
}


def _resolve(playbook: dict, band: int) -> dict:
    table = config.PLAYBOOK_EFFECTIVENESS.get(playbook["code"], {})
    effectiveness = table.get(band, table.get(0, 0.2))
    channel = PLAYBOOK_CHANNEL.get(playbook["code"], "call")
    return {
        **playbook,
        "channel": channel,
        "channel_cost": config.attempt_cost(channel),
        "effectiveness": effectiveness,
        "assumptions": (
            f"Assumes a {effectiveness * 100:.0f}% chance of converting an account in "
            f"the {config.BANDS[band]['label']} band when this playbook is executed."
        ),
    }


def recommend(account: dict, signals: list[dict], risk: dict, cashflow: dict | None) -> dict:
    """Choose the primary playbook, two alternates, and the reasoning."""
    band = int(account.get("band") or 0)
    codes = {signal["code"] for signal in signals}
    changes = (cashflow or {}).get("change_pct")
    evidence: list[str] = []

    primary_code = "CARE_CALL"

    if "disbursement_diversion" in codes:
        primary_code = "DIVERSION_REVIEW"
        evidence.append("Drawdown left the account within 72 hours of disbursement.")
    elif band >= 4:
        primary_code = "LEGAL_REVIEW"
        evidence.append("The balance has passed 90 days past due.")
    elif band == 3:
        primary_code = "FIELD_VISIT"
        evidence.append("61\u201390 days past due with the business believed to be trading.")
    elif "broken_promise" in codes:
        primary_code = "PROMISE_CAPTURE"
        evidence.append("A dated commitment was recorded and not honoured.")
    elif band == 2:
        primary_code = "PART_PAYMENT"
        evidence.append("31\u201360 days past due: cash now beats escalation later.")
    elif band == 1:
        primary_code = "REMIND_LINK"
        evidence.append("Recently past due with an otherwise workable history.")
    elif changes is not None and changes <= -30 and int(account.get("dpd") or 0) == 0:
        clean = int(account.get("instalments_paid") or 0) >= max(
            2, int(account.get("instalments_due") or 1) - 1
        )
        if clean:
            primary_code = "RESTRUCTURE"
            evidence.append(
                f"Takings are down {abs(changes):.0f}% on a previously clean repayment record."
            )
        else:
            primary_code = "CARE_CALL"
            evidence.append("Material decline in takings while the account is still current.")
    elif int(account.get("short_payments_last_3") or 0) >= 2:
        primary_code = "MANDATE_SETUP"
        evidence.append("Repeated part payments suggest a timing problem, not a solvency one.")
    elif int(account.get("next_due_in_days") or 99) <= 10 and band == 0:
        primary_code = "REMIND_LINK"
        evidence.append("The next instalment falls due within ten days.")
    else:
        primary_code = "CARE_CALL"
        evidence.append("Deterioration detected while the account is still current.")

    alternates = _alternates(primary_code, band, codes)
    by_code = config.PLAYBOOK_BY_CODE

    primary = _resolve(by_code[primary_code], band)
    primary["rationale"] = evidence

    return {
        "primary": primary,
        "alternates": [_resolve(by_code[code], band) for code in alternates],
        "risk_band": risk.get("band_label"),
    }


def _alternates(primary_code: str, band: int, codes: set[str]) -> list[str]:
    """Two plausible alternatives, ranked by how far the account is past due."""
    if band >= 4:
        pool = ["LEGAL_REVIEW", "FIELD_VISIT", "PART_PAYMENT"]
    elif band == 3:
        pool = ["FIELD_VISIT", "PART_PAYMENT", "LEGAL_REVIEW"]
    elif band == 2:
        pool = ["PART_PAYMENT", "PROMISE_CAPTURE", "RESTRUCTURE"]
    elif band == 1:
        pool = ["PROMISE_CAPTURE", "REMIND_LINK", "MANDATE_SETUP"]
    else:
        pool = ["CARE_CALL", "REMIND_LINK", "RESTRUCTURE"]

    if primary_code == "DIVERSION_REVIEW":
        pool = ["DIVERSION_REVIEW", "CARE_CALL", "FIELD_VISIT"]
    if "broken_promise" in codes and "PROMISE_CAPTURE" not in pool:
        pool.insert(0, "PROMISE_CAPTURE")

    return [code for code in pool if code != primary_code][:2]


def catalogue() -> list[dict]:
    """The full playbook library, for the product's reference screen."""
    rows = []
    for playbook in config.PLAYBOOKS:
        channel = PLAYBOOK_CHANNEL.get(playbook["code"], "call")
        rows.append(
            {
                **playbook,
                "channel": channel,
                "channel_cost": config.attempt_cost(channel),
                "effectiveness_by_band": [
                    {
                        "band": config.BANDS[index]["label"],
                        "probability": config.PLAYBOOK_EFFECTIVENESS[playbook["code"]].get(index, 0),
                    }
                    for index in range(5)
                ],
            }
        )
    return rows

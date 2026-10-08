"""Engine tests.

The portfolio build takes about half a minute, so it happens once per session
against a temporary database and every test reads from it.

    cd backend && python -m pytest tests -q
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import analytics, config, operations, playbooks, priority, scoring  # noqa: E402
from app.db import create_schema, reset  # noqa: E402
from app.generate import SEED, build_database  # noqa: E402


@pytest.fixture(scope="session")
def workdir():
    """A database directory inside the project, so the suite works under a sandbox."""
    path = Path(__file__).resolve().parent / ".tmp"
    path.mkdir(exist_ok=True)
    return path


@pytest.fixture(scope="session")
def connection(workdir):
    path = workdir / "test.db"
    con = reset(path)
    build_database(con, seed=SEED)
    yield con
    con.close()


# ---------------------------------------------------------------------------
# Book shape
# ---------------------------------------------------------------------------
def test_book_is_a_plausible_lending_portfolio(connection):
    summary = analytics.portfolio_summary(connection)
    assert summary["accounts"] > 400
    assert summary["borrowers"] > 300
    assert summary["book_principal"] > 0

    # A book where a third of accounts are 30+ days late, or where almost nobody
    # is, would not be a credible mid-market lender.
    assert 3.0 <= summary["par30"]["count_pct"] <= 20.0
    assert summary["par60"]["accounts"] <= summary["par30"]["accounts"]
    assert summary["par90"]["accounts"] <= summary["par60"]["accounts"]

    live = connection.execute(
        "SELECT COUNT(*) AS n FROM accounts WHERE status = 'written_off'"
    ).fetchone()["n"]
    disbursed = connection.execute(
        "SELECT COUNT(*) AS n FROM accounts WHERE status != 'closed'"
    ).fetchone()["n"]
    write_off_rate = live / disbursed
    assert 0.02 <= write_off_rate <= 0.15


def test_generation_is_reproducible(workdir):
    first = reset(workdir / "a.db")
    build_database(first, seed=SEED)
    second = reset(workdir / "b.db")
    build_database(second, seed=SEED)

    query = "SELECT ref, dpd, arrears_amount, status FROM accounts ORDER BY id"
    assert [tuple(row) for row in first.execute(query)] == [
        tuple(row) for row in second.execute(query)
    ]
    first.close()
    second.close()


def test_band_history_matches_the_current_book(connection):
    """Roll rates are only meaningful if the reconstruction agrees with today."""
    mismatches = connection.execute(
        "SELECT COUNT(*) AS n FROM accounts a JOIN band_history h "
        "  ON h.account_id = a.id AND h.month_end = ? "
        "WHERE a.status = 'active' AND h.band != a.band",
        (config.AS_OF.isoformat(),),
    ).fetchone()["n"]
    assert mismatches == 0


def test_monthly_migration_rows_are_complete(connection):
    matrix = analytics.migration_matrix(connection, "2026-01-01")
    assert len(matrix["matrix"]) == len(config.BANDS)
    for row in matrix["matrix"]:
        assert len(row["transitions"]) == len(config.BANDS) + 1  # plus the exit column
        if row["total"]:
            assert abs(sum(cell["pct"] for cell in row["transitions"]) - 100) < 1.5


def test_vintage_curves_never_decrease(connection):
    cohorts = analytics.vintage_curves(connection)["cohorts"]
    assert cohorts
    for points in cohorts.values():
        values = [point["cumulative_pct"] for point in points]
        assert values == sorted(values)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def test_risk_index_is_monotonic_in_delinquency():
    def score(dpd: int) -> float:
        return scoring.score_account(
            {
                "dpd": dpd,
                "arrears_amount": dpd * 10_000,
                "instalment": 500_000,
                "monthly_inflow_base": 2_000_000,
                "instalments_paid": 3,
                "total_collected": 1_500_000,
            },
            [],
            None,
        )["index"]

    values = [score(dpd) for dpd in (0, 5, 30, 60, 90, 180)]
    assert values == sorted(values)
    assert values[0] == 0
    assert values[-1] > 40


def test_risk_index_stays_within_range_and_explains_itself():
    result = scoring.score_account(
        {
            "dpd": 400,
            "arrears_amount": 50_000_000,
            "instalment": 1_000_000,
            "monthly_inflow_base": 1_500_000,
            "instalments_paid": 0,
            "total_collected": 0,
        },
        [
            {"code": "broken_promise", "severity": 3, "evidence": {}},
            {"code": "obligation_creep", "severity": 2, "evidence": {}},
            {"code": "balance_erosion", "severity": 1, "evidence": {}},
        ],
        {"change_pct": -70.0, "recent_3m_avg": 300_000, "prior_3m_avg": 1_000_000},
    )
    assert 0 <= result["index"] <= 100
    assert result["index"] > 80
    assert result["band_code"] in {"high", "severe"}
    assert result["reasons"]
    # Every point awarded must be traceable to a component.
    assert abs(sum(result["components"].values()) - result["index"]) < 0.6
    assert sum(scoring.WEIGHTS.values()) == 100


def test_cash_flow_decline_alone_reaches_the_watch_band():
    """A still-current account with a material fall in takings must surface."""
    result = scoring.score_account(
        {
            "dpd": 0,
            "arrears_amount": 0,
            "instalment": 500_000,
            "monthly_inflow_base": 3_000_000,
            "instalments_paid": 4,
            "total_collected": 2_000_000,
        },
        [],
        {"change_pct": -45.0, "recent_3m_avg": 1_650_000, "prior_3m_avg": 3_000_000},
    )
    assert result["index"] >= 16
    assert result["components"]["cashflow_decline"] >= 16
    assert result["reasons"][0]["code"] == "cashflow_decline"


# ---------------------------------------------------------------------------
# Prioritisation
# ---------------------------------------------------------------------------
def _account(**overrides):
    base = {
        "band": 0,
        "instalment": 500_000,
        "arrears_amount": 0,
        "product_code": "WC",
        "dpd": 0,
    }
    base.update(overrides)
    return base


def test_healthy_accounts_are_not_worth_working():
    """A current account with no adverse signal must never reach the queue's top."""
    risk = {"index": 3.0, "band_label": "Low"}
    playbook = playbooks._resolve(config.PLAYBOOK_BY_CODE["CARE_CALL"], 0)
    value = priority.evaluate(_account(), risk, playbook, 20_000_000)
    assert value["priority"] == "low"
    assert value["expected_recovery"] < priority.PRIORITY_MEDIUM
    # And it is not an economically interesting call.
    assert value["expected_recovery"] < 25 * value["attempt_cost"]


def test_expected_value_rises_with_risk_and_exposure():
    playbook = playbooks._resolve(config.PLAYBOOK_BY_CODE["PART_PAYMENT"], 2)
    risk = {"index": 40.0, "band_label": "Elevated"}

    # Both balances are above the reachable amount, so exposure cannot change the
    # answer: the engine prices what is reachable this cycle, not the whole book.
    small = priority.evaluate(_account(band=2, dpd=40, arrears_amount=1_000_000), risk, playbook, 5_000_000)
    large = priority.evaluate(_account(band=2, dpd=40, arrears_amount=1_000_000), risk, playbook, 25_000_000)
    assert small["expected_recovery"] == large["expected_recovery"]

    # Once the balance drops below the reachable amount, it does bind.
    tiny = priority.evaluate(_account(band=2, dpd=40, arrears_amount=1_000_000), risk, playbook, 1_200_000)
    assert tiny["value_at_stake"] == 1_200_000
    assert tiny["expected_recovery"] < small["expected_recovery"]

    riskier = priority.evaluate(
        _account(band=2, dpd=40, arrears_amount=1_000_000),
        {"index": 75.0, "band_label": "High"},
        playbook,
        5_000_000,
    )
    assert riskier["probability_of_loss"] > small["probability_of_loss"]
    assert riskier["expected_recovery"] > small["expected_recovery"]


def test_reachable_value_is_capped_by_the_balance():
    playbook = playbooks._resolve(config.PLAYBOOK_BY_CODE["CARE_CALL"], 1)
    value = priority.evaluate(
        _account(band=1, dpd=12, arrears_amount=200_000, instalment=100_000),
        {"index": 25.0, "band_label": "Watch"},
        playbook,
        900_000,
    )
    # 200k arrears + 3 × 100k instalments would be 500k, but the balance caps it.
    assert value["value_at_stake"] == 500_000
    capped = priority.evaluate(
        _account(band=1, dpd=12, arrears_amount=200_000, instalment=100_000),
        {"index": 25.0, "band_label": "Watch"},
        playbook,
        300_000,
    )
    assert capped["value_at_stake"] == 300_000


def test_ordering_pays_off_most_when_capacity_is_constrained(connection):
    """The value of ordering is a function of how few accounts a team can work.

    With a tight review budget the ordering matters enormously, because the team
    has to choose. With enough capacity to work the whole actionable book, every
    ordering reaches the same accounts and the advantage disappears — which is the
    honest shape of the claim, and worth pinning down.
    """
    tight = analytics.worklist(connection, budget=10)["ranking"]
    middling = analytics.worklist(connection, budget=50)["ranking"]
    loose = analytics.worklist(connection, budget=300)["ranking"]

    assert tight["lift_vs_dpd_order"] > 2.0
    assert middling["lift_vs_dpd_order"] > 1.2
    assert loose["lift_vs_dpd_order"] < middling["lift_vs_dpd_order"]
    assert loose["lift_vs_dpd_order"] < 1.3


def test_queue_prefers_accounts_that_can_still_be_recovered(connection):
    """Sorting by arrears age puts the team on accounts that have run out of options."""
    worklist = analytics.worklist(connection, budget=40)
    northline = [row["band"] for row in worklist["rows"]]
    baseline = [row["band"] for row in worklist["baseline_rows"]]
    assert statistics.mean(northline) < statistics.mean(baseline)
    assert max(baseline) == 4  # the oldest-arrears ordering reaches the 90+ band first


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------
def test_playbook_escalates_with_delinquency():
    def recommend(band: int, dpd: int) -> str:
        return playbooks.recommend(
            {"band": band, "dpd": dpd, "instalments_paid": 3, "instalments_due": 5},
            [],
            {"index": band * 20.0, "band_label": "x"},
            None,
        )["primary"]["code"]

    assert recommend(0, 0) in {"CARE_CALL", "REMIND_LINK"}
    assert recommend(2, 45) == "PART_PAYMENT"
    assert recommend(3, 75) == "FIELD_VISIT"
    assert recommend(4, 120) == "LEGAL_REVIEW"


def test_broken_promise_changes_the_recommendation():
    result = playbooks.recommend(
        {"band": 1, "dpd": 20, "instalments_paid": 2, "instalments_due": 6},
        [{"code": "broken_promise", "severity": 3, "evidence": {}}],
        {"index": 30.0, "band_label": "Watch"},
        None,
    )
    assert result["primary"]["code"] == "PROMISE_CAPTURE"
    assert len(result["alternates"]) == 2


def test_diversion_outranks_delinquency():
    result = playbooks.recommend(
        {"band": 1, "dpd": 5, "instalments_paid": 0, "instalments_due": 1},
        [{"code": "disbursement_diversion", "severity": 3, "evidence": {}}],
        {"index": 25.0, "band_label": "Watch"},
        None,
    )
    assert result["primary"]["code"] == "DIVERSION_REVIEW"


# Playbooks that work by persuasion get less effective the longer an account has
# been ignored. Escalation playbooks are the opposite: a field visit is pointless
# on a current account and only makes sense once the account has aged.
SOFT_PLAYBOOKS = {
    "CARE_CALL", "REMIND_LINK", "PROMISE_CAPTURE", "PART_PAYMENT",
    "RESTRUCTURE", "MANDATE_SETUP", "DIVERSION_REVIEW",
}
ESCALATION_PLAYBOOKS = {"FIELD_VISIT", "LEGAL_REVIEW"}


def test_every_playbook_has_a_published_conversion_rate():
    for playbook in config.PLAYBOOKS:
        table = config.PLAYBOOK_EFFECTIVENESS[playbook["code"]]
        assert set(table) == {0, 1, 2, 3, 4}
        assert all(0 < value < 1 for value in table.values())


def test_persuasion_playbooks_decay_with_delinquency():
    for code in SOFT_PLAYBOOKS:
        values = [config.PLAYBOOK_EFFECTIVENESS[code][index] for index in range(5)]
        assert values == sorted(values, reverse=True), f"{code} is not monotone: {values}"
        assert values[4] < values[0]


def test_escalation_playbooks_do_not_work_before_the_account_is_late():
    for code in ESCALATION_PLAYBOOKS:
        table = config.PLAYBOOK_EFFECTIVENESS[code]
        assert table[4] > table[0], f"{code} should be worth more on an aged account"
        assert table[0] == min(table.values()) or table[0] < table[2]


# ---------------------------------------------------------------------------
# Monitoring and consent
# ---------------------------------------------------------------------------
def test_transaction_signals_are_only_actionable_with_consent(connection):
    rows = connection.execute(
        "SELECT s.actionable, a.monitoring_consent, s.code FROM signal_events s "
        "JOIN accounts a ON a.id = s.account_id"
    ).fetchall()
    assert rows
    for row in rows:
        if row["code"] in ("inflow_decline", "balance_erosion", "pos_activity_drop",
                           "obligation_creep"):
            assert row["actionable"] == (1 if row["monitoring_consent"] == "active" else 0)


def test_monitoring_is_selective_but_covers_most_of_the_value(connection):
    coverage = analytics.monitoring_coverage(connection)
    assert 10 <= coverage["coverage_pct"] <= 60
    assert coverage["coverage_value_pct"] > coverage["coverage_pct"]


# ---------------------------------------------------------------------------
# The write path
# ---------------------------------------------------------------------------
def test_logging_a_promise_then_keeping_it_moves_the_account(connection):
    row = connection.execute(
        "SELECT id, instalment, arrears_amount, dpd FROM accounts "
        "WHERE status = 'active' AND dpd > 30 AND arrears_amount > 0 "
        "ORDER BY arrears_amount DESC LIMIT 1"
    ).fetchone()
    account_id = row["id"]
    arrears_before = row["arrears_amount"]

    action = operations.log_action(
        connection,
        account_id,
        channel="call",
        disposition="promise_to_pay",
        officer="B. Eze",
        playbook_code="PROMISE_CAPTURE",
        promised_date=(config.AS_OF.replace(day=1)).isoformat(),
        promised_amount=arrears_before,
    )
    assert action["promise_id"] is not None

    before = operations.recompute_position(connection, account_id)
    result = operations.resolve_promise(
        connection, account_id, action["promise_id"], kept=True, settled_amount=arrears_before
    )
    assert result["status"] == "kept"
    assert result["position"]["arrears_amount"] < before["arrears_amount"]
    assert result["position"]["band"] <= before["band"]

    promise = connection.execute(
        "SELECT status FROM promises WHERE account_id = ? AND id = ?",
        (account_id, action["promise_id"]),
    ).fetchone()
    assert promise["status"] == "kept"


def test_broken_promise_is_recorded_against_the_action(connection):
    row = connection.execute(
        "SELECT id, arrears_amount FROM accounts WHERE status = 'active' AND dpd > 20 "
        "ORDER BY arrears_amount DESC LIMIT 1"
    ).fetchone()
    action = operations.log_action(
        connection,
        row["id"],
        channel="whatsapp",
        disposition="promise_to_pay",
        officer="D. Yakubu",
        promised_date=(config.AS_OF.replace(day=28)).isoformat(),
        promised_amount=max(1, row["arrears_amount"] // 2),
    )
    operations.resolve_promise(connection, row["id"], action["promise_id"], kept=False)

    promise = connection.execute(
        "SELECT status FROM promises WHERE account_id = ? AND id = ?",
        (row["id"], action["promise_id"]),
    ).fetchone()
    assert promise["status"] == "broken"
    effect = connection.execute(
        "SELECT effect FROM actions WHERE account_id = ? AND promise_id = ?",
        (row["id"], action["promise_id"]),
    ).fetchone()
    assert effect["effect"] == "promise_broken"


def test_unknown_channel_and_disposition_are_rejected(connection):
    account_id = connection.execute("SELECT id FROM accounts LIMIT 1").fetchone()["id"]
    with pytest.raises(ValueError):
        operations.log_action(connection, account_id, "telepathy", "no_answer", "B. Eze")
    with pytest.raises(ValueError):
        operations.log_action(connection, account_id, "call", "vibes", "B. Eze")


# ---------------------------------------------------------------------------
# The ledger's honesty rules
# ---------------------------------------------------------------------------
def test_ledger_refuses_a_claim_it_cannot_support(connection):
    ledger = analytics.roi_ledger(connection)
    assert "interpretation" in ledger
    for arm in ledger["holdout"].values():
        assert arm["accounts"] > 0
    # An incremental estimate is only published when both arms are large enough.
    if ledger["incremental_recovery_estimate"] is not None:
        assert ledger["holdout"]["worked"]["accounts"] >= 15
        assert ledger["holdout"]["control"]["accounts"] >= 15
    else:
        assert ledger["sample_note"]

import { useEffect, useMemo, useState } from "react";
import { IndexScale, Sparkline } from "../components/charts";
import { Avatar, CountUp, Reveal, Select } from "../components/ui";
import { endpoints, invalidate, postJson, useApi } from "../lib/api";
import {
  bandTone,
  money,
  moneyFull,
  monthLabel,
  number,
  percent,
  riskTone,
  shortDate,
} from "../lib/format";

export default function AccountPage({ id, navigate }) {
  const path = id ? endpoints.account(id) : null;
  const { data, loading, error, reload } = useApi(path, { skip: !id });
  const { data: meta } = useApi(endpoints.meta());

  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);

  const account = data?.account;
  const risk = data?.risk;
  const value = data?.priority_value;
  const playbook = data?.playbook;

  const openPromises = useMemo(
    () => (data?.promises ?? []).filter((promise) => promise.status === "open"),
    [data],
  );

  async function refresh(message) {
    invalidate();
    await reload({ fresh: true });
    setFlash(message);
  }

  async function logAction(payload) {
    setBusy(true);
    try {
      await postJson(`/accounts/${id}/actions`, payload);
      await refresh("Contact recorded.");
    } catch (err) {
      setFlash(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function resolve(promiseId, kept) {
    setBusy(true);
    try {
      const result = await postJson(`/accounts/${id}/promises/${promiseId}/resolve`, { kept });
      await refresh(
        kept
          ? `Promise kept. Position now ${result.position.band_label.toLowerCase()} · ${money(result.position.arrears_amount)} outstanding.`
          : "Promise marked broken.",
      );
    } catch (err) {
      setFlash(err.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!flash) return undefined;
    const timer = setTimeout(() => setFlash(null), 6000);
    return () => clearTimeout(timer);
  }, [flash]);

  if (!id) return <p className="page__error">No account selected.</p>;
  if (loading && !data) return <p className="page__note">Loading account…</p>;
  if (error) return <p className="page__error">{error}</p>;
  if (!account) return null;

  const cashflow = data.cashflow_series ?? [];

  return (
    <div className="page page--account">
      <section className="acct__head">
        <div>
          <button className="backlink" type="button" onClick={() => navigate("/app")}>
            ← Back to worklist
          </button>
          <div className="acct__identity">
            <Avatar name={account.borrower_name} size={54} />
            <div>
              <h2 className="acct__name">{account.borrower_name}</h2>
              <p className="acct__meta">
                {account.ref} · {account.product_name} · {account.city}, {account.state}
              </p>
            </div>
          </div>
          <div className="acct__chips">
            <span className="chip" style={{ borderColor: bandTone(account.band), color: bandTone(account.band) }}>
              <span className="dot" />
              {account.dpd > 0 ? `${account.dpd} days past due` : "Current"}
            </span>
            <span className="chip" style={{ borderColor: riskTone(risk.band_code), color: riskTone(risk.band_code) }}>
              Risk {risk.index} · {risk.band_label}
            </span>
            <span className={`chip ${account.monitoring_consent === "active" ? "chip--resolve" : "chip--quiet"}`}>
              {account.monitoring_consent === "active"
                ? "Live data feed"
                : `Monitoring ${account.monitoring_consent}`}
            </span>
            {account.control_group ? (
              <span className="chip chip--quiet" title="Held out of proactive contact to measure effect">
                Holdout slice
              </span>
            ) : null}
            <span className="chip chip--quiet">{account.relationship_manager}</span>
          </div>
        </div>

        <div className="acct__head-figures">
          <div className="stat">
            <span className="eyebrow">Outstanding</span>
            <span className="figure figure--lg">{money(account.outstanding_principal)}</span>
            <span className="stat__note">
              {money(account.outstanding_total)} including remaining interest
            </span>
          </div>
          <div className="stat">
            <span className="eyebrow">Overdue</span>
            <span
              className="figure figure--lg"
              style={{ color: account.arrears_amount > 0 ? "var(--risk)" : "var(--ink-3)" }}
            >
              {money(account.arrears_amount)}
            </span>
            <span className="stat__note">
              Instalment {money(account.instalment)} · {account.tenor_months} months
            </span>
          </div>
        </div>
      </section>

      {flash ? <p className="flash">{flash}</p> : null}

      <div className="acct__grid">
        <div className="acct__col">
          <section className="panel">
            <div className="panel__head">
              <span className="panel__title">Why this account needs attention</span>
              <span className="source">{risk.reasons.length} signals</span>
            </div>

            <IndexScale value={risk.index} bandCode={risk.band_code} tone={riskTone(risk.band_code)} />

            <ol className="reasons">
              {risk.reasons.map((reason) => (
                <li key={reason.code}>
                  <div className="reasons__head">
                    <span className="reasons__label">{reason.label}</span>
                    <span className="reasons__points tnum">+{reason.points}</span>
                  </div>
                  <p className="reasons__detail">{reason.detail}</p>
                  <span className="reasons__bar">
                    <span
                      className="reasons__fill"
                      style={{
                        width: `${Math.min(100, (reason.points / 39) * 100)}%`,
                        background: reason.severity >= 3 ? "var(--risk)" : "var(--signal)",
                      }}
                    />
                  </span>
                </li>
              ))}
              {!risk.reasons.length ? (
                <li className="muted">No adverse signals on this account.</li>
              ) : null}
            </ol>
            <p className="note">{risk.method}</p>
          </section>

          <section className="panel panel--playbook">
            <div className="panel__head">
              <span className="panel__title">Recommended playbook</span>
              <span className="source">
                {playbook.primary.owner} · {playbook.primary.channel.replace("_", " ")}
              </span>
            </div>

            <h3 className="playbook__name">{playbook.primary.name}</h3>
            <p className="playbook__objective">{playbook.primary.objective}</p>

            <ul className="playbook__rationale">
              {playbook.primary.rationale.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>

            <blockquote className="playbook__script">
              {playbook.primary.script
                .replace("{officer}", account.officer || "your officer")
                .replace("{lender}", "Northline Finance")
                .replace("{contact}", account.contact_name)
                .replace("{instalment}", moneyFull(account.instalment))
                .replace("{outstanding}", moneyFull(account.arrears_amount || account.instalment))
                .replace("{account_ref}", account.ref)
                .replace("{due_date}", shortDate(account.next_due_date))
                .replace("{payment_link}", `pay.northline.ng/${account.ref.toLowerCase()}`)
                .replace("{part_amount}", moneyFull(Math.round(account.instalment * 0.4)))
                .replace("{review_date}", "the 28th")
                .replace("{due_day}", "25th")}
            </blockquote>

            <dl className="playbook__facts">
              <div>
                <dt>Timing</dt>
                <dd>{playbook.primary.timing}</dd>
              </div>
              <div>
                <dt>Success means</dt>
                <dd>{playbook.primary.success_metric}</dd>
              </div>
              <div>
                <dt>Attempt cost</dt>
                <dd>{money(playbook.primary.channel_cost)}</dd>
              </div>
              <div>
                <dt>Assumed conversion</dt>
                <dd>{percent(playbook.primary.effectiveness * 100, 0)}</dd>
              </div>
            </dl>

            <div className="playbook__alts">
              <span className="eyebrow">Alternates</span>
              {playbook.alternates.map((alt) => (
                <span className="chip" key={alt.code}>
                  {alt.name} · {percent(alt.effectiveness * 100, 0)}
                </span>
              ))}
            </div>
          </section>

          <ActionForm
            account={account}
            meta={meta}
            playbook={playbook}
            busy={busy}
            onSubmit={logAction}
          />

          {openPromises.length ? (
            <section className="panel">
              <div className="panel__head">
                <span className="panel__title">Open promises</span>
                <span className="source">{openPromises.length} awaiting outcome</span>
              </div>
              <ul className="promises">
                {openPromises.map((promise) => (
                  <li key={promise.id}>
                    <div>
                      <span className="promises__amount tnum">{moneyFull(promise.amount)}</span>
                      <span className="stat__note">
                        Promised for {shortDate(promise.promised_date)} · taken {shortDate(promise.made_at)}
                      </span>
                    </div>
                    <div className="promises__actions">
                      <button
                        className="btn btn--sm"
                        type="button"
                        disabled={busy}
                        onClick={() => resolve(promise.id, true)}
                      >
                        Kept
                      </button>
                      <button
                        className="btn btn--ghost btn--sm"
                        type="button"
                        disabled={busy}
                        onClick={() => resolve(promise.id, false)}
                      >
                        Broken
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="note">
                Marking a promise kept settles it against the oldest overdue instalment and moves the
                delinquency band.
              </p>
            </section>
          ) : null}
        </div>

        <div className="acct__col">
          <section className="panel">
            <div className="panel__head">
              <span className="panel__title">What is at stake</span>
              <span className="source">Expected-value build-up</span>
            </div>
            <dl className="ev">
              <div className="ev__row">
                <dt>Balance at stake</dt>
                <dd>{money(value.balance_at_stake)}</dd>
              </div>
              <div className="ev__row">
                <dt>Reachable this cycle</dt>
                <dd>{money(value.value_at_stake)}</dd>
              </div>
              <div className="ev__row ev__row--sub">
                <dt>{value.reachable_basis}</dt>
                <dd />
              </div>
              <div className="ev__row">
                <dt>Loss given default</dt>
                <dd>{percent(value.loss_given_default * 100, 0)}</dd>
              </div>
              <div className="ev__row">
                <dt>Probability of loss if left</dt>
                <dd>{percent(value.probability_of_loss * 100, 0)}</dd>
              </div>
              <div className="ev__row">
                <dt>Loss at risk</dt>
                <dd>{money(value.loss_at_risk)}</dd>
              </div>
              <div className="ev__row">
                <dt>Playbook conversion</dt>
                <dd>{percent(value.playbook_effectiveness * 100, 0)}</dd>
              </div>
              <div className="ev__row ev__row--total">
                <dt>Expected recovery from acting</dt>
                <dd style={{ color: "var(--resolve)" }}>{moneyFull(value.expected_recovery)}</dd>
              </div>
              <div className="ev__row">
                <dt>Cost of one attempt</dt>
                <dd>{moneyFull(value.attempt_cost)}</dd>
              </div>
              <div className="ev__row">
                <dt>Return per naira spent</dt>
                <dd>
                  {value.attempt_cost
                    ? `${(value.expected_recovery / value.attempt_cost).toFixed(1)}×`
                    : "—"}
                </dd>
              </div>
            </dl>
            <p className="note">
              Every input above is an explicit assumption, published in the model card, so a credit
              committee can disagree with the number instead of distrusting it.
            </p>
          </section>

          <section className="panel">
            <div className="panel__head">
              <span className="panel__title">Repayment record</span>
              <span className="source">
                {account.instalments_paid} of {account.instalments_due} instalments settled
              </span>
            </div>
            <div className="schedule" aria-label="Instalment schedule">
              {(data.schedule ?? []).map((row) => (
                <span
                  key={row.seq}
                  className={`schedule__cell schedule__cell--${row.status}`}
                  title={`Instalment ${row.seq} · due ${shortDate(row.due_date)} · ${moneyFull(row.amount_due)} · ${row.status}`}
                />
              ))}
            </div>
            <div className="legend">
              <span><i className="legend__swatch schedule__cell--paid" />paid</span>
              <span><i className="legend__swatch schedule__cell--partial" />part</span>
              <span><i className="legend__swatch schedule__cell--unpaid" />unpaid</span>
            </div>

            <div className="table-wrap" style={{ marginTop: "var(--s-4)" }}>
              <table className="table table--tight">
                <thead>
                  <tr>
                    <th>Paid</th>
                    <th>Channel</th>
                    <th>Source</th>
                    <th className="numeric">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.payments ?? []).slice(0, 8).map((payment, index) => (
                    <tr key={`${payment.paid_date}-${index}`}>
                      <td className="mono">{shortDate(payment.paid_date)}</td>
                      <td className="muted">{payment.channel.replace(/_/g, " ")}</td>
                      <td className="muted">{payment.source.replace(/_/g, " ")}</td>
                      <td className="numeric">{moneyFull(payment.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="panel__head">
              <span className="panel__title">Operating cash flow</span>
              <span className="source">
                {cashflow.length} months ·{" "}
                {data.cashflow?.change_pct !== null && data.cashflow?.change_pct !== undefined
                  ? `${data.cashflow.change_pct}% vs prior quarter`
                  : "no feed"}
              </span>
            </div>
            <Sparkline
              values={cashflow.map((row) => row.inflow)}
              width={620}
              height={110}
              tone={data.cashflow?.change_pct < 0 ? "var(--signal)" : "var(--ink-2)"}
              fill
            />
            <div className="cashflow__axis">
              <span className="source">{monthLabel(cashflow[0]?.month)}</span>
              <span className="source">{monthLabel(cashflow.at(-1)?.month)}</span>
            </div>
            <div className="cashflow__grid">
              {(cashflow.slice(-6) ?? []).map((row) => (
                <div className="cashflow__cell" key={row.month}>
                  <span className="eyebrow">{monthLabel(row.month)}</span>
                  <span className="tnum">{money(row.inflow)}</span>
                  <span className="source">bal {money(row.closing_balance)}</span>
                </div>
              ))}
            </div>
            {account.monitoring_consent !== "active" ? (
              <p className="note note--signal">
                This account is not under a live data feed, so the figures above come from the most
                recent statement on file rather than continuous monitoring.
              </p>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel__head">
              <span className="panel__title">Account timeline</span>
              <span className="source">{data.timeline?.length ?? 0} events</span>
            </div>
            <ol className="timeline">
              {(data.timeline ?? []).slice(0, 18).map((event, index) => (
                <li key={`${event.kind}-${event.at}-${index}`} className={`timeline__item timeline__item--${event.kind}`}>
                  <span className="timeline__at">{shortDate(event.at)}</span>
                  <span className="timeline__title">{event.title}</span>
                  <span className="timeline__sub">{event.subtitle}</span>
                  {event.detail ? <span className="timeline__detail">{event.detail}</span> : null}
                </li>
              ))}
              {!(data.timeline ?? []).length ? (
                <li className="muted">No activity recorded yet.</li>
              ) : null}
            </ol>
          </section>

          {(data.siblings ?? []).length ? (
            <section className="panel">
              <div className="panel__head">
                <span className="panel__title">Other facilities</span>
                <span className="source">Same borrower</span>
              </div>
              <ul className="siblings">
                {data.siblings.map((sibling) => (
                  <li key={sibling.id}>
                    <button type="button" onClick={() => navigate(`/app/account/${sibling.id}`)}>
                      <span className="name">{sibling.product_name}</span>
                      <span className="ref">{sibling.ref}</span>
                      <span className="tnum">{money(sibling.outstanding_principal)}</span>
                      <span className="tnum muted">{sibling.dpd > 0 ? `${sibling.dpd}d` : "current"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ActionForm({ account, meta, playbook, busy, onSubmit }) {
  const [channel, setChannel] = useState(playbook.primary.channel);
  const [disposition, setDisposition] = useState("promise_to_pay");
  const [officer, setOfficer] = useState(account.officer);
  const [notes, setNotes] = useState("");
  const [promisedDate, setPromisedDate] = useState("2026-10-19");
  const [promisedAmount, setPromisedAmount] = useState(
    Math.round(account.arrears_amount || account.instalment),
  );
  const [playbookCode, setPlaybookCode] = useState(playbook.primary.code);

  const needsPromise = disposition === "promise_to_pay";
  const selectedChannel = (meta?.channels ?? []).find((item) => item.code === channel);

  return (
    <section className="panel panel--action">
      <div className="panel__head">
        <span className="panel__title">Record what you did</span>
        <span className="source">
          costs {money(selectedChannel?.cost ?? 0)} · every attempt is logged
        </span>
      </div>

      <div className="form">
        <Select
          label="Playbook"
          value={playbookCode}
          onChange={setPlaybookCode}
          options={(meta?.playbooks ?? []).map((item) => ({
            value: item.code,
            label: item.name,
            hint: item.owner,
          }))}
        />

        <Select
          label="Channel"
          value={channel}
          onChange={setChannel}
          options={(meta?.channels ?? []).map((item) => ({
            value: item.code,
            label: item.label,
            hint: money(item.cost),
          }))}
        />

        <Select
          label="Outcome"
          value={disposition}
          onChange={setDisposition}
          options={(meta?.dispositions ?? []).map((item) => ({
            value: item.code,
            label: item.label,
          }))}
        />

        <Select
          label="Officer"
          value={officer}
          onChange={setOfficer}
          options={(meta?.officers ?? [account.officer]).map((name) => ({
            value: name,
            label: name,
          }))}
        />

        {needsPromise ? (
          <>
            <label className="field">
              <span className="eyebrow">Promised date</span>
              <input
                type="date"
                value={promisedDate}
                onChange={(event) => setPromisedDate(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="eyebrow">Promised amount</span>
              <input
                type="number"
                value={promisedAmount}
                min="0"
                step="1000"
                onChange={(event) => setPromisedAmount(Number(event.target.value))}
              />
            </label>
          </>
        ) : null}

        <label className="field field--full">
          <span className="eyebrow">Notes</span>
          <textarea
            rows={2}
            value={notes}
            placeholder="What was said, and what happens next."
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
      </div>

      <button
        className="btn btn--signal"
        type="button"
        disabled={busy}
        onClick={() =>
          onSubmit({
            channel,
            disposition,
            officer,
            playbook_code: playbookCode,
            notes,
            promised_date: needsPromise ? promisedDate : null,
            promised_amount: needsPromise ? promisedAmount : null,
          })
        }
      >
        {busy ? "Saving…" : "Log contact"}
      </button>
    </section>
  );
}

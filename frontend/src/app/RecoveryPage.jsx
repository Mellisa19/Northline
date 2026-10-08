import { DistributionBars } from "../components/charts";
import { endpoints, useApi } from "../lib/api";
import { money, number, percent, shortDate } from "../lib/format";

export default function RecoveryPage() {
  const { data, error, loading } = useApi(endpoints.recovery());
  const ledger = data?.ledger;
  const performance = data?.performance;

  if (loading && !data) return <p className="page__note">Loading ledger…</p>;
  if (error) return <p className="page__error">{error}</p>;

  const holdout = ledger?.holdout ?? {};

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">
            Rolling {ledger?.window_days ?? 90} days · snapshot {ledger?.snapshot_month ?? "—"}
          </p>
          <p className="page__lead">
            What came in, what it cost, and — separately — what the holdout slice says about the
            intervention itself.
          </p>
        </div>
        <div className="page__head-stats">
          <HeadStat
            label="Collected on delinquent accounts"
            value={money(ledger?.collected_on_delinquent_accounts ?? 0)}
          />
          <HeadStat label="Cost to collect" value={money(ledger?.cost ?? 0)} note={`${number(ledger?.attempts ?? 0)} attempts`} />
          <HeadStat
            label="Promises kept"
            value={percent(ledger?.promise_kept?.kept_rate ?? 0, 0)}
            tone="var(--resolve)"
            note={`${money(ledger?.promise_kept?.value ?? 0)} settled`}
          />
        </div>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Holdout slice</span>
          <span className="source">worked against deliberately unworked</span>
        </div>
        <div className="holdout holdout--wide">
          {[
            { key: "worked", label: "Worked", data: holdout.worked, tone: "var(--signal)" },
            { key: "control", label: "Left alone", data: holdout.control, tone: "var(--ink-4)" },
          ].map((arm) => (
            <div className="holdout__arm" key={arm.key}>
              <span className="eyebrow">{arm.label}</span>
              <span className="figure figure--lg" style={{ color: arm.tone }}>
                {percent(arm.data?.cure_rate ?? 0, 0)}
              </span>
              <span className="stat__note">
                cured · {number(arm.data?.accounts ?? 0)} accounts · average{" "}
                {arm.data?.avg_dpd ?? "—"} days past due · {money(arm.data?.arrears ?? 0)} arrears
              </span>
            </div>
          ))}
          <div className="holdout__arm">
            <span className="eyebrow">Incremental estimate</span>
            <span className="figure figure--lg" style={{ color: "var(--resolve)" }}>
              {ledger?.incremental_recovery_estimate
                ? money(ledger.incremental_recovery_estimate)
                : "—"}
            </span>
            <span className="stat__note">Not claimed where the sample is too small</span>
          </div>
        </div>
        <p className="note note--signal">{ledger?.interpretation}</p>
        {ledger?.sample_note ? <p className="note">{ledger.sample_note}</p> : null}
      </section>

      <div className="cols-2">
        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Playbook performance</span>
            <span className="source">every logged attempt</span>
          </div>
          <div className="table-wrap">
            <table className="table table--tight">
              <thead>
                <tr>
                  <th>Playbook</th>
                  <th className="numeric">Attempts</th>
                  <th className="numeric">Kept</th>
                  <th className="numeric">Cost / kept</th>
                </tr>
              </thead>
              <tbody>
                {(performance?.by_playbook ?? []).map((row) => (
                  <tr key={row.code}>
                    <td className="name">{row.name}</td>
                    <td className="numeric">{number(row.attempts)}</td>
                    <td className="numeric">
                      {row.kept_rate === null ? "—" : percent(row.kept_rate, 0)}
                    </td>
                    <td className="numeric">{row.cost_per_kept ? money(row.cost_per_kept) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Channel economics</span>
            <span className="source">cost per successful contact</span>
          </div>
          <DistributionBars
            rows={(performance?.by_channel ?? []).map((row) => ({
              label: row.channel.replace(/_/g, " "),
              value: row.win_rate,
              tone: "var(--signal)",
              display: `${row.win_rate}% · ${row.cost_per_win ? money(row.cost_per_win) : "—"}`,
            }))}
          />
          <p className="note">
            Win rate is promises kept or accounts restructured per attempt. Sending a message is cheap;
            a field visit is not, and the difference has to be visible.
          </p>
        </section>
      </div>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Officer productivity</span>
          <span className="source">not a league table on volume alone</span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Officer</th>
                <th className="numeric">Attempts</th>
                <th className="numeric">Wins</th>
                <th className="numeric">Win rate</th>
                <th className="numeric">Cost</th>
                <th>Profile</th>
              </tr>
            </thead>
            <tbody>
              {(performance?.by_officer ?? []).map((row) => (
                <tr key={row.officer}>
                  <td className="name">{row.officer}</td>
                  <td className="numeric">{number(row.attempts)}</td>
                  <td className="numeric">{number(row.wins)}</td>
                  <td className="numeric">{percent(row.win_rate, 0)}</td>
                  <td className="numeric">{money(row.cost)}</td>
                  <td>
                    <span className="riskbar">
                      <span
                        className="riskbar__fill"
                        style={{ width: `${Math.min(100, row.win_rate)}%`, background: "var(--resolve)" }}
                      />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Recovered after write-off</span>
          <span className="source">off-book recovery</span>
        </div>
        <div className="writeoff">
          <div className="stat">
            <span className="eyebrow">Written-off accounts</span>
            <span className="figure figure--lg">{number(ledger?.written_off?.accounts ?? 0)}</span>
          </div>
          <div className="stat">
            <span className="eyebrow">Recovered to date</span>
            <span className="figure figure--lg" style={{ color: "var(--resolve)" }}>
              {money(ledger?.written_off?.recovered ?? 0)}
            </span>
          </div>
          <p className="note">
            Recovery does not stop at write-off. Northline keeps the account in the recovery book and
            keeps attributing cash to it, because writing a balance down is an accounting decision, not
            a collections one.
          </p>
        </div>
      </section>
    </div>
  );
}

function HeadStat({ label, value, note, tone }) {
  return (
    <div className="headstat">
      <span className="eyebrow">{label}</span>
      <span className="figure figure--md" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {note ? <span className="stat__note">{note}</span> : null}
    </div>
  );
}

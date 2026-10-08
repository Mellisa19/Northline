import { DistributionBars, MigrationMatrix, ParTrend, VintageChart } from "../components/charts";
import { endpoints, useApi } from "../lib/api";
import { money, number, percent } from "../lib/format";

export default function ReportsPage() {
  const { data: summary, error } = useApi(endpoints.summary());
  const { data: trend } = useApi(endpoints.parTrend(18));
  const { data: migration } = useApi(endpoints.migration());
  const { data: vintages } = useApi(endpoints.vintages());
  const { data: advance } = useApi(endpoints.advanceWarning());

  if (error) return <p className="page__error">{error}</p>;

  const bands = summary?.band_distribution ?? [];
  const cohorts = Object.keys(vintages?.cohorts ?? {}).length;

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">Portfolio reporting</p>
          <p className="page__lead">
            Roll rates, migration and vintages, rebuilt from dated cash movements rather than from a
            month-end spreadsheet someone typed up.
          </p>
        </div>
        <div className="page__head-stats">
          <HeadStat label="Live accounts" value={number(summary?.accounts ?? 0)} note={`${number(summary?.borrowers ?? 0)} borrowers`} />
          <HeadStat label="Book" value={money(summary?.book_principal ?? 0)} />
          <HeadStat label="Arrears" value={money(summary?.arrears_total ?? 0)} tone="var(--signal)" />
        </div>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Portfolio at risk</span>
          <span className="source">share of outstanding value, monthly</span>
        </div>
        <ParTrend series={trend?.series ?? []} height={250} />
      </section>

      <div className="cols-2">
        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Delinquency distribution</span>
            <span className="source">accounts and value</span>
          </div>
          <DistributionBars
            rows={bands.map((band) => ({
              label: band.label,
              value: band.value,
              tone:
                band.band === 0
                  ? "var(--band-0)"
                  : band.band === 1
                    ? "var(--band-1)"
                    : band.band === 2
                      ? "var(--band-2)"
                      : band.band === 3
                        ? "var(--band-3)"
                        : "var(--band-4)",
              display: `${money(band.value)} · ${band.accounts}`,
            }))}
            max={Math.max(...bands.map((band) => band.value), 1)}
          />
          <p className="note">
            Value-weighted, not count-weighted: a handful of large accounts can carry more risk than
            hundreds of small ones, and the two orderings tell different stories.
          </p>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Early-warning performance</span>
            <span className="source">measured, not asserted</span>
          </div>
          <dl className="ev">
            <div className="ev__row">
              <dt>Accounts that reached 31+ days past due ({advance?.window_months ?? 15}m)</dt>
              <dd>{number(advance?.accounts_reaching_31dpd ?? 0)}</dd>
            </div>
            <div className="ev__row">
              <dt>Flagged in advance — whole book</dt>
              <dd>{percent(advance?.detection_rate_pct ?? 0, 0)}</dd>
            </div>
            <div className="ev__row">
              <dt>Flagged in advance — accounts with a live feed</dt>
              <dd style={{ color: "var(--signal)" }}>
                {percent(advance?.detection_rate_monitored_pct ?? 0, 0)}
              </dd>
            </div>
            <div className="ev__row">
              <dt>Median advance warning</dt>
              <dd>{advance?.median_days ?? "—"} days</dd>
            </div>
            <div className="ev__row">
              <dt>Interquartile range</dt>
              <dd>
                {advance?.p25_days ?? "—"}–{advance?.p75_days ?? "—"} days
              </dd>
            </div>
            <div className="ev__row ev__row--sub">
              <dt>{advance?.method}</dt>
              <dd />
            </div>
          </dl>
        </section>
      </div>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Band migration</span>
          <span className="source">month over month · 2026</span>
        </div>
        <MigrationMatrix matrix={migration?.matrix ?? []} />
        <p className="note">
          The diagonal is inertia. The final column is the exit into write-off or closure. A book where
          the 90+ row barely moves is a book whose recovery process has stopped, not one whose
          borrowers have improved.
        </p>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Vintage curves</span>
          <span className="source">
            {cohorts} disbursement cohorts · cumulative 31+ days past due by months on book
          </span>
        </div>
        <VintageChart cohorts={vintages?.cohorts ?? {}} height={260} />
        <p className="note">
          Cumulative curves never fall: a cohort that has already gone bad cannot un-go-bad. Comparing
          the newest curve against older ones is how underwriting drift shows up before it reaches the
          loss line.
        </p>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">By product</span>
          <span className="source">where risk is concentrating</span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Product</th>
                <th className="numeric">Accounts</th>
                <th className="numeric">Outstanding</th>
                <th className="numeric">30+ past due</th>
                <th>Share of book</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.by_product ?? []).map((row) => (
                <tr key={row.code}>
                  <td className="name">{row.name}</td>
                  <td className="numeric">{number(row.accounts)}</td>
                  <td className="numeric">{money(row.value)}</td>
                  <td className="numeric">{percent(row.par30_pct, 1)}</td>
                  <td>
                    <span className="riskbar">
                      <span
                        className="riskbar__fill"
                        style={{
                          width: `${(row.value / (summary?.book_principal || 1)) * 100}%`,
                          background: "var(--ink-2)",
                        }}
                      />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

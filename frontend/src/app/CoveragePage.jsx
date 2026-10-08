import { DistributionBars } from "../components/charts";
import { endpoints, useApi } from "../lib/api";
import { money, number, percent } from "../lib/format";

export default function CoveragePage() {
  const { data, error, loading } = useApi(endpoints.coverage());

  if (loading && !data) return <p className="page__note">Loading coverage…</p>;
  if (error) return <p className="page__error">{error}</p>;

  const tiers = data?.by_tier ?? {};
  const tierRows = [
    { label: "Full feed", ...(tiers.full ?? {}) },
    { label: "Selective", ...(tiers.selective ?? {}) },
    { label: "No feed", ...(tiers.none ?? {}) },
  ];
  const totalAccounts = tierRows.reduce((sum, row) => sum + (row.accounts ?? 0), 0);

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">Monitoring coverage</p>
          <p className="page__lead">
            A live transaction feed costs money per account per month. Watching everything is not
            affordable and watching nothing is not lending. This screen is the trade-off, stated
            openly.
          </p>
        </div>
        <div className="page__head-stats">
          <HeadStat
            label="Accounts with active consent"
            value={number(data?.consented_accounts ?? 0)}
            note={`${percent(data?.coverage_pct ?? 0, 1)} of accounts`}
          />
          <HeadStat
            label="Value under coverage"
            value={percent(data?.coverage_value_pct ?? 0, 1)}
            tone="var(--resolve)"
            note={money(data?.consented_value ?? 0)}
          />
          <HeadStat
            label="Blind spot"
            value={number(data?.blind_spot_accounts ?? 0)}
            tone="var(--signal)"
            note={`${money(data?.blind_spot_value ?? 0)} at elevated risk, unmonitored`}
          />
        </div>
      </section>

      <div className="cols-2">
        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Coverage by tier</span>
            <span className="source">{number(totalAccounts)} accounts</span>
          </div>
          <DistributionBars
            rows={tierRows.map((row) => ({
              label: row.label,
              value: row.accounts ?? 0,
              tone: row.label === "No feed" ? "var(--ink-4)" : "var(--signal)",
              display: `${row.accounts ?? 0} · ${money(row.value ?? 0)}`,
            }))}
          />
          <p className="note">
            Tier is assigned by exposure and delinquency band, not by relationship. A ₦500k merchant
            advance does not justify a per-account data feed; a ₦40M asset-finance facility does.
          </p>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Consent position</span>
            <span className="source">scope, purpose, expiry</span>
          </div>
          <dl className="ev">
            <div className="ev__row">
              <dt>Active consent</dt>
              <dd>{number(data?.consented_accounts ?? 0)}</dd>
            </div>
            <div className="ev__row">
              <dt>Consent lapsed and awaiting renewal</dt>
              <dd style={{ color: "var(--signal)" }}>{number(data?.expired_accounts ?? 0)}</dd>
            </div>
            <div className="ev__row">
              <dt>Signals detected</dt>
              <dd>{number(data?.signals_total ?? 0)}</dd>
            </div>
            <div className="ev__row">
              <dt>Signals that require consent to act on</dt>
              <dd>{number(data?.signals_requiring_consent ?? 0)}</dd>
            </div>
          </dl>
          <p className="note">
            Transaction signals are only raised where consent is active. Where it has lapsed, the
            detection is still recorded and shown — the account is worked from the lender&rsquo;s own
            repayment records, and the gap is reported as a number rather than hidden.
          </p>
        </section>
      </div>
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

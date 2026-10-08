import { DistributionBars } from "../components/charts";
import { endpoints, useApi } from "../lib/api";
import { percent } from "../lib/format";

export default function ModelPage() {
  const { data, error, loading } = useApi(endpoints.modelCard());

  if (loading && !data) return <p className="page__note">Loading model card…</p>;
  if (error) return <p className="page__error">{error}</p>;

  const weights = data?.weights ?? {};
  const rows = Object.entries(weights)
    .map(([key, value]) => ({
      label: key.replace(/_/g, " "),
      value,
      tone: key === "delinquency" ? "var(--risk)" : key === "cashflow_decline" ? "var(--signal)" : "var(--ink-3)",
      display: `${value} pts`,
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">{data?.type}</p>
          <p className="page__lead">
            {data?.name}. {data?.outputs}. A lending model that cannot be argued with in a credit
            committee is not usable, however accurate it claims to be.
          </p>
        </div>
      </section>

      <div className="cols-2">
        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Component weights</span>
            <span className="source">sums to 100</span>
          </div>
          <DistributionBars rows={rows} />
          <p className="note">
            Weights are policy judgement, set by hand and published, not learned from outcomes. They are
            the most contestable part of the product, which is exactly why they are visible.
          </p>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Bands</span>
            <span className="source">index thresholds</span>
          </div>
          <ul className="bandlist">
            {(data?.bands ?? []).map((band) => (
              <li key={band.code}>
                <span className="bandlist__range tnum">
                  {band.min}–{band.max}
                </span>
                <span className="bandlist__label">{band.label}</span>
              </li>
            ))}
          </ul>
          <div className="panel__head" style={{ marginTop: "var(--s-5)" }}>
            <span className="panel__title">Priority thresholds</span>
          </div>
          <p className="note">
            An account is raised to <strong>high</strong> priority at roughly{" "}
            <span className="mono">₦250,000</span> of expected incremental recovery and to{" "}
            <strong>medium</strong> at <span className="mono">₦60,000</span>. The thresholds are a
            management choice about how much the team&rsquo;s day is worth.
          </p>
        </section>
      </div>

      <section className="panel panel--limits">
        <div className="panel__head">
          <span className="panel__title">Limitations</span>
          <span className="source">stated, not discovered</span>
        </div>
        <ul className="limitations">
          {(data?.limitations ?? []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Planned, not shipped</span>
          <span className="source">the honest roadmap</span>
        </div>
        <ul className="limitations limitations--planned">
          {(data?.planned ?? []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="note">
          No outcome-trained default model ships until twelve months of the lender&rsquo;s own logged
          dispositions exist. Until then the product ranks with a transparent index and says so.
        </p>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Expected-value assumptions</span>
          <span className="source">applied to every account</span>
        </div>
        <dl className="ev">
          <div className="ev__row">
            <dt>Reachable this cycle</dt>
            <dd>overdue balance + three instalments</dd>
          </div>
          <div className="ev__row">
            <dt>Loss given default</dt>
            <dd>per product: asset finance 34% · payroll 55% · working capital 58% · invoice 46% · merchant advance 72%</dd>
          </div>
          <div className="ev__row">
            <dt>Probability of loss</dt>
            <dd>max(band floor, risk index ÷ 100)</dd>
          </div>
          <div className="ev__row">
            <dt>Playbook conversion</dt>
            <dd>per playbook per band, published in the playbook library</dd>
          </div>
          <div className="ev__row">
            <dt>Attempt cost</dt>
            <dd>direct channel cost + officer minutes at ₦1,400 per hour</dd>
          </div>
        </dl>
        <p className="note">
          Change any of these and the ranking changes. That is the point: the model is an argument about
          how lending works, not a black box that settles it.
        </p>
      </section>
    </div>
  );
}

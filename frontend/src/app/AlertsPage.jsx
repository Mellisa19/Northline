import { useState } from "react";
import { endpoints, useApi } from "../lib/api";
import { bandTone, money, number, percent, shortDate } from "../lib/format";

const SEVERITY = { 3: "Acute", 2: "Material", 1: "Watch" };

export default function AlertsPage({ navigate }) {
  const [filter, setFilter] = useState("all");
  const { data, error, loading } = useApi(endpoints.alerts(120));

  if (loading && !data) return <p className="page__note">Loading signals…</p>;
  if (error) return <p className="page__error">{error}</p>;

  const alerts = data?.alerts ?? [];
  const visible =
    filter === "all"
      ? alerts
      : filter === "unactionable"
        ? alerts.filter((alert) => !alert.actionable)
        : alerts.filter((alert) => alert.actionable);

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">Signal feed</p>
          <p className="page__lead">
            Every change the engine detected, dated when it happened. Signals on accounts without a
            live consent are kept and shown — the blind spot is a number worth managing, not a gap to
            hide.
          </p>
        </div>
        <div className="page__head-stats">
          <HeadStat label="Signals" value={number(alerts.length)} />
          <HeadStat
            label="Actionable"
            value={number(alerts.filter((alert) => alert.actionable).length)}
            tone="var(--signal)"
          />
          <HeadStat
            label="Detected without coverage"
            value={number(alerts.filter((alert) => !alert.actionable).length)}
          />
        </div>
      </section>

      <div className="segmented segmented--inline">
        {[
          { key: "all", label: "All" },
          { key: "actionable", label: "Actionable" },
          { key: "unactionable", label: "Outside coverage" },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            className={filter === item.key ? "is-active" : ""}
            onClick={() => setFilter(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <ul className="alerts">
        {visible.map((alert) => (
          <li
            key={alert.id}
            className={`alert${alert.actionable ? "" : " alert--blocked"}`}
            onClick={() => navigate(`/app/account/${alert.account_id}`)}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter") navigate(`/app/account/${alert.account_id}`);
            }}
          >
            <span className="alert__severity" style={{ background: bandTone(alert.band) }} />
            <div className="alert__body">
              <div className="alert__head">
                <span className="alert__label">{alert.label}</span>
                <span className="alert__level">{SEVERITY[alert.severity] ?? "Watch"}</span>
                {!alert.actionable ? (
                  <span className="chip chip--quiet">No monitoring consent</span>
                ) : null}
                {alert.lead_days ? (
                  <span className="chip chip--signal">{alert.lead_days} days early</span>
                ) : null}
              </div>
              <p className="alert__headline">{alert.headline}</p>
              <div className="alert__meta">
                <button
                  type="button"
                  className="alert__borrower"
                  onClick={(event) => {
                    event.stopPropagation();
                    navigate(`/app/account/${alert.account_id}`);
                  }}
                >
                  {alert.borrower_name}
                </button>
                <span className="ref">{alert.ref}</span>
                <span className="muted">{alert.sector}</span>
                <span className="tnum">{money(alert.outstanding_principal)}</span>
                <span className="muted">
                  {alert.dpd > 0 ? `${alert.dpd} days past due` : alert.band_label}
                </span>
                <span className="source">detected {shortDate(alert.detected_at)}</span>
              </div>
            </div>
          </li>
        ))}
        {!visible.length ? <li className="muted">Nothing in this view.</li> : null}
      </ul>
    </div>
  );
}

function HeadStat({ label, value, tone }) {
  return (
    <div className="headstat">
      <span className="eyebrow">{label}</span>
      <span className="figure figure--md" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
    </div>
  );
}

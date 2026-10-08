import { useRef, useState } from "react";
import { postFile } from "../lib/api";
import { money, number, percent } from "../lib/format";
import "./site.css";
import "./triage.css";

/* ==========================================================================
   The lead magnet: run the prospect's own loan tape through the same engine.
   No account, no integration, nothing stored.
   ========================================================================== */

const REQUIRED = ["borrower_name", "outstanding", "instalment", "dpd"];

export default function TriagePage({ navigate }) {
  const [state, setState] = useState({ status: "idle", error: null, result: null });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  async function submit(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setState({ status: "error", error: "That file is not a .csv. Export your loan tape as CSV.", result: null });
      return;
    }
    setState({ status: "loading", error: null, result: null });
    try {
      const result = await postFile("/triage", file);
      setState({ status: "done", error: null, result });
    } catch (error) {
      setState({ status: "error", error: error.message, result: null });
    }
  }

  return (
    <div className="site triage">
      <header className="masthead is-scrolled">
        <div className="shell masthead__inner">
          <a className="brand" href="/" onClick={(event) => { event.preventDefault(); navigate("/"); }}>
            <span className="brand__mark" aria-hidden="true">
              <svg viewBox="0 0 32 32" width="26" height="26">
                <rect width="32" height="32" fill="var(--ink)" />
                <path d="M7 24V8h3.1l7.4 10.2V8H21v16h-3.1L10.5 13.8V24H7z" fill="var(--paper)" />
                <rect x="23" y="8" width="2.4" height="16" fill="var(--signal)" />
              </svg>
            </span>
            <span className="brand__text">
              <strong>Northline</strong>
              <small>Credit &amp; Recovery Intelligence</small>
            </span>
          </a>
          <div className="masthead__actions">
            <button className="btn btn--ghost btn--sm" type="button" onClick={() => navigate("/app")}>
              Open workspace
            </button>
          </div>
        </div>
      </header>

      <main className="shell triage__main">
        <div className="triage__intro">
          <p className="eyebrow eyebrow--signal">Loan tape triage</p>
          <h1 className="display triage__headline">
            Put your own book
            <br />
            through it.
          </h1>
          <p className="lede" style={{ marginTop: "var(--s-4)" }}>
            Export a CSV of your live accounts and see the queue this produces: who to work today,
            what to do with them, and what your current ordering is leaving behind. The file is held
            in memory for this response only.
          </p>

          <div
            className={`dropzone${dragging ? " is-dragging" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              submit(event.dataTransfer.files?.[0]);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => submit(event.target.files?.[0])}
              hidden
            />
            <p className="dropzone__lead">Drop a CSV here, or</p>
            <button className="btn" type="button" onClick={() => inputRef.current?.click()}>
              Choose a file
            </button>
            <p className="note" style={{ marginTop: "var(--s-4)" }}>
              Required columns: <span className="mono">{REQUIRED.join(", ")}</span>. Optional:{" "}
              <span className="mono">product, principal, arrears, monthly_inflow, inflow_change_pct</span>.
            </p>
            <a className="triage__template" href="/api/triage/template" download="northline-loan-tape-template.csv">
              Download the template
            </a>
          </div>

          {state.status === "error" && (
            <p className="triage__error" role="alert">
              {state.error}
            </p>
          )}
          {state.status === "loading" && <p className="note">Scoring the tape…</p>}
        </div>

        {state.result ? <TriageResult result={state.result} /> : <TriageBlurb />}
      </main>
    </div>
  );
}

function TriageBlurb() {
  const points = [
    {
      title: "The same weights the product uses",
      body: "Nine documented components, published in the model card. No separate marketing algorithm.",
    },
    {
      title: "Ordered by money, not by age",
      body: "Expected recovery after loss-given-default and playbook effectiveness, so the top of the list is worth a phone call.",
    },
    {
      title: "Your ordering, compared",
      body: "The result shows what sorting by days past due would reach over the same number of reviews.",
    },
  ];
  return (
    <aside className="triage__aside">
      {points.map((point) => (
        <article key={point.title} className="triage__point">
          <h3>{point.title}</h3>
          <p>{point.body}</p>
        </article>
      ))}
    </aside>
  );
}

function TriageResult({ result }) {
  const rows = result.worklist ?? [];
  const ranking = result.ranking ?? {};

  return (
    <section className="triage__result rise">
      <div className="triage__kpis">
        <Kpi label="Accounts scored" value={number(result.accounts)} />
        <Kpi label="Book outstanding" value={money(result.book_outstanding)} />
        <Kpi
          label="30+ days past due"
          value={percent(result.par30?.value_pct ?? 0, 0)}
          note={`${percent(result.par30?.count_pct ?? 0, 0)} of accounts`}
          tone="var(--signal)"
        />
        <Kpi
          label="Recoverable this cycle"
          value={money(result.expected_recovery_available)}
          tone="var(--resolve)"
          note="Expected incremental recovery"
        />
      </div>

      <div className="triage__compare">
        <div>
          <span className="eyebrow">Ordered by Northline</span>
          <span className="figure figure--md">{money(ranking.northline?.expected_recovery ?? 0)}</span>
          <span className="stat__note">
            {percent(ranking.northline?.value_share_pct ?? 0, 0)} of available value
          </span>
        </div>
        <div>
          <span className="eyebrow">Ordered by days past due</span>
          <span className="figure figure--md">{money(ranking.baseline_dpd_order?.expected_recovery ?? 0)}</span>
          <span className="stat__note">
            {percent(ranking.baseline_dpd_order?.value_share_pct ?? 0, 0)} of available value
          </span>
        </div>
        <div className="triage__lift">
          <span className="eyebrow">Difference</span>
          <span className="figure figure--md" style={{ color: "var(--signal)" }}>
            {ranking.lift_vs_dpd_order ?? "—"}×
          </span>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: "34px" }}>#</th>
              <th>Borrower</th>
              <th className="numeric">Days past due</th>
              <th className="numeric">Outstanding</th>
              <th className="numeric">Risk index</th>
              <th>Why it is here</th>
              <th>Recommended playbook</th>
              <th className="numeric">Expected recovery</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 60).map((row, index) => (
              <tr key={`${row.borrower_name}-${index}`}>
                <td className="ref">{index + 1}</td>
                <td className="name">{row.borrower_name}</td>
                <td className="numeric">{row.dpd}</td>
                <td className="numeric">{money(row.outstanding)}</td>
                <td className="numeric">{row.risk_index}</td>
                <td className="muted">{row.reasons?.[0]?.label ?? "—"}</td>
                <td className="muted">{row.playbook}</td>
                <td className="numeric">{money(row.expected_recovery)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="note" style={{ marginTop: "var(--s-4)" }}>
        {result.note}
      </p>
    </section>
  );
}

function Kpi({ label, value, note, tone }) {
  return (
    <div className="stat">
      <span className="eyebrow">{label}</span>
      <span className="figure figure--lg" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {note ? <span className="stat__note">{note}</span> : null}
    </div>
  );
}

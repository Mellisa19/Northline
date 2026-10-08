import { useMemo, useState } from "react";
import { Avatar, CountUp, Segmented, Select } from "../components/ui";
import { endpoints, useApi } from "../lib/api";
import { useDebounced } from "../lib/motion";
import { bandTone, money, number, percent, riskTone } from "../lib/format";

const BUDGETS = [
  { value: 25, label: "25" },
  { value: 50, label: "50" },
  { value: 100, label: "100" },
  { value: 200, label: "200" },
  { value: 0, label: "All" },
];

const BAND_OPTIONS = [
  { value: "", label: "Any band" },
  { value: "0", label: "Current", tone: "var(--band-0)" },
  { value: "1", label: "1–30 days", tone: "var(--band-1)" },
  { value: "2", label: "31–60 days", tone: "var(--band-2)" },
  { value: "3", label: "61–90 days", tone: "var(--band-3)" },
  { value: "4", label: "90+ days", tone: "var(--band-4)" },
];

const PRODUCT_OPTIONS = [
  { value: "", label: "Any product" },
  { value: "WC", label: "Working capital" },
  { value: "AF", label: "Asset finance" },
  { value: "ID", label: "Invoice discounting" },
  { value: "MCA", label: "Merchant advance" },
  { value: "PAY", label: "Payroll advance" },
];

export default function WorklistPage({ navigate }) {
  const [budget, setBudget] = useState(25);
  const [officer, setOfficer] = useState("");
  const [band, setBand] = useState("");
  const [product, setProduct] = useState("");
  const [search, setSearch] = useState("");
  const query = useDebounced(search);

  const { data: meta } = useApi(endpoints.meta());
  const path = endpoints.worklist({
    budget: budget || undefined,
    officer,
    band,
    product,
    search: query,
  });
  const { data, loading, error } = useApi(path);

  const rows = data?.rows ?? [];
  const ranking = data?.ranking;

  const queue = useMemo(() => {
    const value = rows.reduce((sum, row) => sum + row.expected_recovery, 0);
    const exposure = rows.reduce((sum, row) => sum + row.exposure, 0);
    return {
      value,
      exposure,
      late: rows.filter((row) => row.dpd > 0).length,
      early: rows.filter((row) => row.dpd === 0).length,
    };
  }, [rows]);

  const officerOptions = useMemo(
    () => [
      { value: "", label: "Any officer" },
      ...(meta?.relationship_managers ?? []).map((name) => ({ value: name, label: name })),
    ],
    [meta],
  );

  const filtered = Boolean(officer || band || product || query);

  return (
    <div className="page">
      <section className="queue">
        <div className="queue__figures">
          <div className="queue__figure queue__figure--primary">
            <span className="eyebrow">Recoverable in this queue</span>
            <span className="queue__value">
              <CountUp value={queue.value} format={money} />
            </span>
            <span className="queue__note">
              {percent(ranking?.northline?.value_share_pct ?? 0, 0)} of everything available today
            </span>
          </div>
          <div className="queue__figure">
            <span className="eyebrow">Accounts</span>
            <span className="queue__value queue__value--sm">
              <CountUp value={rows.length} format={number} />
            </span>
            <span className="queue__note">
              {queue.late} late · {queue.early} still current
            </span>
          </div>
          <div className="queue__figure">
            <span className="eyebrow">Exposure covered</span>
            <span className="queue__value queue__value--sm">
              <CountUp value={queue.exposure} format={money} />
            </span>
            <span className="queue__note">balance on the accounts selected</span>
          </div>
          {ranking?.lift_vs_dpd_order ? (
            <div className="queue__figure queue__figure--lift">
              <span className="eyebrow">Against the old order</span>
              <span className="queue__value queue__value--sm">
                <CountUp value={ranking.lift_vs_dpd_order} format={(n) => `${n.toFixed(1)}×`} />
              </span>
              <span className="queue__note">
                vs sorting by days past due at {ranking.baseline_dpd_order.accounts} reviews
              </span>
            </div>
          ) : null}
        </div>
      </section>

      <section className="toolbar">
        <div className="toolbar__budget">
          <span className="eyebrow">Reviews today</span>
          <Segmented value={budget} onChange={setBudget} options={BUDGETS} />
        </div>

        <div className="toolbar__filters">
          <Select
            value={officer}
            onChange={setOfficer}
            options={officerOptions}
            placeholder="Any officer"
            size="sm"
          />
          <Select value={band} onChange={setBand} options={BAND_OPTIONS} placeholder="Any band" size="sm" />
          <Select
            value={product}
            onChange={setProduct}
            options={PRODUCT_OPTIONS}
            placeholder="Any product"
            size="sm"
          />
          <label className="search">
            <span className="search__icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" width="14" height="14">
                <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path d="M11 11l4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </span>
            <input
              type="search"
              value={search}
              placeholder="Borrower, reference, city"
              onChange={(event) => setSearch(event.target.value)}
            />
            {search ? (
              <button type="button" className="search__clear" onClick={() => setSearch("")} aria-label="Clear">
                ×
              </button>
            ) : null}
          </label>
          {filtered ? (
            <button
              type="button"
              className="toolbar__reset"
              onClick={() => {
                setOfficer("");
                setBand("");
                setProduct("");
                setSearch("");
              }}
            >
              Reset
            </button>
          ) : null}
        </div>
      </section>

      {error ? <p className="page__error">{error}</p> : null}

      <section className="table-wrap table-wrap--scroll">
        <table className="table worklist">
          <thead>
            <tr>
              <th style={{ width: "42px" }}>#</th>
              <th>Borrower</th>
              <th>Product</th>
              <th className="numeric">Past due</th>
              <th className="numeric">Outstanding</th>
              <th style={{ width: "118px" }}>Risk</th>
              <th>Why it is here</th>
              <th>Do this</th>
              <th className="numeric">Expected recovery</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={row.id}
                style={{ "--i": Math.min(index, 14) }}
                onClick={() => navigate(`/app/account/${row.id}`)}
                tabIndex={0}
                role="button"
                onKeyDown={(event) => {
                  if (event.key === "Enter") navigate(`/app/account/${row.id}`);
                }}
              >
                <td className="ref">{index + 1}</td>
                <td>
                  <span className="cell-with-avatar">
                    <Avatar name={row.borrower_name} size={28} />
                    <span className="cell-stack">
                      <span className="name">{row.borrower_name}</span>
                      <span className="cell-sub">
                        {row.city} · {row.ref}
                      </span>
                    </span>
                  </span>
                </td>
                <td className="muted">{row.product_name}</td>
                <td className="numeric">
                  <span className="banddot" style={{ background: bandTone(row.band) }} />
                  {row.dpd > 0 ? row.dpd : "—"}
                </td>
                <td className="numeric">{money(row.outstanding_principal)}</td>
                <td>
                  <span className="riskbar" title={`Risk index ${row.risk_index}`}>
                    <span
                      className="riskbar__fill"
                      style={{ width: `${row.risk_index}%`, background: riskTone(row.risk_band_code) }}
                    />
                  </span>
                  <span className="riskbar__label">{Math.round(row.risk_index)}</span>
                </td>
                <td className="worklist__reason">{row.top_reason ?? "—"}</td>
                <td>
                  <span className="playbook-chip">{row.playbook_name}</span>
                </td>
                <td className="numeric worklist__value">{money(row.expected_recovery)}</td>
              </tr>
            ))}
            {!rows.length && !loading ? (
              <tr>
                <td colSpan={9} className="table__empty">
                  Nothing matches these filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        {loading ? <div className="table__loading">Refreshing…</div> : null}
      </section>

      <p className="page__note">
        Ranked by expected recovery after loss-given-default and playbook effectiveness. Every account
        leaves this queue with a recorded disposition.
      </p>
    </div>
  );
}

import { useId, useMemo } from "react";
import { monthLabel } from "../lib/format";

/* ==========================================================================
   Charts are built by hand rather than pulled from a charting library, so the
   data language stays consistent with the rest of the interface: thin rules,
   direct labelling, and one accent that means something.
   ========================================================================== */

function extent(values) {
  const clean = values.filter((value) => Number.isFinite(value));
  if (!clean.length) return [0, 1];
  let min = Math.min(...clean);
  let max = Math.max(...clean);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  return [min, max];
}

function linePath(points) {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point[0].toFixed(2)},${point[1].toFixed(2)}`)
    .join(" ");
}

/** Small trend line for a table cell or a stat block. */
export function Sparkline({ values, width = 92, height = 24, tone = "var(--ink)", fill = false }) {
  const clean = (values || []).map(Number);
  if (clean.length < 2) return <span className="sparkline-empty">—</span>;
  const [min, max] = extent(clean);
  const step = width / (clean.length - 1);
  const points = clean.map((value, index) => [
    index * step,
    height - ((value - min) / (max - min)) * (height - 4) - 2,
  ]);
  const path = linePath(points);
  const gradientId = useId();

  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {fill && (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={tone} stopOpacity="0.16" />
              <stop offset="100%" stopColor={tone} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${path} L${width},${height} L0,${height} Z`} fill={`url(#${gradientId})`} />
        </>
      )}
      <path d={path} fill="none" stroke={tone} strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={points.at(-1)[0]} cy={points.at(-1)[1]} r="2" fill={tone} />
    </svg>
  );
}

/**
 * Portfolio-at-risk trend. Three bands, direct end labels, no legend box.
 */
export function ParTrend({ series, height = 220 }) {
  const width = 720;
  const pad = { top: 18, right: 74, bottom: 26, left: 34 };
  const rows = series || [];
  if (rows.length < 2) return <ChartEmpty height={height} />;

  const values = rows.flatMap((row) => [row.par30_pct, row.par60_pct, row.par90_pct]);
  const [minValue, maxValue] = extent([...values, 0]);
  const max = Math.max(maxValue, 5);
  const min = 0;

  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (index) => pad.left + (index / (rows.length - 1)) * innerW;
  const y = (value) => pad.top + innerH - ((value - min) / (max - min)) * innerH;

  const lines = [
    { key: "par30_pct", tone: "var(--signal)", label: "30+" },
    { key: "par60_pct", tone: "var(--band-3)", label: "60+" },
    { key: "par90_pct", tone: "var(--risk)", label: "90+" },
  ];

  const ticks = [0, max / 2, max];

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Portfolio at risk by month">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} stroke="var(--rule-2)" strokeWidth="1" />
          <text x={pad.left - 8} y={y(tick) + 3} textAnchor="end" className="chart__tick">
            {tick.toFixed(0)}%
          </text>
        </g>
      ))}

      {lines.map((line) => {
        const points = rows.map((row, index) => [x(index), y(row[line.key] ?? 0)]);
        return (
          <g key={line.key}>
            <path d={linePath(points)} fill="none" stroke={line.tone} strokeWidth="1.6" strokeLinejoin="round" />
            <text x={x(rows.length - 1) + 8} y={points.at(-1)[1] + 4} className="chart__label" fill={line.tone}>
              {line.label}
            </text>
          </g>
        );
      })}

      {rows.map((row, index) =>
        index % Math.ceil(rows.length / 6) === 0 || index === rows.length - 1 ? (
          <text key={row.month} x={x(index)} y={height - 6} textAnchor="middle" className="chart__tick">
            {monthLabel(row.month)}
          </text>
        ) : null,
      )}
    </svg>
  );
}

/**
 * Month-over-month band migration. Reads as a heatmap: the diagonal is inertia,
 * the last column is the exit into write-off.
 */
export function MigrationMatrix({ matrix }) {
  const rows = matrix || [];
  if (!rows.length) return <ChartEmpty height={180} />;
  const targets = rows[0].transitions;

  return (
    <div className="matrix" role="table" aria-label="Delinquency band migration">
      <div className="matrix__row matrix__row--head">
        <div className="matrix__corner">
          <span className="eyebrow">From \ To</span>
        </div>
        {targets.map((target) => (
          <div className="matrix__cell matrix__cell--head" key={target.to_band}>
            <span>{target.to_label}</span>
          </div>
        ))}
      </div>

      {rows.map((row) => (
        <div className="matrix__row" key={row.from_band}>
          <div className="matrix__corner matrix__corner--row">
            <span className="matrix__from">{row.from_label}</span>
            <span className="matrix__n">{row.total.toLocaleString()} moves</span>
          </div>
          {row.transitions.map((cell) => (
            <div
              className="matrix__cell"
              key={cell.to_band}
              style={{
                background: cell.pct > 0 ? `rgba(22, 23, 26, ${Math.min(0.82, 0.05 + cell.pct / 100)})` : "transparent",
                color: cell.pct > 42 ? "var(--paper)" : "var(--ink)",
              }}
              title={`${row.from_label} to ${cell.to_label}: ${cell.pct}%`}
            >
              <span className="matrix__pct">{cell.pct >= 0.5 ? `${cell.pct.toFixed(0)}%` : "·"}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Cumulative default curves by disbursement cohort. The newest cohort carries the
 * accent; older ones recede so the shape is readable.
 */
export function VintageChart({ cohorts, height = 240 }) {
  const width = 720;
  const pad = { top: 18, right: 88, bottom: 28, left: 36 };
  const keys = useMemo(() => Object.keys(cohorts || {}).sort(), [cohorts]);
  if (keys.length < 2) return <ChartEmpty height={height} />;

  const maxMob = Math.max(...keys.flatMap((key) => cohorts[key].map((point) => point.months_on_book)));
  const maxPct = Math.max(...keys.flatMap((key) => cohorts[key].map((point) => point.cumulative_pct)), 10);
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (mob) => pad.left + (mob / maxMob) * innerW;
  const y = (pct) => pad.top + innerH - (pct / maxPct) * innerH;

  const ticks = [0, Math.round(maxPct / 2), Math.round(maxPct)];

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Cumulative default by vintage">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} stroke="var(--rule-2)" />
          <text x={pad.left - 8} y={y(tick) + 3} textAnchor="end" className="chart__tick">
            {tick}%
          </text>
        </g>
      ))}

      {[0, Math.round(maxMob / 2), maxMob].map((tick) => (
        <text key={tick} x={x(tick)} y={height - 8} textAnchor="middle" className="chart__tick">
          {tick}m
        </text>
      ))}

      {keys.map((key, index) => {
        const points = cohorts[key]
          .slice()
          .sort((a, b) => a.months_on_book - b.months_on_book)
          .map((point) => [x(point.months_on_book), y(point.cumulative_pct)]);
        const isLatest = index === keys.length - 1;
        const tone = isLatest
          ? "var(--signal)"
          : `rgba(22, 23, 26, ${0.5 - (keys.length - index) * 0.045})`;
        return (
          <g key={key}>
            <path
              d={linePath(points)}
              fill="none"
              stroke={tone}
              strokeWidth={isLatest ? 1.9 : 1}
              strokeLinejoin="round"
            />
            {isLatest && (
              <text x={points.at(-1)[0] + 8} y={points.at(-1)[1] + 4} className="chart__label" fill="var(--signal)">
                {monthLabel(key)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** Horizontal distribution bars with direct value labels. */
export function DistributionBars({ rows, tone, max }) {
  const top = max ?? Math.max(...(rows || []).map((row) => row.value ?? row.accounts ?? 0), 1);
  return (
    <div className="dist">
      {(rows || []).map((row) => {
        const value = row.value ?? row.accounts ?? 0;
        return (
          <div className="dist__row" key={row.label ?? row.code}>
            <span className="dist__label">{row.label}</span>
            <span className="dist__track">
              <span
                className="dist__fill"
                style={{ width: `${Math.max(1.5, (value / top) * 100)}%`, background: row.tone ?? tone ?? "var(--ink)" }}
              />
            </span>
            <span className="dist__value tnum">{row.display ?? value.toLocaleString()}</span>
          </div>
        );
      })}
    </div>
  );
}

/** A single 0–100 index shown against its band thresholds. */
export function IndexScale({ value, bandCode, tone }) {
  const marks = [
    { at: 20, label: "Watch" },
    { at: 40, label: "Elevated" },
    { at: 60, label: "High" },
    { at: 80, label: "Severe" },
  ];
  return (
    <div className="index-scale" data-band={bandCode}>
      <div className="index-scale__track">
        <span className="index-scale__fill" style={{ width: `${Math.max(1.5, value)}%`, background: tone }} />
        <span className="index-scale__pointer" style={{ left: `${Math.min(99, value)}%`, background: tone }} />
      </div>
      <div className="index-scale__marks">
        {marks.map((mark) => (
          <span key={mark.at} className="index-scale__mark" style={{ left: `${mark.at}%` }}>
            <span className="index-scale__tick" />
            <span className="index-scale__mark-label">{mark.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ChartEmpty({ height = 200 }) {
  return (
    <div className="chart-empty" style={{ height }}>
      <span className="eyebrow">No data</span>
    </div>
  );
}

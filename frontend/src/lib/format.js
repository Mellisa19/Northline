const NAIRA = "\u20a6";

/** Compact money for tables and headlines: ₦1.4M, ₦2.6bn. */
export function money(value, { decimals = 1 } = {}) {
  const amount = Number(value) || 0;
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  if (abs >= 1_000_000_000) return `${sign}${NAIRA}${(abs / 1_000_000_000).toFixed(decimals)}bn`;
  if (abs >= 1_000_000) return `${sign}${NAIRA}${(abs / 1_000_000).toFixed(decimals)}M`;
  if (abs >= 1_000) return `${sign}${NAIRA}${(abs / 1_000).toFixed(0)}k`;
  return `${sign}${NAIRA}${abs.toFixed(0)}`;
}

/** Full money, grouped: ₦3,703,000. */
export function moneyFull(value) {
  const amount = Number(value) || 0;
  return `${NAIRA}${Math.round(amount).toLocaleString("en-NG")}`;
}

export function compactNumber(value, decimals = 0) {
  const amount = Number(value) || 0;
  if (Math.abs(amount) >= 1_000_000) return `${(amount / 1_000_000).toFixed(decimals)}M`;
  if (Math.abs(amount) >= 1_000) return `${(amount / 1_000).toFixed(decimals)}k`;
  return `${amount}`;
}

export function number(value) {
  return (Number(value) || 0).toLocaleString("en-NG");
}

export function percent(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(decimals)}%`;
}

export function signed(value, decimals = 1) {
  const amount = Number(value);
  if (Number.isNaN(amount)) return "—";
  return `${amount > 0 ? "+" : ""}${amount.toFixed(decimals)}%`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-05" → "5 Oct 2026" */
export function shortDate(value) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

/** "2026-10" → "Oct 26" */
export function monthLabel(value) {
  if (!value) return "—";
  const [year, month] = value.split("-");
  const index = Number(month) - 1;
  if (Number.isNaN(index) || !MONTHS[index]) return value;
  return `${MONTHS[index]} ${year.slice(2)}`;
}

export function daysLabel(days) {
  if (days === null || days === undefined) return "—";
  if (days <= 0) return "current";
  if (days === 1) return "1 day";
  return `${days} days`;
}

/** Band index to the palette variable and label. */
export const BAND_META = [
  { label: "Current", tone: "var(--band-0)" },
  { label: "1–30 days", tone: "var(--band-1)" },
  { label: "31–60 days", tone: "var(--band-2)" },
  { label: "61–90 days", tone: "var(--band-3)" },
  { label: "90+ days", tone: "var(--band-4)" },
];

export function bandTone(band) {
  return BAND_META[band]?.tone ?? "var(--ink-3)";
}

export const RISK_TONE = {
  low: "var(--resolve)",
  watch: "var(--band-1)",
  elevated: "var(--signal)",
  high: "var(--band-3)",
  severe: "var(--risk)",
};

export function riskTone(code) {
  return RISK_TONE[code] ?? "var(--ink-3)";
}

export function channelLabel(channel) {
  return String(channel || "").replace(/_/g, " ");
}

export function initials(name) {
  return String(name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

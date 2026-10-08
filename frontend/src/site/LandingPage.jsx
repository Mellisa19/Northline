import { useEffect, useMemo, useState } from "react";
import { CountUp, Reveal, Ticker } from "../components/ui";
import { MigrationMatrix, ParTrend, Sparkline } from "../components/charts";
import { endpoints, useApi } from "../lib/api";
import { bandTone, money, moneyFull, monthLabel, number, percent } from "../lib/format";
import "./site.css";

/* ==========================================================================
   The public page.

   Deliberately sparse: one idea per screen, the numbers doing the arguing, and
   motion carrying the eye. Anything a reader would skim is already gone.
   ========================================================================== */

const NAV = [
  { href: "#problem", label: "The problem" },
  { href: "#order", label: "Order" },
  { href: "#how", label: "How it works" },
  { href: "#return", label: "Returns" },
];

function Brand({ navigate, dark = false }) {
  return (
    <a
      className={`brand${dark ? " brand--dark" : ""}`}
      href="/"
      onClick={(event) => {
        event.preventDefault();
        navigate("/");
      }}
    >
      <span className="brand__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="27" height="27">
          <rect width="32" height="32" rx="8" fill={dark ? "var(--clay)" : "var(--ink)"} />
          <path d="M7 24V8h3.1l7.4 10.2V8H21v16h-3.1L10.5 13.8V24H7z" fill="#fff" />
        </svg>
      </span>
      <span className="brand__text">
        <strong>Northline</strong>
        <small>Credit &amp; Recovery</small>
      </span>
    </a>
  );
}

function useScrolled(threshold = 12) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);
  return scrolled;
}

function Masthead({ navigate }) {
  const scrolled = useScrolled();

  return (
    <header className={`masthead${scrolled ? " is-scrolled" : ""}`}>
      <div className="shell masthead__inner">
        <Brand navigate={navigate} dark={!scrolled} />
        <nav className="masthead__nav" aria-label="Sections">
          {NAV.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="masthead__actions">
          <button className="btn btn--sm btn--dark-ghost" type="button" onClick={() => navigate("/sign-in")}>
            Sign in
          </button>
          <button className="btn btn--sm btn--signal" type="button" onClick={() => navigate("/triage")}>
            Triage your book
          </button>
        </div>
      </div>
    </header>
  );
}

/* -------------------------------------------------------------------------- */

function Hero({ summary, meta, navigate }) {
  const facts = [
    { label: "Book under management", value: summary?.book_principal ?? 0, format: money },
    { label: "30+ days past due", value: summary?.par30?.value_pct ?? 0, format: (n) => `${n.toFixed(1)}%` },
    { label: "Need attention today", value: summary?.needs_attention?.accounts ?? 0, format: number },
    { label: "Recoverable now", value: summary?.expected_recovery_available ?? 0, format: money },
  ];

  return (
    <section className="hero">
      <div className="hero__bg" aria-hidden="true">
        <span className="hero__blob hero__blob--a" />
        <span className="hero__blob hero__blob--b" />
        <span className="hero__grid" />
      </div>

      <div className="shell hero__inner">
        <div className="hero__copy">
          <p className="hero__eyebrow enter">
            <span className="hero__pip" />
            {meta?.synthetic ? "Live demo portfolio" : "Live portfolio"} ·{" "}
            {summary?.accounts ? `${number(summary.accounts)} accounts` : "loading"}
          </p>

          <h1 className="display display--xl hero__headline">
            <span className="enter" style={{ "--enter-delay": "60ms" }}>
              Risk doesn&rsquo;t start
            </span>
            <span className="enter" style={{ "--enter-delay": "150ms" }}>
              when a payment
            </span>
            <span className="enter" style={{ "--enter-delay": "240ms" }}>
              is <em>missed</em>.
            </span>
          </h1>

          <p className="hero__sub enter" style={{ "--enter-delay": "330ms" }}>
            Northline ranks your whole book by the money at stake — then tells your team what to do
            about it.
          </p>

          <div className="hero__cta enter" style={{ "--enter-delay": "410ms" }}>
            <button className="btn btn--signal btn--lg" type="button" onClick={() => navigate("/triage")}>
              Triage your loan book
            </button>
            <button className="btn btn--dark-ghost btn--lg" type="button" onClick={() => navigate("/sign-in")}>
              Open the workspace
            </button>
          </div>
        </div>

        <div className="hero__board enter" style={{ "--enter-delay": "480ms" }}>
          <div className="hero__board-head">
            <span className="eyebrow">Portfolio at a glance</span>
            <span className="hero__live">
              <span className="hero__pip" />
              recalculated on every read
            </span>
          </div>

          <div className="hero__figures">
            {facts.map((fact, index) => (
              <div className="hero__figure" key={fact.label} style={{ "--i": index }}>
                <span className="hero__figure-label">{fact.label}</span>
                <span className="hero__figure-value">
                  <CountUp value={fact.value} format={fact.format} />
                </span>
              </div>
            ))}
          </div>

          <div className="hero__coverage">
            <div className="hero__coverage-head">
              <span className="eyebrow">Monitoring coverage</span>
              <span className="tnum">
                {percent(summary?.monitoring?.coverage_value_pct ?? 0, 0)} of value
              </span>
            </div>
            <span className="hero__coverage-track">
              <span
                className="hero__coverage-fill"
                style={{ width: `${summary?.monitoring?.coverage_value_pct ?? 0}%` }}
              />
            </span>
          </div>
        </div>
      </div>

      <Ticker
        items={[
          { label: "Accounts", value: number(summary?.accounts ?? 0) },
          { label: "Borrowers", value: number(summary?.borrowers ?? 0) },
          { label: "Arrears", value: money(summary?.arrears_total ?? 0) },
          { label: "Loss at risk", value: money(summary?.loss_at_risk ?? 0) },
          { label: "Collected, 90 days", value: money(summary?.collected_90d ?? 0) },
          { label: "Cost to collect", value: money(summary?.cost_to_collect_90d ?? 0) },
        ]}
      />
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Problem({ advance, featured }) {
  return (
    <section className="section" id="problem">
      <div className="shell">
        <div className="section__head">
          <Reveal>
            <p className="eyebrow eyebrow--signal">01 — The problem</p>
            <h2 className="display section__title">
              By the time it shows up
              <br />
              as a missed payment,
              <br />
              it is already old news.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lede">
              A business stops being able to pay months before it stops paying. Nobody has time to
              look, so it surfaces in a report instead of a conversation.
            </p>
          </Reveal>
        </div>

        <div className="stats-row">
          <Reveal className="stat-tile" delay={0}>
            <span className="stat-tile__value">
              <CountUp value={advance?.median_days ?? 0} format={(n) => `${Math.round(n)}`} />
            </span>
            <span className="stat-tile__unit">days</span>
            <span className="stat-tile__label">median warning before the first miss</span>
          </Reveal>
          <Reveal className="stat-tile" delay={90}>
            <span className="stat-tile__value">
              <CountUp
                value={advance?.detection_rate_monitored_pct ?? 0}
                format={(n) => `${Math.round(n)}`}
              />
            </span>
            <span className="stat-tile__unit">%</span>
            <span className="stat-tile__label">of monitored accounts flagged in advance</span>
          </Reveal>
          <Reveal className="stat-tile" delay={180}>
            <span className="stat-tile__value">
              <CountUp value={advance?.accounts_flagged_in_advance ?? 0} format={number} />
            </span>
            <span className="stat-tile__label">accounts the book never saw coming</span>
          </Reveal>
        </div>

        {featured ? (
          <Reveal className="case" delay={80}>
            <div className="case__side">
              <span className="eyebrow">Worked example</span>
              <p className="case__name">{featured.descriptor}</p>
              <p className="case__meta">
                {featured.product_name} · {moneyFull(featured.outstanding_principal)} outstanding
              </p>
              <div className="case__timeline">
                <span className="case__mark case__mark--flag">
                  <span className="case__mark-dot" />
                  {featured.lead_days} days before the first miss
                </span>
                <span className="case__line" />
                <span className="case__mark case__mark--late">
                  <span className="case__mark-dot" />
                  {featured.days_past_due} days past due today
                </span>
              </div>
            </div>

            <div className="case__chart">
              <div className="case__chart-head">
                <span className="eyebrow">Monthly takings</span>
                <span className="chip chip--signal">
                  {featured.change_pct === null || featured.change_pct === undefined
                    ? "trend"
                    : `${featured.change_pct}% vs prior quarter`}
                </span>
              </div>
              <Sparkline
                values={(featured.cashflow ?? []).map((row) => row.inflow)}
                width={620}
                height={150}
                tone="var(--clay)"
                fill
              />
              <div className="case__axis">
                <span className="source">{monthLabel(featured.cashflow?.[0]?.month)}</span>
                <span className="source">{monthLabel(featured.cashflow?.at(-1)?.month)}</span>
              </div>
            </div>
          </Reveal>
        ) : null}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function OrderDemo() {
  const [target, setTarget] = useState(25);
  const [budget, setBudget] = useState(25);

  useEffect(() => {
    const timer = setTimeout(() => setBudget(target), 220);
    return () => clearTimeout(timer);
  }, [target]);

  const { data, loading } = useApi(endpoints.orderingDemo(budget));
  const ranking = data;
  const northline = ranking?.northline;
  const baseline = ranking?.baseline_dpd_order;
  const maxValue = Math.max(northline?.expected_recovery ?? 0, baseline?.expected_recovery ?? 0, 1);

  const count = (rows, test) => (rows ?? []).filter(test).length;

  return (
    <section className="section" id="order">
      <div className="shell">
        <div className="section__head">
          <Reveal>
            <p className="eyebrow eyebrow--signal">02 — Order</p>
            <h2 className="display section__title">
              Sorted by arrears,
              <br />
              your list is the accounts
              <br />
              you can no longer save.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lede">
              Drag it. Same team, same effort, different answer.
            </p>
          </Reveal>
        </div>

        <Reveal className="demo">
          <div className="demo__control">
            <div className="demo__budget">
              <span className="eyebrow">Accounts your team can work today</span>
              <span className="demo__budget-value">
                <CountUp value={budget} duration={320} format={(n) => `${Math.round(n)}`} />
              </span>
            </div>
            <input
              type="range"
              min="10"
              max="250"
              step="5"
              value={target}
              aria-label="Accounts your team can work today"
              onChange={(event) => setTarget(Number(event.target.value))}
            />
            <div className="demo__scale">
              <span className="source">10</span>
              <span className="source">130</span>
              <span className="source">250</span>
            </div>
          </div>

          <div className="demo__boards">
            <article className="board board--win">
              <header>
                <span className="eyebrow">Northline order</span>
                <span className="board__value">
                  {loading && !ranking ? "…" : <CountUp value={northline?.expected_recovery ?? 0} format={money} />}
                </span>
              </header>
              <span className="board__track">
                <span
                  className="board__fill"
                  style={{
                    width: `${((northline?.expected_recovery ?? 0) / maxValue) * 100}%`,
                    background: "var(--clay)",
                  }}
                />
              </span>
              <ul className="board__list">
                {(data?.rows ?? []).slice(0, 5).map((row, index) => (
                  <li key={`${row.label}-${index}`} style={{ "--i": index }}>
                    <span className="board__dot" style={{ background: bandTone(row.band) }} />
                    <span className="board__name">{row.label}</span>
                    <span className="board__amt tnum">{money(row.expected_recovery)}</span>
                  </li>
                ))}
              </ul>
            </article>

            <article className="board board--lose">
              <header>
                <span className="eyebrow">Sorted by days past due</span>
                <span className="board__value">
                  {loading && !ranking ? "…" : <CountUp value={baseline?.expected_recovery ?? 0} format={money} />}
                </span>
              </header>
              <span className="board__track">
                <span
                  className="board__fill"
                  style={{
                    width: `${((baseline?.expected_recovery ?? 0) / maxValue) * 100}%`,
                    background: "var(--ink-4)",
                  }}
                />
              </span>
              <ul className="board__list board__list--dim">
                {(data?.baseline_rows ?? []).slice(0, 5).map((row, index) => (
                  <li key={`${row.label}-${index}`} style={{ "--i": index }}>
                    <span className="board__dot" style={{ background: bandTone(row.band) }} />
                    <span className="board__name">{row.label}</span>
                    <span className="board__amt tnum">{money(row.expected_recovery)}</span>
                  </li>
                ))}
              </ul>
            </article>
          </div>

          <div className="demo__verdict">
            <span className="demo__lift">
              <CountUp value={ranking?.lift_vs_dpd_order ?? 0} format={(n) => `${n.toFixed(1)}×`} />
            </span>
            <p>
              more recoverable value from the same {budget} reviews — and{" "}
              <strong>{count(data?.rows, (row) => row.band >= 1 && row.band <= 3)}</strong> of them on
              accounts that can still be turned around, against{" "}
              <strong>{count(data?.baseline_rows, (row) => row.band >= 1 && row.band <= 3)}</strong>{" "}
              the old way.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

const STEPS = [
  { n: "01", verb: "Detect", body: "Takings fall, obligations stack up, part payments start. Dated when it happens." },
  { n: "02", verb: "Explain", body: "Three plain reasons, with the numbers behind them." },
  { n: "03", verb: "Rank", body: "By expected recovery after loss and effort — not by who is most overdue." },
  { n: "04", verb: "Act", body: "One playbook, one script, one owner, one deadline." },
  { n: "05", verb: "Track", body: "Every account leaves the queue with an outcome. That is the dataset." },
];

function How({ navigate }) {
  return (
    <section className="section" id="how">
      <div className="shell">
        <div className="section__head">
          <Reveal>
            <p className="eyebrow eyebrow--signal">03 — How it works</p>
            <h2 className="display section__title">
              Five steps.
              <br />
              The last two move cash.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lede">Most risk tooling stops at step one and calls it intelligence.</p>
          </Reveal>
        </div>

        <ol className="steps">
          {STEPS.map((step, index) => (
            <Reveal as="li" className="step" key={step.n} delay={index * 80}>
              <span className="step__n">{step.n}</span>
              <span className="step__verb">{step.verb}</span>
              <p className="step__body">{step.body}</p>
              <span className="step__line" />
            </Reveal>
          ))}
        </ol>

        <Reveal className="how__cta" delay={120}>
          <button className="btn btn--lg" type="button" onClick={() => navigate("/sign-in")}>
            Open the workspace
          </button>
        </Reveal>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Playbooks({ catalogue }) {
  const rows = catalogue?.playbooks ?? [];
  const [active, setActive] = useState(0);
  const playbook = rows[active];
  const performance = catalogue?.performance ?? {};

  return (
    <section className="section" id="playbooks">
      <div className="shell">
        <div className="section__head">
          <Reveal>
            <p className="eyebrow eyebrow--signal">04 — The answer</p>
            <h2 className="display section__title">
              &ldquo;So what do I do?&rdquo;
              <br />
              is the only question
              <br />
              that matters.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lede">Nine playbooks. Each one has a script your officer can read aloud.</p>
          </Reveal>
        </div>

        <Reveal className="pb">
          <div className="pb__tabs" role="tablist" aria-label="Playbooks">
            {rows.map((item, index) => (
              <button
                key={item.code}
                type="button"
                role="tab"
                aria-selected={index === active}
                className={`pb__tab${index === active ? " is-active" : ""}`}
                onClick={() => setActive(index)}
              >
                <span className="pb__tab-name">{item.name}</span>
                <span className="pb__tab-owner">{item.owner}</span>
              </button>
            ))}
          </div>

          {playbook ? (
            <div className="pb__detail" key={playbook.code}>
              <div className="pb__detail-head">
                <span className="chip chip--signal">{playbook.phase.replace(/_/g, " ")}</span>
                <span className="source">
                  {playbook.channel.replace(/_/g, " ")} · {money(playbook.channel_cost)}
                </span>
              </div>

              <blockquote className="pb__script">{playbook.script}</blockquote>

              <div className="pb__meta">
                <div>
                  <span className="eyebrow">Success means</span>
                  <p>{playbook.success_metric}</p>
                </div>
                <div>
                  <span className="eyebrow">Logged attempts</span>
                  <p>
                    {performance[playbook.code]?.attempts ?? 0}
                    {performance[playbook.code]?.kept_rate != null
                      ? ` · ${percent(performance[playbook.code].kept_rate, 0)} kept`
                      : ""}
                  </p>
                </div>
              </div>

              <div className="pb__bands">
                {playbook.effectiveness_by_band.map((band) => (
                  <div className="pb__band" key={band.band}>
                    <span className="pb__band-label">{band.band}</span>
                    <span className="pb__band-track">
                      <span
                        className="pb__band-fill"
                        style={{ width: `${band.probability * 100}%` }}
                      />
                    </span>
                    <span className="pb__band-value tnum">{percent(band.probability * 100, 0)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </Reveal>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Returns({ recovery, trend }) {
  const ledger = recovery?.ledger;
  const holdout = ledger?.holdout ?? {};
  const arms = [
    { key: "worked", label: "Worked", data: holdout.worked, tone: "var(--clay)" },
    { key: "control", label: "Left alone", data: holdout.control, tone: "var(--ink-4)" },
  ];

  return (
    <section className="section" id="return">
      <div className="shell">
        <div className="section__head">
          <Reveal>
            <p className="eyebrow eyebrow--signal">05 — What it returns</p>
            <h2 className="display section__title">
              Prove it in naira,
              <br />
              not in alerts.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lede">
              Most cash on a delinquent book arrives without a phone call. We only claim the part that
              did not.
            </p>
          </Reveal>
        </div>

        <div className="return">
          <Reveal className="return__ledger">
            <div className="return__row">
              <span className="return__label">Collected on delinquent accounts · 90 days</span>
              <span className="return__value">
                <CountUp value={ledger?.collected_on_delinquent_accounts ?? 0} format={money} />
              </span>
            </div>
            <div className="return__row">
              <span className="return__label">Cost to collect</span>
              <span className="return__value return__value--dim">
                <CountUp value={ledger?.cost ?? 0} format={money} />
              </span>
            </div>
            <div className="return__row">
              <span className="return__label">Promises kept</span>
              <span className="return__value return__value--good">
                <CountUp
                  value={ledger?.promise_kept?.kept_rate ?? 0}
                  format={(n) => `${n.toFixed(0)}%`}
                />
              </span>
            </div>
            <div className="return__row">
              <span className="return__label">Recovered after write-off</span>
              <span className="return__value return__value--good">
                <CountUp value={ledger?.written_off?.recovery_events ?? 0} format={money} />
              </span>
            </div>
          </Reveal>

          <Reveal className="return__holdout" delay={110}>
            <span className="eyebrow">The honest test</span>
            <div className="holdout">
              {arms.map((arm) => (
                <div className="holdout__arm" key={arm.key}>
                  <span className="holdout__label">{arm.label}</span>
                  <span className="holdout__value" style={{ color: arm.tone }}>
                    <CountUp value={arm.data?.cure_rate ?? 0} format={(n) => `${n.toFixed(0)}%`} />
                  </span>
                  <span className="holdout__note">
                    cured · {number(arm.data?.accounts ?? 0)} accounts
                  </span>
                </div>
              ))}
            </div>
            <p className="note note--signal">
              {ledger?.sample_note ??
                "The gap between these two arms is the only honest estimate of what contact is worth."}
            </p>
          </Reveal>
        </div>

        <Reveal className="return__chart" delay={60}>
          <div className="figure-head">
            <span className="eyebrow">Portfolio at risk</span>
            <span className="source">share of value by band, monthly</span>
          </div>
          <ParTrend series={trend?.series ?? []} height={230} />
        </Reveal>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

const LIMITS = [
  { title: "Not a probability", body: "A transparent index with published weights. It ranks." },
  { title: "Consent or nothing", body: "Transaction signals need a live consent. The blind spot is a number we show." },
  { title: "No surveillance", body: "Contact caps enforced in code. No contact lists, ever." },
  { title: "No vanity metrics", body: "Gross collections are labelled as gross collections." },
];

function Limits({ coverage, migration }) {
  return (
    <section className="section" id="limits">
      <div className="shell">
        <div className="section__head">
          <Reveal>
            <p className="eyebrow eyebrow--signal">06 — The limits</p>
            <h2 className="display section__title">
              What it won&rsquo;t do
              <br />
              is part of the product.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lede">
              {coverage?.consented_accounts ?? 0} accounts carry a live feed. The rest are worked from
              your own records.
            </p>
          </Reveal>
        </div>

        <div className="limits">
          {LIMITS.map((limit, index) => (
            <Reveal className="limit" key={limit.title} delay={index * 70}>
              <span className="limit__mark" aria-hidden="true" />
              <h3 className="limit__title">{limit.title}</h3>
              <p className="limit__body">{limit.body}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="limits__matrix" delay={80}>
          <div className="figure-head">
            <span className="eyebrow">Where accounts actually move</span>
            <span className="source">month over month</span>
          </div>
          <MigrationMatrix matrix={migration?.matrix ?? []} />
        </Reveal>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Closing({ navigate, meta }) {
  return (
    <section className="closing">
      <div className="shell closing__inner">
        <Reveal>
          <h2 className="display closing__title">
            Put your own book
            <br />
            through it.
          </h2>
          <p className="closing__sub">
            Upload a CSV. Get the queue, the split, and what your current ordering leaves behind.
            Nothing is stored.
          </p>
          <div className="closing__actions">
            <button className="btn btn--signal btn--lg" type="button" onClick={() => navigate("/triage")}>
              Triage your loan book
            </button>
            <button className="btn btn--dark-ghost btn--lg" type="button" onClick={() => navigate("/sign-up")}>
              Create a workspace
            </button>
          </div>
        </Reveal>
      </div>
      <footer className="footer">
        <div className="shell footer__inner">
          <div className="footer__brand">
            <Brand navigate={navigate} dark />
            <p className="footer__disclosure">{meta?.disclaimer}</p>
          </div>
          <div className="footer__cols">
            <div>
              <span className="eyebrow">Product</span>
              <button type="button" onClick={() => navigate("/sign-in")}>Worklist</button>
              <button type="button" onClick={() => navigate("/sign-in")}>Recovery ledger</button>
              <button type="button" onClick={() => navigate("/sign-in")}>Reporting</button>
              <button type="button" onClick={() => navigate("/sign-in")}>Team</button>
            </div>
            <div>
              <span className="eyebrow">Method</span>
              <button type="button" onClick={() => navigate("/sign-in")}>Model card</button>
              <button type="button" onClick={() => navigate("/sign-in")}>Playbooks</button>
              <button type="button" onClick={() => navigate("/sign-in")}>Coverage</button>
            </div>
            <div>
              <span className="eyebrow">Start</span>
              <button type="button" onClick={() => navigate("/triage")}>Triage a tape</button>
              <button type="button" onClick={() => navigate("/sign-up")}>Create a workspace</button>
            </div>
          </div>
        </div>
      </footer>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function useFeaturedCase() {
  const { data } = useApi(endpoints.featuredCase());
  return data ?? null;
}

export default function LandingPage({ navigate }) {
  const { data: summary } = useApi(endpoints.summary());
  const { data: meta } = useApi(endpoints.meta());
  const { data: advance } = useApi(endpoints.advanceWarning());
  const { data: catalogue } = useApi(endpoints.playbooks());
  const { data: recovery } = useApi(endpoints.recovery());
  const { data: coverage } = useApi(endpoints.coverage());
  const { data: trend } = useApi(endpoints.parTrend(18));
  const { data: migration } = useApi(endpoints.migration());
  const featured = useFeaturedCase();

  return (
    <div className="site">
      <Masthead navigate={navigate} />
      <main>
        <Hero summary={summary} meta={meta} navigate={navigate} />
        <Problem advance={advance} featured={featured} />
        <OrderDemo />
        <How navigate={navigate} />
        <Playbooks catalogue={catalogue} />
        <Returns recovery={recovery} trend={trend} />
        <Limits coverage={coverage} migration={migration} />
        <Closing navigate={navigate} meta={meta} />
      </main>
    </div>
  );
}

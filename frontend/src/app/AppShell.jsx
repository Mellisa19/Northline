import { useEffect, useRef, useState } from "react";
import { Avatar, Spinner } from "../components/ui";
import { endpoints, useApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDismiss } from "../lib/motion";
import { money, number } from "../lib/format";
import WorklistPage from "./WorklistPage";
import AccountPage from "./AccountPage";
import RecoveryPage from "./RecoveryPage";
import ReportsPage from "./ReportsPage";
import AlertsPage from "./AlertsPage";
import PlaybooksPage from "./PlaybooksPage";
import CoveragePage from "./CoveragePage";
import ModelPage from "./ModelPage";
import TeamPage from "./TeamPage";
import "./app.css";

const GROUPS = [
  {
    label: "Recovery",
    items: [
      { view: "worklist", label: "Worklist", hint: "Who to work today" },
      { view: "recovery", label: "Recovery ledger", hint: "Cash, cost, holdout" },
      { view: "alerts", label: "Signals", hint: "What changed" },
    ],
  },
  {
    label: "Portfolio",
    items: [
      { view: "reports", label: "Reporting", hint: "Roll rates, vintages" },
      { view: "coverage", label: "Coverage", hint: "Consent and blind spots" },
    ],
  },
  {
    label: "Method",
    items: [
      { view: "playbooks", label: "Playbooks", hint: "Scripts and outcomes" },
      { view: "model", label: "Model card", hint: "Weights and limits" },
    ],
  },
];

const TITLES = {
  worklist: "Today's worklist",
  recovery: "Recovery ledger",
  alerts: "Signals",
  reports: "Portfolio reporting",
  coverage: "Monitoring coverage",
  playbooks: "Playbooks",
  model: "Model card",
  team: "Your team",
  account: "Account",
};

function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function greeting(hour) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function UserMenu({ navigate }) {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const root = useRef(null);

  useDismiss(root, () => setOpen(false), open);

  if (!user) return null;
  const firstName = user.name.split(" ")[0];

  return (
    <div className="usermenu" ref={root}>
      <button
        type="button"
        className={`usermenu__trigger${open ? " is-open" : ""}`}
        onClick={() => setOpen((state) => !state)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Avatar name={user.name} tone={user.tone} size={30} />
        <span className="usermenu__identity">
          <span className="usermenu__name">{firstName}</span>
          <span className="usermenu__role">{user.role_label}</span>
        </span>
        <span className="usermenu__chevron" aria-hidden="true">
          <svg viewBox="0 0 12 8" width="10" height="7">
            <path d="M1 1.5 6 6.5 11 1.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {open ? (
        <div className="usermenu__panel" role="menu">
          <div className="usermenu__head">
            <Avatar name={user.name} tone={user.tone} size={38} />
            <div>
              <p className="usermenu__full">{user.name}</p>
              <p className="usermenu__email">{user.email}</p>
            </div>
          </div>

          <div className="usermenu__org">
            <span className="eyebrow">Workspace</span>
            <span className="usermenu__org-name">{user.org_name}</span>
            <span className="chip chip--quiet">{user.role_label}</span>
            {user.google_linked ? (
              <span className="chip chip--quiet" title="This account is linked to Google">
                Google
              </span>
            ) : null}
          </div>

          <div className="usermenu__items">
            <button type="button" role="menuitem" onClick={() => { setOpen(false); navigate("/app/team"); }}>
              Your team
            </button>
            <button type="button" role="menuitem" onClick={() => { setOpen(false); navigate("/app/model"); }}>
              Model card
            </button>
            <button type="button" role="menuitem" onClick={() => { setOpen(false); navigate("/app/coverage"); }}>
              Monitoring coverage
            </button>
            <button type="button" role="menuitem" onClick={() => { setOpen(false); navigate("/"); }}>
              Back to the site
            </button>
          </div>

          <button
            type="button"
            className="usermenu__signout"
            disabled={leaving}
            onClick={async () => {
              setLeaving(true);
              await signOut();
              navigate("/sign-in");
            }}
          >
            {leaving ? <Spinner size={14} /> : null}
            {leaving ? "Signing out…" : "Sign out"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function AppShell({ route, navigate }) {
  const { user } = useAuth();
  const { data: summary } = useApi(endpoints.summary());
  const [navOpen, setNavOpen] = useState(false);
  const now = useNow();

  useEffect(() => {
    setNavOpen(false);
  }, [route.path]);

  const view = route.type === "app" ? route.view : "worklist";
  const isAdmin = user?.role === "admin";

  const groups = GROUPS.map((group) => ({ ...group }));
  if (isAdmin) {
    groups.push({
      label: "Workspace",
      items: [{ view: "team", label: "Team", hint: "People and roles" }],
    });
  }

  const overdue = summary?.par30?.accounts ?? 0;

  return (
    <div className="workspace">
      <aside className={`rail${navOpen ? " is-open" : ""}`}>
        <button className="rail__brand" type="button" onClick={() => navigate("/")} title="Back to the site">
          <span className="rail__mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="26" height="26">
              <rect width="32" height="32" rx="8" fill="var(--ink)" />
              <path d="M7 24V8h3.1l7.4 10.2V8H21v16h-3.1L10.5 13.8V24H7z" fill="var(--paper)" />
              <rect x="23" y="8" width="2.4" height="16" rx="1.2" fill="var(--clay)" />
            </svg>
          </span>
          <span className="rail__brand-text">
            <strong>Northline</strong>
            <small>{user?.org_name ?? "Credit & Recovery"}</small>
          </span>
        </button>

        <nav className="rail__nav" aria-label="Workspace">
          {groups.map((group) => (
            <div className="rail__group" key={group.label}>
              <span className="rail__group-label">{group.label}</span>
              {group.items.map((item) => {
                const active = view === item.view;
                return (
                  <button
                    key={item.view}
                    type="button"
                    className={`rail__item${active ? " is-active" : ""}`}
                    aria-current={active ? "page" : undefined}
                    onClick={() => navigate(item.view === "worklist" ? "/app" : `/app/${item.view}`)}
                  >
                    <span className="rail__item-label">
                      {item.label}
                      {item.view === "worklist" && overdue ? (
                        <span className="rail__badge">{number(overdue)}</span>
                      ) : null}
                    </span>
                    <span className="rail__item-hint">{item.hint}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="rail__foot">
          <div className="rail__rule" />
          <span className="eyebrow">Book</span>
          <span className="rail__stat tnum">{money(summary?.book_principal ?? 0)}</span>
          <span className="rail__hint">{number(summary?.accounts ?? 0)} live accounts</span>
          <p className="rail__disclosure">
            Demonstration portfolio generated by Northline. Not real borrower data.
          </p>
        </div>
      </aside>

      <div className="workspace__body">
        <header className="topbar">
          <button
            className="topbar__toggle"
            type="button"
            onClick={() => setNavOpen((open) => !open)}
            aria-expanded={navOpen}
          >
            <span className="topbar__toggle-bar" />
            <span className="topbar__toggle-bar" />
            <span className="topbar__toggle-bar" />
            <span className="sr-only">Toggle navigation</span>
          </button>

          <div className="topbar__title">
            <span className="eyebrow">
              {greeting(now.getHours())}, {user?.name?.split(" ")[0] ?? "there"} ·{" "}
              {now.toLocaleDateString("en-NG", { weekday: "short", day: "numeric", month: "short" })}
            </span>
            <h1 className="topbar__heading">{TITLES[view] ?? "Workspace"}</h1>
          </div>

          <div className="topbar__right">
            <div className="topbar__pulse">
              <span className="topbar__pulse-dot" />
              <span className="topbar__pulse-text">
                <strong>{number(summary?.needs_attention?.accounts ?? 0)}</strong> to work
              </span>
            </div>
            <UserMenu navigate={navigate} />
          </div>
        </header>

        <main className="workspace__main" key={view}>
          <div className="page-enter">
            {view === "worklist" && <WorklistPage navigate={navigate} />}
            {view === "account" && <AccountPage id={route.params?.id} navigate={navigate} />}
            {view === "recovery" && <RecoveryPage navigate={navigate} />}
            {view === "reports" && <ReportsPage />}
            {view === "alerts" && <AlertsPage navigate={navigate} />}
            {view === "playbooks" && <PlaybooksPage />}
            {view === "coverage" && <CoveragePage />}
            {view === "model" && <ModelPage />}
            {view === "team" && <TeamPage />}
          </div>
        </main>
      </div>
    </div>
  );
}

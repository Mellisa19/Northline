/**
 * Render every surface in jsdom against the live API and report what came out.
 *
 * This exists because the development sandbox has no browser. It is not a
 * substitute for looking at the thing, but it does catch the failure that matters
 * most: a page that throws on real data and renders nothing.
 */
import { JSDOM } from "jsdom";

const BASE = "http://127.0.0.1:8010";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});

global.window = dom.window;
global.document = dom.window.document;
// Node 24 exposes a read-only global navigator, so it has to be redefined.
Object.defineProperty(global, "navigator", {
  value: dom.window.navigator,
  configurable: true,
  writable: true,
});
global.HTMLElement = dom.window.HTMLElement;
global.Node = dom.window.Node;
global.Event = dom.window.Event;
global.PopStateEvent = dom.window.PopStateEvent;
global.MutationObserver = dom.window.MutationObserver;
global.requestAnimationFrame = (callback) => setTimeout(() => callback(Date.now()), 0);
global.cancelAnimationFrame = (handle) => clearTimeout(handle);
// jsdom has no layout engine, so scrolling is a no-op rather than an error.
dom.window.scrollTo = () => {};
global.scrollTo = () => {};
global.IS_REACT_ACT_ENVIRONMENT = true;

const realFetch = global.fetch;

/* The workspace is behind a session now, so the harness signs in first and
   forwards the token on every proxied call — exactly what the browser does. */
const signIn = await realFetch(`${BASE}/api/auth/signin`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@northline.ng", password: "northline2026" }),
}).then((response) => response.json());

if (!signIn?.token) {
  console.error("Could not sign in to the API; is the backend seeded?");
  process.exit(1);
}

global.fetch = (input, init = {}) => {
  const url = typeof input === "string" ? input : input.url;
  if (url.startsWith("/api")) {
    const headers = { ...(init.headers ?? {}), Authorization: `Bearer ${signIn.token}` };
    return realFetch(`${BASE}${url}`, { ...init, headers });
  }
  return realFetch(input, init);
};

const problems = [];
const originalError = console.error;
console.error = (...args) => {
  const text = args.map(String).join(" ");
  if (text.includes("not wrapped in act")) return;
  problems.push(text);
  originalError(...args);
};
process.on("unhandledRejection", (reason) => {
  problems.push(`unhandled rejection: ${reason}`);
});

const { createRoot, Root } = await import("../dist-verify/entry.js");
const React = await import("react");
const { act } = React;

/* The app reads its session from localStorage on boot, so the harness plants the
   same key the sign-in form would have written. */
dom.window.localStorage.setItem("northline.session", signIn.token);

function text() {
  return document.getElementById("root").textContent ?? "";
}

async function renderAt(path) {
  window.history.pushState({}, "", path);
  // A fresh container per case: React refuses to attach a second root to one node.
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(React.StrictMode, null, React.createElement(Root)));
  });
  // Let the data hooks settle.
  for (let i = 0; i < 12; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 120));
    });
  }
  const html = host.innerHTML;
  const content = host.textContent ?? "";
  await act(async () => {
    root.unmount();
  });
  host.remove();
  return { html, content };
}

const worklist = await realFetch(`${BASE}/api/worklist?budget=5`, {
  headers: { Authorization: `Bearer ${signIn.token}` },
}).then((r) => r.json());
if (!worklist?.rows?.length) {
  console.error("The worklist came back empty; refusing to report a green run.");
  process.exit(1);
}
const accountId = worklist.rows[0].id;
const accountName = worklist.rows[0].borrower_name;
const firstFigure = worklist.rows[0].expected_recovery;

const CASES = [
  { path: "/", name: "Landing", expect: ["Risk doesn", "Triage your loan book", "Portfolio at a glance", "So what do I do?"] },
  { path: "/triage", name: "Triage", expect: ["Put your own book", "Download the template"] },
  { path: "/sign-in", name: "Sign in", anonymous: true, expect: ["Sign in", "seeded role", "Google sign-in is not configured"] },
  { path: "/sign-up", name: "Sign up", anonymous: true, expect: ["Create your org", "Roles you can hand out"] },
  { path: "/auth/callback", name: "OAuth callback", anonymous: true, expect: ["Google sign-in", "didn't work", "Back to sign in"] },
  { path: "/app", name: "Worklist", expect: ["worklist", "Recoverable in this queue", accountName] },
  { path: `/app/account/${accountId}`, name: "Account 360", expect: ["Why this account needs attention", "Recommended playbook", "What is at stake", accountName] },
  { path: "/app/recovery", name: "Recovery ledger", expect: ["Holdout slice", "Playbook performance"] },
  { path: "/app/reports", name: "Reporting", expect: ["Band migration", "Vintage curves", "Early-warning performance"] },
  { path: "/app/alerts", name: "Signals", expect: ["Signal feed", "Actionable"] },
  { path: "/app/playbooks", name: "Playbooks", expect: ["Pre-delinquency care call", "Promise-to-pay capture"] },
  { path: "/app/coverage", name: "Coverage", expect: ["Monitoring coverage", "Coverage by tier"] },
  { path: "/app/model", name: "Model card", expect: ["Component weights", "Limitations", "Planned, not shipped"] },
  { path: "/app/team", name: "Team", expect: ["Members", "What each role sees", "Add someone"] },
];

let failures = 0;
const results = [];

for (const testCase of CASES) {
  // Signed-in visitors are redirected away from the auth pages, which is the
  // correct behaviour — so those cases are rendered with the session removed.
  if (testCase.anonymous) dom.window.localStorage.removeItem("northline.session");
  else dom.window.localStorage.setItem("northline.session", signIn.token);

  const before = problems.length;
  let rendered;
  try {
    rendered = await renderAt(testCase.path);
  } catch (error) {
    failures += 1;
    results.push({ name: testCase.name, ok: false, note: `threw: ${error.message}` });
    continue;
  }
  const missing = testCase.expect.filter((needle) => !rendered.content.includes(needle));
  const errors = problems.slice(before);
  const ok = missing.length === 0 && errors.length === 0;
  if (!ok) failures += 1;
  results.push({
    name: testCase.name,
    ok,
    chars: rendered.content.length,
    missing: missing.length ? missing : undefined,
    errors: errors.length ? errors.slice(0, 2) : undefined,
  });
}

console.log("\n=== FRONTEND RENDER CHECK ===\n");
for (const result of results) {
  const mark = result.ok ? "PASS" : "FAIL";
  console.log(`${mark}  ${result.name.padEnd(18)} ${String(result.chars ?? "").padStart(7)} chars`);
  if (result.note) console.log(`      ${result.note.slice(0, 400)}`);
  if (result.missing) console.log(`      missing: ${result.missing.join(" | ")}`);
  if (result.errors) result.errors.forEach((line) => console.log(`      error: ${line.slice(0, 220)}`));
}
console.log(`\n${CASES.length - failures}/${CASES.length} surfaces rendered cleanly`);
console.log(`sample account: ${accountName} (id ${accountId}), expected recovery ${firstFigure}`);

process.exit(failures ? 1 : 0);

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import LandingPage from "./site/LandingPage";
import TriagePage from "./site/TriagePage";
import { SignInPage, SignUpPage, AuthCallbackPage } from "./site/AuthPages";
import AppShell from "./app/AppShell";
import { useAuth } from "./lib/auth";
import { Spinner } from "./components/ui";

/* A deliberately small router: the product has a handful of surfaces and a
   dependency-free history listener keeps the bundle honest. */

const APP_ROUTES = [
  { pattern: /^\/app\/?$/, view: "worklist" },
  { pattern: /^\/app\/worklist$/, view: "worklist" },
  { pattern: /^\/app\/recovery$/, view: "recovery" },
  { pattern: /^\/app\/reports$/, view: "reports" },
  { pattern: /^\/app\/alerts$/, view: "alerts" },
  { pattern: /^\/app\/playbooks$/, view: "playbooks" },
  { pattern: /^\/app\/coverage$/, view: "coverage" },
  { pattern: /^\/app\/model$/, view: "model" },
  { pattern: /^\/app\/team$/, view: "team" },
  { pattern: /^\/app\/account\/(\d+)$/, view: "account", params: ["id"] },
];

function subscribe(callback) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function resolve(pathname) {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (path === "/" || path === "") return { type: "landing", path: "/" };
  if (path === "/triage") return { type: "triage", path };
  if (path === "/sign-in") return { type: "sign-in", path };
  if (path === "/sign-up") return { type: "sign-up", path };
  if (path === "/auth/callback") return { type: "auth-callback", path };
  for (const route of APP_ROUTES) {
    const match = path.match(route.pattern);
    if (match) {
      const params = {};
      (route.params ?? []).forEach((name, index) => {
        params[name] = match[index + 1];
      });
      return { type: "app", view: route.view, params, path };
    }
  }
  return { type: "not-found", path };
}

function Booting() {
  return (
    <div className="boot">
      <Spinner size={22} />
      <span className="source">Checking your session…</span>
    </div>
  );
}

export default function App() {
  const pathname = useSyncExternalStore(subscribe, () => window.location.pathname, () => "/");
  const [route, setRoute] = useState(() => resolve(pathname));
  const { status, isAuthenticated } = useAuth();

  useEffect(() => {
    setRoute(resolve(pathname));
  }, [pathname]);

  const navigate = useCallback((next) => {
    if (window.location.pathname === next) return;
    window.history.pushState({}, "", next);
    window.dispatchEvent(new PopStateEvent("popstate"));
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  /* The workspace is private. Anyone landing on it without a session is sent to
     sign in, and anyone already signed in is not shown the forms again. The
     OAuth callback is exempt: it is how a session is created in the first place. */
  useEffect(() => {
    if (status === "checking") return;
    if (route.type === "app" && !isAuthenticated) navigate("/sign-in");
    if ((route.type === "sign-in" || route.type === "sign-up") && isAuthenticated) navigate("/app");
  }, [route, status, isAuthenticated, navigate]);

  useEffect(() => {
    const titles = {
      landing: "Northline — Risk doesn't start when a payment is missed",
      triage: "Northline — Triage a loan book",
      "sign-in": "Northline — Sign in",
      "sign-up": "Northline — Create your workspace",
      "auth-callback": "Northline — Signing you in",
    };
    document.title =
      titles[route.type] ??
      (route.type === "app"
        ? `Northline — ${route.view.replace(/^\w/, (c) => c.toUpperCase())}`
        : "Northline");
  }, [route]);

  if (route.type === "auth-callback") return <AuthCallbackPage navigate={navigate} />;
  if (route.type === "sign-in") return <SignInPage navigate={navigate} />;
  if (route.type === "sign-up") return <SignUpPage navigate={navigate} />;

  if (route.type === "app") {
    if (status === "checking") return <Booting />;
    if (!isAuthenticated) return <Booting />;
    return <AppShell route={route} navigate={navigate} />;
  }

  if (route.type === "triage") return <TriagePage navigate={navigate} />;
  return <LandingPage navigate={navigate} />;
}

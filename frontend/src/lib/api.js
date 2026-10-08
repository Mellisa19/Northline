import { useCallback, useEffect, useRef, useState } from "react";

const BASE = "/api";

/* The signed-in token lives in one place, so every request carries it without
   callers having to remember. */
let authToken = null;
let onUnauthorized = null;

export function setAuthToken(token) {
  authToken = token ?? null;
}

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

async function request(path, options = {}) {
  const headers = { ...(options.headers ?? {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  const response = await fetch(`${BASE}${path}`, { ...options, headers });
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    throw new Error("The service returned an unreadable response.");
  }

  if (response.status === 401 && onUnauthorized) onUnauthorized();

  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg).join(", ")
          : `Request failed (${response.status})`,
    );
  }
  return payload;
}

/* A small cache so several screens share one fetch of the same book. */
const cache = new Map();
const inflight = new Map();

export function fetchJson(path, { fresh = false } = {}) {
  if (!fresh && cache.has(path)) return Promise.resolve(cache.get(path));
  if (inflight.has(path)) return inflight.get(path);

  const promise = request(path)
    .then((payload) => {
      cache.set(path, payload);
      inflight.delete(path);
      return payload;
    })
    .catch((error) => {
      inflight.delete(path);
      throw error;
    });

  inflight.set(path, promise);
  return promise;
}

export function invalidate(prefix = "") {
  for (const key of [...cache.keys()]) {
    if (!prefix || key.startsWith(prefix)) cache.delete(key);
  }
}

export function postJson(path, body, { auth = true } = {}) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...(auth ? {} : {}),
  });
}

export function deleteJson(path) {
  return request(path, { method: "DELETE" });
}

export function postFile(path, file) {
  const form = new FormData();
  form.append("file", file);
  return request(path, { method: "POST", body: form });
}

/** Data hook with loading and error state. */
export function useApi(path, { fresh = false, skip = false } = {}) {
  const [state, setState] = useState(() => ({
    data: !fresh && path ? (cache.get(path) ?? null) : null,
    error: null,
    loading: Boolean(path) && !skip && !(!fresh && cache.get(path)),
  }));
  const mounted = useRef(true);

  const load = useCallback(
    async (options = {}) => {
      if (!path || skip) return;
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const data = await fetchJson(path, { fresh: options.fresh ?? fresh });
        if (mounted.current) setState({ data, error: null, loading: false });
      } catch (error) {
        if (mounted.current) setState({ data: null, error: error.message, loading: false });
      }
    },
    [path, fresh, skip],
  );

  useEffect(() => {
    mounted.current = true;
    load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  return { ...state, reload: load };
}

export const endpoints = {
  meta: () => "/meta",
  summary: () => "/portfolio/summary",
  parTrend: (months = 18) => `/portfolio/par-trend?months=${months}`,
  migration: (since = "2026-01-01") => `/portfolio/migration?since=${since}`,
  vintages: () => "/portfolio/vintages",
  advanceWarning: () => "/portfolio/advance-warning",
  coverage: () => "/portfolio/coverage",
  featuredCase: () => "/portfolio/featured-case",
  orderingDemo: (budget) => `/portfolio/ordering-demo?budget=${budget}`,
  worklist: ({ budget, officer, band, product, search } = {}) => {
    const params = new URLSearchParams();
    if (budget) params.set("budget", budget);
    if (officer) params.set("officer", officer);
    if (band !== undefined && band !== null && band !== "") params.set("band", band);
    if (product) params.set("product", product);
    if (search) params.set("search", search);
    const query = params.toString();
    return `/worklist${query ? `?${query}` : ""}`;
  },
  account: (id) => `/accounts/${id}`,
  recovery: () => "/recovery/summary",
  playbooks: () => "/playbooks",
  alerts: (limit = 40) => `/alerts?limit=${limit}`,
  modelCard: () => "/scoring/model-card",
  roles: () => "/auth/roles",
  demo: () => "/auth/demo",
  me: () => "/auth/me",
  providers: () => "/auth/providers",
  team: () => "/org/team",
  ssoStatus: () => "/org/sso-status",
};

/**
 * Full-page navigation target for Google sign-in.
 *
 * This is deliberately not a fetch: the browser has to visit Google itself, and
 * the backend answers with a redirect. Going through the dev server keeps the
 * whole handshake on one origin, which is what the registered redirect URI
 * expects.
 */
export function googleStartUrl(redirect = "/app") {
  const params = new URLSearchParams({ redirect });
  return `/api/auth/google/start?${params.toString()}`;
}

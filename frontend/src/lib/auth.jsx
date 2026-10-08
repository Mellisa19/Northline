import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { endpoints, fetchJson, invalidate, postJson, setAuthToken, setUnauthorizedHandler } from "./api";

const STORAGE_KEY = "northline.session";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState("checking");
  const [user, setUser] = useState(null);

  /* A 401 from any request means the session is gone: drop it and let the
     router send the person back to sign in. */
  useEffect(() => {
    setUnauthorizedHandler(() => {
      window.localStorage.removeItem(STORAGE_KEY);
      setAuthToken(null);
      invalidate();
      setUser(null);
      setStatus("anonymous");
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      setStatus("anonymous");
      return;
    }
    setAuthToken(stored);
    fetchJson(endpoints.me(), { fresh: true })
      .then((payload) => {
        setUser(payload.user);
        setStatus("authenticated");
      })
      .catch(() => {
        window.localStorage.removeItem(STORAGE_KEY);
        setAuthToken(null);
        setUser(null);
        setStatus("anonymous");
      });
  }, []);

  const adopt = useCallback((payload) => {
    window.localStorage.setItem(STORAGE_KEY, payload.token);
    setAuthToken(payload.token);
    invalidate();
    setUser(payload.user);
    setStatus("authenticated");
    return payload.user;
  }, []);

  const signIn = useCallback(
    async (email, password) => adopt(await postJson("/auth/signin", { email, password })),
    [adopt],
  );

  const signUp = useCallback(
    async (payload) => adopt(await postJson("/auth/signup", payload)),
    [adopt],
  );

  /** Trade the one-time code from the Google callback for a real session. */
  const completeGoogle = useCallback(
    async (code) => adopt(await postJson("/auth/google/session", { code })),
    [adopt],
  );

  const signOut = useCallback(async () => {
    try {
      await postJson("/auth/signout", {});
    } catch {
      /* Signing out locally matters more than the server round trip. */
    }
    window.localStorage.removeItem(STORAGE_KEY);
    setAuthToken(null);
    invalidate();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const refresh = useCallback(async () => {
    const payload = await fetchJson(endpoints.me(), { fresh: true });
    setUser(payload.user);
    return payload.user;
  }, []);

  const value = useMemo(
    () => ({
      status,
      user,
      isAuthenticated: status === "authenticated",
      signIn,
      signUp,
      completeGoogle,
      signOut,
      refresh,
      can: (roles) => Boolean(user) && (Array.isArray(roles) ? roles.includes(user.role) : user.role === roles),
    }),
    [status, user, signIn, signUp, completeGoogle, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

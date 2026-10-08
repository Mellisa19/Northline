import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "../src/App";
import { AuthProvider } from "../src/lib/auth";
import "../src/styles/tokens.css";

/* Mirrors the tree main.jsx renders, so the harness exercises the same providers. */
export function Root() {
  return (
    <AuthProvider>
      <App />
    </AuthProvider>
  );
}

export { App, StrictMode, createRoot };

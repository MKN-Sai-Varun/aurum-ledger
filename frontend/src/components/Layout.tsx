import { useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "../auth/auth-context";
import { ApiError } from "../lib/api";
import { ROLE_LABEL } from "../lib/types";
import { useRoute } from "../lib/useRoute";

export default function Layout({ children }: { children: ReactNode }) {
  const { state, signOut } = useAuth();
  const route = useRoute();
  const [error, setError] = useState<string | null>(null);

  if (state.status !== "signed-in") return null;
  const { user } = state;

  async function handleSignOut() {
    setError(null);
    try {
      await signOut();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't sign out. Try again.");
    }
  }

  const link = (path: string, label: string) => (
    <a
      className={`nav-link${route === path ? " nav-link-current" : ""}`}
      href={`#${path}`}
      aria-current={route === path ? "page" : undefined}
    >
      {label}
    </a>
  );

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">Aurum</span>
          <nav className="nav" aria-label="Main">
            {link("/karigars", "Karigars")}
            {link("/jobs", "Jobs")}
            {link("/ledger", "Ledger")}
            {user.role === "finance_head" && link("/alerts", "Alerts")}
            {user.role === "finance_head" && link("/stock", "Stock")}
            {user.role === "issue_clerk" && link("/issue", "Issue")}
          </nav>
          <div className="topbar-right">
            <span className="user">{user.full_name}</span>
            <span className="chip chip-ok">{ROLE_LABEL[user.role]}</span>
            <button className="btn btn-quiet" onClick={() => void handleSignOut()}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      {error && (
        <p className="banner banner-page" role="alert">
          {error}
        </p>
      )}
      <main className="page page-top">{children}</main>
    </div>
  );
}
import { useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "../auth/auth-context";
import { ApiError } from "../lib/api";
import { ROLE_LABEL } from "../lib/types";

export default function Layout({ children }: { children: ReactNode }) {
  const { state, signOut } = useAuth();
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

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">Aurum</span>
          <nav aria-label="Main">
            <a className="nav-link" href="#/karigars" aria-current="page">
              Karigars
            </a>
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
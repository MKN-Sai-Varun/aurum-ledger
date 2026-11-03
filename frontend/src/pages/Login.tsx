import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../auth/auth-context";
import { ApiError } from "../lib/api";

export default function Login() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">Aurum</span>
        </div>
      </header>

      <main className="page">
        <div className="hero">
          <div>
            <p className="eyebrow">Aurum / Sign in</p>
            <h1 className="hero-title">
              Every gram, <span className="accent highlight">accounted for</span>
            </h1>
            <p className="lede">
              Gold issued, returned and still to be explained, for every karigar,
              on any day.
            </p>
          </div>

          <section className="card status-card">
            <h2 className="card-title">Sign in</h2>
            <form onSubmit={(e) => void submit(e)} noValidate>
              <div className="field">
                <label htmlFor="username">Username</label>
                <input
                  id="username"
                  className="input"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  maxLength={50}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  maxLength={200}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <p className="banner" role="alert">
                  {error}
                </p>
              )}
              <button
                className="btn btn-primary btn-block"
                type="submit"
                disabled={busy || !username.trim() || !password}
              >
                {busy ? "Signing in..." : "Sign in"}
              </button>
            </form>
          </section>
        </div>
      </main>
    </div>
  );
}
import { useCallback, useEffect, useState } from "react";

type Status = "loading" | "ok" | "error";

export default function App() {
  const [status, setStatus] = useState<Status>("loading");

  const check = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    try {
      const response = await fetch("/api/health", { signal });
      const body = await response.json();
      setStatus(response.ok && body.status === "ok" ? "ok" : "error");
    } catch (error) {
      if ((error as Error).name !== "AbortError") setStatus("error");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void check(controller.signal);
    return () => controller.abort();
  }, [check]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">Aurum</span>
          <span aria-live="polite">
            {status === "loading" && (
              <span key="loading" className="chip chip-wait">Checking</span>
            )}
            {status === "ok" && (
              <span key="ok" className="chip chip-ok">Connected</span>
            )}
            {status === "error" && (
              <span key="error" className="chip chip-review">Offline</span>
            )}
          </span>
        </div>
      </header>

      <main className="page">
        <div className="hero">
          <div>
            <p className="eyebrow">Aurum / 00 Status</p>
            <h1 className="hero-title">
              Every gram, <span className="accent highlight">accounted for</span>
            </h1>
            <p className="lede">
              Gold issued, returned and still to be explained, for every karigar,
              on any day.
            </p>
          </div>

          <section className="card status-card" aria-live="polite">
            <p className="eyebrow">Server</p>
            {status === "loading" && (
              <p key="loading" className="status-line swap">Checking the server...</p>
            )}

            {status === "ok" && (
              <p key="ok" className="status-line swap">The ledger server is running.</p>
            )}

            {status === "error" && (
              <div key="error" className="swap">
                <p className="status-line">Can't reach the ledger server.</p>
                <button className="btn btn-primary" onClick={() => void check()}>
                  Try again
                </button>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
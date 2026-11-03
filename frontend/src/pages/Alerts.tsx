import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { ApiError, api } from "../lib/api";
import type { AlertsData } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: AlertsData };

export default function Alerts() {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<AlertsData>("/api/alerts")
      .then((data) => {
        if (!cancelled) setLoad({ status: "ready", data });
      })
      .catch((e) => {
        if (!cancelled) {
          setLoad({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  function retry() {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  return (
    <div className="page-body">
      <div className="page-head">
        <p className="eyebrow">Aurum / 05 Alerts</p>
        <h1 className="page-title">
          Items to <span className="accent">review</span>
        </h1>
        <p className="lede">
          Closed jobs and trends that are worth a closer look. These are prompts
          to check the receipts, not conclusions about anyone.
        </p>
      </div>

      {load.status === "loading" && (
        <div className="grid grid-wide" aria-busy="true" role="status">
          <span className="sr-only">Loading alerts</span>
          <div className="card skeleton" />
          <div className="card skeleton" />
        </div>
      )}

      {load.status === "error" && (
        <section className="card">
          <p className="status-line">{load.message}</p>
          <button className="btn btn-primary" onClick={retry}>
            Try again
          </button>
        </section>
      )}

      {load.status === "ready" && (
        <>
          <div className="summary">
            <div className="stat">
              <span className="stat-value figure">{load.data.drift_count}</span>
              <span className="stat-label">Trends to review</span>
            </div>
            <div className="stat">
              <span className="stat-value figure">{load.data.review_count}</span>
              <span className="stat-label">Jobs to review</span>
            </div>
          </div>

          <details className="rules">
            <summary>How these are chosen</summary>
            <ul>
              {load.data.rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </details>

          {load.data.alerts.length === 0 ? (
            <section className="card">
              <p className="status-line">Nothing to review right now.</p>
              <p className="muted">
                Every closed job is within its agreed wastage, and no trends stand out.
              </p>
            </section>
          ) : (
            <div className="grid grid-wide">
              {load.data.alerts.map((alert, index) => (
                <article
                  className="card alert-card"
                  key={alert.id}
                  style={{ "--i": index } as CSSProperties}
                >
                  <header className="job-head">
                    <div>
                      <p className="eyebrow">{alert.job_no ?? "Karigar"}</p>
                      <h2 className="karigar-name">{alert.karigar}</h2>
                    </div>
                    <span className="chip chip-review">{alert.title}</span>
                  </header>
                  <p className="alert-message">{alert.message}</p>
                  <dl className="slip-rows">
                    {alert.figures.map((f) => (
                      <div className="slip-row" key={f.label}>
                        <dt>{f.label}</dt>
                        <dd className="figure">{f.value}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
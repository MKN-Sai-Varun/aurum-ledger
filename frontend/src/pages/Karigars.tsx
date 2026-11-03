import { useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import type { Karigar } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: Karigar[] };

export default function Karigars() {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Karigar[]>("/api/karigars")
      .then((rows) => {
        if (!cancelled) setLoad({ status: "ready", rows });
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
        <p className="eyebrow">Aurum / 01 Karigars</p>
        <h1 className="page-title">
          Karigars and their <span className="accent">agreed wastage</span>
        </h1>
        <p className="lede">
          The loss allowed per item category. It is applied to the fine gold issued.
        </p>
      </div>

      {load.status === "loading" && (
        <div className="grid" aria-busy="true" role="status">
          <span className="sr-only">Loading karigars</span>
          <div className="card skeleton" />
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

      {load.status === "ready" && load.rows.length === 0 && (
        <section className="card">
          <p className="status-line">No karigars yet.</p>
        </section>
      )}

      {load.status === "ready" && load.rows.length > 0 && (
        <div className="grid">
          {load.rows.map((k) => (
            <article className="card karigar" key={k.id}>
              <header className="karigar-head">
                <h2 className="karigar-name">{k.name}</h2>
                <span className={`chip ${k.is_active ? "chip-ok" : "chip-muted"}`}>
                  {k.is_active ? "Active" : "Inactive"}
                </span>
              </header>
              <p className="karigar-meta">
                <span className="figure">{k.open_jobs}</span> open{" "}
                {k.open_jobs === 1 ? "job" : "jobs"}
              </p>
              {k.wastage.length === 0 ? (
                <p className="muted">No agreed wastage set.</p>
              ) : (
                <dl className="rates">
                  {k.wastage.map((w) => (
                    <div className="rate" key={w.category_id}>
                      <dt>{w.category}</dt>
                      <dd className="figure">{w.wastage_pct} %</dd>
                    </div>
                  ))}
                </dl>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
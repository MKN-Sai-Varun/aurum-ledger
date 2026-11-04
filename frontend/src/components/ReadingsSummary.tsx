import { useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import { KIND_LABEL } from "../lib/types";
import type { ReadingsSummaryData } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: ReadingsSummaryData };

const SOURCE_NAMES: Record<string, string> = {
  GEMINI: "AI reader",
  GROQ: "AI reader",
  TESSERACT: "Local reader",
  NONE: "Not read",
};

export default function ReadingsSummary() {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<ReadingsSummaryData>("/api/readings/summary")
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

  const sources: Record<string, number> = {};
  if (load.status === "ready") {
    for (const [key, count] of Object.entries(load.data.by_source)) {
      const name = SOURCE_NAMES[key] ?? key;
      sources[name] = (sources[name] ?? 0) + count;
    }
  }

  return (
    <section>
      <h2 className="section-heading">Photo readings</h2>

      {load.status === "loading" && (
        <div className="card skeleton" role="status" aria-busy="true">
          <span className="sr-only">Loading photo readings</span>
        </div>
      )}

      {load.status === "error" && (
        <section className="card">
          <p className="status-line">{load.message}</p>
          <button
            className="btn btn-primary"
            onClick={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </button>
        </section>
      )}

      {load.status === "ready" && load.data.total === 0 && (
        <section className="card">
          <p className="status-line">No photo readings yet.</p>
        </section>
      )}

      {load.status === "ready" && load.data.total > 0 && (
        <>
          <div className="summary">
            <div className="stat">
              <span className="stat-value figure">{load.data.total}</span>
              <span className="stat-label">Photos read</span>
            </div>
            <div className="stat">
              <span className="stat-value figure">{load.data.accepted}</span>
              <span className="stat-label">Confirmed as read</span>
            </div>
            <div className="stat">
              <span className="stat-value figure">{load.data.corrected}</span>
              <span className="stat-label">
                Corrected
                {load.data.correction_rate_pct !== null
                  ? ` (${load.data.correction_rate_pct} %)`
                  : ""}
              </span>
            </div>
            <div className="stat">
              <span className="stat-value figure">{load.data.unreadable}</span>
              <span className="stat-label">Couldn't be read</span>
            </div>
          </div>
          <p className="muted manage-note">
            {Object.entries(sources)
              .map(([name, count]) => `${name}: ${count}`)
              .join(" - ")}
            . A correction means the entered value differed from the photo and a reason was
            given. The photo can be the one that is wrong.
          </p>

          {load.data.recent_corrections.length === 0 ? (
            <section className="card">
              <p className="status-line">No corrections so far.</p>
            </section>
          ) : (
            <div className="table-wrap">
              <table className="table table-narrow">
                <thead>
                  <tr>
                    <th scope="col">Entry</th>
                    <th scope="col">Field</th>
                    <th scope="col" className="num">Photo said</th>
                    <th scope="col" className="num">Entered</th>
                    <th scope="col">Reason</th>
                    <th scope="col">By</th>
                  </tr>
                </thead>
                <tbody>
                  {load.data.recent_corrections.map((c) => (
                    <tr key={`${c.txn_no}-${c.target}-${c.at}`}>
                      <td className="figure">{c.txn_no ?? "-"}</td>
                      <td>{c.target === "WEIGHT" ? "Weight" : "Purity"}</td>
                      <td className="num figure">{c.read_value ?? "-"}</td>
                      <td className="num figure">{c.entered_value ?? "-"}</td>
                      <td>{c.reason ?? "-"}</td>
                      <td>{c.by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export { KIND_LABEL };
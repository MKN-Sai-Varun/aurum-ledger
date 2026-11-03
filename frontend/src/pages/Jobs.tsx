import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { useAuth } from "../auth/auth-context";
import ReceiptDialog from "../components/ReceiptDialog";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import type { Job } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: Job[] };

type Filter = "OPEN" | "CLOSED" | "ALL";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "OPEN", label: "Open" },
  { value: "CLOSED", label: "Closed" },
  { value: "ALL", label: "All" },
];

export default function Jobs() {
  const { state } = useAuth();
  const role = state.status === "signed-in" ? state.user.role : null;
  const isClerk = role === "issue_clerk";
  const isFinance = role === "finance_head";

  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>("OPEN");
  const [query, setQuery] = useState("");
  const [receiptFor, setReceiptFor] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Job[]>("/api/jobs")
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

  function replaceJob(updated: Job) {
    setLoad((prev) =>
      prev.status === "ready"
        ? { ...prev, rows: prev.rows.map((j) => (j.job_no === updated.job_no ? updated : j)) }
        : prev,
    );
  }

  async function closeJob(job: Job) {
    if (closing) return;
    setClosing(job.job_no);
    setActionError(null);
    try {
      const updated = await api.post<Job>(`/api/jobs/${job.job_no}/close`);
      replaceJob(updated);
      setConfirming(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      setClosing(null);
    }
  }

  const rows = load.status === "ready" ? load.rows : [];
  const openCount = rows.filter((j) => j.status === "OPEN").length;
  const closedCount = rows.length - openCount;
  const reviewCount = rows.filter((j) => j.review === true).length;
  const receiptJob = receiptFor === null ? undefined : rows.find((j) => j.job_no === receiptFor);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter(
      (j) =>
        (filter === "ALL" || j.status === filter) &&
        (needle === "" ||
          j.job_no.toLowerCase().includes(needle) ||
          j.karigar.toLowerCase().includes(needle)),
    );
  }, [rows, filter, query]);

  return (
    <div className="page-body">
      <div className="page-head">
        <p className="eyebrow">Aurum / 03 Jobs</p>
        <h1 className="page-title">
          Jobs and <span className="accent">returns</span>
        </h1>
        <p className="lede">
          Each job is one batch of gold issued to a karigar. Returns bring the
          outstanding fine gold down.
        </p>
      </div>

      {load.status === "loading" && (
        <div className="grid grid-wide" aria-busy="true" role="status">
          <span className="sr-only">Loading jobs</span>
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

      {load.status === "ready" && (
        <>
          <div className="summary">
            <div className="stat">
              <span className="stat-value figure">{openCount}</span>
              <span className="stat-label">Open jobs</span>
            </div>
            <div className="stat">
              <span className="stat-value figure">{closedCount}</span>
              <span className="stat-label">Closed jobs</span>
            </div>
            {isFinance && (
              <div className="stat">
                <span className="stat-value figure">{reviewCount}</span>
                <span className="stat-label">To review</span>
              </div>
            )}
          </div>

          <div className="toolbar">
            <div className="tabs" role="group" aria-label="Filter jobs">
              {FILTERS.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  className="tab"
                  aria-pressed={filter === f.value}
                  onClick={() => setFilter(f.value)}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="field toolbar-search">
              <label htmlFor="job-search">Search jobs</label>
              <input
                id="job-search"
                className="input"
                type="search"
                autoComplete="off"
                maxLength={100}
                placeholder="Job number or karigar"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <p className="muted toolbar-count" aria-live="polite">
              Showing <span className="figure">{visible.length}</span> of{" "}
              <span className="figure">{rows.length}</span>
            </p>
          </div>

          {actionError && (
            <p className="banner" role="alert">
              {actionError}
            </p>
          )}

          {visible.length === 0 ? (
            <section className="card">
              <p className="status-line">
                {rows.length === 0
                  ? "No jobs yet."
                  : query.trim()
                    ? `No jobs match "${query.trim()}".`
                    : filter === "OPEN"
                      ? "There are no open jobs."
                      : "There are no jobs in this view."}
              </p>
              {query.trim() !== "" && (
                <button className="btn" onClick={() => setQuery("")}>
                  Clear search
                </button>
              )}
              {isClerk && query.trim() === "" && filter === "OPEN" && (
                <a className="btn btn-primary" href="#/issue">
                  Issue gold
                </a>
              )}
            </section>
          ) : (
            <div className="grid grid-wide">
              {visible.map((job, index) => (
                <article
                  className="card job"
                  key={job.job_no}
                  style={{ "--i": index } as CSSProperties}
                >
                  <header className="job-head">
                    <div>
                      <p className="eyebrow">{job.job_no}</p>
                      <h2 className="karigar-name">{job.karigar}</h2>
                      <p className="karigar-meta">
                        {job.category} - opened {showDate(job.opened_on)}
                        {job.closed_on ? `, closed ${showDate(job.closed_on)}` : ""}
                      </p>
                    </div>
                    <span className={`chip ${job.status === "OPEN" ? "chip-ok" : "chip-muted"}`}>
                      {job.status === "OPEN" ? "Open" : "Closed"}
                    </span>
                  </header>

                  <dl className="slip-rows">
                    <div className="slip-row">
                      <dt>Fine gold issued</dt>
                      <dd className="figure">{job.issued_fine_g} g</dd>
                    </div>
                    <div className="slip-row">
                      <dt>Returned</dt>
                      <dd className="figure">{job.returned_fine_g} g</dd>
                    </div>
                    <div className="slip-row slip-key">
                      <dt>Outstanding</dt>
                      <dd className="figure">{job.outstanding_g} g</dd>
                    </div>
                    <div className="slip-row">
                      <dt>Allowed wastage</dt>
                      <dd className="figure">
                        {job.allowed_wastage_g} g ({job.allowed_wastage_pct} %)
                      </dd>
                    </div>
                  </dl>

                  {isFinance && job.status === "CLOSED" && job.review !== null && (
                    <p className="job-flag">
                      {job.review ? (
                        <span className="chip chip-review">
                          To review: {job.unexplained_g} g beyond the agreed wastage
                        </span>
                      ) : (
                        <span className="chip chip-ok">Within the agreed wastage</span>
                      )}
                    </p>
                  )}

                  {isClerk && job.status === "OPEN" && (
                    <div className="job-actions">
                      {confirming === job.job_no ? (
                        <>
                          <p className="manage-note">
                            No more receipts can be added once a job is closed.
                          </p>
                          <button
                            className="btn btn-danger"
                            disabled={closing !== null}
                            onClick={() => void closeJob(job)}
                          >
                            {closing === job.job_no ? "Closing..." : "Yes, close job"}
                          </button>
                          <button
                            className="btn"
                            disabled={closing !== null}
                            onClick={() => setConfirming(null)}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          {job.outstanding_g === "0.000" ? (
                            <>
                              <p className="manage-note">
                                Everything issued has been returned.
                              </p>
                              <button
                                className="btn btn-primary"
                                onClick={() => setConfirming(job.job_no)}
                              >
                                Close job
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                className="btn btn-primary"
                                onClick={() => {
                                  setActionError(null);
                                  setReceiptFor(job.job_no);
                                }}
                              >
                                Record receipt
                              </button>
                              <button className="btn" onClick={() => setConfirming(job.job_no)}>
                                Close job
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </>
      )}

      {receiptJob && (
        <ReceiptDialog
          key={receiptJob.job_no}
          job={receiptJob}
          onSaved={replaceJob}
          onClose={() => setReceiptFor(null)}
        />
      )}
    </div>
  );
}
import { useEffect, useMemo, useState } from "react";
import FollowUpDialog from "../components/FollowUpDialog";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import { parseWeightMg } from "../lib/gold";
import type { AgingData, AgingJob } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: AgingData };

type Row = AgingJob & { band: string };
type Sort = "age" | "outstanding" | "quiet" | "karigar";

const SORTS: { value: Sort; label: string }[] = [
  { value: "age", label: "Oldest first" },
  { value: "outstanding", label: "Most gold outstanding" },
  { value: "quiet", label: "Longest since last entry" },
  { value: "karigar", label: "Karigar A to Z" },
];

const TONE: Record<string, string> = {
  "0-2": "chip-ok",
  "3-7": "chip-muted",
  "8-14": "chip-gold",
  "15+": "chip-review",
};

function ago(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "today";
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

function compare(sort: Sort) {
  return (a: Row, b: Row): number => {
    let result = 0;
    if (sort === "age") result = b.age_days - a.age_days;
    else if (sort === "outstanding") {
      result = (parseWeightMg(b.outstanding_g) ?? 0) - (parseWeightMg(a.outstanding_g) ?? 0);
    } else if (sort === "quiet") {
      result = (b.days_since_activity ?? -1) - (a.days_since_activity ?? -1);
    } else result = a.karigar.localeCompare(b.karigar);
    return result !== 0 ? result : a.job_no.localeCompare(b.job_no);
  };
}

export default function Aging() {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [band, setBand] = useState("ALL");
  const [sort, setSort] = useState<Sort>("age");
  const [query, setQuery] = useState("");
  const [following, setFollowing] = useState<AgingJob | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<AgingData>("/api/job-aging")
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

  const data = load.status === "ready" ? load.data : null;

  const rows = useMemo<Row[]>(
    () => (data ? data.buckets.flatMap((b) => b.jobs.map((job) => ({ ...job, band: b.key }))) : []),
    [data],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows
      .filter(
        (r) =>
          (band === "ALL" || r.band === band) &&
          (needle === "" ||
            r.job_no.toLowerCase().includes(needle) ||
            r.karigar.toLowerCase().includes(needle)),
      )
      .sort(compare(sort));
  }, [rows, band, query, sort]);

  const filtered = band !== "ALL" || query.trim() !== "";

  return (
    <div className="page-body">
      <div className="page-head">
        <p className="eyebrow">Aurum / 08 Job aging</p>
        <h1 className="page-title">
          Open jobs, <span className="accent">by age</span>
        </h1>
        <p className="lede">
          Where fine gold is still outstanding and for how long. A follow-up records a note
          against the job. It doesn't send a message.
        </p>
      </div>

      {notice && (
        <p className="banner banner-ok" role="status">
          {notice}
        </p>
      )}

      {load.status === "loading" && (
        <div className="card skeleton" aria-busy="true" role="status">
          <span className="sr-only">Loading open jobs</span>
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

      {data && data.total_open === 0 && (
        <section className="card">
          <p className="status-line">There are no open jobs.</p>
        </section>
      )}

      {data && data.total_open > 0 && (
        <>
          <div className="summary">
            <div className="stat">
              <span className="stat-value figure">{data.total_open}</span>
              <span className="stat-label">Open jobs</span>
            </div>
            <div className="stat stat-key">
              <span className="stat-value figure">{data.total_outstanding_g}</span>
              <span className="stat-label">Fine gold outstanding (g)</span>
            </div>
          </div>

          <div className="tabs tabs-wrap" role="group" aria-label="Filter by age">
            <button
              type="button"
              className="tab"
              aria-pressed={band === "ALL"}
              onClick={() => setBand("ALL")}
            >
              All ({data.total_open})
            </button>
            {data.buckets.map((b) => (
              <button
                key={b.key}
                type="button"
                className="tab"
                aria-pressed={band === b.key}
                onClick={() => setBand(b.key)}
              >
                {b.label} ({b.count})
              </button>
            ))}
          </div>

          <div className="aging-toolbar">
            <div className="field">
              <label htmlFor="ag-search">Search</label>
              <input
                id="ag-search"
                className="input"
                type="search"
                autoComplete="off"
                maxLength={100}
                placeholder="Job number or karigar"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="ag-sort">Sort by</label>
              <select
                id="ag-sort"
                className="input"
                value={sort}
                onChange={(e) => setSort(e.target.value as Sort)}
              >
                {SORTS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <p className="muted toolbar-count" aria-live="polite">
              Showing <span className="figure">{visible.length}</span> of{" "}
              <span className="figure">{rows.length}</span>
            </p>
          </div>

          {visible.length === 0 ? (
            <section className="card">
              <p className="status-line">No open jobs match.</p>
              {filtered && (
                <button
                  className="btn"
                  onClick={() => {
                    setBand("ALL");
                    setQuery("");
                  }}
                >
                  Clear filters
                </button>
              )}
            </section>
          ) : (
            <div className="table-wrap">
              <table className="table table-aging">
                <thead>
                  <tr>
                    <th scope="col">Job</th>
                    <th scope="col">Karigar</th>
                    <th scope="col">Open for</th>
                    <th scope="col" className="num">Issued (g)</th>
                    <th scope="col" className="num">Outstanding (g)</th>
                    <th scope="col">Last entry</th>
                    <th scope="col">Follow-up</th>
                    <th scope="col" className="col-action">
                      <span className="sr-only">Action</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.job_no}>
                      <td>
                        <div className="figure">{r.job_no}</div>
                        <div className="cell-sub">{r.category}</div>
                      </td>
                      <td>{r.karigar}</td>
                      <td>
                        <span className={`chip ${TONE[r.band] ?? "chip-muted"}`}>
                          {r.age_days} {r.age_days === 1 ? "day" : "days"}
                        </span>
                        <div className="cell-sub">since {showDate(r.opened_on)}</div>
                      </td>
                      <td className="num figure">{r.issued_fine_g}</td>
                      <td className="num figure cell-balance">{r.outstanding_g}</td>
                      <td>
                        {r.last_activity ? (
                          <>
                            <div>{showDate(r.last_activity)}</div>
                            <div className="cell-sub">{ago(r.days_since_activity)}</div>
                          </>
                        ) : (
                          <span className="muted">No entries</span>
                        )}
                      </td>
                      <td className="cell-note">
                        {r.last_followup_note && r.last_followup_on ? (
                          <>
                            <div>{showDate(r.last_followup_on)}</div>
                            <div className="cell-sub">{r.last_followup_note}</div>
                          </>
                        ) : (
                          <span className="muted">None yet</span>
                        )}
                      </td>
                      <td className="col-action">
                        <button
                          className="btn btn-small"
                          onClick={() => {
                            setNotice(null);
                            setFollowing(r);
                          }}
                          aria-label={`Follow up ${r.job_no}`}
                        >
                          Follow up
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {following && (
        <FollowUpDialog
          key={following.job_no}
          job={following}
          onDone={(message) => {
            setFollowing(null);
            setNotice(message);
            setAttempt((n) => n + 1);
          }}
          onClose={() => setFollowing(null)}
        />
      )}
    </div>
  );
}
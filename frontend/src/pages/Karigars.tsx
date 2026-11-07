import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { useAuth } from "../auth/auth-context";
import AddKarigar from "../components/AddKarigar";
import ManageKarigar from "../components/ManageKarigar";
import { ApiError, api } from "../lib/api";
import type { Category, Karigar } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: Karigar[]; categories: Category[] };

const BAR_SCALE_PCT = 5;

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

// Display only: the bar is a visual aid, the exact figure sits beside it.
function barWidth(pct: string): string {
  const value = Number.parseFloat(pct);
  if (!Number.isFinite(value) || value <= 0) return "0%";
  return `${Math.min(100, (value / BAR_SCALE_PCT) * 100)}%`;
}

function byName(a: Karigar, b: Karigar): number {
  return a.name.localeCompare(b.name);
}

export default function Karigars() {
  const { state } = useAuth();
  const canEdit = state.status === "signed-in" && state.user.role === "finance_head";

  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [managingId, setManagingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<Karigar[]>("/api/karigars"),
      canEdit ? api.get<Category[]>("/api/categories") : Promise.resolve([] as Category[]),
    ])
      .then(([rows, categories]) => {
        if (!cancelled) setLoad({ status: "ready", rows, categories });
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
  }, [attempt, canEdit]);

  function retry() {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  function replaceRow(updated: Karigar) {
    setLoad((prev) =>
      prev.status === "ready"
        ? { ...prev, rows: prev.rows.map((r) => (r.id === updated.id ? updated : r)) }
        : prev,
    );
  }

  function addRow(created: Karigar) {
    setLoad((prev) =>
      prev.status === "ready"
        ? { ...prev, rows: [...prev.rows, created].sort(byName) }
        : prev,
    );
  }

  const rows = useMemo(() => load.status === "ready" ? load.rows : [], [load]);
  const categories = load.status === "ready" ? load.categories : [];
  const activeCount = rows.filter((k) => k.is_active).length;
  const openJobs = rows.reduce((sum, k) => sum + k.open_jobs, 0);
  const managing = managingId === null ? undefined : rows.find((k) => k.id === managingId);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? rows.filter((k) => k.name.toLowerCase().includes(needle)) : rows;
  }, [rows, query]);

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
        {load.status === "ready" && !canEdit && (
          <p className="muted manage-note">Only the finance head can change these.</p>
        )}
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

      {load.status === "ready" && rows.length === 0 && (
        <section className="card">
          <p className="status-line">No karigars yet.</p>
          {canEdit && (
            <button className="btn btn-primary" onClick={() => setAdding(true)}>
              Add karigar
            </button>
          )}
        </section>
      )}

      {load.status === "ready" && rows.length > 0 && (
        <>
          <div className="summary">
            <div className="stat">
              <span className="stat-value figure">{activeCount}</span>
              <span className="stat-label">Active karigars</span>
            </div>
            <div className="stat">
              <span className="stat-value figure">{openJobs}</span>
              <span className="stat-label">Open jobs</span>
            </div>
          </div>

          <div className="toolbar">
            <div className="field toolbar-search">
              <label htmlFor="search">Search karigars</label>
              <input
                id="search"
                className="input"
                type="search"
                autoComplete="off"
                maxLength={100}
                placeholder="Type a name"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <p className="muted toolbar-count" aria-live="polite">
              Showing <span className="figure">{visible.length}</span> of{" "}
              <span className="figure">{rows.length}</span>
            </p>
            {canEdit && (
              <button className="btn btn-primary toolbar-add" onClick={() => setAdding(true)}>
                Add karigar
              </button>
            )}
          </div>

          {visible.length === 0 ? (
            <section className="card">
              <p className="status-line">No karigars match "{query.trim()}".</p>
              <button className="btn" onClick={() => setQuery("")}>
                Clear search
              </button>
            </section>
          ) : (
            <div className="grid">
              {visible.map((k, index) => (
                <article
                  className={`card karigar${k.is_active ? "" : " karigar-inactive"}`}
                  key={k.id}
                  style={{ "--i": index } as CSSProperties}
                >
                  <header className="karigar-head">
                    <span className="avatar" aria-hidden="true">
                      {initials(k.name)}
                    </span>
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
                          <span className="bar" aria-hidden="true">
                            <span style={{ width: barWidth(w.wastage_pct) }} />
                          </span>
                        </div>
                      ))}
                    </dl>
                  )}
                  {canEdit && (
                    <button
                      className="btn card-action"
                      onClick={() => setManagingId(k.id)}
                      aria-label={`Manage ${k.name}`}
                    >
                      Manage
                    </button>
                  )}
                </article>
              ))}
            </div>
          )}
        </>
      )}

      {adding && (
        <AddKarigar
          onClose={() => setAdding(false)}
          onCreated={(created) => {
            addRow(created);
            setAdding(false);
            setManagingId(created.id);
          }}
        />
      )}

      {managing && (
        <ManageKarigar
          key={managing.id}
          karigar={managing}
          categories={categories}
          onChanged={replaceRow}
          onClose={() => setManagingId(null)}
        />
      )}
    </div>
  );
}
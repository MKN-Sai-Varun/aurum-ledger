import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import { groupRupees } from "../lib/money";
import type { OldGold } from "../lib/types";
import { PurchaseDetails, VoidPurchase } from "./OldGoldDialogs";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: OldGold[] };

export default function OldGoldList({
  refreshKey,
  isFinance,
}: {
  refreshKey: number;
  isFinance: boolean;
}) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [viewing, setViewing] = useState<string | null>(null);
  const [voiding, setVoiding] = useState<OldGold | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<OldGold[]>("/api/old-gold")
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
  }, [attempt, refreshKey]);

  function replaceRow(updated: OldGold) {
    setLoad((prev) =>
      prev.status === "ready"
        ? { ...prev, rows: prev.rows.map((r) => (r.og_no === updated.og_no ? updated : r)) }
        : prev,
    );
  }

  const rows = load.status === "ready" ? load.rows : [];
  const reviewCount = rows.filter((r) => r.needs_review === true).length;

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (r) =>
        r.bill_no.toLowerCase().includes(needle) ||
        r.customer_name.toLowerCase().includes(needle) ||
        r.og_no.toLowerCase().includes(needle),
    );
  }, [rows, query]);

  return (
    <div>
      {load.status === "loading" && (
        <div className="card skeleton" role="status" aria-busy="true">
          <span className="sr-only">Loading purchases</span>
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

      {load.status === "ready" && rows.length === 0 && (
        <section className="card">
          <p className="status-line">No old gold has been recorded yet.</p>
        </section>
      )}

      {load.status === "ready" && rows.length > 0 && (
        <>
          <div className="summary">
            <div className="stat">
              <span className="stat-value figure">{rows.filter((r) => !r.voided).length}</span>
              <span className="stat-label">Purchases</span>
            </div>
            {isFinance && (
              <div className="stat">
                <span className="stat-value figure">{reviewCount}</span>
                <span className="stat-label">High-value cash to review</span>
              </div>
            )}
          </div>

          <div className="toolbar">
            <div className="field toolbar-search">
              <label htmlFor="og-search">Search purchases</label>
              <input
                id="og-search"
                className="input"
                type="search"
                autoComplete="off"
                maxLength={100}
                placeholder="Bill, customer or purchase number"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <p className="muted toolbar-count" aria-live="polite">
              Showing <span className="figure">{visible.length}</span> of{" "}
              <span className="figure">{rows.length}</span>
            </p>
          </div>

          {visible.length === 0 ? (
            <section className="card">
              <p className="status-line">No purchases match "{query.trim()}".</p>
              <button className="btn" onClick={() => setQuery("")}>
                Clear search
              </button>
            </section>
          ) : (
            <div className="table-wrap">
              <table className="table table-wide">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Purchase</th>
                    <th scope="col" className="num">Fine (g)</th>
                    <th scope="col" className="num">Value (Rs)</th>
                    <th scope="col">Payment</th>
                    <th scope="col">PAN</th>
                    <th scope="col">Status</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.og_no} className={r.voided ? "row-reversed" : undefined}>
                      <td>{showDate(r.entry_date)}</td>
                      <td>
                        <div className="figure">{r.og_no}</div>
                        <div className="cell-sub">
                          {r.bill_no} - {r.customer_name}
                        </div>
                      </td>
                      <td className="num figure">{r.fine_weight_g}</td>
                      <td className="num figure">{groupRupees(r.value)}</td>
                      <td>{r.payment_label}</td>
                      <td className="figure">{r.pan ?? "-"}</td>
                      <td>
                        <div className="flag-row">
                          {r.high_value && <span className="chip chip-gold">High value</span>}
                          {r.needs_review === true && (
                            <span className="chip chip-review">To review</span>
                          )}
                          {r.voided && <span className="chip chip-muted">Voided</span>}
                        </div>
                      </td>
                      <td>
                        <div className="flag-row">
                          <button
                            className="btn btn-small"
                            onClick={() => setViewing(r.og_no)}
                            aria-label={`Details of ${r.og_no}`}
                          >
                            Details
                          </button>
                          {isFinance && !r.voided && (
                            <button
                              className="btn btn-small"
                              onClick={() => setVoiding(r)}
                              aria-label={`Void ${r.og_no}`}
                            >
                              Void
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {viewing && <PurchaseDetails key={viewing} ogNo={viewing} onClose={() => setViewing(null)} />}

      {voiding && (
        <VoidPurchase
          key={voiding.og_no}
          purchase={voiding}
          onDone={(updated) => {
            replaceRow(updated);
            setVoiding(null);
          }}
          onClose={() => setVoiding(null)}
        />
      )}
    </div>
  );
}
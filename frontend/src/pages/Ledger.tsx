import { useEffect, useState } from "react";
import { useAuth } from "../auth/auth-context";
import ReverseDialog from "../components/ReverseDialog";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import { KIND_LABEL } from "../lib/types";
import type { Karigar, LedgerData, LedgerRow, ReversalResult } from "../lib/types";

type KarigarLoad =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: Karigar[] };

type LedgerLoad =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: LedgerData };

export default function Ledger() {
  const { state } = useAuth();
  const isFinance = state.status === "signed-in" && state.user.role === "finance_head";

  const [karigars, setKarigars] = useState<KarigarLoad>({ status: "loading" });
  const [karigarId, setKarigarId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [ledger, setLedger] = useState<LedgerLoad>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const [reversing, setReversing] = useState<LedgerRow | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Karigar[]>("/api/karigars")
      .then((rows) => {
        if (cancelled) return;
        setKarigars({ status: "ready", rows });
        if (rows.length > 0) setKarigarId(String(rows[0].id));
      })
      .catch((e) => {
        if (!cancelled) {
          setKarigars({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const rangeBad = from !== "" && to !== "" && from > to;

  useEffect(() => {
    if (karigarId === "" || rangeBad) return;
    let cancelled = false;
    
    async function fetchLedger() {
      const params = new URLSearchParams();
      if (from) params.set("from", from);
      if (to) params.set("to", to);
      const query = params.toString();
      
      try {
        setLedger({ status: "loading" });
        const data = await api.get<LedgerData>(`/api/karigars/${karigarId}/ledger${query ? `?${query}` : ""}`);
        if (!cancelled) setLedger({ status: "ready", data });
      } catch (e) {
        if (!cancelled) {
          setLedger({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      }
    }
    
    fetchLedger();
    return () => {
      cancelled = true;
    };
  }, [karigarId, from, to, rangeBad, attempt]);

  function reload() {
    setAttempt((n) => n + 1);
  }

  function reversed(result: ReversalResult) {
    setReversing(null);
    setNotice(`${result.reverses_txn_no} reversed as ${result.txn_no}.`);
    reload();
  }

  return (
    <div className="page-body">
      <div className="page-head">
        <p className="eyebrow">Aurum / 04 Ledger</p>
        <h1 className="page-title">
          Every movement, <span className="accent">in order</span>
        </h1>
        <p className="lede">
          Gold issued and returned for one karigar, with the balance after each entry.
          Corrections appear as new entries and never change the past.
        </p>
      </div>

      {karigars.status === "loading" && (
        <div className="card skeleton" role="status" aria-busy="true">
          <span className="sr-only">Loading karigars</span>
        </div>
      )}

      {karigars.status === "error" && (
        <section className="card">
          <p className="status-line">{karigars.message}</p>
          <button className="btn btn-primary" onClick={reload}>
            Try again
          </button>
        </section>
      )}

      {karigars.status === "ready" && karigars.rows.length === 0 && (
        <section className="card">
          <p className="status-line">There are no karigars yet.</p>
        </section>
      )}

      {karigars.status === "ready" && karigars.rows.length > 0 && (
        <>
          <div className="toolbar ledger-filters">
            <div className="field">
              <label htmlFor="l-karigar">Karigar</label>
              <select
                id="l-karigar"
                className="input"
                value={karigarId}
                onChange={(e) => {
                  setKarigarId(e.target.value);
                  setNotice(null);
                }}
              >
                {karigars.rows.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name}
                    {k.is_active ? "" : " (inactive)"}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="l-from">From</label>
              <input
                id="l-from"
                className="input"
                type="date"
                value={from}
                max={to || undefined}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="l-to">To</label>
              <input
                id="l-to"
                className="input"
                type="date"
                value={to}
                min={from || undefined}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
            {(from || to) && (
              <button
                className="btn ledger-clear"
                onClick={() => {
                  setFrom("");
                  setTo("");
                }}
              >
                Clear dates
              </button>
            )}
          </div>

          {rangeBad && (
            <p className="banner" role="alert">
              The start date is after the end date.
            </p>
          )}

          {notice && (
            <p className="banner banner-ok" role="status">
              {notice}
            </p>
          )}

          {!rangeBad && ledger.status === "loading" && (
            <div className="card skeleton" role="status" aria-busy="true">
              <span className="sr-only">Loading the ledger</span>
            </div>
          )}

          {!rangeBad && ledger.status === "error" && (
            <section className="card">
              <p className="status-line">{ledger.message}</p>
              <button className="btn btn-primary" onClick={reload}>
                Try again
              </button>
            </section>
          )}

          {!rangeBad && ledger.status === "ready" && (
            <>
              <div className="summary">
                <div className="stat">
                  <span className="stat-value figure">{ledger.data.opening_balance_g}</span>
                  <span className="stat-label">Opening balance (g)</span>
                </div>
                <div className="stat stat-key">
                  <span className="stat-value figure">{ledger.data.closing_balance_g}</span>
                  <span className="stat-label">Closing balance (g)</span>
                </div>
              </div>

              {ledger.data.entries.length === 0 ? (
                <section className="card">
                  <p className="status-line">
                    {from || to
                      ? "No entries in this date range."
                      : `${ledger.data.karigar} has no entries yet.`}
                  </p>
                </section>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Date</th>
                        <th scope="col">Entry</th>
                        <th scope="col">Job</th>
                        <th scope="col" className="num">Fine (g)</th>
                        <th scope="col" className="num">Change (g)</th>
                        <th scope="col" className="num">Balance (g)</th>
                        {isFinance && <th scope="col">Action</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {ledger.data.entries.map((row) => {
                        const canReverse =
                          isFinance && row.kind !== "REVERSAL" && row.reversed_by === null;
                        return (
                          <tr
                            key={row.txn_no}
                            className={row.reversed_by ? "row-reversed" : undefined}
                          >
                            <td>{showDate(row.entry_date)}</td>
                            <td>
                              <div>
                                {KIND_LABEL[row.kind] ?? row.kind}{" "}
                                <span className="figure muted">{row.txn_no}</span>
                              </div>
                              {row.huid && (
                                <div className="cell-sub figure">HUID {row.huid}</div>
                              )}
                              {row.reversed_by && (
                                <div className="cell-sub">
                                  <span className="chip chip-muted">
                                    Reversed by {row.reversed_by}
                                  </span>
                                </div>
                              )}
                              {row.reverses && (
                                <div className="cell-sub">Cancels {row.reverses}</div>
                              )}
                              {row.note && <div className="cell-sub">{row.note}</div>}
                            </td>
                            <td className="figure">{row.job_no}</td>
                            <td className="num figure">{row.fine_weight_g}</td>
                            <td className="num figure">{row.change_g}</td>
                            <td className="num figure cell-balance">{row.balance_g}</td>
                            {isFinance && (
                              <td>
                                {canReverse && (
                                  <button
                                    className="btn btn-small"
                                    onClick={() => {
                                      setNotice(null);
                                      setReversing(row);
                                    }}
                                    aria-label={`Reverse ${row.txn_no}`}
                                  >
                                    Reverse
                                  </button>
                                )}
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {ledger.data.truncated && (
                <p className="muted manage-note">
                  Showing the first {ledger.data.entries.length} entries. Narrow the
                  dates to see the rest. The closing balance still covers every entry.
                </p>
              )}
            </>
          )}
        </>
      )}

      {reversing && (
        <ReverseDialog
          key={reversing.txn_no}
          row={reversing}
          onDone={reversed}
          onClose={() => setReversing(null)}
        />
      )}
    </div>
  );
}
import { useEffect, useState } from "react";
import RefinerDialog from "../components/RefinerDialog";
import { ApiError, api } from "../lib/api";
import { showDate, todayIST } from "../lib/dates";
import type { Statement, StockMove } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; statement: Statement; moves: StockMove[] };

export default function Stock() {
  const [today] = useState(todayIST);
  const [asOf, setAsOf] = useState(today);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [moving, setMoving] = useState<"SEND" | "RECEIVE" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(asOf) && asOf <= today;

  useEffect(() => {
    if (!dateOk) return;
    let cancelled = false;
    setLoad({ status: "loading" });
    Promise.all([
      api.get<Statement>(`/api/stock/statement?as_of=${asOf}`),
      api.get<StockMove[]>("/api/stock/entries"),
    ])
      .then(([statement, moves]) => {
        if (!cancelled) setLoad({ status: "ready", statement, moves });
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
  }, [asOf, dateOk, attempt]);

  function reload() {
    setAttempt((n) => n + 1);
  }

  const viewingToday = asOf === today;

  return (
    <div className="page-body">
      <div className="page-head">
        <p className="eyebrow">Aurum / 06 Stock</p>
        <h1 className="page-title">
          Where every gram <span className="accent">sits</span>
        </h1>
        <p className="lede">
          The daily stock statement: gold in the vault, with karigars and at the
          refiner. Owner view only.
        </p>
      </div>

      <div className="toolbar ledger-filters">
        <div className="field">
          <label htmlFor="s-date">Statement for</label>
          <input
            id="s-date"
            className="input"
            type="date"
            max={today}
            value={asOf}
            onChange={(e) => {
              setNotice(null);
              setAsOf(e.target.value);
            }}
            aria-invalid={!dateOk}
          />
        </div>
        {dateOk && (
          <a className="btn ledger-clear" href={`/api/stock/statement.csv?as_of=${asOf}`} download>
            Download CSV
          </a>
        )}
      </div>

      {!dateOk && (
        <p className="banner" role="alert">
          Pick a date that is today or earlier.
        </p>
      )}

      {notice && (
        <p className="banner banner-ok" role="status">
          {notice}
        </p>
      )}

      {dateOk && load.status === "loading" && (
        <div className="tile-grid" aria-busy="true" role="status">
          <span className="sr-only">Loading the statement</span>
          <div className="card skeleton" />
          <div className="card skeleton" />
          <div className="card skeleton" />
          <div className="card skeleton" />
        </div>
      )}

      {dateOk && load.status === "error" && (
        <section className="card">
          <p className="status-line">{load.message}</p>
          <button className="btn btn-primary" onClick={reload}>
            Try again
          </button>
        </section>
      )}

      {dateOk && load.status === "ready" && (
        <>
          {!load.statement.consistent && (
            <p className="banner" role="alert">
              These figures don't add up: more gold is recorded as out of the vault than
              was ever in it. Check the opening stock and the refiner movements.
            </p>
          )}

          <div className="tile-grid">
            <div className="card tile tile-key">
              <span className="tile-label">In the vault</span>
              <span className="tile-value figure">{load.statement.vault_g}</span>
              <span className="tile-unit">g fine</span>
            </div>
            <div className="card tile">
              <span className="tile-label">With karigars</span>
              <span className="tile-value figure">{load.statement.karigars_g}</span>
              <span className="tile-unit">g fine</span>
            </div>
            <div className="card tile">
              <span className="tile-label">At the refiner</span>
              <span className="tile-value figure">{load.statement.refiner_g}</span>
              <span className="tile-unit">g fine</span>
            </div>
            <div className="card tile">
              <span className="tile-label">Total stock</span>
              <span className="tile-value figure">{load.statement.total_g}</span>
              <span className="tile-unit">g fine</span>
            </div>
          </div>
          <p className="muted manage-note">
            {load.statement.basis} As of {showDate(load.statement.as_of)}. The CSV is a plain
            file, because the Tally import format wasn't specified.
          </p>

          {viewingToday && (
            <div className="inline stock-actions">
              <button className="btn btn-primary" onClick={() => setMoving("SEND")}>
                Send to refiner
              </button>
              <button
                className="btn"
                onClick={() => setMoving("RECEIVE")}
                disabled={load.statement.refiner_g === "0.000"}
              >
                Receive from refiner
              </button>
            </div>
          )}

          <h2 className="section-heading">With karigars</h2>
          {load.statement.holders.length === 0 ? (
            <section className="card">
              <p className="status-line">No karigar holds any gold on this date.</p>
            </section>
          ) : (
            <div className="table-wrap">
              <table className="table table-narrow">
                <thead>
                  <tr>
                    <th scope="col">Karigar</th>
                    <th scope="col" className="num">Fine gold (g)</th>
                  </tr>
                </thead>
                <tbody>
                  {load.statement.holders.map((h) => (
                    <tr key={h.karigar_id}>
                      <td>{h.karigar}</td>
                      <td className="num figure">{h.balance_g}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2 className="section-heading">Stock movements</h2>
          {load.moves.length === 0 ? (
            <section className="card">
              <p className="status-line">No movements recorded yet.</p>
            </section>
          ) : (
            <div className="table-wrap">
              <table className="table table-narrow">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Movement</th>
                    <th scope="col" className="num">Fine gold (g)</th>
                    <th scope="col">By</th>
                  </tr>
                </thead>
                <tbody>
                  {load.moves.map((m) => (
                    <tr key={m.id}>
                      <td>{showDate(m.entry_date)}</td>
                      <td>
                        <div>{m.label}</div>
                        {m.note && <div className="cell-sub">{m.note}</div>}
                      </td>
                      <td className="num figure">{m.fine_weight_g}</td>
                      <td>{m.by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {moving && load.status === "ready" && (
        <RefinerDialog
          key={moving}
          direction={moving}
          availableG={moving === "SEND" ? load.statement.vault_g : load.statement.refiner_g}
          today={today}
          onSaved={(message) => {
            setMoving(null);
            setNotice(message);
            reload();
          }}
          onClose={() => setMoving(null)}
        />
      )}
    </div>
  );
}
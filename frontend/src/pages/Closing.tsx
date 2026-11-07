import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Dialog from "../components/Dialog";
import { ApiError, api, saveErrorMessage } from "../lib/api";
import { showDate, todayIST } from "../lib/dates";
import { formatSignedG, parseWeightMg } from "../lib/gold";
import { tidyName } from "../lib/text";
import type { CloseRow, DayView, Figures } from "../lib/types";

type ViewLoad =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; view: DayView };

type HistoryLoad =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: CloseRow[] };

function Tiles({ title, figures, key_ }: { title: string; figures: Figures; key_?: boolean }) {
  return (
    <section aria-label={title}>
      <h2 className="section-heading">{title}</h2>
      <div className="tile-grid">
        <div className={`card tile${key_ ? " tile-key" : ""}`}>
          <span className="tile-label">In the vault</span>
          <span className="tile-value figure">{figures.vault_g}</span>
          <span className="tile-unit">g fine</span>
        </div>
        <div className="card tile">
          <span className="tile-label">With karigars</span>
          <span className="tile-value figure">{figures.karigars_g}</span>
          <span className="tile-unit">g fine</span>
        </div>
        <div className="card tile">
          <span className="tile-label">At the refiner</span>
          <span className="tile-value figure">{figures.refiner_g}</span>
          <span className="tile-unit">g fine</span>
        </div>
        <div className="card tile">
          <span className="tile-label">Total stock</span>
          <span className="tile-value figure">{figures.total_g}</span>
          <span className="tile-unit">g fine</span>
        </div>
      </div>
    </section>
  );
}

function differenceChip(signed: string) {
  const zero = parseWeightMg(signed.replace(/^[+-]/, "")) === 0;
  return zero ? (
    <span className="chip chip-ok">Matches the records</span>
  ) : (
    <span className="chip chip-review">
      Counted <span className="figure">{signed}</span> g against the records
    </span>
  );
}

export default function Closing() {
  const [today] = useState(todayIST);
  const [day, setDay] = useState(today);
  const [view, setView] = useState<ViewLoad>({ status: "loading" });
  const [history, setHistory] = useState<HistoryLoad>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const [counted, setCounted] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const dayOk = /^\d{4}-\d{2}-\d{2}$/.test(day) && day <= today;

  useEffect(() => {
    if (!dayOk) return;
    let cancelled = false;
    setView({ status: "loading" });
    api
      .get<DayView>(`/api/closing/day?date=${day}`)
      .then((data) => {
        if (!cancelled) setView({ status: "ready", view: data });
      })
      .catch((e) => {
        if (!cancelled) {
          setView({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [day, dayOk, attempt]);

  useEffect(() => {
    let cancelled = false;
    api
      .get<CloseRow[]>("/api/closing/history")
      .then((rows) => {
        if (!cancelled) setHistory({ status: "ready", rows });
      })
      .catch((e) => {
        if (!cancelled) {
          setHistory({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const v = view.status === "ready" ? view.view : null;
  const expectedMg = v ? parseWeightMg(v.closing.vault_g) : null;
  const countedMg = parseWeightMg(counted);
  const diffMg = countedMg !== null && expectedMg !== null ? countedMg - expectedMg : null;
  const noteClean = tidyName(note);
  const needsNote = diffMg !== null && diffMg !== 0;
  const canClose =
    v !== null &&
    v.closed === null &&
    v.consistent &&
    v.reconciles &&
    diffMg !== null &&
    (!needsNote || noteClean.length >= 5);

  const countedHint =
    counted.trim() !== "" && countedMg === null
      ? "Use a weight in grams with up to 3 decimals, for example 2252.514."
      : null;

  function pickDay(next: string) {
    setDay(next);
    setCounted("");
    setNote("");
    setError(null);
    setNotice(null);
  }

  function openConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canClose) return;
    setError(null);
    setConfirming(true);
  }

  async function closeDay() {
    if (busy || !canClose) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/closing/close", {
        close_date: day,
        counted_vault: counted.trim(),
        note: noteClean === "" ? null : noteClean,
      });
      setConfirming(false);
      setCounted("");
      setNote("");
      setNotice(`${showDate(day)} is closed.`);
      setAttempt((n) => n + 1);
    } catch (e) {
      setError(saveErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-body">
      <div className="page-head">
        <p className="eyebrow">Aurum / 09 Daily closing</p>
        <h1 className="page-title">
          Close the <span className="accent">day</span>
        </h1>
        <p className="lede">
          Where the gold should be at the end of the day, and whether the vault count agrees.
          Gold with karigars and at the refiner comes from the records. Only the vault is counted.
        </p>
      </div>

      <div className="toolbar ledger-filters">
        <div className="field">
          <label htmlFor="cl-date">Day</label>
          <input
            id="cl-date"
            className="input"
            type="date"
            max={today}
            value={day}
            onChange={(e) => pickDay(e.target.value)}
            aria-invalid={!dayOk}
          />
        </div>
      </div>

      {!dayOk && (
        <p className="banner" role="alert">
          Pick a day that is today or earlier.
        </p>
      )}

      {notice && (
        <p className="banner banner-ok" role="status">
          {notice}
        </p>
      )}

      {dayOk && view.status === "loading" && (
        <div className="tile-grid" aria-busy="true" role="status">
          <span className="sr-only">Loading the day</span>
          <div className="card skeleton" />
          <div className="card skeleton" />
          <div className="card skeleton" />
        </div>
      )}

      {dayOk && view.status === "error" && (
        <section className="card">
          <p className="status-line">{view.message}</p>
          <button className="btn btn-primary" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </section>
      )}

      {dayOk && v && (
        <>
          <Tiles title="Opening, at the end of the previous day" figures={v.opening} />

          <h2 className="section-heading">What moved on {showDate(v.date)}</h2>
          <div className="table-wrap">
            <table className="table table-narrow">
              <thead>
                <tr>
                  <th scope="col">Movement</th>
                  <th scope="col" className="num">Entries</th>
                  <th scope="col" className="num">Effect on the vault (g)</th>
                </tr>
              </thead>
              <tbody>
                {v.movements.map((m) => (
                  <tr key={m.key} className={m.count === 0 ? "row-zero" : undefined}>
                    <td>{m.label}</td>
                    <td className="num figure">{m.count}</td>
                    <td className="num figure">{m.effect_g}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="check-line">
            {v.reconciles ? (
              <span className="chip chip-ok">Opening plus movements equals the expected closing</span>
            ) : (
              <span className="chip chip-review">These figures don't add up</span>
            )}
          </p>

          <Tiles title="Expected closing" figures={v.closing} key_ />

          {!v.consistent && (
            <p className="banner" role="alert">
              More gold is recorded as out of the vault than was ever in it. Check the stock page
              before closing this day.
            </p>
          )}

          {v.closed ? (
            <section className="card closed-card" aria-label="Closed day">
              <h2 className="section-heading">Closed</h2>
              {v.closed.changed_since_close && (
                <p className="banner" role="alert">
                  Entries dated on or before this day were recorded after it was closed, so the
                  figures above no longer match what was counted.
                </p>
              )}
              <dl className="slip-rows">
                <div className="slip-row">
                  <dt>Expected in the vault when closed</dt>
                  <dd className="figure">{v.closed.expected_vault_g} g</dd>
                </div>
                <div className="slip-row slip-key">
                  <dt>Counted in the vault</dt>
                  <dd className="figure">{v.closed.counted_vault_g} g</dd>
                </div>
                <div className="slip-row">
                  <dt>Difference</dt>
                  <dd>{differenceChip(v.closed.difference_g)}</dd>
                </div>
                {v.closed.note && (
                  <div className="slip-row">
                    <dt>Note</dt>
                    <dd>{v.closed.note}</dd>
                  </div>
                )}
                <div className="slip-row">
                  <dt>Closed by</dt>
                  <dd>
                    {v.closed.by},{" "}
                    {new Date(v.closed.at).toLocaleString("en-IN", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </dd>
                </div>
              </dl>
            </section>
          ) : (
            <form className="card" onSubmit={openConfirm} noValidate>
              <h2 className="section-heading">Count the vault and close</h2>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="cl-counted">Counted in the vault (g)</label>
                  <input
                    id="cl-counted"
                    className="input input-figure figure"
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    maxLength={11}
                    placeholder="0.000"
                    value={counted}
                    onChange={(e) => setCounted(e.target.value)}
                    aria-invalid={countedHint !== null}
                  />
                  {countedHint && <p className="field-hint">{countedHint}</p>}
                </div>
                <div className="field">
                  <label htmlFor="cl-note">
                    Note{needsNote ? " (required, the count differs)" : " (optional)"}
                  </label>
                  <input
                    id="cl-note"
                    className="input"
                    type="text"
                    autoComplete="off"
                    maxLength={150}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </div>
              </div>

              <div className="preview-line" aria-live="polite">
                <span>Difference from the records</span>
                <span className="figure">
                  {diffMg === null ? "-" : `${formatSignedG(diffMg)} g`}
                </span>
              </div>
              {needsNote && noteClean.length < 5 && (
                <p className="field-hint">
                  The count differs from the records. Add a note of at least 5 characters.
                </p>
              )}
              <p className="muted manage-note">
                Closing saves these figures with your count and note. It can't be edited
                afterwards.
              </p>
              <button className="btn btn-primary btn-block" type="submit" disabled={!canClose}>
                Review and close the day
              </button>
            </form>
          )}
        </>
      )}

      <h2 className="section-heading">Recently closed days</h2>
      {history.status === "loading" && (
        <div className="card skeleton" role="status" aria-busy="true">
          <span className="sr-only">Loading history</span>
        </div>
      )}
      {history.status === "error" && (
        <section className="card">
          <p className="status-line">{history.message}</p>
        </section>
      )}
      {history.status === "ready" && history.rows.length === 0 && (
        <section className="card">
          <p className="status-line">No days have been closed yet.</p>
        </section>
      )}
      {history.status === "ready" && history.rows.length > 0 && (
        <div className="table-wrap">
          <table className="table table-narrow">
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col" className="num">Expected (g)</th>
                <th scope="col" className="num">Counted (g)</th>
                <th scope="col" className="num">Difference (g)</th>
                <th scope="col">Note</th>
                <th scope="col">By</th>
                <th scope="col">
                  <span className="sr-only">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {history.rows.map((r) => (
                <tr key={r.close_date}>
                  <td>{showDate(r.close_date)}</td>
                  <td className="num figure">{r.expected_vault_g}</td>
                  <td className="num figure">{r.counted_vault_g}</td>
                  <td className="num figure">{r.difference_g}</td>
                  <td>{r.note ?? <span className="muted">None</span>}</td>
                  <td>{r.by}</td>
                  <td>
                    <button
                      className="btn btn-small"
                      onClick={() => pickDay(r.close_date)}
                      aria-label={`View ${r.close_date}`}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirming && v && diffMg !== null && (
        <Dialog title="Close this day?" onClose={() => !busy && setConfirming(false)}>
          <dl className="slip-rows">
            <div className="slip-row">
              <dt>Day</dt>
              <dd>{showDate(v.date)}</dd>
            </div>
            <div className="slip-row">
              <dt>Expected in the vault</dt>
              <dd className="figure">{v.closing.vault_g} g</dd>
            </div>
            <div className="slip-row slip-key">
              <dt>Counted in the vault</dt>
              <dd className="figure">{counted.trim()} g</dd>
            </div>
            <div className="slip-row">
              <dt>Difference</dt>
              <dd className="figure">{formatSignedG(diffMg)} g</dd>
            </div>
            {noteClean !== "" && (
              <div className="slip-row">
                <dt>Note</dt>
                <dd>{noteClean}</dd>
              </div>
            )}
          </dl>
          <p className="muted manage-note">A closed day can't be reopened or edited.</p>
          {error && (
            <p className="banner" role="alert">
              {error}
            </p>
          )}
          <div className="inline">
            <button
              className="btn btn-primary"
              type="button"
              disabled={busy}
              onClick={() => void closeDay()}
            >
              {busy ? "Closing..." : "Close the day"}
            </button>
            <button
              className="btn"
              type="button"
              disabled={busy}
              onClick={() => setConfirming(false)}
            >
              Back
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
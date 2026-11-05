import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Dialog from "../components/Dialog";
import PhotoReader, { ReadingSummary } from "../components/PhotoReader";
import SlipView from "../components/SlipView";
import { useAuth } from "../auth/auth-context";
import { ApiError, api, saveErrorMessage } from "../lib/api";
import { addDays, showDate, showTime, todayIST } from "../lib/dates";
import { clearDraft, draftKey, loadDraft, useAutosave } from "../lib/drafts";
import { keyFor, newNonce } from "../lib/idempotency";
import {
  MAX_ISSUE_MG,
  applyPct,
  formatG,
  parsePercentH,
  parsePurityH,
  parseWeightMg,
} from "../lib/gold";
import { checkReading, readingFields } from "../lib/readings";
import type { ReadingAttach } from "../lib/readings";
import type { Karigar, Slip } from "../lib/types";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; karigars: Karigar[] };

interface IssueDraft {
  karigarId: string;
  categoryId: string;
  gross: string;
  purity: string;
  date: string;
  note: string;
}

export default function Issue() {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const [today] = useState(todayIST);
  const minDate = addDays(today, -7);

  const { state: auth } = useAuth();
  const userId = auth.status === "signed-in" ? auth.user.id : 0;
  const draftKeyName = draftKey(userId, "issue");
  const [restored, setRestored] = useState(() => loadDraft<IssueDraft>(draftKeyName));
  const saved = restored?.data;

  const [karigarId, setKarigarId] = useState(saved?.karigarId ?? "");
  const [categoryId, setCategoryId] = useState(saved?.categoryId ?? "");
  const [gross, setGross] = useState(saved?.gross ?? "");
  const [purity, setPurity] = useState(saved?.purity ?? "");
  const [date, setDate] = useState(
    saved && saved.date >= minDate && saved.date <= today ? saved.date : today,
  );
  const [note, setNote] = useState(saved?.note ?? "");

  const [weightRead, setWeightRead] = useState<ReadingAttach | null>(null);
  const [weightReason, setWeightReason] = useState("");
  const [purityRead, setPurityRead] = useState<ReadingAttach | null>(null);
  const [purityReason, setPurityReason] = useState("");

  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slip, setSlip] = useState<Slip | null>(null);
  const [nonce, setNonce] = useState(newNonce);

  useAutosave(
    draftKeyName,
    { karigarId, categoryId, gross, purity, date, note },
    slip === null,
    ["date"],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .get<Karigar[]>("/api/karigars")
      .then((rows) => {
        if (!cancelled) {
          setLoad({ status: "ready", karigars: rows.filter((k) => k.is_active) });
        }
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

  const karigars = load.status === "ready" ? load.karigars : [];
  const karigar = karigars.find((k) => String(k.id) === karigarId);
  const rate = karigar?.wastage.find((w) => String(w.category_id) === categoryId);

  const grossMg = parseWeightMg(gross);
  const purityH = parsePurityH(purity);
  const rateH = rate ? parsePercentH(rate.wastage_pct) : null;
  const fine = grossMg !== null && purityH !== null ? applyPct(grossMg, purityH) : null;
  const allowed = fine !== null && rateH !== null ? applyPct(fine, rateH) : null;

  const grossOk = grossMg !== null && grossMg > 0 && grossMg <= MAX_ISSUE_MG;
  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(date) && date >= minDate && date <= today;

  const weightCheck = checkReading("WEIGHT", gross, weightRead, weightReason);
  const purityCheck = checkReading("PURITY", purity, purityRead, purityReason);
  const readingsOk = weightCheck !== "NEEDS_REASON" && purityCheck !== "NEEDS_REASON";

  const canReview =
    karigar !== undefined &&
    rate !== undefined &&
    grossOk &&
    purityH !== null &&
    fine !== null &&
    fine > 0 &&
    dateOk &&
    readingsOk;

  let grossHint: string | null = null;
  if (gross.trim() !== "") {
    if (grossMg === null) grossHint = "Use up to 3 decimals, for example 120.250.";
    else if (grossMg <= 0) grossHint = "The weight must be above 0.";
    else if (grossMg > MAX_ISSUE_MG) {
      grossHint = `A single issue can't be more than ${formatG(MAX_ISSUE_MG)} g.`;
    }
  }
  let purityHint: string | null = null;
  if (purity.trim() !== "" && purityH === null) {
    purityHint = "Use a purity above 0 and up to 100, with up to 2 decimals.";
  }
  const dateHint = dateOk ? null : "Pick today or one of the previous 7 days.";

  function resetForm() {
    setKarigarId("");
    setCategoryId("");
    setGross("");
    setPurity("");
    setDate(today);
    setNote("");
    setWeightRead(null);
    setWeightReason("");
    setPurityRead(null);
    setPurityReason("");
    setError(null);
    clearDraft(draftKeyName);
    setRestored(null);
    setNonce(newNonce());
  }

  function openReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canReview) return;
    setError(null);
    setReviewing(true);
  }

  async function save() {
    if (busy || !karigar || !rate || !canReview) return;
    setBusy(true);
    setError(null);
    try {
      const trimmedNote = note.trim();
      const payload = {
        karigar_id: karigar.id,
        category_id: rate.category_id,
        gross_weight: gross.trim(),
        purity: purity.trim(),
        entry_date: date,
        note: trimmedNote === "" ? null : trimmedNote,
        ...readingFields("weight", weightRead, weightCheck, weightReason),
        ...readingFields("purity", purityRead, purityCheck, purityReason),
      };
      const result = await api.post<Slip>("/api/issues", payload, {
        "Idempotency-Key": keyFor(nonce, payload),
      });
      setSlip(result);
      setReviewing(false);
      resetForm();
    } catch (e) {
      setError(saveErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-body">
      <div className="page-head no-print">
        <p className="eyebrow">Aurum / 02 Issue</p>
        <h1 className="page-title">
          Issue gold to a <span className="accent">karigar</span>
        </h1>
        <p className="lede">
          Enter the gross weight and purity, or photograph the display and check what was
          read. The fine gold is worked out for you and checked again by the server.
        </p>
      </div>

      {load.status === "loading" && (
        <div className="grid" aria-busy="true" role="status">
          <span className="sr-only">Loading karigars</span>
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

      {load.status === "ready" && slip && (
        <SlipView slip={slip} onNew={() => setSlip(null)} />
      )}

      {load.status === "ready" && !slip && karigars.length === 0 && (
        <section className="card">
          <p className="status-line">There are no active karigars to issue gold to.</p>
        </section>
      )}

      {load.status === "ready" && !slip && karigars.length > 0 && (
        <div className="issue-grid">
          <form className="card" onSubmit={openReview} noValidate>
            {restored && (
              <p className="banner banner-ok draft-banner" role="status">
                <span>
                  Draft restored from {showTime(restored.savedAt)}. Photos aren't kept, so add
                  them again if you need them.
                </span>
                <button type="button" className="btn btn-small" onClick={resetForm}>
                  Discard draft
                </button>
              </p>
            )}
            <div className="form-row">
              <div className="field">
                <label htmlFor="karigar">Karigar</label>
                <select
                  id="karigar"
                  className="input"
                  value={karigarId}
                  onChange={(e) => {
                    setKarigarId(e.target.value);
                    setCategoryId("");
                  }}
                >
                  <option value="">Choose a karigar</option>
                  {karigars.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label htmlFor="category">Item category</label>
                <select
                  id="category"
                  className="input"
                  value={categoryId}
                  disabled={!karigar || karigar.wastage.length === 0}
                  onChange={(e) => setCategoryId(e.target.value)}
                >
                  <option value="">Choose a category</option>
                  {karigar?.wastage.map((w) => (
                    <option key={w.category_id} value={w.category_id}>
                      {w.category} ({w.wastage_pct} %)
                    </option>
                  ))}
                </select>
                {karigar && karigar.wastage.length === 0 && (
                  <p className="field-hint">
                    No agreed wastage is set for this karigar. Ask the finance head to set it.
                  </p>
                )}
              </div>
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="gross">Gross weight (g)</label>
                <input
                  id="gross"
                  className="input input-figure figure"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  maxLength={11}
                  placeholder="0.000"
                  value={gross}
                  onChange={(e) => setGross(e.target.value)}
                  aria-invalid={grossHint !== null}
                />
                {grossHint && <p className="field-hint">{grossHint}</p>}
              </div>

              <div className="field">
                <label htmlFor="purity">Purity (%)</label>
                <input
                  id="purity"
                  className="input input-figure figure"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  maxLength={6}
                  placeholder="91.60"
                  value={purity}
                  onChange={(e) => setPurity(e.target.value)}
                  aria-invalid={purityHint !== null}
                />
                {purityHint && <p className="field-hint">{purityHint}</p>}
              </div>
            </div>

            <div className="photo-section">
              <p className="photo-section-title">Photos (optional)</p>
              <p className="muted manage-note">
                A photo lets the system read the weight and purity. You always confirm the
                result, and a value that differs from the photo needs a reason.
              </p>
              <div className="photo-grid">
                <PhotoReader
                  target="WEIGHT"
                  noun="weight"
                  unit="g"
                  typed={gross}
                  attach={weightRead}
                  reason={weightReason}
                  onAttach={setWeightRead}
                  onFill={setGross}
                  onReason={setWeightReason}
                />
                <PhotoReader
                  target="PURITY"
                  noun="purity"
                  unit="%"
                  typed={purity}
                  attach={purityRead}
                  reason={purityReason}
                  onAttach={setPurityRead}
                  onFill={setPurity}
                  onReason={setPurityReason}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="date">Date</label>
                <input
                  id="date"
                  className="input"
                  type="date"
                  min={minDate}
                  max={today}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  aria-invalid={dateHint !== null}
                />
                {dateHint && <p className="field-hint">{dateHint}</p>}
              </div>

              <div className="field">
                <label htmlFor="note">Note (optional)</label>
                <input
                  id="note"
                  className="input"
                  type="text"
                  autoComplete="off"
                  maxLength={200}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>
            </div>

            <button className="btn btn-primary btn-block" type="submit" disabled={!canReview}>
              Review issue
            </button>
          </form>

          <aside className="card preview" aria-live="polite">
            <p className="eyebrow">Preview</p>
            <div className="preview-line preview-key">
              <span>Fine gold</span>
              <span className="figure preview-main">
                {fine !== null ? `${formatG(fine)} g` : "-"}
              </span>
            </div>
            <div className="preview-line">
              <span>Allowed wastage</span>
              <span className="figure">
                {allowed !== null && rate
                  ? `${formatG(allowed)} g (${rate.wastage_pct} %)`
                  : "-"}
              </span>
            </div>
            <p className="muted manage-note">
              Worked out here as a preview. The slip shows the figures the server confirms.
            </p>
          </aside>
        </div>
      )}

      {reviewing && karigar && rate && fine !== null && allowed !== null && (
        <Dialog title="Review before saving" onClose={() => !busy && setReviewing(false)}>
          <dl className="slip-rows">
            <div className="slip-row">
              <dt>Karigar</dt>
              <dd>{karigar.name}</dd>
            </div>
            <div className="slip-row">
              <dt>Item category</dt>
              <dd>{rate.category}</dd>
            </div>
            <div className="slip-row">
              <dt>Date</dt>
              <dd>{showDate(date)}</dd>
            </div>
            <div className="slip-row">
              <dt>Gross weight</dt>
              <dd className="figure">{grossMg !== null ? formatG(grossMg) : ""} g</dd>
            </div>
            <div className="slip-row">
              <dt>Purity</dt>
              <dd className="figure">{purity.trim()} %</dd>
            </div>
            <div className="slip-row slip-key">
              <dt>Fine gold</dt>
              <dd className="figure">{formatG(fine)} g</dd>
            </div>
            <div className="slip-row">
              <dt>Allowed wastage</dt>
              <dd className="figure">{formatG(allowed)} g</dd>
            </div>
          </dl>
          <ReadingSummary
            items={[
              { noun: "weight", check: weightCheck },
              { noun: "purity", check: purityCheck },
            ]}
          />
          <p className="muted manage-note">
            Saved entries can't be edited. A mistake is corrected with a reversal.
          </p>
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
              onClick={() => void save()}
            >
              {busy ? "Saving..." : "Save issue"}
            </button>
            <button
              className="btn"
              type="button"
              disabled={busy}
              onClick={() => setReviewing(false)}
            >
              Back to edit
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
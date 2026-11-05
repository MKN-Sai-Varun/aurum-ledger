import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../auth/auth-context";
import { api, saveErrorMessage } from "../lib/api";
import { addDays, showDate, showTime, todayIST } from "../lib/dates";
import { clearDraft, draftKey, loadDraft, useAutosave } from "../lib/drafts";
import { keyFor, newNonce } from "../lib/idempotency";
import {
  MAX_ISSUE_MG,
  applyPct,
  formatG,
  parsePurityH,
  parseWeightMg,
} from "../lib/gold";
import { checkReading, readingFields } from "../lib/readings";
import type { ReadingAttach } from "../lib/readings";
import { KIND_LABEL } from "../lib/types";
import type { Job, ReceiptResult } from "../lib/types";
import Dialog from "./Dialog";
import PhotoReader, { ReadingSummary } from "./PhotoReader";

type Kind = "PIECE" | "SCRAP" | "FILINGS";
type Step = "form" | "review" | "done";

const KIND_CHOICES: { value: Kind; label: string }[] = [
  { value: "PIECE", label: "Finished piece" },
  { value: "SCRAP", label: "Scrap" },
  { value: "FILINGS", label: "Filings" },
];

const HUID_RE = /^[A-Z0-9]{6,12}$/;

interface ReceiptDraft {
  kind: string;
  gross: string;
  purity: string;
  huid: string;
  date: string;
  note: string;
}

interface Props {
  job: Job;
  onSaved: (job: Job) => void;
  onClose: () => void;
}

export default function ReceiptDialog({ job, onSaved, onClose }: Props) {
  const [today] = useState(todayIST);
  const lastWeek = addDays(today, -7);
  const minDate = job.opened_on > lastWeek ? job.opened_on : lastWeek;

  const { state: auth } = useAuth();
  const userId = auth.status === "signed-in" ? auth.user.id : 0;
  const draftKeyName = draftKey(userId, `receipt-${job.job_no}`);
  const [restored, setRestored] = useState(() => loadDraft<ReceiptDraft>(draftKeyName));
  const draft = restored?.data;

  const [step, setStep] = useState<Step>("form");
  const [kind, setKind] = useState<Kind>(
    draft && KIND_CHOICES.some((c) => c.value === draft.kind) ? (draft.kind as Kind) : "PIECE",
  );
  const [gross, setGross] = useState(draft?.gross ?? "");
  const [purity, setPurity] = useState(draft?.purity ?? "");
  const [huid, setHuid] = useState(draft?.huid ?? "");
  const [date, setDate] = useState(
    draft && draft.date >= minDate && draft.date <= today ? draft.date : today,
  );
  const [note, setNote] = useState(draft?.note ?? "");

  const [weightRead, setWeightRead] = useState<ReadingAttach | null>(null);
  const [weightReason, setWeightReason] = useState("");
  const [purityRead, setPurityRead] = useState<ReadingAttach | null>(null);
  const [purityReason, setPurityReason] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState<ReceiptResult | null>(null);
  const [nonce] = useState(newNonce);

  useAutosave(
    draftKeyName,
    { kind, gross, purity, huid, date, note },
    saved === null,
    ["date", "kind"],
  );

  function discardDraft() {
    clearDraft(draftKeyName);
    setRestored(null);
    setKind("PIECE");
    setGross("");
    setPurity("");
    setHuid("");
    setDate(today);
    setNote("");
    setWeightRead(null);
    setWeightReason("");
    setPurityRead(null);
    setPurityReason("");
  }

  const grossMg = parseWeightMg(gross);
  const purityH = parsePurityH(purity);
  const fine = grossMg !== null && purityH !== null ? applyPct(grossMg, purityH) : null;
  const outstandingMg = parseWeightMg(job.outstanding_g);
  const huidClean = huid.trim().toUpperCase();

  const grossOk = grossMg !== null && grossMg > 0 && grossMg <= MAX_ISSUE_MG;
  const huidOk = kind !== "PIECE" || HUID_RE.test(huidClean);
  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(date) && date >= minDate && date <= today;
  const withinOutstanding =
    fine !== null && outstandingMg !== null && fine <= outstandingMg;

  const weightCheck = checkReading("WEIGHT", gross, weightRead, weightReason);
  const purityCheck = checkReading("PURITY", purity, purityRead, purityReason);
  const readingsOk = weightCheck !== "NEEDS_REASON" && purityCheck !== "NEEDS_REASON";

  const canReview =
    grossOk &&
    purityH !== null &&
    fine !== null &&
    fine > 0 &&
    huidOk &&
    dateOk &&
    withinOutstanding &&
    readingsOk;
  const remaining =
    fine !== null && outstandingMg !== null && fine <= outstandingMg
      ? outstandingMg - fine
      : null;

  let grossHint: string | null = null;
  if (gross.trim() !== "") {
    if (grossMg === null) grossHint = "Use up to 3 decimals, for example 112.450.";
    else if (grossMg <= 0) grossHint = "The weight must be above 0.";
    else if (grossMg > MAX_ISSUE_MG) {
      grossHint = `A single receipt can't be more than ${formatG(MAX_ISSUE_MG)} g.`;
    }
  }
  const purityHint =
    purity.trim() !== "" && purityH === null
      ? "Use a purity above 0 and up to 100, with up to 2 decimals."
      : null;
  const huidHint =
    kind === "PIECE" && huid.trim() !== "" && !HUID_RE.test(huidClean)
      ? "The HUID must be 6 to 12 letters or digits."
      : null;
  const outstandingHint =
    fine !== null && outstandingMg !== null && fine > outstandingMg
      ? `That is ${formatG(fine)} g of fine gold, but only ${job.outstanding_g} g is outstanding.`
      : null;
  const dateHint = dateOk
    ? null
    : "Pick a date from the day the job opened up to today, within the last 7 days.";

  const kindLabel = KIND_CHOICES.find((c) => c.value === kind)?.label ?? kind;

  function openReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canReview) return;
    setError(null);
    setStep("review");
  }

  async function save() {
    if (busy || !canReview) return;
    setBusy(true);
    setError(null);
    try {
      const trimmedNote = note.trim();
      const payload = {
        job_no: job.job_no,
        kind,
        gross_weight: gross.trim(),
        purity: purity.trim(),
        huid: kind === "PIECE" ? huidClean : null,
        entry_date: date,
        note: trimmedNote === "" ? null : trimmedNote,
        ...readingFields("weight", weightRead, weightCheck, weightReason),
        ...readingFields("purity", purityRead, purityCheck, purityReason),
      };
      const result = await api.post<ReceiptResult>("/api/receipts", payload, {
        "Idempotency-Key": keyFor(nonce, payload),
      });
      setSaved(result);
      onSaved(result.job);
      clearDraft(draftKeyName);
      setStep("done");
    } catch (e) {
      setError(saveErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      title={`Receipt for ${job.job_no}`}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <p className="muted manage-note">
        {job.karigar} - {job.category}
      </p>

      {step === "form" && (
        <form onSubmit={openReview} noValidate>
          {restored && (
            <p className="banner banner-ok draft-banner" role="status">
              <span>
                Draft restored from {showTime(restored.savedAt)}. Photos aren't kept, so add
                them again if you need them.
              </span>
              <button type="button" className="btn btn-small" onClick={discardDraft}>
                Discard draft
              </button>
            </p>
          )}
          <div className="field">
            <label htmlFor="r-kind">What was returned</label>
            <select
              id="r-kind"
              className="input"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
            >
              {KIND_CHOICES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="r-gross">Weight (g)</label>
              <input
                id="r-gross"
                className="input input-figure figure"
                type="text"
                inputMode="decimal"
                autoComplete="off"
                maxLength={11}
                placeholder="0.000"
                value={gross}
                onChange={(e) => setGross(e.target.value)}
                aria-invalid={grossHint !== null || outstandingHint !== null}
              />
              {grossHint && <p className="field-hint">{grossHint}</p>}
            </div>
            <div className="field">
              <label htmlFor="r-purity">Purity (%)</label>
              <input
                id="r-purity"
                className="input input-figure figure"
                type="text"
                inputMode="decimal"
                autoComplete="off"
                maxLength={6}
                placeholder="0.00"
                value={purity}
                onChange={(e) => setPurity(e.target.value)}
                aria-invalid={purityHint !== null}
              />
              {purityHint && <p className="field-hint">{purityHint}</p>}
            </div>
          </div>
          {outstandingHint && <p className="field-hint">{outstandingHint}</p>}

          <div className="photo-section">
            <p className="photo-section-title">Photos (optional)</p>
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

          {kind === "PIECE" && (
            <div className="field">
              <label htmlFor="r-huid">HUID</label>
              <input
                id="r-huid"
                className="input figure"
                type="text"
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                maxLength={12}
                placeholder="6 to 12 letters or digits"
                value={huid}
                onChange={(e) => setHuid(e.target.value)}
                aria-invalid={huidHint !== null}
              />
              {huidHint && <p className="field-hint">{huidHint}</p>}
            </div>
          )}

          <div className="form-row">
            <div className="field">
              <label htmlFor="r-date">Date</label>
              <input
                id="r-date"
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
              <label htmlFor="r-note">Note (optional)</label>
              <input
                id="r-note"
                className="input"
                type="text"
                autoComplete="off"
                maxLength={200}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>

          <div className="manage-section" aria-live="polite">
            <div className="preview-line">
              <span>Fine gold returned</span>
              <span className="figure preview-main">
                {fine !== null ? `${formatG(fine)} g` : "-"}
              </span>
            </div>
            <div className="preview-line">
              <span>Outstanding now</span>
              <span className="figure">{job.outstanding_g} g</span>
            </div>
            <div className="preview-line">
              <span>Outstanding after</span>
              <span className="figure">{remaining !== null ? `${formatG(remaining)} g` : "-"}</span>
            </div>
            <div className="preview-line">
              <span>Allowed wastage</span>
              <span className="figure">
                {job.allowed_wastage_g} g ({job.allowed_wastage_pct} %)
              </span>
            </div>
          </div>

          <button className="btn btn-primary btn-block" type="submit" disabled={!canReview}>
            Review receipt
          </button>
        </form>
      )}

      {step === "review" && fine !== null && grossMg !== null && remaining !== null && (
        <div>
          <dl className="slip-rows">
            <div className="slip-row">
              <dt>Returned as</dt>
              <dd>{kindLabel}</dd>
            </div>
            <div className="slip-row">
              <dt>Date</dt>
              <dd>{showDate(date)}</dd>
            </div>
            <div className="slip-row">
              <dt>Weight</dt>
              <dd className="figure">{formatG(grossMg)} g</dd>
            </div>
            <div className="slip-row">
              <dt>Purity</dt>
              <dd className="figure">{purity.trim()} %</dd>
            </div>
            {kind === "PIECE" && (
              <div className="slip-row">
                <dt>HUID</dt>
                <dd className="figure">{huidClean}</dd>
              </div>
            )}
            <div className="slip-row slip-key">
              <dt>Fine gold returned</dt>
              <dd className="figure">{formatG(fine)} g</dd>
            </div>
            <div className="slip-row">
              <dt>Outstanding after</dt>
              <dd className="figure">{formatG(remaining)} g</dd>
            </div>
          </dl>
          <ReadingSummary
            items={[
              { noun: "weight", check: weightCheck },
              { noun: "purity", check: purityCheck },
            ]}
          />
          <p className="muted manage-note">
            Saved entries can't be edited. The finance head corrects a mistake with a reversal.
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
              {busy ? "Saving..." : "Save receipt"}
            </button>
            <button
              className="btn"
              type="button"
              disabled={busy}
              onClick={() => setStep("form")}
            >
              Back to edit
            </button>
          </div>
        </div>
      )}

      {step === "done" && saved && (
        <div>
          <p className="banner banner-ok" role="status">
            Receipt saved as {saved.txn_no}.
          </p>
          <dl className="slip-rows">
            <div className="slip-row">
              <dt>Returned as</dt>
              <dd>{KIND_LABEL[saved.kind]}</dd>
            </div>
            <div className="slip-row">
              <dt>Weight</dt>
              <dd className="figure">
                {saved.gross_weight_g} g at {saved.purity_pct} %
              </dd>
            </div>
            {saved.huid && (
              <div className="slip-row">
                <dt>HUID</dt>
                <dd className="figure">{saved.huid}</dd>
              </div>
            )}
            <div className="slip-row slip-key">
              <dt>Fine gold returned</dt>
              <dd className="figure">{saved.fine_weight_g} g</dd>
            </div>
            <div className="slip-row">
              <dt>Still outstanding</dt>
              <dd className="figure">{saved.job.outstanding_g} g</dd>
            </div>
            <div className="slip-row">
              <dt>Allowed wastage</dt>
              <dd className="figure">{saved.job.allowed_wastage_g} g</dd>
            </div>
          </dl>
          <button className="btn btn-primary" type="button" onClick={onClose}>
            Done
          </button>
        </div>
      )}
    </Dialog>
  );
}
import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { addDays, showDate, todayIST } from "../lib/dates";
import { MAX_ISSUE_MG, applyPct, formatG, parsePurityH, parseWeightMg } from "../lib/gold";
import {
  BILL_RE,
  HIGH_VALUE_PAISE,
  MAX_RATE_PAISE,
  PAN_RE,
  formatPaise,
  parseRupeesPaise,
  valuePaise,
} from "../lib/money";
import { checkReading, readingFields } from "../lib/readings";
import type { ReadingAttach } from "../lib/readings";
import { tidyName } from "../lib/text";
import type { OldGold } from "../lib/types";
import Dialog from "./Dialog";
import PhotoReader, { ReadingSummary } from "./PhotoReader";
import PurchaseReceipt from "./PurchaseReceipt";

const MODES = [
  { value: "BANK_TRANSFER", label: "Bank transfer" },
  { value: "UPI", label: "UPI" },
  { value: "CHEQUE", label: "Cheque" },
  { value: "CASH", label: "Cash" },
  { value: "ADJUSTED", label: "Adjusted against the new bill" },
];

export default function OldGoldForm({ onSaved }: { onSaved: () => void }) {
  const [today] = useState(todayIST);
  const minDate = addDays(today, -7);

  const [bill, setBill] = useState("");
  const [customer, setCustomer] = useState("");
  const [gross, setGross] = useState("");
  const [deduction, setDeduction] = useState("");
  const [purity, setPurity] = useState("");
  const [rate, setRate] = useState("");
  const [mode, setMode] = useState("");
  const [pan, setPan] = useState("");
  const [date, setDate] = useState(today);
  const [note, setNote] = useState("");

  const [weightRead, setWeightRead] = useState<ReadingAttach | null>(null);
  const [weightReason, setWeightReason] = useState("");
  const [purityRead, setPurityRead] = useState<ReadingAttach | null>(null);
  const [purityReason, setPurityReason] = useState("");

  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<OldGold | null>(null);

  const billClean = bill.trim().toUpperCase();
  const nameClean = tidyName(customer);
  const panClean = pan.trim().toUpperCase();

  const grossMg = parseWeightMg(gross);
  const deductionMg = deduction.trim() === "" ? 0 : parseWeightMg(deduction);
  const purityH = parsePurityH(purity);
  const ratePaise = parseRupeesPaise(rate);

  const netMg =
    grossMg !== null && deductionMg !== null && deductionMg < grossMg
      ? grossMg - deductionMg
      : null;
  const fine = netMg !== null && purityH !== null ? applyPct(netMg, purityH) : null;
  const value = fine !== null && ratePaise !== null ? valuePaise(fine, ratePaise) : null;
  const high = value !== null && value >= HIGH_VALUE_PAISE;

  const grossOk = grossMg !== null && grossMg > 0 && grossMg <= MAX_ISSUE_MG;
  const rateOk = ratePaise !== null && ratePaise > 0 && ratePaise <= MAX_RATE_PAISE;
  const billOk = BILL_RE.test(billClean);
  const nameOk = nameClean.length >= 2;
  const panOk = panClean === "" ? !high : PAN_RE.test(panClean);
  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(date) && date >= minDate && date <= today;

  const weightCheck = checkReading("WEIGHT", gross, weightRead, weightReason);
  const purityCheck = checkReading("PURITY", purity, purityRead, purityReason);
  const readingsOk = weightCheck !== "NEEDS_REASON" && purityCheck !== "NEEDS_REASON";

  const canReview =
    billOk &&
    nameOk &&
    grossOk &&
    netMg !== null &&
    purityH !== null &&
    fine !== null &&
    fine > 0 &&
    rateOk &&
    value !== null &&
    mode !== "" &&
    panOk &&
    dateOk &&
    readingsOk;

  let grossHint: string | null = null;
  if (gross.trim() !== "") {
    if (grossMg === null) grossHint = "Use up to 3 decimals, for example 25.000.";
    else if (grossMg <= 0) grossHint = "The weight must be above 0.";
    else if (grossMg > MAX_ISSUE_MG) {
      grossHint = `A single purchase can't be more than ${formatG(MAX_ISSUE_MG)} g.`;
    }
  }
  let deductionHint: string | null = null;
  if (deduction.trim() !== "") {
    if (deductionMg === null) deductionHint = "Use a weight in grams with up to 3 decimals, or 0.";
    else if (grossMg !== null && deductionMg >= grossMg) {
      deductionHint = "The deduction must be less than the gross weight.";
    }
  }
  const purityHint =
    purity.trim() !== "" && purityH === null
      ? "Use a purity above 0 and up to 100, with up to 2 decimals."
      : null;
  const rateHint =
    rate.trim() !== "" && !rateOk
      ? `Use rupees per gram with up to 2 decimals, above 0 and at most ${formatPaise(MAX_RATE_PAISE)}.`
      : null;
  const billHint =
    bill.trim() !== "" && !billOk
      ? "Use 3 to 30 letters, digits or - / _ . for the bill reference."
      : null;
  const panHint =
    panClean !== "" && !PAN_RE.test(panClean)
      ? "A PAN is 5 letters, 4 digits and 1 letter, for example ABCDE1234F."
      : high && panClean === ""
        ? `A purchase of Rs ${formatPaise(HIGH_VALUE_PAISE)} or more needs the customer's PAN.`
        : null;
  const dateHint = dateOk ? null : "Pick today or one of the previous 7 days.";

  const modeLabel = MODES.find((m) => m.value === mode)?.label ?? "";

  function reset() {
    setBill("");
    setCustomer("");
    setGross("");
    setDeduction("");
    setPurity("");
    setRate("");
    setMode("");
    setPan("");
    setDate(today);
    setNote("");
    setWeightRead(null);
    setWeightReason("");
    setPurityRead(null);
    setPurityReason("");
    setError(null);
  }

  function openReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canReview) return;
    setError(null);
    setReviewing(true);
  }

  async function save() {
    if (busy || !canReview) return;
    setBusy(true);
    setError(null);
    try {
      const trimmedNote = note.trim();
      const result = await api.post<OldGold>("/api/old-gold", {
        bill_no: billClean,
        customer_name: nameClean,
        gross_weight: gross.trim(),
        deduction_weight: deduction.trim() === "" ? "0" : deduction.trim(),
        purity: purity.trim(),
        rate_per_g: rate.trim(),
        payment_mode: mode,
        pan: panClean === "" ? null : panClean,
        entry_date: date,
        note: trimmedNote === "" ? null : trimmedNote,
        ...readingFields("weight", weightRead, weightCheck, weightReason),
        ...readingFields("purity", purityRead, purityCheck, purityReason),
      });
      setDone(result);
      setReviewing(false);
      reset();
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (done) return <PurchaseReceipt purchase={done} onNew={() => setDone(null)} />;

  return (
    <div className="issue-grid">
      <form className="card" onSubmit={openReview} noValidate>
        <div className="form-row">
          <div className="field">
            <label htmlFor="og-bill">Exchange bill reference</label>
            <input
              id="og-bill"
              className="input figure"
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={30}
              placeholder="EXB-2026-0500"
              value={bill}
              onChange={(e) => setBill(e.target.value)}
              aria-invalid={billHint !== null}
            />
            {billHint && <p className="field-hint">{billHint}</p>}
          </div>
          <div className="field">
            <label htmlFor="og-customer">Customer name</label>
            <input
              id="og-customer"
              className="input"
              type="text"
              autoComplete="off"
              maxLength={100}
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
            />
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="og-gross">Gross weight (g)</label>
            <input
              id="og-gross"
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
            <label htmlFor="og-deduction">Deduction (g), such as stones</label>
            <input
              id="og-deduction"
              className="input input-figure figure"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              maxLength={11}
              placeholder="0.000"
              value={deduction}
              onChange={(e) => setDeduction(e.target.value)}
              aria-invalid={deductionHint !== null}
            />
            {deductionHint && <p className="field-hint">{deductionHint}</p>}
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="og-purity">Tested purity (%)</label>
            <input
              id="og-purity"
              className="input input-figure figure"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              maxLength={6}
              placeholder="84.50"
              value={purity}
              onChange={(e) => setPurity(e.target.value)}
              aria-invalid={purityHint !== null}
            />
            {purityHint && <p className="field-hint">{purityHint}</p>}
          </div>
          <div className="field">
            <label htmlFor="og-rate">Rate per gram of fine gold (Rs)</label>
            <input
              id="og-rate"
              className="input input-figure figure"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              maxLength={11}
              placeholder="0.00"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              aria-invalid={rateHint !== null}
            />
            {rateHint && <p className="field-hint">{rateHint}</p>}
          </div>
        </div>

        <div className="photo-section">
          <p className="photo-section-title">Photos (optional)</p>
          <p className="muted manage-note">
            Photograph the scale for the weight and the karat meter printout for the purity.
            You always confirm the result, and a value that differs from the photo needs a
            reason.
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
            <label htmlFor="og-mode">Payment mode</label>
            <select
              id="og-mode"
              className="input"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="">Choose a payment mode</option>
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="og-pan">
              Customer PAN{high ? " (required)" : " (needed at the high-value limit)"}
            </label>
            <input
              id="og-pan"
              className="input figure"
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={10}
              placeholder="ABCDE1234F"
              value={pan}
              onChange={(e) => setPan(e.target.value)}
              aria-invalid={panHint !== null}
            />
            {panHint && <p className="field-hint">{panHint}</p>}
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="og-date">Date</label>
            <input
              id="og-date"
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
            <label htmlFor="og-note">Note (optional)</label>
            <input
              id="og-note"
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
          Review purchase
        </button>
      </form>

      <aside className="card preview" aria-live="polite">
        <p className="eyebrow">Preview</p>
        <div className="preview-line">
          <span>Net weight</span>
          <span className="figure">{netMg !== null ? `${formatG(netMg)} g` : "-"}</span>
        </div>
        <div className="preview-line preview-key">
          <span>Fine gold</span>
          <span className="figure preview-main">{fine !== null ? `${formatG(fine)} g` : "-"}</span>
        </div>
        <div className="preview-line">
          <span>Value</span>
          <span className="figure preview-main">
            {value !== null ? `Rs ${formatPaise(value)}` : "-"}
          </span>
        </div>
        {high && (
          <p className="banner">
            This is a high-value purchase. The customer's PAN is required.
          </p>
        )}
        <p className="muted manage-note">
          Worked out here as a preview. The receipt shows the figures the server confirms.
        </p>
      </aside>

      {reviewing && fine !== null && netMg !== null && value !== null && ratePaise !== null && (
        <Dialog title="Review before saving" onClose={() => !busy && setReviewing(false)}>
          <dl className="slip-rows">
            <div className="slip-row">
              <dt>Bill</dt>
              <dd className="figure">{billClean}</dd>
            </div>
            <div className="slip-row">
              <dt>Customer</dt>
              <dd>{nameClean}</dd>
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
              <dt>Deduction</dt>
              <dd className="figure">{formatG(deductionMg ?? 0)} g</dd>
            </div>
            <div className="slip-row">
              <dt>Net weight</dt>
              <dd className="figure">{formatG(netMg)} g</dd>
            </div>
            <div className="slip-row">
              <dt>Tested purity</dt>
              <dd className="figure">{purity.trim()} %</dd>
            </div>
            <div className="slip-row slip-key">
              <dt>Fine gold</dt>
              <dd className="figure">{formatG(fine)} g</dd>
            </div>
            <div className="slip-row">
              <dt>Rate per gram</dt>
              <dd className="figure">Rs {formatPaise(ratePaise)}</dd>
            </div>
            <div className="slip-row slip-key">
              <dt>Value</dt>
              <dd className="figure">Rs {formatPaise(value)}</dd>
            </div>
            <div className="slip-row">
              <dt>Payment</dt>
              <dd>{modeLabel}</dd>
            </div>
            {panClean !== "" && (
              <div className="slip-row">
                <dt>PAN</dt>
                <dd className="figure">{panClean}</dd>
              </div>
            )}
          </dl>
          <ReadingSummary
            items={[
              { noun: "weight", check: weightCheck },
              { noun: "purity", check: purityCheck },
            ]}
          />
          <p className="muted manage-note">
            Saved purchases can't be edited. The finance head can void a mistaken one.
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
              {busy ? "Saving..." : "Save purchase"}
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
import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { addDays } from "../lib/dates";
import { formatG, parseWeightMg } from "../lib/gold";
import Dialog from "./Dialog";

const MAX_MOVE_MG = 5_000_000;

interface Props {
  direction: "SEND" | "RECEIVE";
  availableG: string;
  today: string;
  onSaved: (message: string) => void;
  onClose: () => void;
}

export default function RefinerDialog({ direction, availableG, today, onSaved, onClose }: Props) {
  const sending = direction === "SEND";
  const minDate = addDays(today, -7);
  const availableMg = parseWeightMg(availableG) ?? 0;

  const [weight, setWeight] = useState("");
  const [date, setDate] = useState(today);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mg = parseWeightMg(weight);
  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(date) && date >= minDate && date <= today;
  const within = mg !== null && mg > 0 && mg <= MAX_MOVE_MG && mg <= availableMg;
  const valid = within && dateOk;

  let hint: string | null = null;
  if (weight.trim() !== "") {
    if (mg === null) hint = "Use up to 3 decimals, for example 25.500.";
    else if (mg <= 0) hint = "The weight must be above 0.";
    else if (mg > MAX_MOVE_MG) hint = `A single movement can't be more than ${formatG(MAX_MOVE_MG)} g.`;
    else if (mg > availableMg) {
      hint = sending
        ? `Only ${formatG(availableMg)} g is in the vault.`
        : `Only ${formatG(availableMg)} g is at the refiner.`;
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError(null);
    try {
      const trimmed = note.trim();
      await api.post("/api/stock/refiner", {
        direction,
        fine_weight: weight.trim(),
        entry_date: date,
        note: trimmed === "" ? null : trimmed,
      });
      onSaved(
        sending
          ? `${weight.trim()} g recorded as sent to the refiner.`
          : `${weight.trim()} g recorded as received from the refiner.`,
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <Dialog
      title={sending ? "Send gold to the refiner" : "Receive gold from the refiner"}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <p className="muted manage-note">
        {sending ? "In the vault" : "At the refiner"}:{" "}
        <span className="figure">{availableG} g</span> of fine gold.
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <div className="field">
          <label htmlFor="m-weight">Fine gold (g)</label>
          <input
            id="m-weight"
            className="input input-figure figure"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            maxLength={11}
            placeholder="0.000"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            aria-invalid={hint !== null}
          />
          {hint && <p className="field-hint">{hint}</p>}
        </div>
        <div className="form-row">
          <div className="field">
            <label htmlFor="m-date">Date</label>
            <input
              id="m-date"
              className="input"
              type="date"
              min={minDate}
              max={today}
              value={date}
              onChange={(e) => setDate(e.target.value)}
              aria-invalid={!dateOk}
            />
            {!dateOk && <p className="field-hint">Pick today or one of the previous 7 days.</p>}
          </div>
          <div className="field">
            <label htmlFor="m-note">Note (optional)</label>
            <input
              id="m-note"
              className="input"
              type="text"
              autoComplete="off"
              maxLength={200}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>
        <p className="muted manage-note">Saved movements can't be edited.</p>
        {error && (
          <p className="banner" role="alert">
            {error}
          </p>
        )}
        <div className="inline">
          <button className="btn btn-primary" type="submit" disabled={busy || !valid}>
            {busy ? "Saving..." : "Record movement"}
          </button>
          <button className="btn" type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  );
}
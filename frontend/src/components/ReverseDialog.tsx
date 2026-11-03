import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import { tidyName } from "../lib/text";
import { KIND_LABEL } from "../lib/types";
import type { LedgerRow, ReversalResult } from "../lib/types";
import Dialog from "./Dialog";

interface Props {
  row: LedgerRow;
  onDone: (result: ReversalResult) => void;
  onClose: () => void;
}

export default function ReverseDialog({ row, onDone, onClose }: Props) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cleaned = tidyName(reason);
  const valid = cleaned.length >= 5 && cleaned.length <= 150;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<ReversalResult>(
        `/api/entries/${row.txn_no}/reverse`,
        { reason: cleaned },
      );
      onDone(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Reverse ${row.txn_no}`} onClose={() => !busy && onClose()}>
      <dl className="slip-rows">
        <div className="slip-row">
          <dt>Entry</dt>
          <dd>
            {KIND_LABEL[row.kind] ?? row.kind} on {showDate(row.entry_date)}
          </dd>
        </div>
        <div className="slip-row">
          <dt>Job</dt>
          <dd className="figure">{row.job_no}</dd>
        </div>
        <div className="slip-row">
          <dt>Fine gold</dt>
          <dd className="figure">{row.fine_weight_g} g</dd>
        </div>
      </dl>
      <p className="muted manage-note">
        The original stays in the ledger. A new entry cancels it, dated today, with your reason.
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <div className="field">
          <label htmlFor="reason">Reason</label>
          <input
            id="reason"
            className="input"
            type="text"
            autoComplete="off"
            maxLength={150}
            placeholder="For example: weight entered wrongly"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="field-count muted">{cleaned.length} / 150, at least 5</p>
        </div>
        {error && (
          <p className="banner" role="alert">
            {error}
          </p>
        )}
        <div className="inline">
          <button className="btn btn-danger" type="submit" disabled={busy || !valid}>
            {busy ? "Reversing..." : "Reverse entry"}
          </button>
          <button className="btn" type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  );
}
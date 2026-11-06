import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import { tidyName } from "../lib/text";
import type { AgingJob } from "../lib/types";
import Dialog from "./Dialog";

interface Props {
  job: AgingJob;
  onDone: (message: string) => void;
  onClose: () => void;
}

export default function FollowUpDialog({ job, onDone, onClose }: Props) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cleaned = tidyName(note);
  const valid = cleaned.length >= 3 && cleaned.length <= 200;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/job-aging/${job.job_no}/follow-ups`, { note: cleaned });
      onDone(`Follow-up recorded for ${job.job_no}.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Follow up ${job.job_no}`} onClose={() => !busy && onClose()}>
      <dl className="slip-rows">
        <div className="slip-row">
          <dt>Karigar</dt>
          <dd>{job.karigar}</dd>
        </div>
        <div className="slip-row">
          <dt>Fine gold outstanding</dt>
          <dd className="figure">{job.outstanding_g} g</dd>
        </div>
        <div className="slip-row">
          <dt>Open for</dt>
          <dd>{job.age_days} days</dd>
        </div>
      </dl>
      {job.last_followup_note && job.last_followup_on && (
        <p className="muted manage-note">
          Last follow-up on {showDate(job.last_followup_on)}: {job.last_followup_note}
        </p>
      )}
      <p className="muted manage-note">
        This records that you followed up, with your note. It doesn't send a message to anyone.
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <div className="field">
          <label htmlFor="fu-note">What happened or what was agreed</label>
          <input
            id="fu-note"
            className="input"
            type="text"
            autoComplete="off"
            maxLength={200}
            placeholder="For example: asked for the pieces by Monday"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <p className="field-count muted">{cleaned.length} / 200, at least 3</p>
        </div>
        {error && (
          <p className="banner" role="alert">
            {error}
          </p>
        )}
        <div className="inline">
          <button className="btn btn-primary" type="submit" disabled={busy || !valid}>
            {busy ? "Saving..." : "Record follow-up"}
          </button>
          <button className="btn" type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  );
}
import { useEffect, useId, useState } from "react";
import type { ChangeEvent } from "react";
import { ApiError, api } from "../lib/api";
import { checkReading } from "../lib/readings";
import type {
  Check,
  ReadingAttach,
  ReadingResponse,
  ReadingTarget,
} from "../lib/readings";

const MAX_BYTES = 5 * 1024 * 1024;

interface Props {
  target: ReadingTarget;
  noun: string;
  unit: string;
  typed: string;
  attach: ReadingAttach | null;
  reason: string;
  onAttach: (attach: ReadingAttach) => void;
  onFill: (value: string) => void;
  onReason: (reason: string) => void;
}

export default function PhotoReader({
  target,
  noun,
  unit,
  typed,
  attach,
  reason,
  onAttach,
  onFill,
  onReason,
}: Props) {
  const inputId = useId();
  const reasonId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewUrl = attach?.previewUrl;
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const source = target === "WEIGHT" ? "scale display" : "karat meter";
  const check = checkReading(target, typed, attach, reason);

  async function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || busy) return;
    if (file.size > MAX_BYTES) {
      setError("The photo is larger than 5 MB. Use a smaller photo.");
      return;
    }
    setBusy(true);
    setError(null);
    const url = URL.createObjectURL(file);
    try {
      const form = new FormData();
      form.append("target", target);
      form.append("image", file);
      const result = await api.postForm<ReadingResponse>("/api/readings", form);
      onAttach({
        id: result.id,
        value: result.value,
        source_label: result.source_label,
        notes: result.notes,
        previewUrl: url,
      });
      onReason("");
      if (result.value !== null) onFill(result.value);
    } catch (e) {
      URL.revokeObjectURL(url);
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="photo-panel">
      <div className="photo-head">
        <span className="photo-title">Photo of the {source}</span>
        <input
          id={inputId}
          className="photo-input"
          type="file"
          accept="image/*"
          capture="environment"
          disabled={busy}
          onChange={(e) => void choose(e)}
        />
        <label className="btn btn-small photo-pick" htmlFor={inputId}>
          {attach ? "Retake photo" : "Take or choose photo"}
        </label>
      </div>

      {busy && (
        <p className="muted manage-note" role="status">
          Reading the photo...
        </p>
      )}

      {error && (
        <p className="banner" role="alert">
          {error}
        </p>
      )}

      {attach && (
        <div className="photo-body">
          <img
            className="photo-img"
            src={attach.previewUrl}
            alt={`Your photo of the ${source}`}
          />
          <div className="photo-result">
            {attach.value !== null ? (
              <>
                <p className="eyebrow">Read by the {attach.source_label.toLowerCase()}</p>
                <p className="photo-value figure">
                  {attach.value} {unit}
                </p>
                <p className="muted manage-note">
                  Check it against the photo. The {noun} field uses this value until you
                  change it.
                </p>
              </>
            ) : (
              <>
                <p className="status-line">The photo couldn't be read.</p>
                <p className="muted manage-note">Type the {noun} from the display.</p>
              </>
            )}
            {attach.notes.map((note) => (
              <p className="muted photo-note" key={note}>
                {note}
              </p>
            ))}
          </div>
        </div>
      )}

      {attach && attach.value !== null && check === "MATCH" && (
        <p className="photo-state">
          <span className="chip chip-ok">The {noun} matches the photo</span>
        </p>
      )}

      {attach && attach.value !== null && (check === "NEEDS_REASON" || check === "OVERRIDE") && (
        <div className="photo-mismatch" role="alert">
          <p>
            The {noun} you entered ({typed.trim() === "" ? "nothing" : typed.trim()}) doesn't
            match the photo reading ({attach.value}). Use the reading, or explain why the photo
            is wrong.
          </p>
          <div className="inline">
            <button
              className="btn btn-small"
              type="button"
              onClick={() => {
                onFill(attach.value ?? "");
                onReason("");
              }}
            >
              Use the photo reading
            </button>
          </div>
          <div className="field photo-reason">
            <label htmlFor={reasonId}>Reason for overriding (at least 5 characters)</label>
            <input
              id={reasonId}
              className="input"
              type="text"
              autoComplete="off"
              maxLength={150}
              placeholder="For example: glare on the display"
              value={reason}
              onChange={(e) => onReason(e.target.value)}
            />
          </div>
          {check === "OVERRIDE" && (
            <p className="muted manage-note">This will be recorded as a correction.</p>
          )}
        </div>
      )}
    </div>
  );
}

export function ReadingSummary({ items }: { items: { noun: string; check: Check }[] }) {
  const lines = items.flatMap(({ noun, check }) => {
    if (check === "MATCH") return [`The ${noun} matches the photo reading.`];
    if (check === "OVERRIDE") {
      return [
        `The ${noun} differs from the photo reading and will be recorded as a correction.`,
      ];
    }
    return [];
  });
  if (lines.length === 0) return null;
  return (
    <div className="manage-note">
      {lines.map((line) => (
        <p className="muted" key={line}>
          {line}
        </p>
      ))}
    </div>
  );
}
import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { RATE_PATTERN, normaliseRate, tidyName } from "../lib/text";
import type { Category, Karigar } from "../lib/types";
import Dialog from "./Dialog";

interface Props {
  karigar: Karigar;
  categories: Category[];
  onChanged: (updated: Karigar) => void;
  onClose: () => void;
}

type Status = { kind: "ok" | "error"; text: string } | null;

export default function ManageKarigar({ karigar, categories, onChanged, onClose }: Props) {
  const [name, setName] = useState(karigar.name);
  const [drafts, setDrafts] = useState<Record<number, string>>(() => {
    const start: Record<number, string> = {};
    for (const w of karigar.wastage) start[w.category_id] = w.wastage_pct;
    return start;
  });
  const [confirmOff, setConfirmOff] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  const currentRate = (categoryId: number): string =>
    karigar.wastage.find((w) => w.category_id === categoryId)?.wastage_pct ?? "";

  async function run(action: () => Promise<Karigar>, success: string): Promise<boolean> {
    if (busy) return false;
    setBusy(true);
    setStatus(null);
    try {
      const updated = await action();
      onChanged(updated);
      setStatus({ kind: "ok", text: success });
      return true;
    } catch (e) {
      setStatus({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Something went wrong. Try again.",
      });
      return false;
    } finally {
      setBusy(false);
    }
  }

  const cleanedName = tidyName(name);
  const nameChanged = cleanedName !== "" && cleanedName !== karigar.name;

  function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!nameChanged) return;
    void run(
      () => api.patch<Karigar>(`/api/karigars/${karigar.id}`, { name: cleanedName }),
      "Name saved.",
    );
  }

  function saveRate(event: FormEvent<HTMLFormElement>, category: Category) {
    event.preventDefault();
    const value = (drafts[category.id] ?? "").trim();
    void run(
      () =>
        api.put<Karigar>(`/api/karigars/${karigar.id}/wastage/${category.id}`, {
          wastage_pct: value,
        }),
      `${category.name} rate saved.`,
    );
  }

  async function setActive(active: boolean) {
    const done = await run(
      () => api.patch<Karigar>(`/api/karigars/${karigar.id}`, { is_active: active }),
      active ? "Karigar reactivated." : "Karigar deactivated.",
    );
    if (done) setConfirmOff(false);
  }

  return (
    <Dialog title={`Manage ${karigar.name}`} onClose={onClose}>
      <form className="manage-section" onSubmit={rename} noValidate>
        <label htmlFor="mk-name">Name</label>
        <div className="inline">
          <input
            id="mk-name"
            className="input"
            type="text"
            autoComplete="off"
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="btn btn-primary" type="submit" disabled={busy || !nameChanged}>
            Save name
          </button>
        </div>
      </form>

      <section className="manage-section">
        <h3 className="section-title">Agreed wastage</h3>
        <p className="muted manage-note">
          Percent of the fine gold issued, with up to 2 decimals. Past entries keep
          the rate that applied when they were made.
        </p>
        {categories.map((category) => {
          const draft = drafts[category.id] ?? "";
          const trimmed = draft.trim();
          const valid = RATE_PATTERN.test(trimmed);
          const current = currentRate(category.id);
          const changed = valid && (current === "" || normaliseRate(trimmed) !== current);
          return (
            <form
              className="rate-edit"
              key={category.id}
              onSubmit={(e) => saveRate(e, category)}
              noValidate
            >
              <label htmlFor={`rate-${category.id}`}>{category.name}</label>
              <div className="inline">
                <input
                  id={`rate-${category.id}`}
                  className="input input-figure figure"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  maxLength={6}
                  placeholder="Not set"
                  value={draft}
                  onChange={(e) =>
                    setDrafts((prev) => ({ ...prev, [category.id]: e.target.value }))
                  }
                  aria-invalid={trimmed !== "" && !valid}
                />
                <span className="unit">%</span>
                <button className="btn" type="submit" disabled={busy || !changed}>
                  Save
                </button>
              </div>
              {trimmed !== "" && !valid && (
                <p className="field-hint">Use a number from 0 to 100 with up to 2 decimals.</p>
              )}
            </form>
          );
        })}
      </section>

      <section className="manage-section">
        <h3 className="section-title">Status</h3>
        {karigar.is_active ? (
          karigar.open_jobs > 0 ? (
            <p className="muted">
              Can't deactivate while there {karigar.open_jobs === 1 ? "is" : "are"}{" "}
              <span className="figure">{karigar.open_jobs}</span> open{" "}
              {karigar.open_jobs === 1 ? "job" : "jobs"}. Close them first.
            </p>
          ) : confirmOff ? (
            <div>
              <p className="manage-note">
                An inactive karigar can't be issued new gold. Their history stays.
              </p>
              <div className="inline">
                <button
                  className="btn btn-danger"
                  type="button"
                  disabled={busy}
                  onClick={() => void setActive(false)}
                >
                  Yes, deactivate
                </button>
                <button className="btn" type="button" onClick={() => setConfirmOff(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button className="btn" type="button" onClick={() => setConfirmOff(true)}>
              Deactivate karigar
            </button>
          )
        ) : (
          <button
            className="btn btn-primary"
            type="button"
            disabled={busy}
            onClick={() => void setActive(true)}
          >
            Reactivate karigar
          </button>
        )}
      </section>

      {status && (
        <p
          className={status.kind === "error" ? "banner" : "banner banner-ok"}
          role={status.kind === "error" ? "alert" : "status"}
        >
          {status.text}
        </p>
      )}
    </Dialog>
  );
}
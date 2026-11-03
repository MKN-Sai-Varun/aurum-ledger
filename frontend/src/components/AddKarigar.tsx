import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { tidyName } from "../lib/text";
import type { Karigar } from "../lib/types";
import Dialog from "./Dialog";

interface Props {
  onCreated: (created: Karigar) => void;
  onClose: () => void;
}

export default function AddKarigar({ onCreated, onClose }: Props) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleaned = tidyName(name);
    if (busy || !cleaned) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<Karigar>("/api/karigars", { name: cleaned });
      onCreated(created);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <Dialog title="Add a karigar" onClose={onClose}>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <div className="field">
          <label htmlFor="new-name">Name</label>
          <input
            id="new-name"
            className="input"
            type="text"
            autoComplete="off"
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <p className="muted manage-note">
          You will set the agreed wastage next. A karigar can't be issued gold
          until a rate exists for the item category.
        </p>
        {error && (
          <p className="banner" role="alert">
            {error}
          </p>
        )}
        <button
          className="btn btn-primary btn-block"
          type="submit"
          disabled={busy || !tidyName(name)}
        >
          {busy ? "Adding..." : "Add karigar"}
        </button>
      </form>
    </Dialog>
  );
}
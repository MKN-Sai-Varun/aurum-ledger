import { useEffect } from "react";

// Drafts of forms, kept on this device so a refresh or a power cut doesn't lose them.
// They never hold customer names, PANs or photos, expire after a day, and are
// removed when the clerk signs out.

const PREFIX = "aurum.draft.";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface Draft<T> {
  data: T;
  savedAt: number;
}

export function draftKey(userId: number, form: string): string {
  return `${PREFIX}${userId}.${form}`;
}

export function loadDraft<T>(key: string): Draft<T> | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { data?: T; savedAt?: number };
    if (!parsed || typeof parsed.savedAt !== "number" || parsed.data === undefined) return null;
    if (Date.now() - parsed.savedAt > MAX_AGE_MS) {
      window.localStorage.removeItem(key);
      return null;
    }
    return { data: parsed.data, savedAt: parsed.savedAt };
  } catch {
    return null;
  }
}

export function clearDraft(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Storage is unavailable, so there is nothing to clear.
  }
}

export function clearAllDrafts(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const name = window.localStorage.key(i);
      if (name && name.startsWith(PREFIX)) keys.push(name);
    }
    keys.forEach((name) => window.localStorage.removeItem(name));
  } catch {
    // Storage is unavailable, so there is nothing to clear.
  }
}

/** Save the form 0.4 seconds after the last change. A form with nothing typed saves nothing. */
export function useAutosave(
  key: string,
  data: Record<string, string>,
  active: boolean,
  ignore: string[] = [],
): void {
  const json = JSON.stringify(data);
  const ignoreKey = ignore.join(",");

  useEffect(() => {
    if (!active) return;
    const values = JSON.parse(json) as Record<string, string>;
    const skip = ignoreKey ? ignoreKey.split(",") : [];
    const blank = Object.entries(values).every(
      ([name, value]) => skip.includes(name) || value === "",
    );
    const timer = window.setTimeout(() => {
      try {
        if (blank) window.localStorage.removeItem(key);
        else
          window.localStorage.setItem(key, JSON.stringify({ data: values, savedAt: Date.now() }));
      } catch {
        // Storage is full or blocked. The form still works, it just isn't kept.
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [key, json, active, ignoreKey]);
}
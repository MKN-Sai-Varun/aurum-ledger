import { useCallback, useState } from "react";
import type { Lang } from "./i18n";

const KEY = "aurum.lang";

function read(): Lang {
  try {
    return window.localStorage.getItem(KEY) === "en" ? "en" : "ta";
  } catch {
    return "ta";
  }
}

export function useLang(): [Lang, (next: Lang) => void] {
  const [lang, setLangState] = useState<Lang>(read);
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // The choice just isn't remembered.
    }
  }, []);
  return [lang, setLang];
}
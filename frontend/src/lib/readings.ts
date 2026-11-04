import { formatG, formatPctH, parsePurityH, parseWeightMg } from "./gold";

export type ReadingTarget = "WEIGHT" | "PURITY";

/** NONE: no usable photo. MATCH: typed value equals the reading.
 *  NEEDS_REASON: differs and no reason yet. OVERRIDE: differs, with a reason. */
export type Check = "NONE" | "MATCH" | "NEEDS_REASON" | "OVERRIDE";

export const MIN_REASON = 5;

export interface ReadingResponse {
  id: number;
  target: string;
  source: string;
  source_label: string;
  value: string | null;
  readable: boolean;
  notes: string[];
}

export interface ReadingAttach {
  id: number;
  value: string | null;
  source_label: string;
  notes: string[];
  previewUrl: string;
}

/** The typed text in the same canonical form the server uses, or null if invalid. */
export function canonicalValue(target: ReadingTarget, text: string): string | null {
  if (target === "WEIGHT") {
    const mg = parseWeightMg(text);
    return mg === null ? null : formatG(mg);
  }
  const hundredths = parsePurityH(text);
  return hundredths === null ? null : formatPctH(hundredths);
}

export function checkReading(
  target: ReadingTarget,
  typed: string,
  attach: ReadingAttach | null,
  reason: string,
): Check {
  if (!attach || attach.value === null) return "NONE";
  if (canonicalValue(target, typed) === attach.value) return "MATCH";
  return reason.trim().length >= MIN_REASON ? "OVERRIDE" : "NEEDS_REASON";
}

/** The request fields for one photo reading. Empty when no usable photo is attached. */
export function readingFields(
  prefix: "weight" | "purity",
  attach: ReadingAttach | null,
  check: Check,
  reason: string,
): Record<string, unknown> {
  if (!attach || attach.value === null) return {};
  const fields: Record<string, unknown> = { [`${prefix}_reading_id`]: attach.id };
  if (check === "OVERRIDE") fields[`${prefix}_override_reason`] = reason.trim();
  return fields;
}
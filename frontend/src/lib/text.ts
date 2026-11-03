/** Collapse repeated spaces, as the server does. */
export function tidyName(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(" ");
}

/** The shape the server accepts for a percentage: up to 2 decimals. */
export const RATE_PATTERN = /^[0-9]{1,3}(\.[0-9]{1,2})?$/;

/** Make "3" and "3.00" comparable, with no floating point involved. */
export function normaliseRate(value: string): string {
  const [whole, fraction = ""] = value.trim().split(".");
  return `${Number(whole)}.${fraction.padEnd(2, "0")}`;
}
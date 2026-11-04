// Mirrors the server's money rules. Money is integer paise. The server's result is final.

/** Assumption A-22: the brief gives no threshold. Must match the server's constant. */
export const HIGH_VALUE_PAISE = 20_000_000;
export const MAX_RATE_PAISE = 10_000_000;

export const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
export const BILL_RE = /^[A-Z0-9][A-Z0-9/_.-]{2,29}$/;
const RUPEES_RE = /^[0-9]{1,7}(\.[0-9]{1,2})?$/;

export function parseRupeesPaise(text: string): number | null {
  const value = text.trim();
  if (!RUPEES_RE.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

/** Milligrams times paise per gram, divided by 1000, rounded half up. */
export function valuePaise(fineMg: number, ratePaise: number): number {
  const product = fineMg * ratePaise + 500;
  return (product - (product % 1000)) / 1000;
}

const grouping = new Intl.NumberFormat("en-IN");

export function formatPaise(paise: number): string {
  const rupees = Math.floor(paise / 100);
  return `${grouping.format(rupees)}.${String(paise % 100).padStart(2, "0")}`;
}

/** Group a server amount such as "258787.50" as "2,58,787.50". */
export function groupRupees(text: string): string {
  const [whole, fraction = "00"] = text.split(".");
  return `${grouping.format(Number(whole))}.${fraction}`;
}
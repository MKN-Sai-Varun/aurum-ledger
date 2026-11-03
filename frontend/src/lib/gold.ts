// Mirrors the server's integer maths. Weights are milligrams and
// percentages are hundredths of a percent. The server's result is final.

export const MAX_ISSUE_MG = 2_000_000;

const WEIGHT_RE = /^[0-9]{1,6}(\.[0-9]{1,3})?$/;
const PERCENT_RE = /^[0-9]{1,3}(\.[0-9]{1,2})?$/;

function scaled(text: string, places: number): number {
  const [whole, fraction = ""] = text.split(".");
  return Number(whole) * 10 ** places + Number(fraction.padEnd(places, "0"));
}

export function parseWeightMg(text: string): number | null {
  const value = text.trim();
  return WEIGHT_RE.test(value) ? scaled(value, 3) : null;
}

/** Purity: above 0 and up to 100. */
export function parsePurityH(text: string): number | null {
  const value = text.trim();
  if (!PERCENT_RE.test(value)) return null;
  const hundredths = scaled(value, 2);
  return hundredths >= 1 && hundredths <= 10_000 ? hundredths : null;
}

/** A percentage from 0 to 100, such as the agreed wastage. */
export function parsePercentH(text: string): number | null {
  const value = text.trim();
  if (!PERCENT_RE.test(value)) return null;
  const hundredths = scaled(value, 2);
  return hundredths <= 10_000 ? hundredths : null;
}

/** Percentage of an amount, rounded half up, using integers only. */
export function applyPct(mg: number, hundredths: number): number {
  const product = mg * hundredths + 5_000;
  return (product - (product % 10_000)) / 10_000;
}

export function formatG(mg: number): string {
  return `${Math.floor(mg / 1000)}.${String(mg % 1000).padStart(3, "0")}`;
}
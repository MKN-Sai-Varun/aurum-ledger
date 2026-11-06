// All Tamil and English text for the karigar page lives here, so a Tamil reader
// can correct it in one place. Gold figures always use Latin digits.

export type Lang = "ta" | "en";
type Pair = { ta: string; en: string };

export const TEXT = {
  title: { ta: "எனது தங்கக் கணக்கு", en: "My gold account" },
  balanceLabel: { ta: "என்னிடம் உள்ள தூய தங்கம்", en: "Fine gold with me" },
  unit: { ta: "கிராம்", en: "grams" },
  openJobs: { ta: "நடப்பில் உள்ள வேலைகள்", en: "Open jobs" },
  jobsHeading: { ta: "எனது வேலைகள்", en: "My jobs" },
  entriesHeading: { ta: "சீட்டுகள் மற்றும் பதிவுகள்", en: "Slips and entries" },
  issued: { ta: "வழங்கப்பட்டது", en: "Issued" },
  returned: { ta: "திரும்பப் பெறப்பட்டது", en: "Returned" },
  outstanding: { ta: "மீதம்", en: "Still with me" },
  open: { ta: "நடப்பில்", en: "Open" },
  closed: { ta: "முடிந்தது", en: "Closed" },
  job: { ta: "வேலை எண்", en: "Job" },
  slipNo: { ta: "சீட்டு எண்", en: "Slip no." },
  item: { ta: "நகை வகை", en: "Item" },
  gross: { ta: "மொத்த எடை", en: "Gross weight" },
  purity: { ta: "தூய்மை", en: "Purity" },
  fine: { ta: "தூய தங்கம்", en: "Fine gold" },
  change: { ta: "மாற்றம்", en: "Change" },
  noEntries: { ta: "இன்னும் பதிவுகள் எதுவும் இல்லை.", en: "No entries yet." },
  noJobs: { ta: "இன்னும் வேலைகள் இல்லை.", en: "No jobs yet." },
  loading: { ta: "ஏற்றுகிறது...", en: "Loading..." },
  retry: { ta: "மீண்டும் முயற்சிக்கவும்", en: "Try again" },
  latestOnly: {
    ta: "சமீபத்திய பதிவுகள் மட்டும் காட்டப்படுகின்றன.",
    en: "Only the latest entries are shown.",
  },
  readOnly: {
    ta: "இது பார்ப்பதற்கு மட்டும். ஏதேனும் தவறு இருந்தால் மேலாளரிடம் கூறுங்கள்.",
    en: "This page is for viewing only. If something looks wrong, tell the manager.",
  },
  language: { ta: "மொழி", en: "Language" },
} satisfies Record<string, Pair>;

export type TextKey = keyof typeof TEXT;

export const KIND_TEXT: Record<string, Pair> = {
  ISSUE: { ta: "தங்கம் வழங்கப்பட்டது", en: "Gold issued" },
  RECEIPT_PIECE: { ta: "நகை திரும்பப் பெறப்பட்டது", en: "Finished piece returned" },
  RECEIPT_SCRAP: { ta: "கழிவு தங்கம் திரும்பப் பெறப்பட்டது", en: "Scrap returned" },
  RECEIPT_FILINGS: { ta: "தூள் தங்கம் திரும்பப் பெறப்பட்டது", en: "Filings returned" },
  REVERSAL: { ta: "திருத்தம்", en: "Correction" },
};

export const CATEGORY_TEXT: Record<string, Pair> = {
  Necklace: { ta: "ஆரம்", en: "Necklace" },
  Chain: { ta: "சங்கிலி", en: "Chain" },
  Bangle: { ta: "வளையல்", en: "Bangle" },
  Ring: { ta: "மோதிரம்", en: "Ring" },
  Earring: { ta: "காதணி", en: "Earring" },
};

export function pick(map: Record<string, Pair>, key: string, lang: Lang): string {
  return map[key]?.[lang] ?? key;
}
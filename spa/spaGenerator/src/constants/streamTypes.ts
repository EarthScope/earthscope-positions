// ─────────────────────────────────────────────────────────────────────────────
// Single source of truth for processing-center and stream-type enumerations.
//
// EDIT THE TWO LISTS BELOW — every page (Station Builder, Fetch Data, PPSD,
// Replay) reads from them, so changes propagate everywhere.
//
//   • label            — the display name (change freely)
//   • defaultSelected  — whether the entry's filter checkbox/chip starts checked
//   • order            — entries render in the order listed here (00:CWU first)
//
// Add / remove / reorder rows as needed; `code` is the value matched against
// GEOSNCL strings (center = 2nd dot-segment; stream type = first 2 chars of the
// 4th dot-segment) and must not change unless the underlying data does.
// ─────────────────────────────────────────────────────────────────────────────

export interface CenterDef {
  code: string;
  label: string;
  defaultSelected: boolean;
}

export interface StreamTypeDef {
  code: string;
  label: string;
  defaultSelected: boolean;
}

/** Processing centers (GEOSNCL 2-char center code). */
export const PROC_CENTER_DEFS: CenterDef[] = [
  { code: "PB", label: "EarthScope", defaultSelected: true },
  { code: "PW", label: "CWU", defaultSelected: true },
  { code: "NC", label: "USGS Moffett", defaultSelected: true },
  { code: "BK", label: "UCB", defaultSelected: true },
  { code: "CI", label: "USGS Pasadena", defaultSelected: true },
];

/** Stream types (2-char solution+type code). */
export const STREAM_TYPE_DEFS: StreamTypeDef[] = [
  { code: "00", label: "Fastlane", defaultSelected: true },
  { code: "10", label: "PIVOT Fast", defaultSelected: false },
  { code: "12", label: "PIVOT Complete", defaultSelected: false },
  { code: "13", label: "PIVOT Combined", defaultSelected: false },
  { code: "20", label: "RTNet", defaultSelected: true },
  { code: "30", label: "Onboard Septentrio", defaultSelected: true },
  { code: "40", label: "Onboard TrimbleRTX", defaultSelected: true },
  { code: "50", label: "Network", defaultSelected: false },
  { code: "60", label: "JPL PPP", defaultSelected: false },
];

// ── Derived lookups (do not edit; computed from the enumerations above) ───────

/** Ordered stream-type entries — alias kept for existing `v-for` usage. */
export const STREAM_TYPES: StreamTypeDef[] = STREAM_TYPE_DEFS;

export const CENTER_CODES: string[] = PROC_CENTER_DEFS.map((c) => c.code);
export const STREAM_TYPE_CODES: string[] = STREAM_TYPE_DEFS.map((s) => s.code);

/** Codes whose checkbox/chip should start selected. */
export const DEFAULT_CENTER_CODES: string[] = PROC_CENTER_DEFS.filter(
  (c) => c.defaultSelected,
).map((c) => c.code);
export const DEFAULT_STREAM_TYPE_CODES: string[] = STREAM_TYPE_DEFS.filter(
  (s) => s.defaultSelected,
).map((s) => s.code);

/** center code → display name. */
export const PROC_CENTERS: Record<string, string> = Object.fromEntries(
  PROC_CENTER_DEFS.map((c) => [c.code, c.label]),
);

/** 2-char stream-type code → full label. */
export const SOL_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  STREAM_TYPE_DEFS.map((s) => [s.code, s.label]),
);

/** First digit of the stream-type code → solution (processing) name. */
export const SOL_LABELS: Record<string, string> = {
  "0": "CWU",
  "1": "PIVOT",
  "2": "RTNet",
  "3": "Septa",
  "4": "RTX",
  "5": "Net",
  "6": "JPL",
};

/** Second digit of the stream-type code → solution-type name. */
export const TYPE_LABELS: Record<string, string> = {
  "0": "Fast",
  "1": "RTK",
  "2": "Compl",
  "3": "F+C",
};

/** Human label for a 2-char stream-type code (falls back to digit composition). */
export function solTypeLabel(code: string): string {
  if (SOL_TYPE_LABELS[code]) return SOL_TYPE_LABELS[code];
  const sol = SOL_LABELS[code[0]] ?? code[0] ?? "";
  const typ = TYPE_LABELS[code[1]] ?? code[1] ?? "";
  return `${sol} ${typ}`.trim();
}

/** Sort stream-type codes into the canonical display order (unknown codes last). */
export function sortSolTypes(codes: string[]): string[] {
  return [...codes].sort((a, b) => {
    const ia = STREAM_TYPE_CODES.indexOf(a);
    const ib = STREAM_TYPE_CODES.indexOf(b);
    return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
  });
}

/** Intersect available codes with the default-selected set, preserving order. */
export function defaultSelectedCenters(available: string[]): string[] {
  return available.filter((c) => DEFAULT_CENTER_CODES.includes(c));
}
export function defaultSelectedStreamTypes(available: string[]): string[] {
  return available.filter((c) => DEFAULT_STREAM_TYPE_CODES.includes(c));
}

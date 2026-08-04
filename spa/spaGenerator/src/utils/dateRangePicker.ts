/**
 * Per-box click handling for Quasar's `q-date` in `range` mode, for use when
 * the calendar icon is embedded inside each of two independent fields ("From"
 * and "To").
 *
 * Quasar's range-mode day click has no mouse-drag support at all — it's
 * strictly two clicks: the first click starts a pending selection (emits
 * nothing), the second click completes it. Click the same day twice and it
 * emits a plain date string; click two different days and it emits a
 * `{from, to}` object. This handler routes each shape accordingly: a plain
 * string only touches the field whose popup is open, leaving the other field
 * untouched; a `{from, to}` object sets both fields at once.
 *
 * IMPORTANT: bind the `q-date` with `:model-value="null"` (a static prop, not
 * a `v-model`), not the current start/end range. If the popup shows the
 * already-selected multi-day range, clicking a day *inside* that range is
 * interpreted by Quasar as removing that day from the existing selection and
 * emits `null` instead of starting a fresh pick — the very first click
 * silently clears things instead of doing anything useful. Starting every
 * popup open from a blank slate avoids that.
 *
 * `onCommit`, if given, runs once a selection actually completes (either
 * branch) — wire it to close the popup, since a completed pick has nothing
 * left for the user to do in it.
 */
export function createBoxRangeSelectHandler(
  setSingle: (date: string) => void,
  commitRange: (from: string, to: string) => void,
  onCommit?: () => void,
) {
  return function onSelect(val: { from: string; to: string } | string | null): void {
    if (!val) return;

    if (typeof val === "string") {
      // Same day clicked twice — only the field this popup belongs to changes.
      setSingle(val);
      onCommit?.();
      return;
    }

    // Two different days clicked — a genuine range.
    if (!val.from || !val.to) return;
    commitRange(val.from, val.to);
    onCommit?.();
  };
}

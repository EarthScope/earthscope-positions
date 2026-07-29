/**
 * Click-to-build range selection for Quasar's `q-date` in `range` mode.
 *
 * Quasar only emits a genuine `{from, to}` pair when the user drags across
 * days; a plain click with no drag emits a bare date string. Left to itself,
 * every plain click just re-picks a new single day — there's no way to build
 * a multi-day range without dragging.
 *
 * This wraps the `@update:model-value` handler so two independent clicks also
 * work: click 1 sets the start (shown immediately as a one-day selection),
 * click 2 sets the end and completes the span. Dragging still completes a
 * range in one motion, exactly as before.
 */
export function createRangeSelectHandler(
  setDisplay: (from: string, to: string) => void,
  commit: (from: string, to: string) => void,
) {
  let pendingStart: string | null = null;

  return function onRangeSelect(val: { from: string; to: string } | string | null): void {
    if (!val) return;

    if (typeof val === "string") {
      // Plain click, no drag.
      if (pendingStart === null) {
        pendingStart = val;
        setDisplay(val, val);
      } else {
        const a = pendingStart;
        const b = val;
        pendingStart = null;
        commit(a <= b ? a : b, a <= b ? b : a);
      }
      return;
    }

    // A drag produced a genuine range directly.
    pendingStart = null;
    if (!val.from || !val.to) return;
    commit(val.from, val.to);
  };
}

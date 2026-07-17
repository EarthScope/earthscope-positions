import { ref } from "vue";
import { openFetchMissingPost } from "../api";
import type { FetchMissingBody } from "../types";

// Module-level singletons — persist across route navigation and keep the job
// running when the user switches tabs (like the PPSD / Replay pages).  Only one
// fetch can be active at a time (guarded by `running`).

export interface FetchLogEntry {
  text: string;
  isError: boolean;
  isDone: boolean;
}

// ── Wizard config (persisted across navigation) ──────────────────────────────
const step           = ref(1);
const selectedLists  = ref<string[]>([]);
const startDate      = ref("");
const endDate        = ref("");
const filterCenters  = ref<string[]>([]);
const filterSolTypes = ref<string[]>([]);
const workers        = ref(10);

// ── Job state ────────────────────────────────────────────────────────────────
const logs      = ref<FetchLogEntry[]>([]);
const running   = ref(false);
const done      = ref(false);
const exitCode  = ref<number | null>(null);
const current   = ref(0);   // day-level progress
const total     = ref(0);
const startedAt = ref<number | null>(null);

let _cancel: (() => void) | null = null;

function reset() {
  logs.value = [];
  done.value = false;
  exitCode.value = null;
  current.value = 0;
  total.value = 0;
}

/** Start a fetch. Resolution of lists + filters happens server-side (POST).
 *  The stream keeps running even if the page component unmounts. */
function start(body: FetchMissingBody) {
  if (running.value) return;
  reset();
  running.value = true;
  startedAt.value = Date.now();

  _cancel = openFetchMissingPost(body, (evt) => {
    if (typeof evt.total === "number") total.value = evt.total;
    if (typeof evt.current === "number") current.value = evt.current;

    if (evt.type === "done") {
      exitCode.value = evt.code ?? 0;
      done.value = true;
      running.value = false;
      _cancel = null;
      if (total.value > 0) current.value = total.value;
      logs.value.push({ text: evt.msg ?? "Done.", isError: (evt.code ?? 0) !== 0, isDone: true });
    } else {
      logs.value.push({
        text: evt.msg ?? "",
        isError: evt.type === "error",
        isDone: false,
      });
    }
  });
}

function cancel() {
  if (_cancel) { _cancel(); _cancel = null; }
  running.value = false;
  done.value = true;
  exitCode.value = 1;
  logs.value.push({ text: "Canceled by user.", isError: false, isDone: true });
}

export function useFetchJob() {
  return {
    step, selectedLists, startDate, endDate, filterCenters, filterSolTypes, workers,
    logs, running, done, exitCode, current, total, startedAt,
    start, cancel, reset,
  };
}

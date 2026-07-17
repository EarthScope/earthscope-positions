import { ref } from "vue";
import { openExportStream } from "../api";
import type { FetchEvent } from "../types";

// Module-level singletons — persist across route navigation and keep the export
// running (logs flowing) when the user switches tabs, like the PPSD / Fetch /
// Replay pages.  Only one export runs at a time (guarded by `running`).

export type ExportFormat = "miniseed" | "geojson";
export interface ExportLogEntry { text: string; isError: boolean; isDone: boolean }

// ── Config (persisted) ────────────────────────────────────────────────────────
const format        = ref<ExportFormat>("miniseed");
const gjFormat      = ref<"compact" | "full" | "both">("both");
const selectedLists = ref<string[]>([]);
const startDate     = ref("");
const endDate       = ref("");
const force         = ref(false);

// Path-spec editor (persisted, incl. unsaved edits).  `specFormatLoaded` tracks
// which format `specContent` was loaded for, so we only reload when needed.
const specContent      = ref("");
const specFileName     = ref("");
const specFormatLoaded = ref<ExportFormat | "">("");

// ── Job state (persisted) ─────────────────────────────────────────────────────
const logs     = ref<ExportLogEntry[]>([]);
const running  = ref(false);
const done     = ref(false);
const exitCode = ref<number | null>(null);

let _cancel: (() => void) | null = null;

function start() {
  if (running.value) return;
  logs.value = [];
  done.value = false;
  exitCode.value = null;
  running.value = true;

  _cancel = openExportStream(
    {
      format: format.value,
      lists: [...selectedLists.value],
      start: startDate.value,
      end: endDate.value,
      gj_format: gjFormat.value,
      force: force.value,
    },
    (evt: FetchEvent) => {
      if (evt.type === "done") {
        exitCode.value = evt.code ?? 0;
        done.value = true;
        running.value = false;
        _cancel = null;
        logs.value.push({ text: evt.msg ?? "Done.", isError: (evt.code ?? 0) !== 0, isDone: true });
      } else {
        logs.value.push({ text: evt.msg ?? "", isError: evt.type === "error", isDone: false });
      }
    },
  );
}

function cancel() {
  if (_cancel) { _cancel(); _cancel = null; }
  running.value = false;
  done.value = true;
  exitCode.value = 1;
  logs.value.push({ text: "Canceled by user.", isError: false, isDone: true });
}

export function useExportJob() {
  return {
    format, gjFormat, selectedLists, startDate, endDate, force,
    specContent, specFileName, specFormatLoaded,
    logs, running, done, exitCode,
    start, cancel,
  };
}

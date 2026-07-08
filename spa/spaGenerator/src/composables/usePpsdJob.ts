import { ref } from "vue";

// Module-level singletons — persist across route navigation
export interface PpsdLogEntry {
  text: string;
  isError: boolean;
  isDone: boolean;
}

export interface PpsdCompletedFile {
  path: string;
  label: string;
}

// Filter state (populated from API; all selected by default)
const filterCenters  = ref<string[]>([]);
const filterSolTypes = ref<string[]>([]);

const logs = ref<PpsdLogEntry[]>([]);
const running = ref(false);
const done = ref(false);
const exitCode = ref<number | null>(null);
const progressCurrent = ref(0);
const progressTotal   = ref(0);
const completedFiles  = ref<PpsdCompletedFile[]>([]);

let _cancel: (() => void) | null = null;

export function usePpsdJob() {
  return {
    filterCenters, filterSolTypes,
    logs, running, done, exitCode,
    progressCurrent, progressTotal, completedFiles,
    getCancel, setCancel, clearCancel,
  };
}

function getCancel() { return _cancel; }
function setCancel(fn: (() => void) | null) { _cancel = fn; }
function clearCancel() { _cancel = null; }

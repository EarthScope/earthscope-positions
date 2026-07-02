<template>
  <q-page class="q-pa-md">
    <div class="row q-col-gutter-md">

      <!-- ── Left: configuration ─────────────────────────────────────────── -->
      <div class="col-12 col-md-4 col-lg-3">
        <q-card flat bordered class="config-card">
          <q-card-section class="q-pb-xs">
            <div class="text-subtitle1 text-weight-medium">PPSD Configuration</div>
          </q-card-section>
          <q-separator />
          <q-card-section class="q-gutter-sm">

            <!-- Station lists -->
            <q-select
              v-model="selectedLists"
              :options="listOptions"
              label="Station list(s)"
              multiple
              use-chips
              dense
              outlined
              emit-value
              map-options
              :disable="running"
            />

            <!-- Date range -->
            <div class="row q-gutter-xs">
              <q-input
                v-model="startDate"
                label="Start date"
                dense
                outlined
                class="col"
                mask="####-##-##"
                placeholder="YYYY-MM-DD"
                :disable="running"
              />
              <q-input
                v-model="endDate"
                label="End date"
                dense
                outlined
                class="col"
                mask="####-##-##"
                placeholder="YYYY-MM-DD"
                :disable="running"
              />
              <q-btn flat dense round icon="date_range" size="sm" class="self-center" :disable="running">
                <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                  <q-date v-model="dateRange" range mask="YYYY-MM-DD" @update:model-value="onRangeSelect">
                    <div class="row items-center justify-end">
                      <q-btn v-close-popup label="Close" color="primary" flat />
                    </div>
                  </q-date>
                </q-popup-proxy>
              </q-btn>
            </div>

            <!-- Processing centers -->
            <div class="text-caption text-grey-6 q-mt-xs">Processing centers</div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="c in ALL_CENTERS"
                :key="c"
                :selected="filterCenters.includes(c)"
                clickable
                dense
                size="sm"
                :color="filterCenters.includes(c) ? 'primary' : 'grey-3'"
                :text-color="filterCenters.includes(c) ? 'white' : 'black'"
                :disable="running"
                @click="toggleItem(filterCenters, c)"
              >{{ c }}</q-chip>
            </div>

            <!-- PPP solutions -->
            <div class="text-caption text-grey-6">PPP solutions</div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="s in ALL_SOLUTIONS"
                :key="s.v"
                :selected="filterSolutions.includes(s.v)"
                clickable
                dense
                size="sm"
                :color="filterSolutions.includes(s.v) ? 'primary' : 'grey-3'"
                :text-color="filterSolutions.includes(s.v) ? 'white' : 'black'"
                :disable="running"
                @click="toggleItem(filterSolutions, s.v)"
              >{{ s.v }} {{ s.label }}</q-chip>
            </div>

            <!-- Solution types -->
            <div class="text-caption text-grey-6">Solution types</div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="t in ALL_TYPES"
                :key="t.v"
                :selected="filterTypes.includes(t.v)"
                clickable
                dense
                size="sm"
                :color="filterTypes.includes(t.v) ? 'primary' : 'grey-3'"
                :text-color="filterTypes.includes(t.v) ? 'white' : 'black'"
                :disable="running"
                @click="toggleItem(filterTypes, t.v)"
              >{{ t.v }} {{ t.label }}</q-chip>
            </div>

          </q-card-section>
          <q-separator />
          <q-card-section class="q-gutter-sm">

            <!-- Action buttons -->
            <q-btn
              class="full-width"
              color="primary"
              icon="workspaces"
              label="By Processing Center"
              :disable="!canRun || running"
              @click="runPpsd('by-center')"
              unelevated
            />
            <q-btn
              class="full-width"
              color="secondary"
              icon="show_chart"
              label="By Stream"
              :disable="!canRun || running"
              @click="runPpsd('by-stream')"
              unelevated
            />
            <q-btn
              class="full-width"
              color="teal"
              icon="layers"
              label="By Solution Type"
              :disable="!canRun || running"
              @click="runPpsd('by-solution')"
              unelevated
            />
            <q-btn
              class="full-width"
              color="deep-orange"
              icon="grid_view"
              label="By Center × Solution"
              :disable="!canRun || running"
              @click="runPpsd('by-center-solution')"
              unelevated
            />

            <q-btn
              v-if="running"
              class="full-width q-mt-xs"
              flat
              color="negative"
              icon="stop"
              label="Cancel"
              @click="cancelJob"
            />

            <q-btn
              v-if="done && exitCode === 0"
              class="full-width q-mt-sm"
              flat
              color="primary"
              icon="folder_open"
              label="View in File Plots"
              to="/plots"
            />

          </q-card-section>
        </q-card>
      </div>

      <!-- ── Right: output ──────────────────────────────────────────────── -->
      <div class="col-12 col-md-8 col-lg-9">

        <!-- Progress bar (shown while running) -->
        <q-card v-if="running || (done && progressTotal > 0)" flat bordered class="q-mb-md">
          <q-card-section class="q-py-sm">
            <div class="row items-center q-gutter-sm">
              <q-spinner v-if="running" color="primary" size="18px" />
              <q-icon v-else-if="exitCode === 0" name="check_circle" color="positive" size="18px" />
              <q-icon v-else name="error" color="negative" size="18px" />
              <div class="col text-caption">
                {{ progressTotal > 0
                  ? `Processing ${progressCurrent} of ${progressTotal}`
                  : (running ? 'Starting…' : 'Done') }}
              </div>
            </div>
            <q-linear-progress
              v-if="progressTotal > 0"
              :value="progressCurrent / progressTotal"
              color="primary"
              class="q-mt-xs"
              rounded
            />
          </q-card-section>
        </q-card>

        <!-- Log output -->
        <q-card flat bordered class="log-card q-mb-md">
          <q-card-section class="q-pb-xs row items-center">
            <div class="text-subtitle1 text-weight-medium col">Log</div>
            <q-badge v-if="running" color="primary" label="Running" class="q-mr-xs" />
            <q-btn v-if="logs.length && !running" flat dense round icon="delete_sweep" size="sm" @click="clearLog" />
          </q-card-section>
          <q-separator />
          <q-card-section class="log-section" ref="logEl">
            <div v-if="!logs.length" class="text-grey-5 text-caption">
              Select station list(s) and a date range, then click an action button.
            </div>
            <div
              v-for="(entry, i) in logs"
              :key="i"
              class="log-line"
              :class="entry.isError ? 'text-negative' : entry.isDone ? 'text-positive text-weight-medium' : ''"
            >{{ entry.text }}</div>
          </q-card-section>
        </q-card>

        <!-- Completed files -->
        <q-card v-if="completedFiles.length" flat bordered>
          <q-card-section class="q-pb-xs row items-center">
            <div class="text-subtitle1 text-weight-medium col">
              Completed files ({{ completedFiles.length }})
            </div>
          </q-card-section>
          <q-separator />
          <q-list dense>
            <q-item v-for="(f, i) in completedFiles" :key="i" dense>
              <q-item-section avatar>
                <q-icon name="insert_drive_file" color="positive" size="18px" />
              </q-item-section>
              <q-item-section>
                <q-item-label class="text-caption">{{ f.label }}</q-item-label>
                <q-item-label caption class="mono">{{ f.path }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card>

      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { usePpsdJob } from "../composables/usePpsdJob";
import type { PpsdMode } from "../types";

const {
  selectedLists, startDate, endDate, dateRange,
  filterCenters, filterSolutions, filterTypes,
  logs, running, done, exitCode,
  progressCurrent, progressTotal, completedFiles,
  getCancel, setCancel, clearCancel,
} = usePpsdJob();

// ── Constants ──────────────────────────────────────────────────────────────

const ALL_CENTERS = ["PB", "PW", "NC", "BK", "CI"];
const ALL_SOLUTIONS = [
  { v: "0", label: "CWU Fastlane"   },
  { v: "1", label: "Trimble PIVOT"  },
  { v: "2", label: "RTNet"          },
  { v: "3", label: "Septentrio"     },
  { v: "4", label: "RTX on-board"   },
  { v: "5", label: "Network"        },
  { v: "6", label: "JPL PPP"        },
];
const ALL_TYPES = [
  { v: "0", label: "PPP/AR FAST"       },
  { v: "1", label: "DIF/RTK"           },
  { v: "2", label: "PPP/AR COMPLETE"   },
  { v: "3", label: "PPP/AR FAST+COMPL."},
];

// ── State ──────────────────────────────────────────────────────────────────

const availableLists = ref<string[]>([]);
const logEl = ref<{ $el?: HTMLElement } | null>(null);

// ── Computed ───────────────────────────────────────────────────────────────

const listOptions = computed(() =>
  availableLists.value.map((l) => ({ label: l, value: l }))
);

const canRun = computed(
  () => selectedLists.value.length > 0
    && startDate.value.length === 10
    && endDate.value.length === 10
);

// ── Init ───────────────────────────────────────────────────────────────────

onMounted(async () => {
  try {
    const res = await fetch("/api/station-lists");
    const data = await res.json();
    availableLists.value = data.lists ?? [];
  } catch { /* ignore */ }
});

// ── Helpers ────────────────────────────────────────────────────────────────

function toggleItem(list: string[], item: string): void {
  const idx = list.indexOf(item);
  if (idx === -1) list.push(item);
  else list.splice(idx, 1);
}

function onRangeSelect(val: { from: string; to: string } | null) {
  if (!val) return;
  startDate.value = val.from;
  endDate.value = val.to;
}

function clearLog() {
  logs.value = [];
  done.value = false;
  exitCode.value = null;
  progressCurrent.value = 0;
  progressTotal.value = 0;
  completedFiles.value = [];
}

function cancelJob() {
  const cancel = getCancel();
  if (cancel) { cancel(); clearCancel(); }
  running.value = false;
  done.value = true;
  exitCode.value = 1;
  logs.value.push({ text: "Canceled by user.", isError: false, isDone: true });
}

async function scrollLog() {
  await nextTick();
  const el = logEl.value?.$el ?? (logEl.value as unknown as HTMLElement | null);
  if (el) el.scrollTop = el.scrollHeight;
}

async function runPpsd(mode: PpsdMode) {
  if (!canRun.value || running.value) return;
  logs.value = [];
  done.value = false;
  exitCode.value = null;
  progressCurrent.value = 0;
  progressTotal.value = 0;
  completedFiles.value = [];
  running.value = true;

  const params = new URLSearchParams();
  for (const l of selectedLists.value) params.append("lists", l);
  params.set("start", startDate.value);
  params.set("end", endDate.value);
  params.set("mode", mode);
  if (filterCenters.value.length)   params.set("centers",   filterCenters.value.join(","));
  if (filterSolutions.value.length) params.set("solutions", filterSolutions.value.join(","));
  if (filterTypes.value.length)     params.set("types",     filterTypes.value.join(","));

  const controller = new AbortController();
  setCancel(() => controller.abort());

  try {
    const resp = await fetch(`/api/ppsd/run?${params}`, { signal: controller.signal });
    if (!resp.body) throw new Error("No response body");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        try {
          const evt = JSON.parse(line.slice(5).trim());
          if (evt.type === "done") {
            exitCode.value = evt.code ?? 0;
            done.value = true;
            logs.value.push({ text: evt.msg ?? "Done.", isError: false, isDone: true });
          } else if (evt.type === "progress") {
            progressCurrent.value = evt.current ?? progressCurrent.value;
            progressTotal.value   = evt.total   ?? progressTotal.value;
            logs.value.push({ text: evt.msg ?? "", isError: false, isDone: false });
          } else if (evt.type === "file") {
            progressCurrent.value = evt.current ?? progressCurrent.value;
            progressTotal.value   = evt.total   ?? progressTotal.value;
            completedFiles.value.push({ path: evt.path ?? "", label: evt.label ?? "" });
          } else {
            logs.value.push({ text: evt.msg ?? "", isError: evt.type === "error", isDone: false });
          }
          await scrollLog();
        } catch { /* skip malformed SSE */ }
      }
    }
  } catch (err: unknown) {
    if ((err as Error).name !== "AbortError") {
      logs.value.push({ text: String(err), isError: true, isDone: false });
      done.value = true;
      exitCode.value = 1;
    }
  } finally {
    running.value = false;
    clearCancel();
  }
}
</script>

<style scoped>
.config-card {
  position: sticky;
  top: 16px;
}
.log-card {
  min-height: 200px;
}
.log-section {
  font-family: monospace;
  font-size: 0.78rem;
  max-height: 50vh;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-line {
  line-height: 1.5;
}
.mono {
  font-family: monospace;
  font-size: 0.75rem;
}
</style>

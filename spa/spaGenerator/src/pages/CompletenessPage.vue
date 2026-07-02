<template>
  <q-page class="q-pa-md">
    <PageHelp title="Completeness &amp; Latency">
      <p>Color-coded heatmap of data availability per station per time window.</p>
      <div class="help-section-label">Color scale</div>
      <ul>
        <li><strong>White</strong> — not yet attempted</li>
        <li><strong>Grey</strong> — fetch error (API unreachable or no data)</li>
        <li><strong>Red → Yellow → Green</strong> — 0 % → 50 % → 100 % completeness</li>
      </ul>
      <div class="help-section-label">Usage</div>
      <ul>
        <li>Select a station list and date range, then click <strong>Load</strong></li>
        <li>Results are paginated; use the arrows to step through stations</li>
        <li>Click <strong>Fetch Missing</strong> to download data for stations that have never been tried</li>
        <li>The <em>Latency</em> heatmap below shows ingest delay in seconds</li>
      </ul>
    </PageHelp>

    <!-- ── Controls ────────────────────────────────────────────────────── -->
    <div class="row items-end q-gutter-sm q-mb-sm">

      <!-- Station list -->
      <q-select
        v-model="selectedList"
        :options="listOptions"
        label="Station list"
        dense
        outlined
        emit-value
        map-options
        style="min-width: 180px"
        @update:model-value="onListChange"
      />

      <!-- Search within list -->
      <q-input
        v-model="searchText"
        label="Filter stations"
        dense
        outlined
        clearable
        style="min-width: 260px"
        placeholder="e.g. (*.PB.* | *.CI.*) & LY_"
        @blur="onSearchChange"
        @keyup.enter="onSearchChange"
        @clear="onSearchChange"
      >
        <template #prepend><q-icon name="search" size="xs" /></template>
      </q-input>

      <!-- Date range -->
      <q-input
        v-model="startDate"
        label="From"
        dense
        outlined
        style="width: 120px"
        mask="####-##-##"
        placeholder="YYYY-MM-DD"
        @change="onFromChange"
      />
      <q-input
        v-model="endDate"
        label="To"
        dense
        outlined
        style="width: 120px"
        mask="####-##-##"
        placeholder="YYYY-MM-DD"
        @change="onToChange"
      />
      <!-- Single range calendar picker -->
      <q-btn flat dense round icon="date_range" size="sm" class="self-center">
        <q-popup-proxy ref="calendarProxy" cover transition-show="scale" transition-hide="scale">
          <q-date
            v-model="dateRange"
            range
            mask="YYYY-MM-DD"
            @update:model-value="onRangeSelect"
          >
            <div class="row items-center justify-end">
              <q-btn v-close-popup label="Close" color="primary" flat />
            </div>
          </q-date>
        </q-popup-proxy>
      </q-btn>

      <!-- Quick-select windows -->
      <div class="row items-center q-gutter-xs">
        <q-btn
          v-for="w in TIME_WINDOWS"
          :key="w.label"
          :label="w.label"
          :color="activeWindow === w.label ? 'primary' : 'grey-5'"
          :flat="activeWindow !== w.label"
          :unelevated="activeWindow === w.label"
          dense
          size="sm"
          no-caps
          @click="applyWindow(w)"
        />
      </div>

      <!-- Batch size -->
      <q-select
        v-model="pageSize"
        :options="BATCH_OPTIONS"
        label="Batch"
        dense
        outlined
        emit-value
        map-options
        style="width: 90px"
        @update:model-value="page = 0; loadCompleteness()"
      />

      <!-- Refresh -->
      <q-btn icon="refresh" flat dense round :loading="loading" @click="loadCompleteness" />

      <!-- Fetch missing -->
      <q-btn
        label="Fetch Missing"
        icon="cloud_download"
        color="primary"
        dense
        outline
        no-caps
        size="sm"
        class="self-center"
        @click="openFetchDialog"
      />
    </div>

    <!-- ── Fetch Missing dialog ────────────────────────────────────────────── -->
    <q-dialog v-model="fetchOpen" persistent>
      <q-card style="min-width: 700px; max-width: 94vw; width: 800px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Fetch Missing Data</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="fetchRunning" />
        </q-card-section>

        <q-card-section class="q-pt-sm q-pb-xs">
          <div class="text-caption text-grey-7">
            {{ startDate }} → {{ endDate }}
            &nbsp;·&nbsp; Page {{ (data?.page ?? 0) + 1 }} ({{ pageGeosncls.length }} station{{ pageGeosncls.length !== 1 ? "s" : "" }})
          </div>
          <div class="text-caption text-grey-6 q-mt-xs">
            Only stations on the current page are checked. Stations with existing data or prior no-data records are skipped automatically.
          </div>
        </q-card-section>

        <q-card-section class="q-pt-xs" style="padding-bottom: 0">
          <div
            class="fetch-log q-pa-sm rounded-borders"
            style="background: #1a1a2e; font-family: monospace; font-size: 12px; line-height: 1.5; height: 55vh; overflow-y: auto"
            ref="fetchLogEl"
          >
            <div v-if="!fetchLog.length" style="color: #666">Ready. Press Fetch to start.</div>
            <div
              v-for="(line, i) in fetchLog"
              :key="i"
              :style="{ color: line.type === 'error' ? '#ef9a9a' : line.type === 'done' ? '#a5d6a7' : '#e0e0e0' }"
            >{{ line.msg }}</div>
          </div>
        </q-card-section>

        <q-card-actions align="right" class="q-pa-md">
          <q-select
            v-model="fetchWorkers"
            :options="[5, 10, 20, 30, 50]"
            label="Workers"
            dense
            outlined
            style="width: 90px"
            :disable="fetchRunning"
          />
          <q-btn
            v-if="!fetchRunning && !fetchDone"
            label="Fetch"
            color="primary"
            unelevated
            no-caps
            :disable="pageGeosncls.length === 0"
            @click="startFetch"
          />
          <q-btn
            v-if="fetchRunning"
            label="Cancel"
            color="negative"
            flat
            no-caps
            @click="cancelFetch"
          />
          <q-btn
            v-if="fetchDone"
            label="Fetch Again"
            color="primary"
            flat
            no-caps
            @click="fetchDone = false; fetchLog = []"
          />
          <q-btn
            v-if="fetchDone"
            label="Close"
            color="primary"
            unelevated
            no-caps
            v-close-popup
            @click="fetchLog = []; fetchDone = false"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Empty state ──────────────────────────────────────────────────── -->
    <div
      v-if="!data && !loading"
      class="flex flex-center text-grey-5 q-pa-xl"
      style="min-height: 200px"
    >
      <div class="text-center">
        <q-icon name="grid_on" size="48px" class="q-mb-sm" />
        <div>Select a date range above to view completeness data.</div>
      </div>
    </div>

    <!-- ── Loading ──────────────────────────────────────────────────────── -->
    <div v-else-if="loading" class="flex flex-center q-pa-xl">
      <q-spinner size="40px" color="primary" />
    </div>

    <!-- ── Heatmaps ─────────────────────────────────────────────────────── -->
    <template v-else-if="data">

      <!-- Meta line + top pagination -->
      <div class="row items-center q-gutter-sm q-mb-xs flex-wrap">
        <span class="text-caption text-grey-6">
          Showing {{ data.stations.length }} of {{ data.total }} station(s) ·
          {{ data.bucketStarts.length }} × {{ binLabel }} bins
          ({{ spanLabel }})
        </span>
        <div class="row items-center" style="gap: 2px">
          <template v-for="(p, i) in pageStrip" :key="i">
            <span v-if="p === '…'" class="text-caption text-grey-5 q-px-xs">…</span>
            <q-btn
              v-else
              :label="String(p)"
              flat
              dense
              no-caps
              size="sm"
              :color="p === data.page + 1 ? 'primary' : 'grey-7'"
              :class="p === data.page + 1 ? 'text-weight-bold' : ''"
              style="min-width: 28px"
              @click="goToPage(Number(p) - 1)"
            />
          </template>
        </div>
      </div>

      <!-- Completeness heatmap -->
      <div class="text-subtitle2 q-mb-xs q-mt-sm">Completeness</div>
      <HeatmapGrid
        :stations="data.stations"
        :bucket-starts="data.bucketStarts"
        :color-fn="completenessColor"
        :tooltip-fn="completenessTooltip"
      />
      <div class="row items-center q-gutter-md q-mt-xs q-mb-sm">
        <div
          v-for="l in COMPLETENESS_LEGEND"
          :key="l.label"
          class="row items-center q-gutter-xs"
        >
          <div
            class="legend-swatch"
            :style="{ background: l.color, borderColor: l.border ? '#bdbdbd' : undefined }"
          />
          <span class="text-caption">{{ l.label }}</span>
        </div>
      </div>

      <!-- Latency heatmap -->
      <div class="text-subtitle2 q-mb-xs q-mt-sm">Ingest Latency</div>
      <HeatmapGrid
        :stations="data.stations"
        :bucket-starts="data.bucketStarts"
        :color-fn="latencyColor"
        :tooltip-fn="latencyTooltip"
      />
      <div class="row items-center q-gutter-md q-mt-xs">
        <div
          v-for="l in LATENCY_LEGEND"
          :key="l.label"
          class="row items-center q-gutter-xs"
        >
          <div
            class="legend-swatch"
            :style="{ background: l.color, borderColor: l.border ? '#bdbdbd' : undefined }"
          />
          <span class="text-caption">{{ l.label }}</span>
        </div>
        <span class="text-caption text-grey-6">(linear: 0 – 1.5 – 5 s)</span>
      </div>

      <!-- Bottom pagination -->
      <div class="row items-center justify-center q-mt-md" style="gap: 3px">
        <template v-for="(p, i) in pageStrip" :key="i">
          <span v-if="p === '…'" class="text-caption text-grey-5 q-px-xs">…</span>
          <q-btn
            v-else
            :label="String(p)"
            :unelevated="p === data.page + 1"
            :flat="p !== data.page + 1"
            dense
            no-caps
            :color="p === data.page + 1 ? 'primary' : 'grey-7'"
            :class="p === data.page + 1 ? 'text-weight-bold' : ''"
            style="min-width: 32px"
            @click="goToPage(Number(p) - 1)"
          />
        </template>
      </div>
    </template>

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import HeatmapGrid from "../components/HeatmapGrid.vue";
import { getStationLists, getCompleteness, openFetchMissingStream } from "../api";
import type { CompletenessResponse, BucketData, FetchEvent } from "../types";
import { useSharedControls } from "../composables/useSharedControls";

// ─── Constants ────────────────────────────────────────────────────────────────

const TIME_WINDOWS = [
  { label: "24h",  hours: 24  },
  { label: "3d",   hours: 72  },
  { label: "7d",   hours: 168 },
  { label: "30d",  hours: 720 },
  { label: "90d",  hours: 2160},
] as const;

const BATCH_OPTIONS = [
  { label: "10",  value: 10  },
  { label: "25",  value: 25  },
  { label: "50",  value: 50  },
  { label: "100", value: 100 },
  { label: "200", value: 200 },
];

const COMPLETENESS_LEGEND = [
  { label: "Not tried",    color: "#ffffff",           border: true },
  { label: "Fetch error",  color: "#9e9e9e",           border: false },
  { label: "0%",           color: "hsl(0,100%,50%)"   },
  { label: "50%",          color: "hsl(60,100%,60%)"  },
  { label: "100%",         color: "hsl(120,100%,30%)" },
];

// Linear piecewise: 0 s → green, 1.5 s → yellow, 5 s → red
const LATENCY_LEGEND = [
  { label: "Not tried", color: "#ffffff", border: true },
  { label: "No data",   color: "#616161" },
  { label: "0 s",       color: "hsl(120,100%,30%)" },
  { label: "1.5 s",     color: "hsl(60,100%,60%)"  },
  { label: "≥ 5 s",    color: "hsl(0,100%,50%)"   },
];

// ─── State ────────────────────────────────────────────────────────────────────

const loading = ref(false);

// Station list dropdown
const listOptions = ref<{ label: string; value: string }[]>([]);
const { selectedList, searchText, startDate, endDate, activeWindow, rangeDays, dateRange } = useSharedControls();

// Pagination
const page = ref(0);
const pageSize = ref(25);

// Completeness response (declared here so pageGeosncls computed can reference it)
const data = ref<CompletenessResponse | null>(null);

// ─── Fetch Missing dialog ─────────────────────────────────────────────────────

const fetchOpen = ref(false);
const fetchRunning = ref(false);
const fetchDone = ref(false);
const fetchWorkers = ref(10);
const fetchLog = ref<FetchEvent[]>([]);
const fetchLogEl = ref<HTMLElement | null>(null);
let _cancelFetch: (() => void) | null = null;

const pageGeosncls = computed<string[]>(
  () => data.value?.stations.map((s) => s.geosncl) ?? []
);

function openFetchDialog() {
  fetchLog.value = [];
  fetchDone.value = false;
  fetchRunning.value = false;
  fetchOpen.value = true;
}

function cancelFetch() {
  if (_cancelFetch) {
    _cancelFetch();
    _cancelFetch = null;
  }
  fetchRunning.value = false;
  fetchDone.value = true;
  fetchLog.value.push({ type: "done", msg: "Canceled by user.", code: 1 });
}

function startFetch() {
  fetchRunning.value = true;
  fetchDone.value = false;
  fetchLog.value = [];
  _cancelFetch = openFetchMissingStream(
    {
      start: startDate.value,
      end: endDate.value,
      workers: fetchWorkers.value,
      geosncls: pageGeosncls.value,
    },
    async (evt) => {
      fetchLog.value.push(evt);
      await nextTick();
      if (fetchLogEl.value) fetchLogEl.value.scrollTop = fetchLogEl.value.scrollHeight;
      if (evt.type === "done") {
        fetchRunning.value = false;
        fetchDone.value = true;
        _cancelFetch = null;
        loadCompleteness();
      }
    },
  );
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadListOptions();
  if (!startDate.value) {
    applyWindow(TIME_WINDOWS.find((w) => w.label === "7d")!);
  } else {
    loadCompleteness();
  }
});

// ─── Station lists ────────────────────────────────────────────────────────────

async function loadListOptions() {
  try {
    const resp = await getStationLists();
    listOptions.value = [
      { label: "All", value: "all" },
      ...resp.lists.map((l) => ({ label: l, value: l })),
    ];
  } catch (e) {
    console.error("Failed to load station lists", e);
    listOptions.value = [{ label: "All", value: "all" }];
  }
}

function onListChange() {
  page.value = 0;
  loadCompleteness();
}

function onSearchChange() {
  page.value = 0;
  loadCompleteness();
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

function dateStr(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function parseDateStr(s: string): Date | null {
  const d = new Date(s + "T00:00:00Z");
  return isNaN(d.getTime()) ? null : d;
}

function _syncRange() {
  if (startDate.value && endDate.value) {
    dateRange.value = { from: startDate.value, to: endDate.value };
  }
}

function onFromChange() {
  const from = parseDateStr(startDate.value);
  if (from) {
    const to = new Date(from.getTime() + rangeDays.value * 86_400_000);
    endDate.value = dateStr(to);
  }
  _syncRange();
  activeWindow.value = null;
  page.value = 0;
  loadCompleteness();
}

function onToChange() {
  const from = parseDateStr(startDate.value);
  const to = parseDateStr(endDate.value);
  if (from && to && to > from) {
    rangeDays.value = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  }
  _syncRange();
  activeWindow.value = null;
  page.value = 0;
  loadCompleteness();
}

function onRangeSelect(val: { from: string; to: string } | null) {
  // val is null while the user is mid-drag (only from selected, not to yet)
  if (!val?.from || !val?.to) return;
  startDate.value = val.from;
  endDate.value = val.to;
  const from = parseDateStr(val.from);
  const to = parseDateStr(val.to);
  if (from && to && to > from) {
    rangeDays.value = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  }
  activeWindow.value = null;
  page.value = 0;
  loadCompleteness();
}

function applyWindow(w: { label: string; hours: number }) {
  const end = new Date();
  const start = new Date(end.getTime() - w.hours * 3_600_000);
  startDate.value = dateStr(start);
  endDate.value = dateStr(end);
  rangeDays.value = Math.round(w.hours / 24);
  _syncRange();
  activeWindow.value = w.label;
  page.value = 0;
  loadCompleteness();
}

// ─── Completeness load ────────────────────────────────────────────────────────

async function loadCompleteness() {
  if (!startDate.value || !endDate.value) return;
  loading.value = true;
  try {
    data.value = await getCompleteness({
      list: selectedList.value,
      search: searchText.value || "",
      start: startDate.value,
      end: endDate.value,
      page: page.value,
      size: pageSize.value,
    });
  } catch (e) {
    console.error("Failed to load completeness", e);
  } finally {
    loading.value = false;
  }
}

function goToPage(p: number) {
  if (!data.value) return;
  const clamped = Math.max(0, Math.min(p, data.value.totalPages - 1));
  if (clamped === page.value) return;
  page.value = clamped;
  loadCompleteness();
}

// ─── Display computed ─────────────────────────────────────────────────────────

const pageStrip = computed((): (number | "…")[] => {
  const total = data.value?.totalPages ?? 1;
  const cur = (data.value?.page ?? 0) + 1; // 1-indexed
  if (total <= 10) return Array.from({ length: total }, (_, i) => i + 1);

  const shown = new Set<number>([1, total]);
  for (let p = Math.max(1, cur - 2); p <= Math.min(total, cur + 2); p++) {
    shown.add(p);
  }
  const sorted = Array.from(shown).sort((a, b) => a - b);
  const result: (number | "…")[] = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) result.push("…");
    result.push(sorted[i]);
  }
  return result;
});

const binLabel = computed(() => {
  const m = data.value?.binMinutes ?? 15;
  if (m < 60)   return `${m}-min`;
  if (m < 1440) return `${m / 60}-hour`;
  return `${m / 1440}-day`;
});

const spanLabel = computed(() => {
  const d = data.value;
  if (!d || d.bucketStarts.length < 2) return "";
  const spanDays =
    (d.bucketStarts[d.bucketStarts.length - 1] - d.bucketStarts[0]) / 86_400_000;
  return spanDays < 2
    ? `${(spanDays * 24).toFixed(0)} h`
    : `${Math.round(spanDays)} d`;
});

// ─── Color functions ──────────────────────────────────────────────────────────

// Shared ntrip HSL scheme: 0→red, 0.5→yellow, 1→green
function _scoreColor(score: number): string {
  const hue = Math.round(score * 120);
  const lightness =
    score <= 0.5
      ? Math.round(50 + score * 20)
      : Math.round(60 - (score - 0.5) * 60);
  return `hsl(${hue}, 100%, ${lightness}%)`;
}

function completenessColor(bucket: BucketData): string {
  switch (bucket.state) {
    case "not-tried": return "#ffffff";
    case "no-data":   return _scoreColor(0);
    case "error":     return "#9e9e9e";
    case "has-data":  return _scoreColor(Math.min(1, Math.max(0, bucket.completeness ?? 0)));
    default:          return "#eeeeee";
  }
}

// Piecewise linear: 0 s → score 1 (green), 1.5 s → score 0.5 (yellow), 5 s → score 0 (red)
function _latencyScore(latS: number): number {
  if (latS <= 0)    return 1;
  if (latS <= 1.5)  return 1 - latS / 3;              // 1.0 → 0.5
  if (latS <= 5)    return 0.5 * (5 - latS) / 3.5;    // 0.5 → 0.0
  return 0;
}

function latencyColor(bucket: BucketData): string {
  switch (bucket.state) {
    case "not-tried": return "#ffffff";
    case "no-data":   return "#616161";
    case "error":     return "#9e9e9e";
    case "has-data":  return _scoreColor(_latencyScore(bucket.meanIngestLatencyS ?? 0));
    default:          return "#eeeeee";
  }
}

// ─── Tooltip functions ────────────────────────────────────────────────────────

function isoLabel(epochMs: number): string {
  return new Date(epochMs).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

function completenessTooltip(geosncl: string, bucket: BucketData): string {
  const lines = [geosncl, isoLabel(bucket.bucketStartMs)];
  switch (bucket.state) {
    case "not-tried": lines.push("Not yet attempted"); break;
    case "no-data":   lines.push("No data returned by API"); break;
    case "error":     lines.push("Fetch attempted — API returned an error (400/422)"); break;
    case "has-data": {
      const pct = ((bucket.completeness ?? 0) * 100).toFixed(1);
      lines.push(`Completeness: ${pct}% (${bucket.rowCount} / ${bucket.expectedCount} samples)`);
      if (bucket.meanIngestLatencyS != null)
        lines.push(`Ingest latency: ${bucket.meanIngestLatencyS.toFixed(2)} s`);
      if (bucket.meanProcessingDelayS != null)
        lines.push(`Processing delay: ${bucket.meanProcessingDelayS.toFixed(3)} s`);
    }
  }
  return lines.join("\n");
}

function latencyTooltip(geosncl: string, bucket: BucketData): string {
  const lines = [geosncl, isoLabel(bucket.bucketStartMs)];
  switch (bucket.state) {
    case "not-tried": lines.push("Not yet attempted"); break;
    case "no-data":   lines.push("No data returned by API"); break;
    case "error":     lines.push("Fetch attempted — API returned an error (400/422)"); break;
    case "has-data": {
      if (bucket.meanIngestLatencyS != null)
        lines.push(`Ingest latency: ${bucket.meanIngestLatencyS.toFixed(2)} s`);
      else
        lines.push("Ingest latency: N/A");
      if (bucket.meanProcessingDelayS != null)
        lines.push(`Processing delay: ${bucket.meanProcessingDelayS.toFixed(3)} s`);
      const pct = ((bucket.completeness ?? 0) * 100).toFixed(1);
      lines.push(`Completeness: ${pct}%`);
    }
  }
  return lines.join("\n");
}
</script>

<style scoped>
.legend-swatch {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  border: 1px solid #ccc;
  display: inline-block;
  flex-shrink: 0;
}
</style>

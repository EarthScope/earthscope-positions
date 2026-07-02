<template>
  <q-page class="q-pa-md column no-wrap" style="height: calc(100vh - 50px)">

    <!-- ── Controls ─────────────────────────────────────────────────────── -->
    <div class="row items-center q-gutter-sm q-mb-xs flex-shrink-0">
      <q-select
        v-model="selectedList"
        :options="listOptions"
        label="Station list"
        dense outlined emit-value map-options
        style="min-width: 180px"
        @update:model-value="reloadStations"
      />
      <q-input
        v-model="searchText"
        label="Filter stations"
        dense outlined clearable
        style="min-width: 220px"
        placeholder="e.g. (*.PB.* | *.CI.*) & LY_"
        @blur="reloadStations"
        @keyup.enter="reloadStations"
        @clear="reloadStations"
      >
        <template #prepend><q-icon name="search" size="xs" /></template>
      </q-input>
      <q-input v-model="startDate" label="From" dense outlined style="width: 120px"
        mask="####-##-##" placeholder="YYYY-MM-DD" @change="onFromChange" />
      <q-input v-model="endDate" label="To" dense outlined style="width: 120px"
        mask="####-##-##" placeholder="YYYY-MM-DD" @change="onToChange" />
      <q-btn flat dense round icon="date_range" size="sm" class="self-center">
        <q-popup-proxy cover transition-show="scale" transition-hide="scale">
          <q-date v-model="dateRange" range mask="YYYY-MM-DD" @update:model-value="onRangeSelect">
            <div class="row items-center justify-end">
              <q-btn v-close-popup label="Close" color="primary" flat />
            </div>
          </q-date>
        </q-popup-proxy>
      </q-btn>
      <div class="row items-center q-gutter-xs">
        <q-btn v-for="w in TIME_WINDOWS" :key="w.label" :label="w.label"
          :color="activeWindow === w.label ? 'primary' : 'grey-5'"
          :flat="activeWindow !== w.label" :unelevated="activeWindow === w.label"
          dense size="sm" no-caps @click="applyWindow(w)" />
      </div>
      <q-checkbox v-model="downsampleEnabled" label="Downsample" dense size="sm" />
      <q-btn label="Fetch Missing" icon="cloud_download" color="primary" dense outline no-caps
        size="sm" class="self-center" @click="openFetchDialog" />
    </div>

    <!-- ── Selection controls ────────────────────────────────────────────── -->
    <div class="row items-center q-gutter-sm q-mb-xs flex-shrink-0">
      <q-btn label="Clear"            dense flat no-caps size="sm" icon="clear_all"   @click="clearSelection" />
      <q-btn label="Select All"       dense flat no-caps size="sm" icon="select_all"  @click="selectAll" />
      <q-btn label="Save Selection"   dense flat no-caps size="sm" icon="save"
        :disable="selected.size === 0" @click="openSaveDialog" />
      <q-checkbox v-model="removeMean" label="Remove mean" dense size="sm" />
      <q-input v-model.number="outlierThreshold" label="Outlier (m)" type="number"
        dense outlined style="width: 95px" :min="0.01" :step="0.5" />
      <span class="text-caption text-grey-6 self-center">
        · Shift+click to add · Shift+drag to zoom · right-click to reset zoom · Shift+click line to deselect
      </span>
      <q-space />
      <span class="text-caption text-grey-6 self-center">
        {{ selected.size }} stream{{ selected.size === 1 ? "" : "s" }} selected
        <span v-if="positionsLoading"> · loading…</span>
        <span v-else-if="selected.size > 0">
          · {{ totalPointsLoaded.toLocaleString() }} pts
          <span v-if="anyDownsampled">(downsampled)</span>
        </span>
      </span>
    </div>

    <!-- ── Main split ────────────────────────────────────────────────────── -->
    <div class="row col no-wrap" style="min-height: 0">

      <!-- Station tree -->
      <div
        class="tree-panel q-pr-sm"
        style="width: 260px; min-width: 200px; overflow-y: auto; flex-shrink: 0"
        tabindex="0"
        @keydown="onTreeKeydown"
      >
        <div v-if="stationsLoading" class="flex flex-center q-pa-md">
          <q-spinner size="24px" color="primary" />
        </div>
        <template v-else>
          <div
            v-for="item in flatItems"
            :key="item.key"
            class="tree-row"
            :class="{ 'tree-focused': item.key === focusedKey }"
          >
            <div v-if="item.type === 'group'" class="row items-center no-wrap tree-item"
              @click.stop="onItemClick(item, $event)">
              <q-btn flat dense round
                :icon="expandedSet.has(item.id) ? 'expand_more' : 'chevron_right'"
                size="xs" color="grey-7" @click.stop="toggleExpand(item.id)" />
              <q-checkbox :model-value="groupCheckState(item.id)" dense size="sm"
                @update:model-value="onGroupCheck(item.id, $event)" @click.stop />
              <span class="tree-label text-weight-medium" style="font-size:12px">
                {{ item.id }}
                <span class="text-grey-6 text-caption">({{ item.children.length }})</span>
              </span>
            </div>
            <div v-else class="row items-center no-wrap tree-item tree-child"
              @click.stop="onItemClick(item, $event)">
              <q-checkbox :model-value="selected.has(item.geosncl)" dense size="sm"
                @update:model-value="onStationCheck(item.geosncl, $event)" @click.stop />
              <span class="tree-label" style="font-size:11px; font-family: monospace">
                {{ item.geosncl }}
              </span>
            </div>
          </div>
        </template>
      </div>

      <!-- Charts -->
      <div class="col column no-wrap q-pl-sm" style="min-width: 0; overflow-y: auto">
        <div v-if="selected.size === 0" class="flex flex-center text-grey-5" style="height: 100%">
          <div class="text-center">
            <q-icon name="show_chart" size="48px" class="q-mb-sm" />
            <div>Select stations on the left to plot positions.</div>
          </div>
        </div>
        <template v-else>
          <div v-if="noDataForRange" class="flex flex-center text-grey-6" style="min-height:80px">
            <div class="text-center">
              <q-icon name="event_busy" size="32px" class="q-mb-xs" />
              <div class="text-caption">No data for <b>{{ startDate }}</b> → <b>{{ endDate }}</b>. Adjust the date range.</div>
            </div>
          </div>
          <!-- Position time-series -->
          <div v-for="comp in COMPONENTS" :key="comp.key" class="chart-block q-mb-sm">
            <div class="text-caption text-grey-7 q-mb-xs">{{ comp.label }}</div>
            <canvas :ref="el => setCanvas(comp.key, el)" class="chart-canvas" />
          </div>

          <!-- Power spectra -->
          <div class="text-subtitle2 text-grey-8 q-mt-md q-mb-xs">Power Spectra</div>
          <div v-for="comp in COMPONENTS" :key="'s_' + comp.key" class="chart-block q-mb-sm">
            <div class="text-caption text-grey-7 q-mb-xs">{{ comp.specLabel }}</div>
            <canvas :ref="el => setSpecCanvas(comp.key, el)" class="chart-canvas" />
          </div>
        </template>
      </div>
    </div>

    <!-- ── Fetch Missing dialog ──────────────────────────────────────────── -->
    <q-dialog v-model="fetchOpen" persistent>
      <q-card style="min-width: 620px; max-width: 90vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Fetch Missing Data</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="fetchRunning" />
        </q-card-section>
        <q-card-section class="q-pt-sm">
          <div class="text-caption text-grey-7">
            List: <b>{{ selectedList === "all" ? "All (select a specific list)" : selectedList }}</b>
            &nbsp;·&nbsp; {{ startDate }} → {{ endDate }}
          </div>
          <div v-if="selectedList === 'all'" class="text-warning q-mt-xs text-caption">
            ⚠ Select a specific station list before fetching.
          </div>
        </q-card-section>
        <q-card-section v-if="fetchLog.length" style="max-height: 42vh; overflow-y: auto" class="q-pt-none">
          <div class="q-pa-sm rounded-borders"
            style="background:#1a1a2e; font-family:monospace; font-size:12px; line-height:1.5"
            ref="fetchLogEl">
            <div v-for="(line, i) in fetchLog" :key="i"
              :style="{ color: line.type==='error' ? '#ef9a9a' : line.type==='done' ? '#a5d6a7' : '#e0e0e0' }">
              {{ line.msg }}
            </div>
          </div>
        </q-card-section>
        <q-card-actions align="right" class="q-pa-md">
          <q-select v-model="fetchWorkers" :options="[5,10,20,30,50]" label="Workers"
            dense outlined style="width:90px" />
          <q-btn v-if="!fetchRunning && !fetchDone" label="Fetch" color="primary" unelevated no-caps
            :disable="selectedList === 'all'" @click="startFetch" />
          <q-btn v-if="fetchDone" label="Close" color="primary" flat no-caps v-close-popup
            @click="fetchLog = []; fetchDone = false" />
          <q-btn v-if="fetchRunning" label="Running…" flat no-caps disable />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Save Selection dialog ────────────────────────────────────────── -->
    <q-dialog v-model="saveOpen" persistent>
      <q-card style="min-width: 400px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Save Station List</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="saveRunning" />
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">{{ selected.size }} stream(s) will be saved.</div>
          <q-input v-model="saveListName" label="List name" dense outlined autofocus
            :error="!!saveError" :error-message="saveError"
            placeholder="e.g. my-stations"
            @keyup.enter="doSave"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pa-md">
          <q-btn label="Cancel" flat no-caps v-close-popup :disable="saveRunning" />
          <q-btn label="Save" color="primary" unelevated no-caps
            :loading="saveRunning" :disable="!saveListName.trim()"
            @click="doSave" />
        </q-card-actions>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { Chart, registerables } from "chart.js";
import { getStationLists, getStations, getPositions, getDataRange, openFetchMissingStream, saveStationList } from "../api";
import type { PositionTrace, FetchEvent } from "../types";
import { useSharedControls } from "../composables/useSharedControls";

Chart.register(...registerables);

// ─── Constants ────────────────────────────────────────────────────────────────

const TIME_WINDOWS = [
  { label: "24h",  hours: 24   },
  { label: "3d",   hours: 72   },
  { label: "7d",   hours: 168  },
  { label: "30d",  hours: 720  },
  { label: "90d",  hours: 2160 },
] as const;

const COMPONENTS = [
  { key: "east",  label: "East (mm)",  specLabel: "East PSD (mm²)"  },
  { key: "north", label: "North (mm)", specLabel: "North PSD (mm²)" },
  { key: "up",    label: "Up (mm)",    specLabel: "Up PSD (mm²)"    },
] as const;

const COLORS = [
  "#1565C0","#2E7D32","#C62828","#F57F17","#6A1B9A",
  "#00838F","#AD1457","#4E342E","#37474F","#558B2F",
  "#0288D1","#388E3C","#E53935","#FB8C00","#8E24AA",
  "#00ACC1","#D81B60","#6D4C41","#546E7A","#689F38",
];

// ─── State ────────────────────────────────────────────────────────────────────

const listOptions = ref<{ label: string; value: string }[]>([]);
const { selectedList, searchText, startDate, endDate, dateRange, rangeDays, activeWindow } = useSharedControls();
const stationsLoading = ref(false);

const downsampleEnabled  = ref(true);
const removeMean         = ref(false);
const outlierThreshold   = ref(5); // metres

type TreeGroup   = { type: "group";   key: string; id: string; children: string[] };
type TreeStation = { type: "station"; key: string; geosncl: string; groupId: string };
type TreeItem    = TreeGroup | TreeStation;

const stationGroups = ref<Map<string, string[]>>(new Map());
const expandedSet   = ref<Set<string>>(new Set());
const selected      = ref<Set<string>>(new Set());
const focusedKey    = ref<string | null>(null);

const positionCache    = ref<Map<string, PositionTrace>>(new Map());
const positionsLoading = ref(false);

// ── Chart objects (plain, not reactive – Vue proxy breaks Chart.js) ──────────
const _canvas:     Record<string, HTMLCanvasElement | null> = { east: null, north: null, up: null };
const _chart:      Record<string, Chart | null>             = { east: null, north: null, up: null };
const _specCanvas: Record<string, HTMLCanvasElement | null> = { east: null, north: null, up: null };
const _specChart:  Record<string, Chart | null>             = { east: null, north: null, up: null };

// Cleanup functions for canvas event listeners
const _canvasCleanup:     Record<string, (() => void) | null> = { east: null, north: null, up: null };
const _specCanvasCleanup: Record<string, (() => void) | null> = { east: null, north: null, up: null };

// ── Zoom state (reactive, watched to sync charts) ───────────────────────────
const _posZoom  = ref<{ min: number; max: number } | null>(null);
const _specZoom = ref<{ min: number; max: number } | null>(null);

// ── Interaction state (plain, not reactive – updated on every mouse event) ───
const _posDragState  = { active: false, chartKey: "", startPx: 0, currentPx: 0 };
const _specDragState = { active: false, chartKey: "", startPx: 0, currentPx: 0 };
const _crosshair     = { posX: null as number | null, specX: null as number | null };

// ── Save Selection dialog ────────────────────────────────────────────────────
const saveOpen     = ref(false);
const saveRunning  = ref(false);
const saveListName = ref("");
const saveError    = ref("");

function openSaveDialog() {
  saveListName.value = "";
  saveError.value    = "";
  saveRunning.value  = false;
  saveOpen.value     = true;
}

async function doSave() {
  const name = saveListName.value.trim();
  if (!name) { saveError.value = "Name is required."; return; }
  if (/[/\\.]\./.test(name)) { saveError.value = "Invalid characters in name."; return; }
  saveError.value   = "";
  saveRunning.value = true;
  try {
    await saveStationList(name, [...selected.value]);
    // Refresh list options, keeping current selection
    const currentList = selectedList.value;
    await loadListOptions();
    selectedList.value = currentList;
    saveOpen.value = false;
  } catch (e: any) {
    saveError.value = e?.response?.data?.error ?? "Failed to save.";
  } finally {
    saveRunning.value = false;
  }
}

// ── Fetch dialog ─────────────────────────────────────────────────────────────
const fetchOpen    = ref(false);
const fetchRunning = ref(false);
const fetchDone    = ref(false);
const fetchWorkers = ref(10);
const fetchLog     = ref<FetchEvent[]>([]);
const fetchLogEl   = ref<HTMLElement | null>(null);

let loadTimer: ReturnType<typeof setTimeout> | null = null;

// ─── Computed ─────────────────────────────────────────────────────────────────

const flatItems = computed((): TreeItem[] => {
  const items: TreeItem[] = [];
  for (const [id, children] of stationGroups.value) {
    items.push({ type: "group", key: id, id, children });
    if (expandedSet.value.has(id))
      for (const g of children) items.push({ type: "station", key: g, geosncl: g, groupId: id });
  }
  return items;
});

const totalPointsLoaded = computed(() => {
  let n = 0;
  for (const g of selected.value) n += positionCache.value.get(g)?.times.length ?? 0;
  return n;
});

const anyDownsampled = computed(() =>
  [...selected.value].some(g => (positionCache.value.get(g)?.downsampleFactor ?? 1) > 1)
);

const noDataForRange = computed(() =>
  !positionsLoading.value &&
  selected.value.size > 0 &&
  [...selected.value].every(g => {
    const t = positionCache.value.get(g);
    return t !== undefined && t.times.length === 0;
  })
);

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadListOptions();
  if (!startDate.value) {
    try {
      const range = await getDataRange();
      if (range.max) {
        // Default to the last 7 days of available data, not today
        const maxDate = new Date(range.max + "T12:00:00Z");
        const minDate = new Date(maxDate.getTime() - 7 * 86_400_000);
        endDate.value   = range.max;
        startDate.value = dateStr(minDate);
        rangeDays.value = 7;
        activeWindow.value = "7d";
        _syncRange();
      } else {
        applyWindow(TIME_WINDOWS.find(w => w.label === "7d")!);
      }
    } catch {
      applyWindow(TIME_WINDOWS.find(w => w.label === "7d")!);
    }
  }
  await reloadStations();
});

onBeforeUnmount(() => {
  [...Object.values(_chart), ...Object.values(_specChart)].forEach(c => c?.destroy());
  [...Object.values(_canvasCleanup), ...Object.values(_specCanvasCleanup)].forEach(fn => fn?.());
});

// ─── Station lists ────────────────────────────────────────────────────────────

async function loadListOptions() {
  try {
    const r = await getStationLists();
    listOptions.value = [{ label: "All", value: "all" }, ...r.lists.map(l => ({ label: l, value: l }))];
  } catch { listOptions.value = [{ label: "All", value: "all" }]; }
}

async function reloadStations() {
  stationsLoading.value = true;
  try {
    const r = await getStations({ list: selectedList.value, search: searchText.value || undefined });
    const groups = new Map<string, string[]>();
    for (const { geosncl } of r.stations) {
      const id = geosncl.split(".")[0];
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id)!.push(geosncl);
    }
    stationGroups.value = groups;
  } catch (e) { console.error(e); }
  finally { stationsLoading.value = false; }
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

function dateStr(d: Date) { return d.toISOString().slice(0, 10); }
function parseDateStr(s: string) {
  const d = new Date(s + "T00:00:00Z"); return isNaN(d.getTime()) ? null : d;
}
function _syncRange() {
  if (startDate.value && endDate.value) dateRange.value = { from: startDate.value, to: endDate.value };
}

function applyWindow(w: { label: string; hours: number }) {
  const end = new Date(), start = new Date(end.getTime() - w.hours * 3_600_000);
  startDate.value = dateStr(start); endDate.value = dateStr(end);
  rangeDays.value = Math.round(w.hours / 24); _syncRange();
  activeWindow.value = w.label;
  positionCache.value.clear(); scheduleLoad();
}
function onFromChange() {
  const from = parseDateStr(startDate.value);
  if (from) endDate.value = dateStr(new Date(from.getTime() + rangeDays.value * 86_400_000));
  _syncRange(); activeWindow.value = null; positionCache.value.clear(); scheduleLoad();
}
function onToChange() {
  const from = parseDateStr(startDate.value), to = parseDateStr(endDate.value);
  if (from && to && to > from) rangeDays.value = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  _syncRange(); activeWindow.value = null; positionCache.value.clear(); scheduleLoad();
}
function onRangeSelect(val: { from: string; to: string } | null) {
  if (!val?.from || !val?.to) return;
  startDate.value = val.from; endDate.value = val.to;
  const from = parseDateStr(val.from), to = parseDateStr(val.to);
  if (from && to && to > from) rangeDays.value = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  activeWindow.value = null; positionCache.value.clear(); scheduleLoad();
}

// ─── Tree interaction ─────────────────────────────────────────────────────────

function toggleExpand(id: string) {
  const s = new Set(expandedSet.value); s.has(id) ? s.delete(id) : s.add(id); expandedSet.value = s;
}
function groupCheckState(id: string): boolean | null {
  const ch = stationGroups.value.get(id) ?? [];
  const n = ch.filter(g => selected.value.has(g)).length;
  return n === 0 ? false : n === ch.length ? true : null;
}
function _setSelected(next: Set<string>) { selected.value = next; scheduleLoad(); }

function onGroupCheck(id: string, checked: boolean) {
  const ch = stationGroups.value.get(id) ?? [], next = new Set(selected.value);
  if (checked) ch.forEach(g => next.add(g)); else ch.forEach(g => next.delete(g));
  _setSelected(next);
}
function onStationCheck(geosncl: string, checked: boolean) {
  const next = new Set(selected.value);
  checked ? next.add(geosncl) : next.delete(geosncl);
  _setSelected(next);
}
function onItemClick(item: TreeItem, event: MouseEvent) {
  focusedKey.value = item.key;
  const adding = event.shiftKey;
  const next = new Set(adding ? selected.value : new Set<string>());
  if (item.type === "group") {
    const ch = stationGroups.value.get(item.id) ?? [];
    const allSel = ch.every(g => selected.value.has(g));
    if (adding && allSel) ch.forEach(g => next.delete(g)); else ch.forEach(g => next.add(g));
  } else {
    if (adding && selected.value.has(item.geosncl)) next.delete(item.geosncl);
    else next.add(item.geosncl);
  }
  _setSelected(next);
}
function clearSelection() { _setSelected(new Set()); }
function selectAll() {
  const all = new Set<string>();
  for (const ch of stationGroups.value.values()) ch.forEach(g => all.add(g));
  _setSelected(all);
}
function onTreeKeydown(e: KeyboardEvent) {
  const items = flatItems.value; if (!items.length) return;
  const idx = items.findIndex(i => i.key === focusedKey.value);
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const next = e.key === "ArrowDown" ? Math.min(items.length - 1, idx < 0 ? 0 : idx + 1)
                                     : Math.max(0, idx < 0 ? 0 : idx - 1);
  const item = items[next]; focusedKey.value = item.key;
  const nextSel = new Set(e.shiftKey ? selected.value : new Set<string>());
  if (item.type === "group") (stationGroups.value.get(item.id) ?? []).forEach(g => nextSel.add(g));
  else nextSel.add(item.geosncl);
  _setSelected(nextSel);
}

// ─── Canvas management ────────────────────────────────────────────────────────

function setCanvas(key: string, el: unknown) {
  const canvas = el as HTMLCanvasElement | null;
  if (!canvas) {
    _chart[key]?.destroy(); _chart[key] = null;
    _canvasCleanup[key]?.(); _canvasCleanup[key] = null;
  } else {
    _canvas[key] = canvas;
    _canvasCleanup[key] = _attachListeners(canvas, key, "pos");
  }
}
function setSpecCanvas(key: string, el: unknown) {
  const canvas = el as HTMLCanvasElement | null;
  if (!canvas) {
    _specChart[key]?.destroy(); _specChart[key] = null;
    _specCanvasCleanup[key]?.(); _specCanvasCleanup[key] = null;
  } else {
    _specCanvas[key] = canvas;
    _specCanvasCleanup[key] = _attachListeners(canvas, key, "spec");
  }
}

function _attachListeners(canvas: HTMLCanvasElement, chartKey: string, group: "pos" | "spec"): () => void {
  const drag = group === "pos" ? _posDragState : _specDragState;
  const zoomRef = group === "pos" ? _posZoom : _specZoom;
  const getChart = () => group === "pos" ? _chart[chartKey] : _specChart[chartKey];
  const renderPeers = () => {
    const peers = group === "pos" ? Object.values(_chart) : Object.values(_specChart);
    peers.forEach(c => c?.render());
  };

  const onMousedown = (e: MouseEvent) => {
    if (!e.shiftKey) return;
    e.preventDefault();
    drag.active = true; drag.chartKey = chartKey;
    drag.startPx = e.offsetX; drag.currentPx = e.offsetX;
  };

  const onMousemove = (e: MouseEvent) => {
    const chart = getChart();
    if (chart) {
      const xVal = chart.scales["x"]?.getValueForPixel(e.offsetX);
      if (group === "pos") _crosshair.posX = xVal ?? null;
      else                 _crosshair.specX = xVal ?? null;
      renderPeers();
    }
    if (drag.active && drag.chartKey === chartKey) {
      drag.currentPx = e.offsetX;
      getChart()?.render();
    }
  };

  const onMouseup = (e: MouseEvent) => {
    if (!drag.active || drag.chartKey !== chartKey) return;
    drag.currentPx = e.offsetX;
    const chart = getChart();
    if (chart && Math.abs(drag.currentPx - drag.startPx) > 5) {
      const xMin = Math.min(drag.startPx, drag.currentPx);
      const xMax = Math.max(drag.startPx, drag.currentPx);
      const dMin = chart.scales["x"]?.getValueForPixel(xMin);
      const dMax = chart.scales["x"]?.getValueForPixel(xMax);
      if (dMin !== undefined && dMax !== undefined && dMax > dMin)
        zoomRef.value = { min: dMin, max: dMax };
    }
    drag.active = false;
  };

  const onMouseleave = () => {
    if (group === "pos") _crosshair.posX = null; else _crosshair.specX = null;
    if (drag.active && drag.chartKey === chartKey) drag.active = false;
    renderPeers();
  };

  const onContextmenu = (e: MouseEvent) => { e.preventDefault(); zoomRef.value = null; };

  canvas.addEventListener("mousedown",    onMousedown);
  canvas.addEventListener("mousemove",    onMousemove);
  canvas.addEventListener("mouseup",      onMouseup);
  canvas.addEventListener("mouseleave",   onMouseleave);
  canvas.addEventListener("contextmenu",  onContextmenu);
  return () => {
    canvas.removeEventListener("mousedown",   onMousedown);
    canvas.removeEventListener("mousemove",   onMousemove);
    canvas.removeEventListener("mouseup",     onMouseup);
    canvas.removeEventListener("mouseleave",  onMouseleave);
    canvas.removeEventListener("contextmenu", onContextmenu);
  };
}

// ─── Chart helpers ────────────────────────────────────────────────────────────

function _colorFor(geosncl: string): string {
  const all = [...stationGroups.value.values()].flat();
  return COLORS[(Math.max(0, all.indexOf(geosncl))) % COLORS.length];
}

function _epochLabel(ms: number): string {
  const d = new Date(ms);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
    + " " + d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
}

function _interactionPlugin(chartKey: string, group: "pos" | "spec"): object {
  const drag   = group === "pos" ? _posDragState : _specDragState;
  const xhair  = group === "pos" ? (() => _crosshair.posX) : (() => _crosshair.specX);

  return {
    id: `iact-${group}-${chartKey}`,
    afterDraw(chart: Chart) {
      const ctx = chart.ctx;
      const { left, right, top, bottom } = chart.chartArea;

      // Crosshair
      const xData = xhair();
      if (xData !== null) {
        const xPx = chart.scales["x"]?.getPixelForValue(xData);
        if (xPx !== undefined && xPx >= left && xPx <= right) {
          ctx.save();
          ctx.strokeStyle = "rgba(80,80,80,0.5)";
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 3]);
          ctx.beginPath(); ctx.moveTo(xPx, top); ctx.lineTo(xPx, bottom); ctx.stroke();
          ctx.restore();
        }
      }

      // Drag selection box (only on the chart being dragged)
      if (drag.active && drag.chartKey === chartKey) {
        const x1 = Math.max(left,  Math.min(drag.startPx, drag.currentPx));
        const x2 = Math.min(right, Math.max(drag.startPx, drag.currentPx));
        if (x2 > x1) {
          ctx.save();
          ctx.fillStyle   = "rgba(33,150,243,0.12)";
          ctx.strokeStyle = "rgba(33,150,243,0.7)";
          ctx.lineWidth = 1;
          ctx.fillRect(x1, top, x2 - x1, bottom - top);
          ctx.strokeRect(x1, top, x2 - x1, bottom - top);
          ctx.restore();
        }
      }
    },
  };
}

function _makeOnClick(group: "pos" | "spec"): (e: any, elems: any[], chart: Chart) => void {
  return (event, elements, chart) => {
    if (!event.native?.shiftKey) return;
    let dsIdx = elements.length > 0 ? elements[0].datasetIndex : -1;
    if (dsIdx < 0) {
      const nearest = chart.getElementsAtEventForMode(event.native, "nearest", { intersect: false }, false);
      if (nearest.length) dsIdx = nearest[0].datasetIndex;
    }
    if (dsIdx < 0) return;
    const geosncl = chart.data.datasets[dsIdx]?.label;
    if (!geosncl) return;
    const next = new Set(selected.value); next.delete(geosncl); _setSelected(next);
  };
}

function _makePosChart(key: string, label: string): Chart | null {
  const canvas = _canvas[key]; if (!canvas) return null;
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: { mode: "nearest", intersect: false, axis: "x" },
      scales: {
        x: { type: "linear", ticks: { maxTicksLimit: 8, callback: v => _epochLabel(Number(v)) }, grid: { color: "#e0e0e0" } },
        y: { title: { display: true, text: label, font: { size: 11 } }, grid: { color: "#e0e0e0" } },
      },
      plugins: {
        legend: { position: "right", labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            title: items => _epochLabel(Number(items[0].parsed.x)),
            label: item  => `${item.dataset.label}: ${item.parsed.y?.toFixed(2) ?? "—"} mm`,
          },
        },
      },
      onClick: _makeOnClick("pos"),
    },
    plugins: [_interactionPlugin(key, "pos")] as any,
  });
}

// Tick positions (cycles/day) for the linear spectra x-axis, chosen so each maps
// to a round period (5m → 288 cpd, 10m → 144, … 1d → 1 cpd).
const _SPEC_TICKS = [1, 2, 4, 8, 24, 48, 96, 144, 288]; // cpd

function _specFreqLabel(v: number | string): string {
  const f = Number(v); if (!f) return "";
  const p = 1 / f;
  if (p >= 1)       return `${p.toFixed(0)}d`;
  if (p * 24 >= 1)  return `${(p * 24).toFixed(0)}h`;
  return `${(p * 1440).toFixed(0)}m`;
}

function _makeSpecChart(key: string, label: string): Chart | null {
  const canvas = _specCanvas[key]; if (!canvas) return null;
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: { mode: "nearest", intersect: false, axis: "x" },
      scales: {
        x: {
          type: "linear" as const,
          min: 0,
          max: 290,
          afterBuildTicks: (scale: any) => {
            scale.ticks = _SPEC_TICKS.map(v => ({ value: v }));
          },
          title: { display: true, text: "Frequency (cycles/day)", font: { size: 10 } },
          ticks: { callback: _specFreqLabel },
          grid: { color: "#e0e0e0" },
        },
        y: { type: "logarithmic", title: { display: true, text: label, font: { size: 11 } }, grid: { color: "#e0e0e0" } },
      },
      plugins: {
        legend: { position: "right", labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            title: items => {
              const f = items[0].parsed.x; if (!f) return "";
              const p = 1 / f;
              return p >= 1 ? `Period: ${p.toFixed(2)} d` : p * 24 >= 1 ? `Period: ${(p*24).toFixed(2)} h` : `Period: ${(p*1440).toFixed(2)} min`;
            },
            label: item => `${item.dataset.label}: ${item.parsed.y?.toExponential(2) ?? "—"} mm²`,
          },
        },
      },
      onClick: _makeOnClick("spec"),
    },
    plugins: [_interactionPlugin(key, "spec")] as any,
  });
}

// ─── Zoom watchers ────────────────────────────────────────────────────────────

watch(_posZoom, zoom => {
  for (const c of Object.values(_chart)) {
    if (!c) continue;
    const xs = (c.options.scales as any)?.x;
    if (!xs) continue;
    if (zoom) { xs.min = zoom.min; xs.max = zoom.max; } else { delete xs.min; delete xs.max; }
    c.update("none");
  }
});
watch(_specZoom, zoom => {
  for (const c of Object.values(_specChart)) {
    if (!c) continue;
    const xs = (c.options.scales as any)?.x;
    if (!xs) continue;
    if (zoom) { xs.min = zoom.min; xs.max = zoom.max; } else { delete xs.min; delete xs.max; }
    c.update("none");
  }
});

// ─── Data processing ─────────────────────────────────────────────────────────

function _median(arr: number[]): number {
  const s = [...arr].sort((a, b) => a - b), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function _nextPow2(n: number): number { let p = 1; while (p < n) p <<= 1; return p; }

function _fftPower(input: number[]): number[] {
  const n = input.length;
  const re = [...input], im = new Array(n).fill(0);
  let j = 0;
  for (let i = 1; i < n; i++) {
    let bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len, wRe = Math.cos(ang), wIm = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cRe = 1, cIm = 0;
      for (let k = 0; k < (len >> 1); k++) {
        const h = len >> 1;
        const uRe = re[i+k], uIm = im[i+k];
        const vRe = re[i+k+h]*cRe - im[i+k+h]*cIm, vIm = re[i+k+h]*cIm + im[i+k+h]*cRe;
        re[i+k] = uRe+vRe; im[i+k] = uIm+vIm;
        re[i+k+h] = uRe-vRe; im[i+k+h] = uIm-vIm;
        const nc = cRe*wRe - cIm*wIm; cIm = cRe*wIm + cIm*wRe; cRe = nc;
      }
    }
  }
  const half = n >> 1;
  return Array.from({ length: half }, (_, i) => (re[i]*re[i] + im[i]*im[i]) / (n*n));
}

type Processed = { chartData: Array<{ x: number; y: number | null }>; specTimes: number[]; specVals: number[] };

function processComponent(trace: PositionTrace, comp: "east" | "north" | "up"): Processed {
  const raw = trace[comp] as (number | null)[];
  const times = trace.times;
  const validRaw = raw.filter((v): v is number => v !== null);
  if (!validRaw.length) return { chartData: [], specTimes: [], specVals: [] };

  const med = _median(validRaw);
  const thresh = outlierThreshold.value;
  const filtered: (number | null)[] = raw.map(v => v !== null && Math.abs(v - med) <= thresh ? v : null);

  const inliers = filtered.filter((v): v is number => v !== null);
  const mean = inliers.length ? inliers.reduce((s, v) => s + v, 0) / inliers.length : 0;

  const displayed: (number | null)[] = filtered.map(v =>
    v !== null ? (removeMean.value ? v - mean : v) * 1000 : null
  );

  // Gap detection: median consecutive dt among valid points
  const dts: number[] = [];
  for (let i = 1; i < times.length; i++)
    if (displayed[i] !== null && displayed[i-1] !== null) dts.push(times[i] - times[i-1]);
  const medDt = dts.length ? _median(dts) : 0;
  const gapThresh = 3 * medDt;

  const chartData: Array<{ x: number; y: number | null }> = [];
  for (let i = 0; i < times.length; i++) {
    chartData.push({ x: times[i], y: displayed[i] });
    if (medDt > 0 && i < times.length - 1 && times[i+1] - times[i] > gapThresh)
      chartData.push({ x: (times[i] + times[i+1]) / 2, y: null });
  }

  const specTimes: number[] = [], specVals: number[] = [];
  times.forEach((t, i) => { if (displayed[i] !== null) { specTimes.push(t); specVals.push(displayed[i] as number); } });

  return { chartData, specTimes, specVals };
}

const _SPEC_MAX_FREQ  = 288;  // cpd — 5-minute period
const _SPEC_N_BINS    = 500;  // linear frequency bins in [0, _SPEC_MAX_FREQ]

function computeSpectrum(times: number[], vals: number[]): Array<{ x: number; y: number }> {
  if (vals.length < 16) return [];
  const dts = times.slice(1).map((t, i) => (t - times[i]) / 86_400_000).filter(d => d > 0);
  if (!dts.length) return [];
  const dtDays = _median(dts);
  if (dtDays <= 0) return [];

  const n2 = _nextPow2(vals.length);
  const padded = new Array(n2).fill(0);
  for (let i = 0; i < vals.length; i++)
    padded[i] = vals[i] * 0.5 * (1 - Math.cos(2 * Math.PI * i / Math.max(1, vals.length - 1)));

  const power  = _fftPower(padded);
  const bw     = _SPEC_MAX_FREQ / _SPEC_N_BINS;
  const binSum = new Float64Array(_SPEC_N_BINS);
  const binCnt = new Int32Array(_SPEC_N_BINS);

  for (let k = 1; k < n2 >> 1; k++) {
    const freq = k / (n2 * dtDays);
    if (freq > _SPEC_MAX_FREQ) break;
    const b = Math.min(Math.floor(freq / bw), _SPEC_N_BINS - 1);
    if (power[k] > 0) { binSum[b] += power[k]; binCnt[b]++; }
  }

  const result: Array<{ x: number; y: number }> = [];
  for (let b = 0; b < _SPEC_N_BINS; b++)
    if (binCnt[b] > 0) result.push({ x: (b + 0.5) * bw, y: binSum[b] / binCnt[b] });
  return result;
}

// ─── Chart update ─────────────────────────────────────────────────────────────

function updateCharts() {
  for (const { key, label, specLabel } of COMPONENTS) {
    if (!_chart[key])     _chart[key]     = _makePosChart(key, label);
    if (!_specChart[key]) _specChart[key] = _makeSpecChart(key, specLabel);

    const posDatasets: object[] = [], specDatasets: object[] = [];

    for (const geosncl of selected.value) {
      const trace = positionCache.value.get(geosncl);
      const col   = key as "east" | "north" | "up";
      const color = _colorFor(geosncl);
      let chartData: Array<{ x: number; y: number | null }> = [];
      let specPts:   Array<{ x: number; y: number }> = [];
      if (trace) {
        const p = processComponent(trace, col);
        chartData = p.chartData;
        specPts   = computeSpectrum(p.specTimes, p.specVals);
      }
      const base = { label: geosncl, borderColor: color, backgroundColor: color + "22",
                     borderWidth: 1, pointRadius: 0, tension: 0, spanGaps: false };
      posDatasets.push({ ...base, data: chartData });
      specDatasets.push({ ...base, data: specPts });
    }

    const pc = _chart[key], sc = _specChart[key];
    if (pc)  { pc.data.datasets  = posDatasets  as any; pc.update("none"); }
    if (sc)  { sc.data.datasets  = specDatasets as any; sc.update("none"); }
  }
}

// ─── Position loading ─────────────────────────────────────────────────────────

function scheduleLoad() {
  if (loadTimer) clearTimeout(loadTimer);
  loadTimer = setTimeout(loadPositions, 300);
}

async function loadPositions() {
  if (!selected.value.size || !startDate.value || !endDate.value) { updateCharts(); return; }
  const needed = [...selected.value].filter(g => !positionCache.value.has(g));
  if (needed.length > 0) {
    positionsLoading.value = true;
    try {
      const r = await getPositions({
        geosncls: needed.join(","), start: startDate.value, end: endDate.value,
        downsample: downsampleEnabled.value,
      });
      for (const trace of r.stations) positionCache.value.set(trace.geosncl, trace);
    } catch (e) { console.error("Failed to load positions", e); }
    finally { positionsLoading.value = false; }
  }
  updateCharts();
}

// ─── Watches ─────────────────────────────────────────────────────────────────

watch(selected,                        () => scheduleLoad(),                          { deep: false });
watch([removeMean, outlierThreshold],  () => updateCharts());
watch(downsampleEnabled,               () => { positionCache.value.clear(); scheduleLoad(); });

// ─── Fetch missing ────────────────────────────────────────────────────────────

function openFetchDialog() {
  fetchLog.value = []; fetchDone.value = false; fetchRunning.value = false; fetchOpen.value = true;
}
function startFetch() {
  fetchRunning.value = true; fetchLog.value = [];
  openFetchMissingStream(
    { list: selectedList.value, start: startDate.value, end: endDate.value, workers: fetchWorkers.value },
    async (evt) => {
      fetchLog.value.push(evt);
      await nextTick();
      if (fetchLogEl.value) fetchLogEl.value.scrollTop = fetchLogEl.value.scrollHeight;
      if (evt.type === "done") { fetchRunning.value = false; fetchDone.value = true; await reloadStations(); }
    },
  );
}
</script>

<style scoped>
.tree-panel:focus { outline: none; }
.tree-row { min-height: 26px; }
.tree-row.tree-focused > .tree-item { background: rgba(21,101,192,0.12); border-radius: 4px; }
.tree-item { cursor: pointer; padding: 2px 4px; border-radius: 4px; user-select: none; }
.tree-item:hover { background: rgba(0,0,0,0.06); }
.tree-child { padding-left: 28px; }
.tree-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }

.chart-block { position: relative; height: 230px; }
.chart-canvas { position: absolute; inset: 18px 0 0 0; height: calc(100% - 18px) !important; }
</style>

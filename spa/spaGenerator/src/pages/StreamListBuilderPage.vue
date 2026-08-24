<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useQuasar } from 'quasar';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useListDelete } from '../composables/useListDelete';
import {
  PROC_CENTERS, SOL_TYPE_LABELS, solTypeLabel, sortSolTypes,
  defaultSelectedCenters, defaultSelectedStreamTypes,
} from '../constants/streamTypes';

interface StationData { station: string; lat: number | null; lon: number | null; streams: string[]; }

const STREAM_API = '/api/stream-lists';    // stream (geosncl) lists
const STATION_API = '/api/station-lists';  // station (station-code) lists
const COLOR_UNSELECTED = '#9E9E9E';
const COLOR_SELECTED   = '#1565C0';

const $q = useQuasar();

const loading = ref(true);
const stations = ref<StationData[]>([]);
const stationMap = new Map<string, StationData>();

// Visible stations = include-list stations − exclude-list stations.
const includeLists = ref<string[]>([]);
const excludeLists = ref<string[]>([]);
const stationListOptions = ref<string[]>([]);
const visibleStations = ref(new Set<string>());

// Selection = enabled streams (geosncls).
const enabledStreams = ref(new Set<string>());

// Stream-list management.
const streamListOptions = ref<string[]>([]);
const listName = ref('');

const activeStation = ref<StationData | null>(null);
const panelPos = ref<Record<string, string>>({ left: '0px', top: '0px' });

let map: L.Map | null = null;
const markers = new Map<string, L.CircleMarker>();
const _stationCache = new Map<string, string[]>();

const streamCount = computed(() => enabledStreams.value.size);
const visibleCount = computed(() => visibleStations.value.size);

// ── Stream description ────────────────────────────────────────────────────────
function describeStream(gs: string): string {
  const p = gs.split('.');
  if (p.length < 4) return gs;
  const ctr = PROC_CENTERS[p[1] ?? ''] ?? p[1] ?? '';
  const st = (p[3] ?? '').substring(0, 2);
  return `${ctr} · ${st} ${SOL_TYPE_LABELS[st] ?? ''}`.trim();
}

// ── Markers (only visible stations) ───────────────────────────────────────────
function markerColor(station: string): string {
  const st = stationMap.get(station);
  const hasEnabled = !!st && st.streams.some(gs => enabledStreams.value.has(gs));
  return hasEnabled ? COLOR_SELECTED : COLOR_UNSELECTED;
}
function updateAllMarkers() {
  for (const [station, m] of markers.entries()) m.setStyle({ fillColor: markerColor(station) });
}
function addMarker(station: StationData) {
  if (station.lat === null || station.lon === null) return;
  const marker = L.circleMarker([station.lat, station.lon], {
    radius: 5, color: '#fff', weight: 1, fillColor: markerColor(station.station), fillOpacity: 0.85,
  });
  marker.bindTooltip(station.station, { direction: 'top', offset: [0, -5] });
  marker.on('click', (e) => { L.DomEvent.stopPropagation(e); handleMarkerClick(station); });
  marker.addTo(map!);
  markers.set(station.station, marker);
}
function rebuildMarkers() {
  if (!map) return;
  for (const m of markers.values()) map.removeLayer(m);
  markers.clear();
  for (const s of stations.value) {
    if (visibleStations.value.has(s.station) && s.lat !== null && s.lon !== null) addMarker(s);
  }
}

// ── Selection ─────────────────────────────────────────────────────────────────
function handleMarkerClick(station: StationData) {
  const s = new Set(enabledStreams.value);
  const allOn = station.streams.length > 0 && station.streams.every(gs => s.has(gs));
  if (allOn) for (const gs of station.streams) s.delete(gs);   // toggle off
  else for (const gs of station.streams) s.add(gs);            // select all streams
  enabledStreams.value = s;
  updateAllMarkers();
  activeStation.value = station;
  nextTick(() => updatePanelPosition(station));
}
function toggleStream(gs: string) {
  const s = new Set(enabledStreams.value);
  if (s.has(gs)) s.delete(gs); else s.add(gs);
  enabledStreams.value = s;
  updateAllMarkers();
}
function selectAllVisible() {
  const s = new Set(enabledStreams.value);
  for (const station of visibleStations.value) {
    const st = stationMap.get(station);
    if (st) for (const gs of st.streams) s.add(gs);
  }
  enabledStreams.value = s; updateAllMarkers();
}
function clearSelection() { enabledStreams.value = new Set(); updateAllMarkers(); }

// ── Filter by processing center / stream type (visible stations only) ─────────
const filterCenters  = ref<string[]>([]);
const filterSolTypes = ref<string[]>([]);

const visibleStreamList = computed(() => {
  const out: string[] = [];
  for (const code of visibleStations.value) {
    const st = stationMap.get(code);
    if (st) out.push(...st.streams);
  }
  return out;
});
const availableCenters = computed(() => {
  const s = new Set<string>();
  for (const gs of visibleStreamList.value) {
    const p = gs.split('.');
    if (p.length >= 2 && p[1]) s.add(p[1]);
  }
  return [...s].sort();
});
const availableSolTypes = computed(() => {
  const s = new Set<string>();
  for (const gs of visibleStreamList.value) {
    const p = gs.split('.');
    if (p.length >= 4 && (p[3] ?? '').length >= 2) s.add(p[3].slice(0, 2));
  }
  return sortSolTypes([...s]);
});
// The chip filters must always keep at least one selection, so `matchingStreams`
// is never trivially empty.  The defaults are an intersection with a fixed
// preference list, which can come back empty when a network uses none of the
// preferred centers/types -- fall back to everything available rather than
// leaving the user with an empty filter and no way to tell why.
function withFallback(preferred: string[], available: string[]): string[] {
  return preferred.length ? preferred : [...available];
}
watch(availableCenters, (v) => {
  filterCenters.value = withFallback(defaultSelectedCenters(v), v);
});
watch(availableSolTypes, (v) => {
  filterSolTypes.value = withFallback(defaultSelectedStreamTypes(v), v);
});

function toggleFilter(list: string[], item: string, label: string): void {
  const i = list.indexOf(item);
  if (i < 0) { list.push(item); return; }
  if (list.length === 1) {
    $q.notify({ type: 'warning', timeout: 1500,
                message: `At least one ${label} must stay selected.` });
    return;
  }
  list.splice(i, 1);
}

const matchingStreams = computed(() => visibleStreamList.value.filter((gs) => {
  const p = gs.split('.');
  if (p.length < 4) return false;
  return filterCenters.value.includes(p[1]) && filterSolTypes.value.includes(p[3].slice(0, 2));
}));

// Replace the working set outright -- unlike add/remove, the result does not
// depend on what was already selected.
function setMatchingStreams() {
  enabledStreams.value = new Set(matchingStreams.value);
  updateAllMarkers();
}
function addMatchingStreams() {
  if (!matchingStreams.value.length) return;
  const s = new Set(enabledStreams.value);
  for (const gs of matchingStreams.value) s.add(gs);
  enabledStreams.value = s;
  updateAllMarkers();
}
function removeMatchingStreams() {
  if (!matchingStreams.value.length) return;
  const s = new Set(enabledStreams.value);
  for (const gs of matchingStreams.value) s.delete(gs);
  enabledStreams.value = s;
  updateAllMarkers();
}

// ── Include / exclude station lists (auto-apply) ──────────────────────────────
async function getStationCodes(name: string): Promise<string[]> {
  if (_stationCache.has(name)) return _stationCache.get(name)!;
  try {
    const r = await axios.get(`${STATION_API}/${encodeURIComponent(name)}`);
    const codes = (r.data.stations ?? []).map((s: string) => s.toUpperCase());
    _stationCache.set(name, codes);
    return codes;
  } catch { return []; }
}
async function recomputeVisible() {
  const inc = new Set<string>(), exc = new Set<string>();
  for (const n of includeLists.value) (await getStationCodes(n)).forEach(s => inc.add(s));
  for (const n of excludeLists.value) (await getStationCodes(n)).forEach(s => exc.add(s));
  const vis = new Set<string>();
  for (const s of inc) if (!exc.has(s)) vis.add(s);
  visibleStations.value = vis;
  // Changing include/exclude resets the manual selection.
  enabledStreams.value = new Set();
  activeStation.value = null;
  rebuildMarkers();
}
watch([includeLists, excludeLists], () => { recomputeVisible(); }, { deep: true });

// ── List options ──────────────────────────────────────────────────────────────
async function loadStationListOptions() {
  try { stationListOptions.value = (await axios.get(STATION_API)).data.lists ?? []; }
  catch { stationListOptions.value = []; }
}
async function loadStreamListOptions() {
  try { streamListOptions.value = (await axios.get(STREAM_API)).data.lists ?? []; }
  catch { streamListOptions.value = []; }
}

// ── Save / manage stream lists ────────────────────────────────────────────────
async function persistStreamList(name: string, geosncls: string[]): Promise<boolean> {
  try {
    // Posting geosncls (rather than raw JSONL) keeps the server-side edid
    // enrichment, without which `es-pos fetch --list` 422s on every request.
    await axios.post(`${STREAM_API}/${encodeURIComponent(name)}`, { geosncls });
    $q.notify({ type: 'positive', message: `Saved stream list "${name}" (${geosncls.length} streams)` });
    listName.value = '';
    await loadStreamListOptions();
    return true;
  } catch { $q.notify({ type: 'negative', message: 'Save failed' }); return false; }
}

async function saveList() {
  const name = listName.value.trim();
  if (!name || enabledStreams.value.size === 0) return;
  await persistStreamList(name, [...enabledStreams.value]);
}

// ── Preview / edit the pending list before saving ────────────────────────────
// Shows the selection as one geosncl per line.  The saved-list editor works on
// raw JSONL because those files exist on disk already (with their edids); a
// pending list has no file yet, so this edits the geosncls and lets the server
// attach edids on save exactly as the plain Save button does.
const pendingOpen  = ref(false);
const pendingText  = ref('');
const pendingSaving = ref(false);
const pendingError = ref('');

function parsePendingLines(text: string): string[] {
  return [...new Set(text.split('\n').map(l => l.trim()).filter(Boolean))];
}
const pendingCount = computed(() => parsePendingLines(pendingText.value).length);

function openSavePreview() {
  pendingError.value = ''; pendingSaving.value = false;
  pendingText.value = [...enabledStreams.value].sort().join('\n');
  pendingOpen.value = true;
}

async function savePendingList() {
  const name = listName.value.trim();
  if (!name) { pendingError.value = 'Name is required.'; return; }
  const geosncls = parsePendingLines(pendingText.value);
  if (!geosncls.length) { pendingError.value = 'The list is empty.'; return; }
  pendingSaving.value = true; pendingError.value = '';
  // Keep the on-screen selection in step with what was actually saved, so the
  // map and the "will be saved" count don't drift from the file.
  enabledStreams.value = new Set(geosncls);
  updateAllMarkers();
  if (await persistStreamList(name, geosncls)) pendingOpen.value = false;
  pendingSaving.value = false;
}

async function loadStreamListIntoSelection(name: string) {
  try {
    const r = await axios.get(`${STREAM_API}/${encodeURIComponent(name)}`);
    enabledStreams.value = new Set((r.data.geosncls ?? []) as string[]);
    updateAllMarkers();
    $q.notify({ type: 'positive', message: `Loaded ${enabledStreams.value.size} stream(s) from "${name}".` });
  } catch { $q.notify({ type: 'negative', message: 'Load failed' }); }
}

const { confirmDeleteList, promptRenameList } = useListDelete(loadStreamListOptions, undefined, STREAM_API);
function renameListAction(name: string) { setTimeout(() => promptRenameList(name), 0); }
function deleteListAction(name: string) { setTimeout(() => confirmDeleteList(name), 0); }

// Edit stream list (raw JSONL)
const editOpen = ref(false);
const editName = ref('');
const editContent = ref('');
const editSaving = ref(false);
const editError = ref('');
const editLineCount = computed(() => editContent.value ? editContent.value.split('\n').filter(l => l.trim()).length : 0);
async function openEditList(name: string) {
  editError.value = ''; editSaving.value = false;
  try {
    const r = await axios.get(`${STREAM_API}/${encodeURIComponent(name)}/raw`);
    editName.value = name; editContent.value = r.data.content ?? ''; editOpen.value = true;
  } catch { $q.notify({ type: 'negative', message: 'Could not open list' }); }
}
async function doSaveEdit(target: string) {
  const name = String(target).trim();
  if (!name) { editError.value = 'Name is required.'; return; }
  editSaving.value = true; editError.value = '';
  try {
    await axios.post(`${STREAM_API}/${encodeURIComponent(name)}/raw`, { content: editContent.value });
    $q.notify({ type: 'positive', message: `Saved ${name}.jsonl` });
    await loadStreamListOptions();
    editOpen.value = false;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    editError.value = err?.response?.data?.error ?? 'Save failed.';
  } finally { editSaving.value = false; }
}

// ── Update XX-Active lists (NCEDC) ────────────────────────────────────────────
const saRunning = ref(false);
const saLog = ref<{ text: string; isError?: boolean; isDone?: boolean }[]>([]);
function updateActiveFromNcedc() {
  if (saRunning.value) return;
  saRunning.value = true; saLog.value = [];
  const es = new EventSource('/api/stream-lists/update-active-from-ncedc');
  es.onmessage = (ev) => {
    try {
      const d = JSON.parse(ev.data);
      if (d.type === 'done') {
        saLog.value.push({ text: d.msg ?? 'Done', isDone: d.code === 0, isError: d.code !== 0 });
        es.close(); saRunning.value = false; loadStreamListOptions();
      } else if (d.type === 'error') {
        saLog.value.push({ text: d.msg ?? 'Error', isError: true });
      } else {
        saLog.value.push({ text: d.msg ?? '' });
      }
    } catch { /* ignore */ }
  };
  es.onerror = () => { es.close(); saRunning.value = false; };
}

// ── Map / panel / lifecycle ───────────────────────────────────────────────────
function updatePanelPosition(station: StationData) {
  if (!map || station.lat === null || station.lon === null) return;
  const mapEl = document.getElementById('stream-list-map'); if (!mapEl) return;
  const pt = map.latLngToContainerPoint(L.latLng(station.lat, station.lon));
  let left = pt.x + 14, top = pt.y - 60;
  if (left + 260 > mapEl.clientWidth) left = pt.x - 270;
  if (top < 8) top = 8;
  if (top + 330 > mapEl.clientHeight) top = mapEl.clientHeight - 335;
  panelPos.value = { left: left + 'px', top: top + 'px' };
}
function initMap() {
  const mapEl = document.getElementById('stream-list-map')!;
  map = L.map(mapEl, { center: [38, -98], zoom: 4 });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors', maxZoom: 18,
  }).addTo(map);
  rebuildMarkers();
  map.on('move', () => { if (activeStation.value) updatePanelPosition(activeStation.value); });
  map.on('click', () => { activeStation.value = null; });
  map.on('dragstart', () => { activeStation.value = null; });
}

onMounted(async () => {
  const [dataRes] = await Promise.allSettled([
    axios.get('/api/station-builder/data'), loadStationListOptions(), loadStreamListOptions(),
  ]);
  if (dataRes.status === 'fulfilled') {
    stations.value = dataRes.value.data.stations ?? [];
    for (const s of stations.value) stationMap.set(s.station, s);
  }
  loading.value = false;
  await nextTick();
  initMap();
});
onUnmounted(() => {
  if (map) { map.remove(); map = null; }
  markers.clear();
});
</script>

<template>
  <q-page class="row no-wrap" style="height:calc(100vh - 90px); overflow:hidden">
    <div class="col-auto column no-wrap" style="width:310px; border-right:1px solid #e0e0e0">
      <q-scroll-area class="col">
        <div class="q-pa-sm">
          <div class="text-subtitle2 q-mb-xs">Stream List Builder</div>
          <div class="text-caption text-grey-6 q-mb-sm">
            Pick streams from stations in your include lists. Saves to stream lists.
          </div>

          <!-- Include / exclude station lists -->
          <div class="text-overline text-grey-7 q-mb-xs">Include Station Lists</div>
          <q-select v-model="includeLists" :options="stationListOptions" label="Show stations from…"
                    multiple use-chips dense outlined class="q-mb-sm" />
          <div class="text-overline text-grey-7 q-mb-xs">Exclude Station Lists</div>
          <q-select v-model="excludeLists" :options="stationListOptions" label="Hide stations from…"
                    multiple use-chips dense outlined />
          <div class="text-caption text-grey-7 q-mt-xs">
            {{ visibleCount }} station(s) shown · {{ streamCount }} stream(s) selected
          </div>
          <div class="row items-center q-gutter-xs q-mt-xs">
            <q-btn flat dense size="sm" label="Select all" color="primary" @click="selectAllVisible" />
            <q-btn flat dense size="sm" label="Clear" color="grey-7" @click="clearSelection" />
          </div>

          <q-separator class="q-my-sm" />

          <!-- Filter by processing center / stream type -->
          <div class="text-overline text-grey-7 q-mb-xs">Filter Streams</div>
          <div class="text-caption text-grey-6 q-mb-xs">Processing centers</div>
          <div class="row q-gutter-xs">
            <q-chip
              v-for="c in availableCenters" :key="c"
              :selected="filterCenters.includes(c)"
              clickable dense size="sm"
              :color="filterCenters.includes(c) ? 'primary' : 'grey-3'"
              :text-color="filterCenters.includes(c) ? 'white' : 'black'"
              @click="toggleFilter(filterCenters, c, 'processing center')"
            >{{ c }} {{ PROC_CENTERS[c] ?? '' }}</q-chip>
          </div>
          <div class="text-caption text-grey-6 q-mt-xs">Stream type</div>
          <div class="row q-gutter-xs">
            <q-chip
              v-for="code in availableSolTypes" :key="code"
              :selected="filterSolTypes.includes(code)"
              clickable dense size="sm"
              :color="filterSolTypes.includes(code) ? 'primary' : 'grey-3'"
              :text-color="filterSolTypes.includes(code) ? 'white' : 'black'"
              @click="toggleFilter(filterSolTypes, code, 'stream type')"
            >{{ code }} {{ solTypeLabel(code) }}</q-chip>
          </div>
          <div class="text-caption text-grey-7 q-mt-xs">{{ matchingStreams.length }} stream(s) match</div>
          <div class="row items-center q-gutter-xs q-mt-xs">
            <q-btn flat dense size="sm" label="Only matching" color="primary"
                   :disable="matchingStreams.length === 0" @click="setMatchingStreams">
              <q-tooltip>Replace the selection with exactly the matching streams</q-tooltip>
            </q-btn>
            <q-btn flat dense size="sm" label="Add matching" color="positive"
                   :disable="matchingStreams.length === 0" @click="addMatchingStreams">
              <q-tooltip>Add the matching streams to the current selection</q-tooltip>
            </q-btn>
            <q-btn flat dense size="sm" label="Remove matching" color="negative"
                   :disable="matchingStreams.length === 0" @click="removeMatchingStreams">
              <q-tooltip>Remove the matching streams from the current selection</q-tooltip>
            </q-btn>
          </div>

          <q-separator class="q-my-sm" />

          <!-- Save stream list -->
          <div class="text-overline text-grey-7 q-mb-xs">Save Stream List</div>
          <q-input v-model="listName" label="List name" dense outlined class="q-mb-xs" clearable />
          <div class="text-caption q-mb-xs" :class="streamCount ? 'text-grey-7' : 'text-grey-5'">
            {{ streamCount }} stream(s) will be saved
          </div>
          <q-btn class="full-width q-mb-xs" size="sm" color="positive" unelevated label="Save"
                 :disable="!listName.trim() || streamCount === 0" @click="saveList" />
          <q-btn class="full-width q-mb-sm" size="sm" color="primary" outline no-caps
                 icon="edit_note" label="Preview / edit before saving"
                 :disable="streamCount === 0" @click="openSavePreview" />

          <!-- Manage stream lists -->
          <div class="text-overline text-grey-7 q-mb-xs">Stream Lists</div>
          <q-list dense bordered class="rounded-borders" style="max-height:180px; overflow:auto">
            <q-item v-for="n in streamListOptions" :key="n" dense>
              <q-item-section><q-item-label class="text-caption">{{ n }}</q-item-label></q-item-section>
              <q-item-section side>
                <div class="row items-center no-wrap">
                  <q-btn flat dense round icon="download" size="sm" color="primary"
                         @click="loadStreamListIntoSelection(n)"><q-tooltip>Load into selection</q-tooltip></q-btn>
                  <q-btn flat dense round icon="drive_file_rename_outline" size="sm" color="grey-8"
                         @click="renameListAction(n)"><q-tooltip>Rename</q-tooltip></q-btn>
                  <q-btn flat dense round icon="edit_note" size="sm" color="grey-8"
                         @click="openEditList(n)"><q-tooltip>Edit</q-tooltip></q-btn>
                  <q-btn flat dense round icon="delete" size="sm" color="negative"
                         @click="deleteListAction(n)"><q-tooltip>Delete</q-tooltip></q-btn>
                </div>
              </q-item-section>
            </q-item>
          </q-list>

          <q-separator class="q-my-sm" />

          <!-- XX-Active -->
          <q-btn class="full-width q-mb-xs" size="sm" color="deep-orange" unelevated
                 icon="refresh" label="Update XX-Active Lists" :disable="saRunning" @click="updateActiveFromNcedc" />
          <div v-if="saLog.length" class="sa-log q-mt-xs">
            <div v-for="(e, i) in saLog" :key="i"
                 :class="e.isError ? 'text-negative' : e.isDone ? 'text-positive text-weight-medium' : 'text-grey-8'">
              {{ e.text }}
            </div>
          </div>

          <q-separator class="q-my-sm" />
          <div class="text-overline text-grey-7 q-mb-xs">Legend</div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" style="background:#9E9E9E"></div><span>No streams selected</span>
          </div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" style="background:#1565C0"></div><span>Has selected stream(s)</span>
          </div>
        </div>
      </q-scroll-area>
    </div>

    <div class="col" style="position:relative; min-height:0; overflow:hidden">
      <div v-if="loading" class="absolute-full flex flex-center" style="z-index:2000; background:rgba(255,255,255,0.85)">
        <q-spinner-dots color="primary" size="48px" />
      </div>
      <div v-if="!loading && visibleCount === 0" class="absolute-full flex flex-center text-grey-5"
           style="z-index:500; pointer-events:none">
        <div class="text-center">
          <q-icon name="filter_alt" size="42px" class="q-mb-sm" />
          <div>Select an Include Station List to show stations.</div>
        </div>
      </div>

      <div v-if="activeStation" class="bg-white rounded-borders"
           :style="{ ...panelPos, position:'absolute', width:'256px', zIndex:800, boxShadow:'0 4px 16px rgba(0,0,0,0.22)' }">
        <div class="row items-center q-px-sm q-pt-xs">
          <span class="text-subtitle2 col">{{ activeStation.station }}</span>
          <q-btn flat dense round icon="close" size="xs" @click="activeStation = null" />
        </div>
        <q-separator />
        <q-scroll-area style="height:220px">
          <q-list dense>
            <q-item v-for="gs in activeStation.streams" :key="gs" tag="label" dense>
              <q-item-section avatar style="min-width:28px; padding-right:4px">
                <q-checkbox :model-value="enabledStreams.has(gs)" @update:model-value="toggleStream(gs)" size="xs" dense />
              </q-item-section>
              <q-item-section>
                <q-item-label class="text-caption">{{ gs }}</q-item-label>
                <q-item-label caption>{{ describeStream(gs) }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="activeStation.streams.length === 0">
              <q-item-section class="text-caption text-grey-6">No streams for this station.</q-item-section>
            </q-item>
          </q-list>
        </q-scroll-area>
      </div>

      <div id="stream-list-map" style="width:100%; height:100%"></div>
    </div>

    <!-- Edit stream list -->
    <q-dialog v-model="pendingOpen" maximized>
      <q-card class="column no-wrap">
        <q-card-section class="row items-center q-py-sm bg-primary text-white">
          <q-icon name="edit_note" class="q-mr-sm" />
          <div class="text-subtitle1">Stream list to save</div>
          <q-space />
          <q-input v-model="listName" dense outlined dark label="List name" style="width:280px"
                   :suffix="'.jsonl'" :disable="pendingSaving" />
          <q-btn flat round dense icon="close" class="q-ml-sm" v-close-popup :disable="pendingSaving" />
        </q-card-section>
        <q-banner v-if="pendingError" dense class="bg-red-1 text-negative">{{ pendingError }}</q-banner>
        <q-card-section class="q-py-xs text-caption text-grey-7">
          One geosncl per line. Blank lines and duplicates are dropped. Saving also
          updates the selection on the map to match what you edit here.
        </q-card-section>
        <q-card-section class="col q-pa-none" style="min-height:0">
          <q-input v-model="pendingText" type="textarea" outlined class="edit-jsonl fit"
                   input-class="edit-jsonl-input" :disable="pendingSaving" />
        </q-card-section>
        <q-separator />
        <q-card-actions align="right" class="q-pa-md">
          <div class="text-caption text-grey-6 q-mr-auto">{{ pendingCount }} stream(s) will be saved</div>
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="pendingSaving" />
          <q-btn no-caps unelevated color="positive" label="Save" :loading="pendingSaving"
                 :disable="!listName.trim() || pendingCount === 0" @click="savePendingList" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="editOpen" maximized>
      <q-card class="column no-wrap">
        <q-card-section class="row items-center q-py-sm bg-primary text-white">
          <q-icon name="edit_note" class="q-mr-sm" />
          <div class="text-subtitle1">Edit stream list</div>
          <q-space />
          <q-input v-model="editName" dense outlined dark label="List name" style="width:280px" :suffix="'.jsonl'" />
          <q-btn flat round dense icon="close" class="q-ml-sm" v-close-popup :disable="editSaving" />
        </q-card-section>
        <q-banner v-if="editError" dense class="bg-red-1 text-negative">{{ editError }}</q-banner>
        <q-card-section class="col q-pa-none" style="min-height:0">
          <q-input v-model="editContent" type="textarea" outlined class="edit-jsonl fit"
                   input-class="edit-jsonl-input" :disable="editSaving" />
        </q-card-section>
        <q-separator />
        <q-card-actions align="right" class="q-pa-md">
          <div class="text-caption text-grey-6 q-mr-auto">{{ editLineCount }} line(s)</div>
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="editSaving" />
          <q-btn no-caps unelevated color="primary" label="Save" :loading="editSaving"
                 :disable="!editName.trim()" @click="doSaveEdit(editName.trim())" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<style scoped>
.legend-dot { width:10px; height:10px; border-radius:50%; border:1px solid #fff; box-shadow:0 0 0 1px #aaa; flex-shrink:0; }
.edit-jsonl { height:100%; }
.edit-jsonl :deep(.q-field__control), .edit-jsonl :deep(.q-field__control-container) { height:100%; }
.edit-jsonl :deep(.edit-jsonl-input) { height:100% !important; font-family:monospace; font-size:12px; line-height:1.5; resize:none; }
.sa-log { font-family:monospace; font-size:0.72rem; max-height:140px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; }
</style>

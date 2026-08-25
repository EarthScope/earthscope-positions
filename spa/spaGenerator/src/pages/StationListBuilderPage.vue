<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useQuasar } from 'quasar';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useListDelete } from '../composables/useListDelete';

// ── Types ─────────────────────────────────────────────────────────────────────
interface StationData { station: string; lat: number | null; lon: number | null; streams: string[]; }

const STATION_API = '/api/station-lists';
const COLOR_UNSELECTED = '#9E9E9E';
const COLOR_SELECTED   = '#1565C0';

const $q = useQuasar();

// ── State ─────────────────────────────────────────────────────────────────────
const loading = ref(true);
const stations = ref<StationData[]>([]);
const stationMap = new Map<string, StationData>();
const selectedStations = ref(new Set<string>());

const history = ref<string[][]>([[]]);
const historyIdx = ref(0);

// What to do with a newly selected batch of stations -- map rectangle drag,
// Add Network Stations, and Radial Search all funnel through applySelection().
// Persisted so it survives a reload; 'exclude' is the pre-rename value the
// radial dialog used to store on its own.
type SelectMode = 'only' | 'add' | 'remove';
const _storedMode = localStorage.getItem('stationSelectMode')
  ?? localStorage.getItem('radialMode');
const selectMode = ref<SelectMode>(
  _storedMode === 'add' ? 'add'
  : (_storedMode === 'remove' || _storedMode === 'exclude') ? 'remove'
  : 'only');
watch(selectMode, (m) => localStorage.setItem('stationSelectMode', m));

const SELECT_MODE_OPTIONS = [
  { label: 'Only',   value: 'only'   },
  { label: 'Add',    value: 'add'    },
  { label: 'Remove', value: 'remove' },
];

/** Combine a freshly-identified batch of stations with the current selection
 *  according to selectMode, then commit it (history + markers). */
function applySelection(hits: Set<string> | string[]): number {
  const batch = hits instanceof Set ? hits : new Set(hits);
  let ss: Set<string>;
  if (selectMode.value === 'only') {
    ss = new Set(batch);
  } else if (selectMode.value === 'add') {
    ss = new Set(selectedStations.value);
    batch.forEach(h => ss.add(h));
  } else {
    ss = new Set(selectedStations.value);
    batch.forEach(h => ss.delete(h));
  }
  selectedStations.value = ss;
  pushHistory(ss);
  updateAllMarkers();
  activeStation.value = null;
  return batch.size;
}
const shiftHeld  = ref(false);

const listOptions   = ref<string[]>([]);
const selectedLists = ref<string[]>([]);
const listName      = ref('');

const activeStation = ref<StationData | null>(null);
const panelPos = ref<Record<string, string>>({ left: '0px', top: '0px' });

const selRect = ref<{ x: number; y: number; w: number; h: number } | null>(null);
const rectOverlayRef = ref<HTMLDivElement | null>(null);

let map: L.Map | null = null;
const markers = new Map<string, L.CircleMarker>();

const selCount = computed(() => selectedStations.value.size);
const selRectStyle = computed(() => {
  const r = selRect.value;
  return r ? { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' } : {};
});

// ── Markers ─────────────────────────────────────────────────────────────────
// Streams appear in the tooltip once zoomed in close enough to read them.
const STREAM_TOOLTIP_ZOOM = 11;

function markerColor(station: string): string {
  return selectedStations.value.has(station) ? COLOR_SELECTED : COLOR_UNSELECTED;
}
function updateAllMarkers() {
  for (const [station, m] of markers.entries()) m.setStyle({ fillColor: markerColor(station) });
}
function tooltipContent(station: StationData): string {
  const showStreams = !!map && map.getZoom() >= STREAM_TOOLTIP_ZOOM && station.streams.length > 0;
  if (!showStreams) return `<strong>${station.station}</strong>`;
  return `<strong>${station.station}</strong><br>${station.streams.join('<br>')}`;
}
function refreshTooltips() {
  for (const [code, m] of markers.entries()) {
    const s = stationMap.get(code);
    if (s) m.setTooltipContent(tooltipContent(s));
  }
}
function addMarker(station: StationData) {
  if (station.lat === null || station.lon === null) return;
  const marker = L.circleMarker([station.lat, station.lon], {
    radius: 5, color: '#fff', weight: 1, fillColor: markerColor(station.station), fillOpacity: 0.85,
  });
  marker.bindTooltip(tooltipContent(station), { direction: 'top', offset: [0, -5] });
  marker.on('click', (e) => { L.DomEvent.stopPropagation(e); handleMarkerClick(station); });
  marker.addTo(map!);
  markers.set(station.station, marker);
}

// ── Selection ───────────────────────────────────────────────────────────────
function setStationSelected(station: string, sel: boolean) {
  const ss = new Set(selectedStations.value);
  if (sel) ss.add(station); else ss.delete(station);
  selectedStations.value = ss;
}
/** Always flips membership — used by direct clicks (marker or popup button),
 * independent of the box-select toggle/union modes below. */
function toggleStationSelection(code: string) {
  setStationSelected(code, !selectedStations.value.has(code));
  pushHistory(selectedStations.value);
  updateAllMarkers();
}
function handleMarkerClick(station: StationData) {
  toggleStationSelection(station.station);
  activeStation.value = station;
  nextTick(() => updatePanelPosition(station));
}
function selectAll() {
  selectedStations.value = new Set(
    stations.value.filter(s => s.lat !== null && s.lon !== null).map(s => s.station));
  pushHistory(selectedStations.value); updateAllMarkers(); activeStation.value = null;
}
function selectNone() {
  selectedStations.value = new Set();
  pushHistory(new Set()); updateAllMarkers(); activeStation.value = null;
}
function selectInBounds(bounds: L.LatLngBounds) {
  const hits = new Set<string>();
  for (const s of stations.value) {
    if (s.lat === null || s.lon === null) continue;
    if (bounds.contains(L.latLng(s.lat, s.lon))) hits.add(s.station);
  }
  applySelection(hits);
}

// ── History ─────────────────────────────────────────────────────────────────
function pushHistory(stationCodes: Set<string>) {
  const snap = [...stationCodes].sort();
  const tail = history.value.slice(0, historyIdx.value + 1);
  tail.push(snap);
  if (tail.length > 100) tail.shift();
  history.value = tail; historyIdx.value = tail.length - 1;
}
function restoreHistoryAt(idx: number) {
  selectedStations.value = new Set(history.value[idx] ?? []);
  updateAllMarkers(); activeStation.value = null;
}
function histBack()    { if (historyIdx.value > 0) { historyIdx.value--; restoreHistoryAt(historyIdx.value); } }
function histForward() { if (historyIdx.value < history.value.length - 1) { historyIdx.value++; restoreHistoryAt(historyIdx.value); } }

// ── Radial search (client-side haversine over coordinates) ────────────────────
const radialOpen = ref(false);
const radialLat  = ref<number | null>(null);
const radialLon  = ref<number | null>(null);
const radialKm   = ref<number | null>(100);
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371, toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
function applyRadial() {
  if (radialLat.value === null || radialLon.value === null || !radialKm.value) return;
  const hits = new Set<string>();
  for (const s of stations.value) {
    if (s.lat === null || s.lon === null) continue;
    if (haversineKm(radialLat.value, radialLon.value, s.lat, s.lon) <= radialKm.value) hits.add(s.station);
  }
  applySelection(hits);
  $q.notify({ type: 'positive', message: `Radial: ${hits.size} station(s) within ${radialKm.value} km (${selectMode.value}).` });
  radialOpen.value = false;
}
/** Open the Radial Search dialog pre-filled with a station's coordinates as the
 * search center (the "epicenter"). */
function openRadialFromStation(station: StationData) {
  if (station.lat === null || station.lon === null) return;
  radialLat.value = station.lat;
  radialLon.value = station.lon;
  radialOpen.value = true;
}

// ── Networks (station names only) ─────────────────────────────────────────────
const networkOptions  = ref<string[]>([]);
const selectedNetwork = ref<string | null>(null);
const networkLoading  = ref(false);
const networkMsg      = ref('');
const networkLastList = ref('');

async function loadNetworks() {
  try { networkOptions.value = (await axios.get('/api/station-builder/networks')).data.networks ?? []; }
  catch { networkOptions.value = []; }
}
async function loadNetworkStations(refresh = false) {
  if (!selectedNetwork.value || networkLoading.value) return;
  networkLoading.value = true;
  networkMsg.value = refresh ? 'Re-querying…' : 'Loading…';
  try {
    const r = await axios.get('/api/station-builder/network-stations', {
      params: { network: selectedNetwork.value, refresh },
    });
    const codes: string[] = (r.data.stations ?? []).map((s: string) => s.toUpperCase());
    applySelection(codes);

    // Loading a network also leaves a saved station list behind, so surface
    // its name and whether it came from disk -- otherwise a cached load looks
    // identical to a fresh query while quietly not hitting the API.
    networkLastList.value = r.data.name ?? '';
    const via = r.data.cached
      ? `loaded from saved list "${r.data.name}"`
      : `saved as station list "${r.data.name}"`;
    const verb = selectMode.value === 'remove' ? 'Removed' : 'Applied';
    networkMsg.value = `${verb} ${codes.length} station(s) from ${selectedNetwork.value} — ${via}.`;
    await loadListOptions();   // the new list should appear in the list dropdown
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    networkMsg.value = err?.response?.data?.error ?? String(e);
  } finally { networkLoading.value = false; }
}

// ── Station lists (load / save / edit / rename / delete) ──────────────────────
async function loadListOptions() {
  try { listOptions.value = (await axios.get(STATION_API)).data.lists ?? []; }
  catch { listOptions.value = []; }
}
async function loadFromSelectedLists(names: string[]) {
  const ss = new Set<string>();
  for (const name of names) {
    try {
      const r = await axios.get(`${STATION_API}/${encodeURIComponent(name)}`);
      for (const s of (r.data.stations ?? []) as string[]) ss.add(s.toUpperCase());
    } catch { /* ignore */ }
  }
  selectedStations.value = ss;
  pushHistory(ss); updateAllMarkers();
}
watch(selectedLists, (n) => loadFromSelectedLists(n));

async function saveList() {
  const name = listName.value.trim();
  if (!name || selectedStations.value.size === 0) return;
  try {
    await axios.post(`${STATION_API}/${encodeURIComponent(name)}`, { stations: [...selectedStations.value] });
    $q.notify({ type: 'positive', message: `Saved station list "${name}" (${selectedStations.value.size} stations)` });
    listName.value = '';
    await loadListOptions();
  } catch { $q.notify({ type: 'negative', message: 'Save failed' }); }
}

function _onListRenamed(oldName: string, newName: string) {
  const i = selectedLists.value.indexOf(oldName);
  if (i >= 0) { const c = [...selectedLists.value]; c[i] = newName; selectedLists.value = c; }
}
const { confirmDeleteList, promptRenameList } = useListDelete(loadListOptions, _onListRenamed, STATION_API);
function renameListAction(name: string) { setTimeout(() => promptRenameList(name), 0); }
function deleteListAction(name: string) { setTimeout(() => confirmDeleteList(name), 0); }

// Edit station list (raw JSONL)
const editOpen = ref(false);
const editOrigName = ref('');
const editName = ref('');
const editContent = ref('');
const editSaving = ref(false);
const editError = ref('');
const editLineCount = computed(() => editContent.value ? editContent.value.split('\n').filter(l => l.trim()).length : 0);

async function openEditList(name: string) {
  editError.value = ''; editSaving.value = false;
  try {
    const r = await axios.get(`${STATION_API}/${encodeURIComponent(name)}/raw`);
    editOrigName.value = name; editName.value = name; editContent.value = r.data.content ?? '';
    editOpen.value = true;
  } catch { $q.notify({ type: 'negative', message: 'Could not open list' }); }
}
async function doSaveEdit(target: string) {
  const name = String(target).trim();
  if (!name) { editError.value = 'Name is required.'; return; }
  editSaving.value = true; editError.value = '';
  try {
    await axios.post(`${STATION_API}/${encodeURIComponent(name)}/raw`, { content: editContent.value });
    $q.notify({ type: 'positive', message: `Saved ${name}.jsonl` });
    await loadListOptions();
    editOpen.value = false;
    if (selectedLists.value.includes(name)) loadFromSelectedLists(selectedLists.value);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    editError.value = err?.response?.data?.error ?? 'Save failed.';
  } finally { editSaving.value = false; }
}

// ── Coordinates (editable station-coordinate file) ────────────────────────────
async function reloadStations() {
  try {
    const list = (await axios.get('/api/station-builder/data')).data.stations ?? [];
    for (const s of list as StationData[]) {
      const station = s.station.toUpperCase();
      const existing = stationMap.get(station);
      if (existing) {
        const moved = existing.lat !== s.lat || existing.lon !== s.lon;
        existing.lat = s.lat; existing.lon = s.lon; existing.streams = s.streams ?? [];
        if (map && moved) { const m = markers.get(station); if (m) { map.removeLayer(m); markers.delete(station); } }
        if (map && !markers.has(station)) addMarker(existing);
      } else {
        const data: StationData = { station, lat: s.lat, lon: s.lon, streams: [...(s.streams ?? [])] };
        stations.value.push(data); stationMap.set(station, data);
        if (map) addMarker(data);
      }
    }
    updateAllMarkers();
    refreshTooltips();
  } catch { /* ignore */ }
}

const coordFileInput = ref<HTMLInputElement | null>(null);
async function onCoordFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  let text = ''; try { text = await file.text(); } catch { return; }
  try {
    const r = await axios.post('/api/coordinates/update', { content: text });
    $q.notify({ type: 'positive', message: `Coordinates: +${r.data.added} new, ${r.data.updated} changed (${r.data.total}).` });
    await reloadStations();
  } catch (err: unknown) {
    const e2 = err as { response?: { data?: { error?: string } } };
    $q.notify({ type: 'negative', multiLine: true, timeout: 9000, message: e2?.response?.data?.error ?? 'Upload failed.' });
  }
}
const coordEditOpen = ref(false);
const coordEditContent = ref('');
const coordEditSaving = ref(false);
const coordEditError = ref('');
const coordEditPath = ref('');
async function openEditCoordinates() {
  coordEditError.value = ''; coordEditSaving.value = false;
  try {
    const r = await axios.get('/api/coordinates/raw');
    coordEditContent.value = r.data.content ?? '';
    coordEditPath.value = r.data.path ?? '';
    coordEditOpen.value = true;
  } catch (err: unknown) {
    // Surface what the server actually said, and which file it tried. The old
    // blanket "Could not open coordinates file" hid the one detail that
    // identifies the problem.
    const e2 = err as { response?: { data?: { error?: string; path?: string } } };
    const detail = e2?.response?.data?.error ?? String(err);
    const where = e2?.response?.data?.path;
    $q.notify({
      type: 'negative', multiLine: true, timeout: 9000,
      message: where
        ? `Could not open coordinates file (${where}): ${detail}`
        : `Could not open coordinates file: ${detail}`,
    });
  }
}
async function doSaveCoordinates() {
  coordEditSaving.value = true; coordEditError.value = '';
  try {
    const r = await axios.put('/api/coordinates/raw', { content: coordEditContent.value });
    $q.notify({ type: 'positive', message: `Saved coordinates (${r.data.count} stations).` });
    coordEditOpen.value = false; await reloadStations();
  } catch (err: unknown) {
    const e2 = err as { response?: { data?: { error?: string } } };
    coordEditError.value = e2?.response?.data?.error ?? 'Save failed.';
  } finally { coordEditSaving.value = false; }
}

// ── Map / drag / lifecycle ────────────────────────────────────────────────────
function updatePanelPosition(station: StationData) {
  if (!map || station.lat === null || station.lon === null) return;
  const mapEl = document.getElementById('station-list-map'); if (!mapEl) return;
  const pt = map.latLngToContainerPoint(L.latLng(station.lat, station.lon));
  let left = pt.x + 14, top = pt.y - 40;
  if (left + 240 > mapEl.clientWidth) left = pt.x - 250;
  if (top < 8) top = 8;
  panelPos.value = { left: left + 'px', top: top + 'px' };
}
function onKeyDown(e: KeyboardEvent) { if (e.key === 'Shift') shiftHeld.value = true; }
function onKeyUp(e: KeyboardEvent) { if (e.key === 'Shift') shiftHeld.value = false; }

function onRectMouseDown(e: MouseEvent) {
  if (!map) return;
  const rect = map.getContainer().getBoundingClientRect();
  const startX = e.clientX - rect.left, startY = e.clientY - rect.top;
  selRect.value = { x: startX, y: startY, w: 0, h: 0 };
  const onMove = (me: MouseEvent) => {
    const cx = me.clientX - rect.left, cy = me.clientY - rect.top;
    selRect.value = { x: Math.min(startX, cx), y: Math.min(startY, cy), w: Math.abs(cx - startX), h: Math.abs(cy - startY) };
  };
  const onUp = (me: MouseEvent) => {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    const cx = me.clientX - rect.left, cy = me.clientY - rect.top;
    selRect.value = null;
    if (Math.abs(cx - startX) + Math.abs(cy - startY) > 8 && map) {
      selectInBounds(L.latLngBounds(
        map.containerPointToLatLng(L.point(startX, startY)),
        map.containerPointToLatLng(L.point(cx, cy))));
    }
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function initMap() {
  const mapEl = document.getElementById('station-list-map')!;
  map = L.map(mapEl, { center: [38, -98], zoom: 4 });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors', maxZoom: 18,
  }).addTo(map);
  for (const s of stations.value) addMarker(s);
  map.on('move', () => { if (activeStation.value) updatePanelPosition(activeStation.value); });
  map.on('zoomend', refreshTooltips);
  map.on('click', () => { activeStation.value = null; });
  map.on('dragstart', () => { activeStation.value = null; });
}

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  const [dataRes] = await Promise.allSettled([
    axios.get('/api/station-builder/data'), loadListOptions(), loadNetworks(),
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
  window.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('keyup', onKeyUp);
  if (map) { map.remove(); map = null; }
  markers.clear();
});
</script>

<template>
  <q-page class="row no-wrap" style="height:calc(100vh - 90px); overflow:hidden">
    <!-- Left panel -->
    <div class="col-auto column no-wrap" style="width:300px; border-right:1px solid #e0e0e0">
      <q-scroll-area class="col">
        <div class="q-pa-sm">
          <div class="text-subtitle2 q-mb-xs">Station List Builder</div>
          <div class="text-caption text-grey-6 q-mb-sm">Down-select stations. Saves to station lists.</div>

          <!-- Load lists -->
          <q-select
            v-model="selectedLists" :options="listOptions" label="Station Lists"
            multiple use-chips dense outlined>
            <template #option="scope">
              <q-item v-bind="scope.itemProps">
                <q-item-section><q-item-label>{{ scope.opt }}</q-item-label></q-item-section>
                <q-item-section side>
                  <div class="row items-center no-wrap">
                    <q-btn flat dense round icon="drive_file_rename_outline" size="sm" color="grey-8"
                           @click.stop="renameListAction(scope.opt)"><q-tooltip>Rename</q-tooltip></q-btn>
                    <q-btn flat dense round icon="edit_note" size="sm" color="grey-8"
                           @click.stop="openEditList(scope.opt)"><q-tooltip>Edit</q-tooltip></q-btn>
                    <q-btn flat dense round icon="delete" size="sm" color="negative"
                           @click.stop="deleteListAction(scope.opt)"><q-tooltip>Delete</q-tooltip></q-btn>
                  </div>
                </q-item-section>
              </q-item>
            </template>
          </q-select>

          <div class="row items-center q-gutter-xs q-mt-xs">
            <q-btn flat dense size="sm" label="All" color="primary" @click="selectAll" />
            <q-btn flat dense size="sm" label="None" color="grey-7" @click="selectNone" />
            <q-space />
            <q-btn flat dense round icon="undo" size="sm" :disable="historyIdx<=0" @click="histBack" />
            <q-btn flat dense round icon="redo" size="sm" :disable="historyIdx>=history.length-1" @click="histForward" />
          </div>
          <div class="text-caption text-grey-6 q-mt-sm">New selections</div>
          <q-btn-toggle
            v-model="selectMode"
            spread no-caps dense unelevated
            toggle-color="primary"
            :options="SELECT_MODE_OPTIONS"
          >
            <q-tooltip max-width="300px">
              What happens to stations picked by a map drag, Add Network Stations, or
              Radial Search — <b>Only</b> replaces the selection, <b>Add</b> merges into
              it, <b>Remove</b> subtracts them from it.
            </q-tooltip>
          </q-btn-toggle>
          <div class="text-caption text-grey-7 q-mt-xs">{{ selCount }} station(s) selected</div>

          <q-separator class="q-my-sm" />

          <!-- Radial search -->
          <q-btn class="full-width q-mb-xs" size="sm" color="indigo" unelevated
                 icon="my_location" label="Radial Search" @click="radialOpen = true" />

          <!-- Networks (station names) -->
          <div class="text-overline text-grey-7 q-mb-xs">Load Network (stations)</div>
          <q-select v-model="selectedNetwork" :options="networkOptions" label="Network"
                    dense outlined clearable class="q-mb-xs" />
          <q-btn class="full-width q-mb-xs" size="sm" color="primary" unelevated
                 icon="lan" label="Add Network Stations"
                 :disable="!selectedNetwork || networkLoading" :loading="networkLoading"
                 @click="loadNetworkStations(false)">
            <q-tooltip max-width="280px">
              Adds the network's stations to the selection and saves them as a station
              list named after the network. If that list already exists it is loaded
              from disk instead of re-querying the API.
            </q-tooltip>
          </q-btn>
          <q-btn v-if="networkLastList" class="full-width q-mb-xs" size="sm" flat dense
                 color="grey-8" icon="refresh" label="Re-query network" no-caps
                 :disable="!selectedNetwork || networkLoading"
                 @click="loadNetworkStations(true)">
            <q-tooltip max-width="280px">
              Ignore the saved list, query the API again, and overwrite
              "{{ networkLastList }}" — discards any hand-edits to it.
            </q-tooltip>
          </q-btn>
          <div v-if="networkMsg" class="text-caption text-grey-7 q-mb-sm">{{ networkMsg }}</div>

          <q-separator class="q-my-sm" />

          <!-- Coordinates -->
          <div class="text-overline text-grey-7 q-mb-xs">Coordinates</div>
          <input ref="coordFileInput" type="file" accept=".csv,text/csv" style="display:none" @change="onCoordFileChange" />
          <q-btn class="full-width q-mb-xs" size="sm" color="blue-grey" unelevated
                 icon="upload_file" label="Add Coordinate File" @click="coordFileInput?.click()">
            <q-tooltip max-width="280px">
              Merge a CSV (station,latitude,longitude,height[,source]) into the stored
              coordinates. Rows in the uploaded file win on station matches; source
              defaults to “user”. Nothing is replaced wholesale — use Edit Coordinates
              for that.
            </q-tooltip>
          </q-btn>
          <q-btn class="full-width q-mb-xs" size="sm" color="blue-grey" outline
                 icon="edit_location_alt" label="Edit Coordinates" @click="openEditCoordinates" />

          <q-separator class="q-my-sm" />

          <!-- Save -->
          <div class="text-overline text-grey-7 q-mb-xs">Save Station List</div>
          <q-input v-model="listName" label="List name" dense outlined class="q-mb-xs" clearable />
          <div class="text-caption q-mb-xs" :class="selCount ? 'text-grey-7' : 'text-grey-5'">
            {{ selCount }} station(s) will be saved
          </div>
          <q-btn class="full-width" size="sm" color="positive" unelevated label="Save"
                 :disable="!listName.trim() || selCount === 0" @click="saveList" />

          <q-separator class="q-my-sm" />
          <div class="text-overline text-grey-7 q-mb-xs">Legend</div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" style="background:#9E9E9E"></div><span>Not selected</span>
          </div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" style="background:#1565C0"></div><span>Selected</span>
          </div>
          <div class="text-caption text-grey-6 q-mt-sm">Shift+drag to box-select.</div>
        </div>
      </q-scroll-area>
    </div>

    <!-- Map -->
    <div class="col" style="position:relative; min-height:0; overflow:hidden">
      <div v-if="loading" class="absolute-full flex flex-center" style="z-index:2000; background:rgba(255,255,255,0.85)">
        <q-spinner-dots color="primary" size="48px" />
      </div>
      <div ref="rectOverlayRef"
           :style="{ position:'absolute', inset:'0', cursor: shiftHeld ? 'crosshair':'default',
                     'pointer-events': shiftHeld ? 'auto':'none', zIndex:900, userSelect:'none' }"
           @mousedown.prevent="onRectMouseDown">
        <div v-if="selRect" :style="selRectStyle"
             style="position:absolute; border:2px solid #1976D2; background:rgba(25,118,210,0.1); pointer-events:none"></div>
      </div>
      <div v-if="activeStation" class="bg-white rounded-borders q-pa-sm"
           :style="{ ...panelPos, position:'absolute', width:'250px', zIndex:800, boxShadow:'0 4px 16px rgba(0,0,0,0.22)' }">
        <div class="row items-center">
          <span class="text-subtitle2 col">{{ activeStation.station }}</span>
          <q-btn flat dense round icon="close" size="xs" @click="activeStation = null" />
        </div>
        <div class="text-caption text-grey-7">
          {{ activeStation.lat?.toFixed(4) }}, {{ activeStation.lon?.toFixed(4) }}<br>
          {{ activeStation.streams.length }} stream(s)
          <template v-if="activeStation.streams.length">
            <br><span v-for="gs in activeStation.streams" :key="gs">{{ gs }}<br></span>
          </template>
        </div>
        <div class="row items-center q-gutter-xs q-mt-xs">
          <q-btn flat dense size="sm"
                 :label="selectedStations.has(activeStation.station) ? 'Deselect' : 'Select'"
                 :color="selectedStations.has(activeStation.station) ? 'negative' : 'primary'"
                 @click="toggleStationSelection(activeStation.station)" />
          <q-btn flat dense size="sm" icon="my_location" color="indigo"
                 :disable="activeStation.lat === null || activeStation.lon === null"
                 @click="openRadialFromStation(activeStation)">
            <q-tooltip>Radial search centered here</q-tooltip>
          </q-btn>
        </div>
      </div>
      <div id="station-list-map" style="width:100%; height:100%"></div>
    </div>

    <!-- Radial dialog -->
    <q-dialog v-model="radialOpen">
      <q-card style="min-width:320px">
        <q-card-section class="text-subtitle1">Radial Search</q-card-section>
        <q-card-section class="q-gutter-sm q-pt-none">
          <q-input v-model.number="radialLat" type="number" label="Latitude" dense outlined />
          <q-input v-model.number="radialLon" type="number" label="Longitude" dense outlined />
          <q-input v-model.number="radialKm" type="number" label="Distance (km)" dense outlined />
          <div class="text-caption text-grey-7">Mode (shared with the map and network selection)</div>
          <q-option-group v-model="selectMode" inline :options="SELECT_MODE_OPTIONS" />
          <div class="text-caption text-grey-6">
            Only = replace selection; Add = add to selection; Remove = subtract (for rings).
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn unelevated color="primary" label="Apply"
                 :disable="radialLat===null || radialLon===null || !radialKm" @click="applyRadial" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Edit station list -->
    <q-dialog v-model="editOpen" maximized>
      <q-card class="column no-wrap">
        <q-card-section class="row items-center q-py-sm bg-primary text-white">
          <q-icon name="edit_note" class="q-mr-sm" />
          <div class="text-subtitle1">Edit station list</div>
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

    <!-- Edit coordinates -->
    <q-dialog v-model="coordEditOpen" maximized>
      <q-card class="column no-wrap">
        <q-card-section class="row items-center q-py-sm bg-blue-grey text-white">
          <q-icon name="edit_location_alt" class="q-mr-sm" />
          <div class="text-subtitle1">
            Edit coordinates
            <span v-if="coordEditPath" class="text-caption q-ml-sm" style="opacity:.8">{{ coordEditPath }}</span>
          </div>
          <q-space />
          <div class="text-caption">station,latitude,longitude,height[,source]</div>
          <q-btn flat round dense icon="close" class="q-ml-sm" v-close-popup :disable="coordEditSaving" />
        </q-card-section>
        <q-banner v-if="coordEditError" dense class="bg-red-1 text-negative">
          <pre class="coord-error">{{ coordEditError }}</pre>
        </q-banner>
        <q-card-section class="col q-pa-none" style="min-height:0">
          <q-input v-model="coordEditContent" type="textarea" outlined class="edit-jsonl fit"
                   input-class="edit-jsonl-input" :disable="coordEditSaving" />
        </q-card-section>
        <q-separator />
        <q-card-actions align="right" class="q-pa-md">
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="coordEditSaving" />
          <q-btn no-caps unelevated color="primary" label="Save" :loading="coordEditSaving" @click="doSaveCoordinates" />
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
.coord-error { margin:0; font-family:monospace; font-size:12px; white-space:pre-wrap; word-break:break-word; max-height:30vh; overflow-y:auto; }
</style>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useQuasar } from 'quasar';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface StationData {
  site: string;
  lat: number | null;
  lon: number | null;
  streams: string[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PROC_CENTERS: Record<string, string> = {
  PB: 'EarthScope',
  PW: 'CWU',
  NC: 'USGS Menlo Park',
  BK: 'UCB',
  CI: 'USGS Pasadena',
};

const SOL_TYPE_LABELS: Record<string, string> = {
  '00': 'CWU Fast',
  '10': 'PIVOT Fast',
  '12': 'PIVOT Complete',
  '13': 'PIVOT Fast+Compl',
  '20': 'RTNet Fast',
  '30': 'Septa Fast',
  '40': 'RTX Fast',
  '50': 'Network Fast',
  '60': 'JPL Fast',
};

const COLOR_UNSELECTED = '#9E9E9E';
const COLOR_SELECTED   = '#1565C0';
const COLOR_NO_STREAMS = '#E65100'; // selected but no streams pass filter

// ── State ─────────────────────────────────────────────────────────────────────

const $q = useQuasar();

const loading   = ref(true);
const stations  = ref<StationData[]>([]);
const stationMap = new Map<string, StationData>(); // O(1) lookup by site

const selectedStations = ref(new Set<string>());
const enabledStreams    = ref(new Set<string>());

// history[i] = sorted array of selected site IDs
const history    = ref<string[][]>([[]]);
const historyIdx = ref(0);

// Behaviour modes
const unionMode  = ref(true);
const toggleMode = ref(true);
const rectMode   = ref(false);
const shiftHeld  = ref(false);

// Filters (all = no filtering)
const filterCenters   = ref<string[]>(Object.keys(PROC_CENTERS));
const filterSolTypes  = ref<string[]>(Object.keys(SOL_TYPE_LABELS));

// Saved lists
const listOptions    = ref<string[]>([]);
const selectedLists  = ref<string[]>([]);
const listName       = ref('');

// Active station detail panel
const activeStation = ref<StationData | null>(null);
const panelPos = ref<Record<string, string>>({ left: '0px', top: '0px' });

// Rectangle selection drawing state
const rectOverlayRef = ref<HTMLDivElement | null>(null);
const selRect = ref<{ x: number; y: number; w: number; h: number } | null>(null);

// ── Leaflet refs ──────────────────────────────────────────────────────────────

let map: L.Map | null = null;
const markers = new Map<string, L.CircleMarker>();

// ── Computed ──────────────────────────────────────────────────────────────────

const selCount    = computed(() => selectedStations.value.size);
const streamCount = computed(() => enabledStreams.value.size);

const selRectStyle = computed(() => {
  const r = selRect.value;
  if (!r) return {};
  return { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function passesFilter(gs: string): boolean {
  const parts = gs.split('.');
  if (parts.length < 4) return true;
  const center   = parts[1] ?? '';
  const solType  = (parts[3] ?? '').substring(0, 2);
  return filterCenters.value.includes(center)
    && (filterSolTypes.value.includes(solType) || filterSolTypes.value.length === 0);
}

function describeStream(gs: string): string {
  const parts = gs.split('.');
  if (parts.length < 4) return gs;
  const ctr     = PROC_CENTERS[parts[1] ?? ''] ?? parts[1] ?? '';
  const solType = (parts[3] ?? '').substring(0, 2);
  const label   = SOL_TYPE_LABELS[solType] ?? solType;
  return `${ctr} · ${solType} ${label}`;
}

// ── Marker colours ────────────────────────────────────────────────────────────

function markerColor(site: string): string {
  if (!selectedStations.value.has(site)) return COLOR_UNSELECTED;
  const station = stationMap.get(site);
  if (!station) return COLOR_SELECTED;
  const hasEnabled = station.streams.some(gs => enabledStreams.value.has(gs));
  return hasEnabled ? COLOR_SELECTED : COLOR_NO_STREAMS;
}

function updateAllMarkers() {
  for (const [site, marker] of markers.entries()) {
    const col = markerColor(site);
    marker.setStyle({ fillColor: col });
  }
}

// ── Selection helpers ─────────────────────────────────────────────────────────

function computeEnabledStreams() {
  const s = new Set<string>();
  for (const site of selectedStations.value) {
    const station = stationMap.get(site);
    if (!station) continue;
    for (const gs of station.streams) {
      if (passesFilter(gs)) s.add(gs);
    }
  }
  enabledStreams.value = s;
}

function setStationSelected(site: string, sel: boolean) {
  const ss = new Set(selectedStations.value);
  const es = new Set(enabledStreams.value);
  const station = stationMap.get(site);
  if (sel) {
    ss.add(site);
    if (station) {
      for (const gs of station.streams) {
        if (passesFilter(gs)) es.add(gs);
      }
    }
  } else {
    ss.delete(site);
    if (station) {
      for (const gs of station.streams) es.delete(gs);
    }
  }
  selectedStations.value = ss;
  enabledStreams.value = es;
}

function toggleStream(gs: string) {
  const s = new Set(enabledStreams.value);
  if (s.has(gs)) s.delete(gs); else s.add(gs);
  enabledStreams.value = s;
  updateAllMarkers();
}

function selectAllStreams(station: StationData | null) {
  if (!station) return;
  const s = new Set(enabledStreams.value);
  for (const gs of station.streams) s.add(gs);
  enabledStreams.value = s;
  updateAllMarkers();
}

function selectNoStreams(station: StationData | null) {
  if (!station) return;
  const s = new Set(enabledStreams.value);
  for (const gs of station.streams) s.delete(gs);
  enabledStreams.value = s;
  updateAllMarkers();
}

// ── History ───────────────────────────────────────────────────────────────────

function pushHistory(sites: Set<string>) {
  const snap = [...sites].sort();
  const tail = history.value.slice(0, historyIdx.value + 1);
  tail.push(snap);
  if (tail.length > 100) tail.shift();
  history.value = tail;
  historyIdx.value = tail.length - 1;
}

function restoreHistoryAt(idx: number) {
  const snap = history.value[idx] ?? [];
  selectedStations.value = new Set(snap);
  computeEnabledStreams();
  updateAllMarkers();
  activeStation.value = null;
}

function histBack() {
  if (historyIdx.value <= 0) return;
  historyIdx.value--;
  restoreHistoryAt(historyIdx.value);
}

function histForward() {
  if (historyIdx.value >= history.value.length - 1) return;
  historyIdx.value++;
  restoreHistoryAt(historyIdx.value);
}

// ── Bulk selection ────────────────────────────────────────────────────────────

function selectAll() {
  const ss = new Set<string>(
    stations.value
      .filter(s => s.lat !== null && s.lon !== null)
      .map(s => s.site)
  );
  selectedStations.value = ss;
  computeEnabledStreams();
  pushHistory(ss);
  updateAllMarkers();
  activeStation.value = null;
}

function selectNone() {
  selectedStations.value = new Set();
  enabledStreams.value = new Set();
  pushHistory(new Set());
  updateAllMarkers();
  activeStation.value = null;
}

function selectInBounds(bounds: L.LatLngBounds) {
  let ss = unionMode.value
    ? new Set(selectedStations.value)
    : new Set<string>();

  let changed = false;
  for (const station of stations.value) {
    if (station.lat === null || station.lon === null) continue;
    if (!bounds.contains(L.latLng(station.lat, station.lon))) continue;

    if (toggleMode.value && ss.has(station.site)) {
      ss.delete(station.site);
      changed = true;
    } else if (!ss.has(station.site)) {
      ss.add(station.site);
      changed = true;
    }
  }

  if (changed || !unionMode.value) {
    selectedStations.value = ss;
    computeEnabledStreams();
    pushHistory(ss);
    updateAllMarkers();
  }
}

// ── Filters / Apply ───────────────────────────────────────────────────────────

function applyFilters() {
  computeEnabledStreams();
  updateAllMarkers();
}

// ── Load / Save ───────────────────────────────────────────────────────────────

async function loadListOptions() {
  try {
    const r = await axios.get('/api/station-lists');
    listOptions.value = r.data.lists ?? [];
  } catch {}
}

async function loadFromSelectedLists(names: string[]) {
  if (!names.length) {
    selectedStations.value = new Set();
    enabledStreams.value = new Set();
    pushHistory(new Set());
    updateAllMarkers();
    return;
  }
  const allEnabled  = new Set<string>();
  const allSelected = new Set<string>();
  for (const name of names) {
    try {
      const r = await axios.get(`/api/station-lists/${encodeURIComponent(name)}`);
      for (const gs of (r.data.geosncls ?? []) as string[]) {
        allEnabled.add(gs);
        const site = gs.split('.')[0]?.toUpperCase();
        if (site) allSelected.add(site);
      }
    } catch {}
  }
  enabledStreams.value = allEnabled;
  selectedStations.value = allSelected;
  pushHistory(allSelected);
  updateAllMarkers();
}

async function saveList() {
  const name = listName.value.trim();
  if (!name || enabledStreams.value.size === 0) return;
  const geosncls = [...enabledStreams.value].sort();
  try {
    await axios.post(`/api/station-lists/${encodeURIComponent(name)}`, { geosncls });
    $q.notify({ type: 'positive', message: `Saved "${name}" (${geosncls.length} streams)` });
    listName.value = '';
    await loadListOptions();
  } catch {
    $q.notify({ type: 'negative', message: 'Save failed' });
  }
}

// ── Map: marker click ─────────────────────────────────────────────────────────

function updatePanelPosition(station: StationData) {
  if (!map || station.lat === null || station.lon === null) return;
  const mapEl = document.getElementById('station-builder-map');
  if (!mapEl) return;
  const pt = map.latLngToContainerPoint(L.latLng(station.lat, station.lon));
  const mw = mapEl.clientWidth;
  const mh = mapEl.clientHeight;
  let left = pt.x + 14;
  let top  = pt.y - 60;
  if (left + 258 > mw) left = pt.x - 270;
  if (top < 8)         top  = 8;
  if (top + 330 > mh)  top  = mh - 335;
  panelPos.value = { left: left + 'px', top: top + 'px' };
}

function handleMarkerClick(station: StationData) {
  const wasSelected = selectedStations.value.has(station.site);
  if (wasSelected && toggleMode.value) {
    setStationSelected(station.site, false);
  } else if (!wasSelected) {
    setStationSelected(station.site, true);
  }
  pushHistory(selectedStations.value);
  updateAllMarkers();
  // Show / refresh the detail panel
  activeStation.value = station;
  nextTick(() => updatePanelPosition(station));
}

function addMarker(station: StationData) {
  const marker = L.circleMarker([station.lat!, station.lon!], {
    radius: 5,
    color: '#fff',
    weight: 1,
    fillColor: COLOR_UNSELECTED,
    fillOpacity: 0.85,
  });
  marker.bindTooltip(station.site, { direction: 'top', offset: [0, -5] });
  marker.on('click', (e) => {
    L.DomEvent.stopPropagation(e);
    handleMarkerClick(station);
  });
  marker.addTo(map!);
  markers.set(station.site, marker);
}

// ── Shift key tracking ────────────────────────────────────────────────────────

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Shift') shiftHeld.value = true;
}

function onKeyUp(e: KeyboardEvent) {
  if (e.key === 'Shift') shiftHeld.value = false;
}

// ── Rectangle selection ───────────────────────────────────────────────────────

function onRectMouseDown(e: MouseEvent) {
  if (!map) return;

  // Use the Leaflet map container's bounding rect — this is the coordinate
  // system that containerPointToLatLng expects.
  const mapContainer = map.getContainer();
  const mapRect = mapContainer.getBoundingClientRect();
  const startX = e.clientX - mapRect.left;
  const startY = e.clientY - mapRect.top;

  selRect.value = { x: startX, y: startY, w: 0, h: 0 };

  const onMove = (me: MouseEvent) => {
    const curX = me.clientX - mapRect.left;
    const curY = me.clientY - mapRect.top;
    selRect.value = {
      x: Math.min(startX, curX),
      y: Math.min(startY, curY),
      w: Math.abs(curX - startX),
      h: Math.abs(curY - startY),
    };
  };

  const onUp = (me: MouseEvent) => {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);

    const curX = me.clientX - mapRect.left;
    const curY = me.clientY - mapRect.top;
    selRect.value = null;

    const dragDist = Math.abs(curX - startX) + Math.abs(curY - startY);
    if (dragDist > 8 && map) {
      const bounds = L.latLngBounds(
        map.containerPointToLatLng(L.point(startX, startY)),
        map.containerPointToLatLng(L.point(curX, curY)),
      );
      selectInBounds(bounds);
    }
  };

  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// ── Map initialisation ────────────────────────────────────────────────────────

function initMap() {
  const mapEl = document.getElementById('station-builder-map')!;
  map = L.map(mapEl, { center: [38, -98], zoom: 4 });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(map);

  for (const station of stations.value) {
    if (station.lat !== null && station.lon !== null) addMarker(station);
  }

  // Keep detail panel aligned when map pans
  map.on('move', () => {
    if (activeStation.value) updatePanelPosition(activeStation.value);
  });
  // Close panel on any map interaction (click background, drag, zoom, scroll)
  map.on('click', () => { activeStation.value = null; });
  map.on('dragstart', () => { activeStation.value = null; });
  map.on('zoomstart', () => { activeStation.value = null; });
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);

  const [stationsRes] = await Promise.allSettled([
    axios.get('/api/station-builder/data'),
    loadListOptions(),
  ]);

  if (stationsRes.status === 'fulfilled') {
    stations.value = stationsRes.value.data.stations ?? [];
    for (const s of stations.value) stationMap.set(s.site, s);
  }
  loading.value = false;

  await nextTick();
  initMap();
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('keyup', onKeyUp);
  map?.remove();
  map = null;
});

// Watch list multiselect to load those geosncl sets onto the map
watch(selectedLists, (names) => loadFromSelectedLists(names));
</script>

<template>
  <q-page class="column no-wrap" style="height:calc(100vh - 50px); overflow:hidden">
    <PageHelp title="Station Builder">
      <p>Build reusable station lists by selecting stations on an interactive map.</p>
      <div class="help-section-label">Selecting stations</div>
      <ul>
        <li><strong>Click</strong> a dot to select or deselect a single station (turns blue when selected)</li>
        <li><strong>Shift + drag</strong> on the map to rectangle-select all stations in an area</li>
        <li>Toggle <strong>Union</strong> (add) vs <strong>Intersection</strong> (keep shared) to control how new selections combine</li>
      </ul>
      <div class="help-section-label">Filtering</div>
      <ul>
        <li>Use the center and stream-type checkboxes in the left panel to narrow visible stations</li>
        <li>Click <strong>Apply</strong> after changing filters</li>
      </ul>
      <div class="help-section-label">Saving</div>
      <ul>
        <li>Enter a name in the Save field and click <strong>Save</strong> to store the selection as a list</li>
        <li>Saved lists appear in all other pages (Completeness, Positions, PPSD, Replay)</li>
      </ul>
    </PageHelp>

    <!-- ── Top controls bar ─────────────────────────────────────────────────── -->
    <div class="row items-center q-gutter-xs q-px-sm q-py-xs flex-shrink-0"
         style="background:#f5f5f5; border-bottom:1px solid #ddd; flex-wrap:nowrap">

      <!-- Station list multiselect -->
      <q-select
        v-model="selectedLists"
        :options="listOptions"
        label="Load lists"
        dense outlined multiple use-chips
        style="min-width:200px; max-width:340px"
        class="col-auto"
      />

      <q-separator vertical class="q-mx-xs" />

      <q-btn flat dense size="sm" label="All"  color="primary" @click="selectAll" />
      <q-btn flat dense size="sm" label="None" color="grey-7"  @click="selectNone" />

      <q-separator vertical class="q-mx-xs" />

      <q-checkbox v-model="unionMode"  label="Union"  size="sm" dense color="primary" />
      <q-checkbox v-model="toggleMode" label="Toggle" size="sm" dense color="primary" />

      <q-separator vertical class="q-mx-xs" />

      <q-btn flat dense round icon="arrow_back"    size="sm"
             :disable="historyIdx <= 0" @click="histBack"
             title="Previous selection" />
      <q-btn flat dense round icon="arrow_forward" size="sm"
             :disable="historyIdx >= history.length - 1" @click="histForward"
             title="Next selection" />

      <q-separator vertical class="q-mx-xs" />

      <!-- Rectangle selection toggle -->
      <q-btn
        :flat="!rectMode" :unelevated="rectMode"
        :color="rectMode ? 'primary' : 'grey-6'"
        icon="crop_square" size="sm" dense round
        title="Drag-rectangle selection mode"
        @click="rectMode = !rectMode"
      />

      <!-- Status chip -->
      <q-chip dense color="primary" text-color="white" class="q-ml-xs"
              :label="`${selCount} sta · ${streamCount} streams`" />
    </div>

    <!-- ── Body: left filter panel + map ────────────────────────────────────── -->
    <div class="row col no-wrap" style="overflow:hidden; min-height:0">

      <!-- Left filter panel -->
      <q-scroll-area class="col-auto flex-shrink-0"
                     style="width:224px; border-right:1px solid #ddd; background:#fafafa">
        <div class="q-pa-sm">

          <div class="text-caption text-grey-6 q-mb-sm" style="line-height:1.3">
            Filters apply to selected stations' streams.
            Click <strong>Apply</strong> to update counts.
          </div>

          <!-- Processing Center -->
          <div class="text-overline text-grey-7 q-mt-xs q-mb-xs">Processing Center</div>
          <div class="column q-gutter-none q-mb-sm">
            <q-checkbox
              v-for="[k, v] in Object.entries(PROC_CENTERS)" :key="k"
              v-model="filterCenters" :val="k" dense size="sm"
              :label="`${k} – ${v}`"
            />
          </div>

          <!-- Stream Type (PPP solution + solution type combined) -->
          <div class="text-overline text-grey-7 q-mb-xs">Stream Type</div>
          <div class="column q-gutter-none q-mb-sm">
            <q-checkbox
              v-for="[k, v] in Object.entries(SOL_TYPE_LABELS)" :key="k"
              v-model="filterSolTypes" :val="k" dense size="xs"
              :label="`${k}: ${v}`"
            />
          </div>

          <!-- Apply -->
          <q-btn class="full-width q-mb-sm" size="sm" color="primary" unelevated
                 label="Apply Filters" @click="applyFilters" />

          <q-separator class="q-my-sm" />

          <!-- Save section -->
          <div class="text-overline text-grey-7 q-mb-xs">Save List</div>
          <q-input v-model="listName" label="List name" dense outlined
                   class="q-mb-sm" clearable />
          <q-btn class="full-width" size="sm" color="positive" unelevated
                 label="Save"
                 :disable="!listName.trim() || streamCount === 0"
                 @click="saveList" />

          <q-separator class="q-my-sm" />

          <!-- Legend -->
          <div class="text-overline text-grey-7 q-mb-xs">Legend</div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" :style="{ background: '#9E9E9E' }"></div>
            <span>Not selected</span>
          </div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" :style="{ background: '#1565C0' }"></div>
            <span>Selected (has streams)</span>
          </div>
          <div class="row items-center q-gutter-xs text-caption">
            <div class="legend-dot" :style="{ background: '#E65100' }"></div>
            <span>Selected (no matching streams)</span>
          </div>
        </div>
      </q-scroll-area>

      <!-- ── Map container ─────────────────────────────────────────────────── -->
      <div class="col" style="position:relative; min-height:0; overflow:hidden">

        <!-- Loading overlay -->
        <div v-if="loading"
             class="absolute-full flex flex-center"
             style="z-index:2000; background:rgba(255,255,255,0.85)">
          <q-spinner-dots color="primary" size="48px" />
        </div>

        <!-- Rectangle selection overlay: active in rectMode or while Shift is held -->
        <div
          ref="rectOverlayRef"
          :style="{
            position: 'absolute',
            inset: '0',
            cursor: (rectMode || shiftHeld) ? 'crosshair' : 'default',
            'pointer-events': (rectMode || shiftHeld) ? 'auto' : 'none',
            zIndex: 900,
            userSelect: 'none',
          }"
          @mousedown.prevent="onRectMouseDown"
        >
          <div v-if="selRect" :style="selRectStyle"
               style="position:absolute; border:2px solid #1976D2; background:rgba(25,118,210,0.1); pointer-events:none"></div>
        </div>

        <!-- Station detail panel -->
        <div
          v-if="activeStation"
          class="bg-white rounded-borders"
          :style="{ ...panelPos, position: 'absolute', width: '256px', zIndex: '800', boxShadow: '0 4px 16px rgba(0,0,0,0.22)' }"
        >
          <!-- Header -->
          <div class="row items-center q-px-sm q-pt-xs">
            <span class="text-subtitle2 col">{{ activeStation.site }}</span>
            <q-btn flat dense round icon="close" size="xs" @click="activeStation = null" />
          </div>
          <q-separator />

          <!-- Stream list -->
          <q-scroll-area style="height:220px">
            <q-list dense>
              <q-item
                v-for="gs in activeStation.streams" :key="gs"
                tag="label" dense
              >
                <q-item-section avatar style="min-width:28px; padding-right:4px">
                  <q-checkbox
                    :model-value="enabledStreams.has(gs)"
                    @update:model-value="toggleStream(gs)"
                    size="xs" dense
                  />
                </q-item-section>
                <q-item-section>
                  <q-item-label
                    class="text-caption"
                    style="font-family:monospace; font-size:10px; word-break:break-all"
                  >{{ gs }}</q-item-label>
                  <q-item-label caption style="font-size:9px">{{ describeStream(gs) }}</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-scroll-area>

          <!-- Stream all/none -->
          <q-separator />
          <div class="row q-pa-xs q-gutter-xs justify-end">
            <q-btn size="xs" flat label="All streams"  @click="selectAllStreams(activeStation)" />
            <q-btn size="xs" flat label="None" color="grey-6" @click="selectNoStreams(activeStation)" />
          </div>
        </div>

        <!-- Leaflet map mount point -->
        <div id="station-builder-map" style="height:100%; width:100%; background:#e8e8e8"></div>

      </div>
    </div>
  </q-page>
</template>

<style scoped>
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid #fff;
  box-shadow: 0 0 0 1px #aaa;
  flex-shrink: 0;
}
</style>

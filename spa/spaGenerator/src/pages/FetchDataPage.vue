<template>
  <q-page class="q-pa-md">
    <div class="row justify-center">
      <div class="col-12 col-md-11 col-lg-10">
        <q-stepper
          v-model="step"
          color="primary"
          animated
          flat
          bordered
          header-nav
        >
          <!-- ── Step 1: choose stations ─────────────────────────────────── -->
          <q-step :name="1" title="Choose stations" icon="checklist" :done="step > 1">
            <div class="text-body2 text-grey-7 q-mb-md">
              Pick one or more station lists to download position data for. Build
              lists in the <router-link to="/station-builder">Station Builder</router-link>.
            </div>

            <q-select
              v-model="selectedLists"
              :options="listOptions"
              label="Station list(s)"
              multiple use-chips dense outlined emit-value map-options
              :disable="running"
            >
              <template #option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section><q-item-label>{{ scope.opt.label }}</q-item-label></q-item-section>
                  <q-menu context-menu>
                    <q-list dense style="min-width:140px">
                      <q-item clickable v-close-popup @click.stop="confirmDeleteList(scope.opt.value)">
                        <q-item-section avatar><q-icon name="delete" color="negative" size="18px" /></q-item-section>
                        <q-item-section>Delete</q-item-section>
                      </q-item>
                    </q-list>
                  </q-menu>
                </q-item>
              </template>
            </q-select>

            <q-stepper-navigation>
              <q-btn
                color="primary" label="Continue" no-caps unelevated
                :disable="!selectedLists.length"
                @click="step = 2"
              />
            </q-stepper-navigation>
          </q-step>

          <!-- ── Step 2: date range & filters ────────────────────────────── -->
          <q-step :name="2" title="Date range & filters" icon="date_range" :done="step > 2">
            <div class="row q-gutter-sm items-center q-mb-md">
              <q-input
                v-model="startDate" label="Start date" dense outlined
                mask="####-##-##" placeholder="YYYY-MM-DD" style="width: 160px"
                :disable="running"
              />
              <q-input
                v-model="endDate" label="End date" dense outlined
                mask="####-##-##" placeholder="YYYY-MM-DD" style="width: 160px"
                :disable="running"
              />
              <q-btn flat dense round icon="event" :disable="running">
                <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                  <q-date v-model="dateRange" range mask="YYYY-MM-DD" @update:model-value="onRangeSelect">
                    <div class="row items-center justify-end">
                      <q-btn v-close-popup label="Close" color="primary" flat />
                    </div>
                  </q-date>
                </q-popup-proxy>
              </q-btn>
            </div>

            <div class="text-caption text-grey-6">Processing centers (all = no filter)</div>
            <div class="row q-gutter-xs q-mb-sm">
              <q-chip
                v-for="c in availableCenters" :key="c"
                :selected="filterCenters.includes(c)" clickable dense size="sm"
                :color="filterCenters.includes(c) ? 'primary' : 'grey-3'"
                :text-color="filterCenters.includes(c) ? 'white' : 'black'"
                :disable="running"
                @click="toggleItem(filterCenters, c)"
              >{{ c }}</q-chip>
            </div>

            <div class="text-caption text-grey-6">Stream type (all = no filter)</div>
            <div class="row q-gutter-xs q-mb-sm">
              <q-chip
                v-for="code in availableSolTypes" :key="code"
                :selected="filterSolTypes.includes(code)" clickable dense size="sm"
                :color="filterSolTypes.includes(code) ? 'primary' : 'grey-3'"
                :text-color="filterSolTypes.includes(code) ? 'white' : 'black'"
                :disable="running"
                @click="toggleItem(filterSolTypes, code)"
              >{{ code }} {{ solTypeLabel(code) }}</q-chip>
            </div>

            <q-input
              v-model.number="workers" type="number" min="1" max="50"
              label="Parallel workers" dense outlined style="width: 160px"
              :disable="running"
            />

            <q-stepper-navigation>
              <q-btn color="primary" label="Continue" no-caps unelevated :disable="!datesValid" @click="step = 3" />
              <q-btn flat color="grey-7" label="Back" no-caps class="q-ml-sm" @click="step = 1" />
            </q-stepper-navigation>
          </q-step>

          <!-- ── Step 3: review & fetch ──────────────────────────────────── -->
          <q-step :name="3" title="Fetch" icon="cloud_download">
            <div class="text-body2 q-mb-sm">
              <div><strong>Lists:</strong> {{ selectedLists.join(", ") || "—" }}</div>
              <div><strong>Range:</strong> {{ startDate || "—" }} → {{ endDate || "—" }}</div>
              <div v-if="filterCenters.length && filterCenters.length < availableCenters.length">
                <strong>Centers:</strong> {{ filterCenters.join(", ") }}
              </div>
              <div v-if="filterSolTypes.length && filterSolTypes.length < availableSolTypes.length">
                <strong>Stream types:</strong> {{ filterSolTypes.join(", ") }}
              </div>
              <div><strong>Workers:</strong> {{ workers }}</div>
            </div>

            <div class="row q-gutter-sm q-mb-md">
              <q-btn
                v-if="!running"
                color="primary" icon="cloud_download" label="Start fetch" no-caps unelevated
                :disable="!canStart"
                @click="startFetch"
              />
              <q-btn v-else color="negative" icon="stop" label="Cancel" no-caps outline @click="cancel" />
              <q-btn flat color="grey-7" label="Back" no-caps :disable="running" @click="step = 2" />
              <q-btn
                v-if="done && exitCode === 0"
                flat color="primary" icon="grid_on" label="View Completeness" no-caps to="/completeness"
              />
            </div>

            <!-- Progress -->
            <q-card v-if="running || done" flat bordered class="q-mb-md">
              <q-card-section class="q-py-sm">
                <div class="row items-center q-gutter-sm">
                  <q-spinner v-if="running" color="primary" size="18px" />
                  <q-icon v-else-if="exitCode === 0" name="check_circle" color="positive" size="18px" />
                  <q-icon v-else name="error" color="negative" size="18px" />
                  <div class="col text-caption">
                    {{ total > 0 ? `Day ${current} of ${total}` : (running ? "Starting…" : "Finished") }}
                  </div>
                </div>
                <q-linear-progress
                  v-if="total > 0" :value="current / total"
                  color="primary" track-color="grey-3" rounded class="q-mt-xs" size="8px"
                />
              </q-card-section>
            </q-card>

            <!-- Log -->
            <q-card flat bordered>
              <q-card-section class="q-pb-xs row items-center">
                <div class="text-subtitle2 text-weight-medium col">Log</div>
                <q-badge v-if="running" color="primary" label="Running" />
              </q-card-section>
              <q-separator />
              <q-card-section class="log-section" ref="logEl">
                <div v-if="!logs.length" class="text-grey-5 text-caption">
                  Click “Start fetch” to download missing data.
                </div>
                <div
                  v-for="(entry, i) in logs" :key="i"
                  class="log-line"
                  :class="entry.isError ? 'text-negative' : entry.isDone ? 'text-positive text-weight-medium' : ''"
                >{{ entry.text }}</div>
              </q-card-section>
            </q-card>
          </q-step>
        </q-stepper>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { useFetchJob } from "../composables/useFetchJob";
import { useListDelete } from "../composables/useListDelete";
import {
  solTypeLabel, sortSolTypes, defaultSelectedCenters, defaultSelectedStreamTypes,
} from "../constants/streamTypes";

const {
  step, selectedLists, startDate, endDate, filterCenters, filterSolTypes, workers,
  logs, running, done, exitCode, current, total, start, cancel,
} = useFetchJob();

const listOptions       = ref<{ label: string; value: string }[]>([]);
const availableCenters  = ref<string[]>([]);
const availableSolTypes = ref<string[]>([]);
const dateRange         = ref<{ from: string; to: string } | null>(null);
const logEl             = ref<{ $el?: HTMLElement } | null>(null);

const datesValid = computed(() => startDate.value.length === 10 && endDate.value.length === 10);
const canStart   = computed(() => selectedLists.value.length > 0 && datesValid.value && !running.value);

function toggleItem(list: string[], item: string): void {
  const i = list.indexOf(item);
  if (i >= 0) list.splice(i, 1); else list.push(item);
}

function onRangeSelect(val: { from: string; to: string } | null) {
  if (!val) return;
  startDate.value = val.from;
  endDate.value = val.to;
}

async function loadListOptions() {
  try {
    const res = await fetch("/api/station-lists");
    const data = await res.json();
    listOptions.value = (data.lists ?? []).map((l: string) => ({ label: l, value: l }));
  } catch { listOptions.value = []; }
}

async function fetchFilterOptions() {
  try {
    const params = new URLSearchParams();
    for (const l of selectedLists.value) params.append("lists", l);
    const res = await fetch(`/api/station-lists/filter-options?${params}`);
    if (!res.ok) return;
    const data = await res.json();
    availableCenters.value  = data.centers  ?? [];
    availableSolTypes.value = sortSolTypes(data.sol_types ?? []);
    // Selected per the default-selected flags in constants/streamTypes.ts.
    // Keep any prior choices the user already made this session.
    if (!filterCenters.value.length)  filterCenters.value  = defaultSelectedCenters(availableCenters.value);
    if (!filterSolTypes.value.length) filterSolTypes.value = defaultSelectedStreamTypes(availableSolTypes.value);
  } catch { /* ignore */ }
}

const { confirmDeleteList } = useListDelete(loadListOptions);

async function scrollLog() {
  await nextTick();
  const el = logEl.value?.$el ?? (logEl.value as unknown as HTMLElement | null);
  if (el) el.scrollTop = el.scrollHeight;
}

function startFetch() {
  if (!canStart.value) return;
  const centersSubset  = filterCenters.value.length < availableCenters.value.length;
  const solSubset      = filterSolTypes.value.length < availableSolTypes.value.length;
  start({
    lists: [...selectedLists.value],
    filter_centers:   centersSubset ? [...filterCenters.value] : [],
    filter_sol_types: solSubset ? [...filterSolTypes.value] : [],
    start: startDate.value,
    end: endDate.value,
    workers: workers.value,
  });
}

onMounted(async () => {
  await loadListOptions();
  await fetchFilterOptions();
});

// Refresh available filters when the list selection changes; reset filter
// choices to "all" so they map to the new lists.
watch(selectedLists, async () => {
  filterCenters.value = [];
  filterSolTypes.value = [];
  await fetchFilterOptions();
});

watch(logs, () => { scrollLog(); }, { deep: true });
</script>

<style scoped>
.log-section {
  font-family: monospace;
  font-size: 0.78rem;
  max-height: 45vh;
  overflow-y: auto;
  overflow-x: auto;
}
/* Keep each log line intact (don't wrap the trailing date); scroll if too long. */
.log-line { line-height: 1.5; white-space: pre; }
</style>

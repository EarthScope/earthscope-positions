<template>
  <q-page class="q-pa-md">
    <div class="row q-col-gutter-md">

      <!-- ── Left: configuration ─────────────────────────────────────────── -->
      <div class="col-12 col-md-4 col-lg-3">
        <q-card flat bordered class="config-card">
          <q-card-section class="q-pb-xs">
            <div class="text-subtitle1 text-weight-medium">Convert / Export</div>
            <div class="text-caption text-grey-6">Arrow → MiniSEED / GeoJSON</div>
          </q-card-section>
          <q-separator />
          <q-card-section class="q-gutter-sm">

            <!-- Format -->
            <div class="text-caption text-grey-6">Output format</div>
            <q-btn-toggle
              v-model="format"
              spread no-caps dense unelevated
              :disable="running"
              toggle-color="primary"
              :options="[
                { label: 'MiniSEED', value: 'miniseed' },
                { label: 'GeoJSON',  value: 'geojson'  },
              ]"
            />

            <!-- GeoJSON sub-format -->
            <template v-if="format === 'geojson'">
              <div class="text-caption text-grey-6 q-mt-xs">GeoJSON variant</div>
              <q-btn-toggle
                v-model="gjFormat"
                spread no-caps dense unelevated
                :disable="running"
                toggle-color="teal"
                :options="[
                  { label: 'Compact', value: 'compact' },
                  { label: 'Full',    value: 'full'    },
                  { label: 'Both',    value: 'both'    },
                ]"
              />
            </template>

            <!-- Stream lists -->
            <q-select
              v-model="selectedLists"
              :options="listOptions"
              label="Stream list(s)"
              multiple use-chips dense outlined emit-value map-options
              :disable="running"
              class="q-mt-sm"
            />

            <!-- Date range -->
            <div class="row q-gutter-xs">
              <q-input v-model="startDate" label="Start date" dense outlined class="col"
                mask="####-##-##" placeholder="YYYY-MM-DD" :disable="running">
                <template #append>
                  <q-icon name="event" size="xs" class="cursor-pointer">
                    <q-popup-proxy ref="fromPopup" cover transition-show="scale" transition-hide="scale">
                      <q-date :model-value="null" range mask="YYYY-MM-DD" @update:model-value="onFromBoxSelect">
                        <div class="row items-center justify-end">
                          <q-btn v-close-popup label="Close" color="primary" flat />
                        </div>
                      </q-date>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
              <q-input v-model="endDate" label="End date" dense outlined class="col"
                mask="####-##-##" placeholder="YYYY-MM-DD" :disable="running">
                <template #append>
                  <q-icon name="event" size="xs" class="cursor-pointer">
                    <q-popup-proxy ref="toPopup" cover transition-show="scale" transition-hide="scale">
                      <q-date :model-value="null" range mask="YYYY-MM-DD" @update:model-value="onToBoxSelect">
                        <div class="row items-center justify-end">
                          <q-btn v-close-popup label="Close" color="primary" flat />
                        </div>
                      </q-date>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
            </div>

            <q-toggle v-model="force" label="Overwrite existing files" dense :disable="running" />

          </q-card-section>
          <q-separator />
          <q-card-section class="q-gutter-sm">
            <q-btn
              class="full-width"
              color="primary" icon="sync_alt" label="Convert" no-caps unelevated
              :disable="!canRun || running"
              @click="runExport"
            />
            <q-btn
              v-if="running"
              class="full-width" flat color="negative" icon="stop" label="Cancel" no-caps
              @click="cancelExport"
            />
          </q-card-section>
        </q-card>
      </div>

      <!-- ── Right: path-spec editor + log ───────────────────────────────── -->
      <div class="col-12 col-md-8 col-lg-9">

        <!-- Path-spec editor -->
        <q-card flat bordered class="q-mb-md">
          <q-card-section class="q-pb-xs row items-center">
            <div class="text-subtitle1 text-weight-medium col">
              Output path template
              <span class="text-caption text-grey-6">({{ specFileName || specFileFor(format) }})</span>
            </div>
            <q-btn flat dense no-caps size="sm" icon="refresh" label="Reload"
              :disable="specLoading || running" @click="loadSpec(true)" />
            <q-btn flat dense no-caps size="sm" icon="save" label="Save spec" color="primary"
              :loading="specSaving" :disable="specLoading || running" @click="saveSpec" />
          </q-card-section>
          <q-separator />
          <q-card-section class="q-pt-sm">
            <div class="text-caption text-grey-6 q-mb-xs">
              Controls the output directory structure &amp; filenames. Edit, click
              <b>Save spec</b>, then <b>Convert</b> (enable overwrite to remake existing files).
            </div>
            <q-input
              v-model="specContent"
              type="textarea"
              outlined dense
              class="spec-editor"
              input-style="font-family: monospace; font-size: 12px; min-height: 320px;"
              :disable="specLoading || running"
              :error="!!specError"
              :error-message="specError"
            />
          </q-card-section>
        </q-card>

        <!-- Progress + log -->
        <q-card flat bordered class="log-card">
          <q-card-section class="q-pb-xs row items-center">
            <div class="text-subtitle1 text-weight-medium col">Log</div>
            <q-badge v-if="running" color="primary" label="Running" class="q-mr-xs" />
            <q-icon v-else-if="done && exitCode === 0" name="check_circle" color="positive" size="18px" />
            <q-icon v-else-if="done" name="error" color="negative" size="18px" />
          </q-card-section>
          <q-separator />
          <q-card-section class="log-section" ref="logEl">
            <div v-if="!logs.length" class="text-grey-5 text-caption">
              Choose a format, stream list(s), and date range, then click Convert.
            </div>
            <div
              v-for="(entry, i) in logs" :key="i"
              class="log-line"
              :class="entry.isError ? 'text-negative' : entry.isDone ? 'text-positive text-weight-medium' : ''"
            >{{ entry.text }}</div>
          </q-card-section>
        </q-card>

      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue";
import { useQuasar } from "quasar";
import { getStreamLists, getExportSpec, saveExportSpec } from "../api";
import { useExportJob } from "../composables/useExportJob";
import type { ExportFormat } from "../composables/useExportJob";
import { createBoxRangeSelectHandler } from "../utils/dateRangePicker";

const $q = useQuasar();

// Persisted across navigation (config + editor + running job with live logs).
const {
  format, gjFormat, selectedLists, startDate, endDate, force,
  specContent, specFileName, specFormatLoaded,
  logs, running, done, exitCode,
  start, cancel,
} = useExportJob();

// View-local (not persisted)
const listOptions = ref<{ label: string; value: string }[]>([]);
const specLoading = ref(false);
const specSaving  = ref(false);
const specError   = ref("");
const logEl       = ref<{ $el?: HTMLElement } | null>(null);

// ── Computed ────────────────────────────────────────────────────────────────────
const canRun = computed(() =>
  selectedLists.value.length > 0
  && startDate.value.length === 10
  && endDate.value.length === 10
);

function specFileFor(f: ExportFormat): string {
  return f === "miniseed" ? "miniseed_path_spec.toml" : "geojson_path_spec.toml";
}

// ── Helpers ──────────────────────────────────────────────────────────────────────
const fromPopup = ref<{ hide?: () => void } | null>(null);
const toPopup   = ref<{ hide?: () => void } | null>(null);
const onFromBoxSelect = createBoxRangeSelectHandler(
  (date) => { startDate.value = date; if (!endDate.value) endDate.value = date; },
  (from, to) => { startDate.value = from; endDate.value = to; },
  () => fromPopup.value?.hide?.(),
);
const onToBoxSelect = createBoxRangeSelectHandler(
  (date) => { endDate.value = date; if (!startDate.value) startDate.value = date; },
  (from, to) => { startDate.value = from; endDate.value = to; },
  () => toPopup.value?.hide?.(),
);

async function scrollLog() {
  await nextTick();
  const el = logEl.value?.$el ?? (logEl.value as unknown as HTMLElement | null);
  if (el) el.scrollTop = el.scrollHeight;
}

async function loadListOptions() {
  try {
    const r = await getStreamLists();
    listOptions.value = r.lists.map(l => ({ label: l, value: l }));
  } catch { listOptions.value = []; }
}

async function loadSpec(forceReload = false) {
  // Don't clobber unsaved edits already loaded for this format.
  if (!forceReload && specFormatLoaded.value === format.value && specContent.value) return;
  specLoading.value = true;
  specError.value = "";
  try {
    const r = await getExportSpec(format.value);
    specContent.value = r.content;
    specFileName.value = r.path;
    specFormatLoaded.value = format.value;
  } catch (e: any) {
    specError.value = e?.response?.data?.error ?? "Failed to load spec.";
  } finally {
    specLoading.value = false;
  }
}

async function saveSpec() {
  specSaving.value = true;
  specError.value = "";
  try {
    await saveExportSpec(format.value, specContent.value);
    $q.notify({ type: "positive", message: `Saved ${specFileName.value || specFileFor(format.value)}` });
  } catch (e: any) {
    specError.value = e?.response?.data?.error ?? "Failed to save spec.";
  } finally {
    specSaving.value = false;
  }
}

function runExport() {
  if (!canRun.value || running.value) return;
  start();
}

function cancelExport() {
  cancel();
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadListOptions();
  await loadSpec();       // no-op if already loaded for the current format
  scrollLog();            // if we returned mid-run, jump to the latest logs
});

// Reload the spec when switching format (unless we already have it for that one).
watch(format, () => { loadSpec(); });

// Keep the log scrolled to the newest line as it streams.
watch(logs, () => { scrollLog(); }, { deep: true });
</script>

<style scoped>
.config-card { position: sticky; top: 16px; }
.log-card { min-height: 180px; }
.log-section {
  font-family: monospace;
  font-size: 0.78rem;
  max-height: 40vh;
  overflow-y: auto;
  overflow-x: auto;
}
.log-line { line-height: 1.5; white-space: pre; }
</style>

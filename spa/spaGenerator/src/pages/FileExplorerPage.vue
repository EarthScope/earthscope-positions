<template>
  <q-page class="row no-wrap" style="height: calc(100vh - 50px); overflow: hidden">

    <!-- ── Left: tree, rooted at the data directory ──────────────────────── -->
    <div class="col-auto column no-wrap bg-grey-1 border-right" style="width: 320px; min-width: 220px">
      <div class="q-px-sm q-pt-sm q-pb-xs flex-shrink-0">
        <div class="text-caption text-weight-medium text-grey-7">File Explorer</div>
        <div class="text-caption text-grey-5" style="word-break: break-all">{{ rootPath }}</div>
      </div>
      <q-separator />

      <q-scroll-area class="col">
        <div v-if="rootLoading" class="flex flex-center q-pa-md">
          <q-spinner-dots color="primary" size="28px" />
        </div>
        <q-list v-else dense>
          <template v-for="{ node, depth } in flatTree" :key="node.path">
            <q-item
              dense clickable
              :active="node.type === 'file' && isSelected(node.path)"
              active-class="bg-blue-1"
              :style="{ paddingLeft: (depth * 16 + 4) + 'px' }"
              :data-file-path="node.path"
              @click="handleClick(node)"
            >
              <!-- Tick to add a picture to the side-by-side stack.  Only on the
                   kinds whose whole preview is one image; @click.stop so ticking
                   does not also change the single selection. -->
              <q-item-section
                v-if="isCheckable(node)"
                side
                style="min-width: 24px; padding-right: 0"
              >
                <q-checkbox
                  dense
                  size="xs"
                  :model-value="isChecked(node.path)"
                  @click.stop
                  @update:model-value="toggleChecked(node)"
                />
              </q-item-section>
              <q-item-section avatar style="min-width: 22px; padding-right: 4px">
                <q-icon
                  v-if="node.type === 'dir'"
                  name="chevron_right" size="16px" color="grey-6"
                  :class="['caret-icon', expanded.has(node.path) && 'caret-open']"
                />
                <q-icon v-else :name="kindIcon(node.kind)" size="15px" :color="kindColor(node.kind)" />
              </q-item-section>

              <q-item-section>
                <q-item-label class="text-caption" style="word-break: break-all">{{ node.name }}</q-item-label>
                <q-item-label v-if="node.type === 'file' && node.size != null" caption class="text-grey-5">
                  {{ fmtSize(node.size) }}
                </q-item-label>
              </q-item-section>

              <q-item-section v-if="node.type === 'dir' && loadingPaths.has(node.path)" side>
                <q-spinner size="12px" color="grey-5" />
              </q-item-section>
            </q-item>
          </template>

          <q-item v-if="!rootLoading && tree.length === 0" dense>
            <q-item-section>
              <q-item-label class="text-caption text-grey-5 q-pa-sm">Data directory is empty</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-scroll-area>
    </div>

    <!-- ── Right: preview / summary + file actions ───────────────────────── -->
    <div class="col column no-wrap bg-white" style="overflow: hidden">

      <div v-if="!selectedPath && !multiSelected" class="col flex flex-center text-grey-4">
        <div class="text-center">
          <q-icon name="folder_open" size="64px" />
          <div class="text-caption q-mt-sm">Select a file from the tree</div>
        </div>
      </div>

      <template v-else>
        <!-- Action bar -->
        <div class="row items-center q-pa-sm q-gutter-xs flex-shrink-0 border-bottom">
          <div v-if="multiSelected" class="col text-caption text-grey-7">
            {{ checked.length }} image{{ checked.length === 1 ? "" : "s" }} checked
            <q-btn flat dense no-caps size="sm" label="Clear" color="grey-8"
                   class="q-ml-xs" @click="clearChecked" />
          </div>
          <div v-else class="col text-caption text-grey-7" style="word-break: break-all">
            {{ selectedPath }}
            <span v-if="summary?.size != null" class="text-grey-5"> — {{ fmtSize(summary.size) }}</span>
          </div>
          <!-- Rename/Delete act on one file, so they are hidden while several
               are shown rather than silently applying to just the last one. -->
          <template v-if="!multiSelected">
            <q-btn v-if="summary?.editable" flat dense no-caps size="sm" icon="edit_note"
                   label="Edit" color="primary" @click="openEdit" />
            <q-btn flat dense no-caps size="sm" icon="drive_file_rename_outline"
                   label="Rename" color="grey-8" @click="openRename" />
            <q-btn flat dense no-caps size="sm" icon="delete" label="Delete"
                   color="negative" @click="openDelete" />
          </template>
        </div>

        <!-- Every checked picture, one panel each, in tree order -->
        <q-scroll-area v-if="multiSelected" class="col">
          <div class="q-pa-md">
            <div class="text-subtitle2 q-mb-sm">
              {{ checked.length }} image{{ checked.length === 1 ? "" : "s" }}
            </div>
            <div v-for="c in checkedInTreeOrder" :key="c.path" class="q-mb-lg">
              <div class="row items-center no-wrap q-mb-xs">
                <div class="col text-caption text-grey-7" style="word-break: break-all">
                  {{ c.path }}
                </div>
                <q-btn flat dense round size="sm" icon="close" color="grey-6"
                       @click="checked = checked.filter(x => x.path !== c.path)">
                  <q-tooltip>Uncheck this one</q-tooltip>
                </q-btn>
              </div>
              <img
                :src="previewUrlFor(c)" :alt="c.path"
                style="max-width: 100%; height: auto; border: 1px solid #e0e0e0; border-radius: 4px"
              />
            </div>
          </div>
        </q-scroll-area>

        <q-scroll-area v-else class="col">
          <div class="q-pa-md">
            <div v-if="summaryLoading" class="flex flex-center q-pa-xl">
              <q-spinner-dots color="primary" size="40px" />
            </div>

            <template v-else-if="summary">
              <!-- Images render as before -->
              <div v-if="summary.kind === 'image'" class="column items-center">
                <img :src="downloadUrl" :alt="selectedPath"
                     style="max-width: 100%; height: auto; border: 1px solid #e0e0e0" />
              </div>

              <template v-else>
                <q-banner v-if="summary.error" dense class="bg-orange-1 text-orange-9 q-mb-md">
                  Could not summarize this file: {{ summary.error }}
                  <div class="text-caption">Rename and delete still work.</div>
                </q-banner>

                <!-- Plot the samples the file actually contains -->
                <template v-if="summary.plottable && !summary.error">
                  <div class="text-subtitle2 q-mb-xs">
                    {{ summary.kind === 'miniseed' ? 'Waveform' : 'Time series' }}
                  </div>
                  <div v-if="plotFailed" class="text-caption text-orange-9 q-mb-md">
                    Could not plot this file — the summary below still applies.
                  </div>
                  <img
                    v-else
                    :src="plotUrl" :alt="`Waveform of ${selectedPath}`"
                    class="q-mb-md"
                    style="max-width: 100%; height: auto; border: 1px solid #e0e0e0; border-radius: 4px"
                    @error="plotFailed = true"
                  />
                </template>

                <div class="text-subtitle2 q-mb-xs">{{ kindLabel(summary.kind) }}</div>
                <q-markup-table v-if="summary.rows?.length" flat bordered dense
                                class="q-mb-md" style="max-width: 560px">
                  <tbody>
                    <tr v-for="([k, v], i) in summary.rows" :key="i">
                      <td class="text-grey-7" style="width: 40%">{{ k }}</td>
                      <td class="text-weight-medium">{{ v }}</td>
                    </tr>
                  </tbody>
                </q-markup-table>
                <div v-else-if="!summary.error" class="text-caption text-grey-6 q-mb-md">
                  No summary available for this file type.
                </div>

                <!-- Arrow: column schema -->
                <template v-if="summary.schema?.length">
                  <div class="text-subtitle2 q-mb-xs">Columns</div>
                  <q-markup-table flat bordered dense style="max-width: 560px">
                    <thead>
                      <tr><th class="text-left">Name</th><th class="text-left">Type</th><th class="text-right">Nulls</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in summary.schema" :key="c.name">
                        <td>{{ c.name }}</td><td class="text-grey-7">{{ c.type }}</td>
                        <td class="text-right">{{ c.nulls.toLocaleString() }}</td>
                      </tr>
                    </tbody>
                  </q-markup-table>
                </template>

                <!-- Arrow: continuous blocks -->
                <template v-if="summary.blocks?.length">
                  <div class="text-subtitle2 q-mb-xs q-mt-md">
                    Continuous blocks
                    <span
                      v-if="summary.blocks_total && summary.blocks_total > summary.blocks.length"
                      class="text-caption text-grey-6 text-weight-regular"
                    >
                      — first {{ summary.blocks.length }} of
                      {{ summary.blocks_total.toLocaleString() }}
                    </span>
                  </div>
                  <q-markup-table flat bordered dense style="max-width: 560px">
                    <thead>
                      <tr>
                        <th class="text-left">#</th>
                        <th class="text-left">Start</th>
                        <th class="text-left">End</th>
                        <th class="text-right">Duration</th>
                        <th class="text-right">Samples</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(b, i) in summary.blocks" :key="i">
                        <td class="text-grey-7">{{ i + 1 }}</td>
                        <td>{{ b.start }}</td>
                        <td>{{ b.end }}</td>
                        <td class="text-right">{{ b.duration }}</td>
                        <td class="text-right">{{ b.samples.toLocaleString() }}</td>
                      </tr>
                    </tbody>
                  </q-markup-table>
                </template>

                <!-- MiniSEED: channels -->
                <template v-if="summary.channels?.length">
                  <div class="text-subtitle2 q-mb-xs">Channels</div>
                  <q-markup-table flat bordered dense style="max-width: 560px">
                    <thead>
                      <tr><th class="text-left">Source ID</th><th class="text-right">Samples</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in summary.channels" :key="c.name">
                        <td>{{ c.name }}</td><td class="text-right">{{ c.samples.toLocaleString() }}</td>
                      </tr>
                    </tbody>
                  </q-markup-table>
                </template>

                <!-- CSV: per-column detail -->
                <template v-if="summary.columns?.length">
                  <div class="text-subtitle2 q-mb-xs">Columns</div>
                  <q-markup-table flat bordered dense class="q-mb-md" style="max-width: 720px">
                    <thead>
                      <tr>
                        <th class="text-left">Name</th>
                        <th class="text-right">Filled</th>
                        <th class="text-right">Blank</th>
                        <th class="text-left">Range / values</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in summary.columns" :key="c.name">
                        <td>{{ c.name }}</td>
                        <td class="text-right">{{ c.filled.toLocaleString() }}</td>
                        <td class="text-right" :class="c.blank ? 'text-orange-9' : 'text-grey-5'">
                          {{ c.blank.toLocaleString() }}
                        </td>
                        <td class="text-grey-7">{{ c.detail }}</td>
                      </tr>
                    </tbody>
                  </q-markup-table>
                </template>

                <!-- TOML: flattened settings -->
                <template v-if="summary.settings?.length">
                  <div class="text-subtitle2 q-mb-xs">Settings</div>
                  <q-markup-table flat bordered dense class="q-mb-md" style="max-width: 720px">
                    <thead>
                      <tr><th class="text-left">Key</th><th class="text-left">Value</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="st in summary.settings" :key="st.key">
                        <td style="white-space: nowrap">{{ st.key }}</td>
                        <td class="text-weight-medium" style="word-break: break-all">{{ st.value }}</td>
                      </tr>
                    </tbody>
                  </q-markup-table>
                </template>

                <!-- JSONL / CSV / GeoJSON: first lines -->
                <template v-if="summary.sample?.length">
                  <div class="text-subtitle2 q-mb-xs">
                    First {{ summary.sample.length }} line(s)
                    <span v-if="summary.sample_total && summary.sample_total > summary.sample.length"
                          class="text-caption text-grey-6">
                      of {{ summary.sample_total.toLocaleString() }}
                    </span>
                  </div>
                  <pre class="sample-block">{{ summary.sample.join('\n') }}</pre>
                </template>
              </template>
            </template>
          </div>
        </q-scroll-area>
      </template>
    </div>

    <!-- ── Edit dialog ───────────────────────────────────────────────────── -->
    <q-dialog v-model="editOpen" maximized>
      <q-card class="column no-wrap">
        <q-card-section class="row items-center q-py-sm bg-primary text-white">
          <q-icon name="edit_note" class="q-mr-sm" />
          <div class="text-subtitle1">Edit</div>
          <div class="text-caption q-ml-sm" style="opacity:.85; word-break: break-all">{{ selectedPath }}</div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup :disable="editSaving" />
        </q-card-section>
        <q-banner v-if="editError" dense class="bg-red-1 text-negative">{{ editError }}</q-banner>
        <q-card-section class="col q-pa-none" style="min-height: 0">
          <q-input v-model="editContent" type="textarea" outlined class="edit-area fit"
                   input-class="edit-area-input" :disable="editSaving" />
        </q-card-section>
        <q-separator />
        <q-card-actions align="right" class="q-pa-md">
          <div class="text-caption text-grey-6 q-mr-auto">{{ editLineCount }} non-blank line(s)</div>
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="editSaving" />
          <q-btn no-caps unelevated color="primary" label="Save" :loading="editSaving" @click="saveEdit" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Rename dialog ─────────────────────────────────────────────────── -->
    <q-dialog v-model="renameOpen">
      <q-card style="min-width: 420px">
        <q-card-section class="text-subtitle1">Rename file</q-card-section>
        <q-card-section class="q-pt-none">
          <q-input v-model="renameValue" dense outlined autofocus label="New name"
                   :error="!!renameError" :error-message="renameError"
                   @keyup.enter="doRename" />
          <div class="text-caption text-grey-6 q-mt-xs">
            Name only — the file stays in the same directory.
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="renameSaving" />
          <q-btn unelevated no-caps color="primary" label="Rename"
                 :loading="renameSaving" :disable="!renameValue.trim()" @click="doRename" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Delete confirm ────────────────────────────────────────────────── -->
    <q-dialog v-model="deleteOpen">
      <q-card style="min-width: 420px">
        <q-card-section class="row items-center">
          <q-icon name="warning" color="negative" size="28px" class="q-mr-sm" />
          <div class="text-subtitle1">Delete this file?</div>
        </q-card-section>
        <q-card-section class="q-pt-none text-caption" style="word-break: break-all">
          {{ selectedPath }}
          <div class="text-grey-6 q-mt-xs">This cannot be undone.</div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="deleting" />
          <q-btn unelevated no-caps color="negative" label="Delete"
                 :loading="deleting" @click="doDelete" />
        </q-card-actions>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from "vue";
import { useRoute } from "vue-router";
import { useQuasar } from "quasar";
import axios from "axios";

const route = useRoute();
const $q = useQuasar();

interface Entry {
  name: string;
  type: "file" | "dir";
  path: string;
  kind: string;
  /** For .arrow only: "positions" | "completeness" | "ppsd". */
  arrowKind?: string | null;
  size: number | null;
  mtime: number;
}
interface TreeNode extends Entry { children: TreeNode[] | null }

interface Summary {
  path: string; name: string; kind: string; size: number; mtime: number;
  editable: boolean;
  rows?: [string, string][];
  schema?: { name: string; type: string; nulls: number }[];
  /** Arrow only: uninterrupted runs of samples. One block = no restarts. */
  blocks?: { start: string; end: string; duration: string; samples: number }[];
  /** Total blocks before the listing cap, so the header can say what is elided. */
  blocks_total?: number;
  channels?: { name: string; samples: number }[];
  columns?: { name: string; filled: number; blank: number; detail: string }[];
  settings?: { key: string; value: string }[];
  stations?: string[];
  sample?: string[];
  sample_total?: number;
  plottable?: boolean;
  error?: string;
}

const tree         = ref<TreeNode[]>([]);
const expanded     = ref(new Set<string>());
const loadingPaths = ref(new Set<string>());
const rootLoading  = ref(false);
const rootPath     = ref("");

const selectedPath   = ref("");
//: Files ticked for side-by-side viewing.  Empty whenever a single file is
//: being previewed, so every existing single-file code path is untouched.
const checked        = ref<{ path: string; kind: string; arrowKind?: string | null }[]>([]);
const summary        = ref<Summary | null>(null);
const summaryLoading = ref(false);

const downloadUrl = computed(() =>
  selectedPath.value ? `/api/files/download?path=${encodeURIComponent(selectedPath.value)}` : "");

// Server-rendered: a station-day at 1 Hz is 86,400 samples per channel, far
// more than is worth shipping to the browser for a preview.
function plotUrlFor(path: string): string {
  return path ? `/api/files/plot?path=${encodeURIComponent(path)}` : "";
}
const plotUrl = computed(() => plotUrlFor(selectedPath.value));

/** How to render one checked file: a stored image is served directly, a PPSD
 *  array has to be rendered to a PNG first. */
function previewUrlFor(c: { path: string; kind: string }): string {
  return c.kind === "image"
    ? `/api/files/download?path=${encodeURIComponent(c.path)}`
    : plotUrlFor(c.path);
}

const multiSelected = computed(() => checked.value.length > 0);

//: Checked files in tree order, so the stack reads the same way the tree does
//: however they were ticked.
const checkedInTreeOrder = computed(() => {
  const order = new Map(flatFiles.value.map(({ node }, i) => [node.path, i]));
  return [...checked.value].sort(
    (a, b) => (order.get(a.path) ?? 1e9) - (order.get(b.path) ?? 1e9));
});
const plotFailed = ref(false);
watch(selectedPath, () => { plotFailed.value = false; });

// ── Presentation helpers ─────────────────────────────────────────────────────
const KIND_ICONS: Record<string, string> = {
  arrow: "table_chart", miniseed: "graphic_eq", geojson: "public",
  jsonl: "list_alt", image: "image", text: "description", other: "insert_drive_file",
  csv: "grid_on", toml: "settings",
};
const KIND_COLORS: Record<string, string> = {
  arrow: "teal-6", miniseed: "deep-purple-5", geojson: "green-7",
  jsonl: "blue-grey-6", image: "blue-grey-4", text: "grey-6", other: "grey-5",
  csv: "orange-7", toml: "brown-5",
};
const KIND_LABELS: Record<string, string> = {
  arrow: "Arrow position file", miniseed: "MiniSEED", geojson: "GeoJSON",
  jsonl: "JSONL list", image: "Image", text: "Text file", other: "File",
  csv: "CSV table", toml: "TOML configuration",
};
function kindIcon(k: string)  { return KIND_ICONS[k]  ?? KIND_ICONS.other; }
function kindColor(k: string) { return KIND_COLORS[k] ?? KIND_COLORS.other; }
function kindLabel(k: string) { return KIND_LABELS[k] ?? KIND_LABELS.other; }

function fmtSize(n: number | null): string {
  if (n == null) return "";
  let v = n;
  for (const unit of ["B", "KB", "MB", "GB"]) {
    if (v < 1024) return `${unit === "B" ? v : v.toFixed(1)} ${unit}`;
    v /= 1024;
  }
  return `${v.toFixed(1)} TB`;
}

const flatTree = computed<{ node: TreeNode; depth: number }[]>(() => {
  const out: { node: TreeNode; depth: number }[] = [];
  function walk(nodes: TreeNode[], depth: number) {
    for (const node of nodes) {
      out.push({ node, depth });
      if (node.type === "dir" && expanded.value.has(node.path) && node.children) {
        walk(node.children, depth + 1);
      }
    }
  }
  walk(tree.value, 0);
  return out;
});

// ── Tree ─────────────────────────────────────────────────────────────────────
function toNode(e: Entry): TreeNode { return { ...e, children: null }; }

async function fetchChildren(node: TreeNode, force = false): Promise<void> {
  if (node.children !== null && !force) return;
  loadingPaths.value.add(node.path);
  try {
    const r = await axios.get<{ entries: Entry[] }>("/api/files/list", { params: { path: node.path } });
    node.children = r.data.entries.map(toNode);
  } catch {
    node.children = [];
  } finally {
    loadingPaths.value.delete(node.path);
  }
}

async function loadRoot(): Promise<void> {
  rootLoading.value = true;
  try {
    const r = await axios.get<{ entries: Entry[]; root: string }>("/api/files/list", { params: { path: "" } });
    tree.value = r.data.entries.map(toNode);
    rootPath.value = r.data.root ?? "";
  } finally {
    rootLoading.value = false;
  }
}

/** Re-read the directory holding *path* so a rename/delete shows up. */
async function refreshParentOf(path: string): Promise<void> {
  const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
  if (!parent) { await loadRoot(); return; }
  const node = findNode(parent);
  if (node) await fetchChildren(node, true);
  else await loadRoot();
}

function findNode(path: string): TreeNode | null {
  let found: TreeNode | null = null;
  function walk(nodes: TreeNode[]) {
    for (const n of nodes) {
      if (n.path === path) { found = n; return; }
      if (n.children) walk(n.children);
      if (found) return;
    }
  }
  walk(tree.value);
  return found;
}

function toggleDir(node: TreeNode) {
  if (expanded.value.has(node.path)) expanded.value.delete(node.path);
  else { expanded.value.add(node.path); fetchChildren(node); }
}

async function selectFile(path: string) {
  selectedPath.value = path;
  summary.value = null;
  summaryLoading.value = true;
  try {
    summary.value = (await axios.get<Summary>("/api/files/summary", { params: { path } })).data;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    $q.notify({ type: "negative", message: err?.response?.data?.error ?? "Could not read file." });
    summary.value = null;
  } finally {
    summaryLoading.value = false;
  }
}

/**
 * Files whose whole preview is one picture: real images, and the PPSD arrays
 * that render as a three-panel PNG.  Those are the ones worth stacking several
 * of at once — a time series or a table gains nothing from it.
 */
function isCheckable(node: TreeNode): boolean {
  return node.type === "file" && (node.kind === "image" || node.arrowKind === "ppsd");
}

function isChecked(path: string): boolean {
  return checked.value.some((c) => c.path === path);
}

function toggleChecked(node: TreeNode) {
  if (isChecked(node.path)) {
    checked.value = checked.value.filter((c) => c.path !== node.path);
  } else {
    checked.value = [...checked.value,
      { path: node.path, kind: node.kind, arrowKind: node.arrowKind }];
  }
}

function clearChecked() { checked.value = []; }

function isSelected(path: string): boolean {
  return selectedPath.value === path || isChecked(path);
}

function handleClick(node: TreeNode) {
  if (node.type === "dir") { toggleDir(node); return; }
  // Clicking a file that is not one of the stackable kinds drops the whole
  // checked set — it is about to be replaced by a single-file preview anyway,
  // and leaving ticks behind that no longer drive the pane is worse than
  // losing them.
  if (!isCheckable(node)) clearChecked();
  selectFile(node.path);
}

// ── Edit ─────────────────────────────────────────────────────────────────────
const editOpen    = ref(false);
const editContent = ref("");
const editSaving  = ref(false);
const editError   = ref("");
const editLineCount = computed(() =>
  editContent.value ? editContent.value.split("\n").filter(l => l.trim()).length : 0);

async function openEdit() {
  editError.value = ""; editSaving.value = false;
  try {
    const r = await axios.get<{ content: string }>("/api/files/raw", { params: { path: selectedPath.value } });
    editContent.value = r.data.content ?? "";
    editOpen.value = true;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    $q.notify({ type: "negative", multiLine: true, timeout: 8000,
                message: err?.response?.data?.error ?? "Could not open file for editing." });
  }
}

async function saveEdit() {
  editSaving.value = true; editError.value = "";
  try {
    await axios.put("/api/files/raw", { path: selectedPath.value, content: editContent.value });
    $q.notify({ type: "positive", message: `Saved ${selectedPath.value}` });
    editOpen.value = false;
    await selectFile(selectedPath.value);      // counts in the summary must follow the edit
    await refreshParentOf(selectedPath.value); // size in the tree too
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    editError.value = err?.response?.data?.error ?? "Save failed.";
  } finally {
    editSaving.value = false;
  }
}

// ── Rename ───────────────────────────────────────────────────────────────────
const renameOpen   = ref(false);
const renameValue  = ref("");
const renameSaving = ref(false);
const renameError  = ref("");

function openRename() {
  renameError.value = "";
  renameValue.value = selectedPath.value.split("/").pop() ?? "";
  renameOpen.value = true;
}

async function doRename() {
  const name = renameValue.value.trim();
  if (!name) return;
  renameSaving.value = true; renameError.value = "";
  const old = selectedPath.value;
  try {
    const r = await axios.post<{ path: string }>("/api/files/rename", { path: old, name });
    renameOpen.value = false;
    await refreshParentOf(old);
    await selectFile(r.data.path);
    $q.notify({ type: "positive", message: `Renamed to ${name}` });
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    renameError.value = err?.response?.data?.error ?? "Rename failed.";
  } finally {
    renameSaving.value = false;
  }
}

// ── Delete ───────────────────────────────────────────────────────────────────
const deleteOpen = ref(false);
const deleting   = ref(false);
function openDelete() { deleteOpen.value = true; }

async function doDelete() {
  deleting.value = true;
  const target = selectedPath.value;
  try {
    await axios.delete("/api/files", { params: { path: target } });
    deleteOpen.value = false;
    selectedPath.value = ""; summary.value = null;
    await refreshParentOf(target);
    $q.notify({ type: "positive", message: `Deleted ${target}` });
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } };
    $q.notify({ type: "negative", message: err?.response?.data?.error ?? "Delete failed." });
  } finally {
    deleting.value = false;
  }
}

// ── Deep-link (?path=…) ──────────────────────────────────────────────────────
// The PPSD tab links here with a path relative to the *plots* directory, from
// when this page was rooted there. Accept both by prefixing "plots/" when the
// bare path is not present at the root.
/**
 * Reveal and select ``raw`` — used by the ?path= deep link the Completeness
 * heatmap produces when you click a cell.
 *
 * Expanding the tree down to the file is a convenience; *showing* it is the
 * point.  So a failure to walk the tree (an unfetched parent, a listing that
 * has moved on, a path the tree does not contain) falls through to selecting
 * the file anyway — the summary endpoint takes any valid path.  Landing on an
 * empty File Explorer with no explanation is the one outcome worth ruling out.
 */
async function openPath(raw: string) {
  if (!raw) return;
  const candidates = raw.startsWith("plots/") ? [raw] : [raw, `plots/${raw}`];
  for (const path of candidates) {
    const parts = path.split("/");
    let nodes = tree.value;
    let prefix = "";
    let ok = true;
    for (let i = 0; i < parts.length - 1; i++) {
      prefix = prefix ? `${prefix}/${parts[i]}` : parts[i];
      const dir = nodes.find((n) => n.path === prefix && n.type === "dir");
      if (!dir) { ok = false; break; }
      expanded.value.add(dir.path);
      await fetchChildren(dir);
      nodes = dir.children ?? [];
    }
    if (!ok) continue;
    if (!nodes.some((n) => n.path === path)) continue;
    await selectFile(path);
    await nextTick();
    document.querySelector(`[data-file-path="${path}"]`)?.scrollIntoView({ block: "nearest" });
    return;
  }
  // Tree walk failed — show the file regardless.  selectFile() reports its own
  // error if the server cannot read it either.
  await selectFile(raw);
}

// ── Keyboard navigation ──────────────────────────────────────────────────────
const flatFiles = computed(() => flatTree.value.filter(({ node }) => node.type === "file"));

function navigate(dir: 1 | -1) {
  const files = flatFiles.value;
  if (!files.length) return;
  const idx = files.findIndex(({ node }) => node.path === selectedPath.value);
  const next = idx === -1 ? 0 : Math.max(0, Math.min(files.length - 1, idx + dir));
  const target = files[next];
  if (!target || target.node.path === selectedPath.value) return;
  selectFile(target.node.path);
  nextTick(() => {
    document.querySelector(`[data-file-path="${target.node.path}"]`)?.scrollIntoView({ block: "nearest" });
  });
}

function onKeyDown(e: KeyboardEvent) {
  if (editOpen.value || renameOpen.value || deleteOpen.value) return;
  const tag = (e.target as HTMLElement)?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (e.key === "ArrowDown") { e.preventDefault(); navigate(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); navigate(-1); }
}

onMounted(async () => {
  window.addEventListener("keydown", onKeyDown);
  await loadRoot();
  const q = route.query.path;
  if (typeof q === "string" && q) await openPath(q);
});

watch(() => route.query.path, (q) => {
  if (typeof q === "string" && q && q !== selectedPath.value) openPath(q);
});

onUnmounted(() => window.removeEventListener("keydown", onKeyDown));
</script>

<style scoped>
.border-right  { border-right: 1px solid #e0e0e0; }
.border-bottom { border-bottom: 1px solid #e0e0e0; }
.caret-icon { transition: transform 0.15s ease; flex-shrink: 0; }
.caret-open { transform: rotate(90deg); }
.sample-block {
  font-family: monospace; font-size: 11px; line-height: 1.5;
  background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px;
  padding: 8px; max-width: 100%; overflow-x: auto; white-space: pre;
}
/* Quasar sizes a textarea from its content, so without stretching the field's
   own wrappers the input stays short and the rest of the maximized dialog is
   dead space.  Same rule set the other list editors use. */
.edit-area { height: 100%; }
.edit-area :deep(.q-field__control),
.edit-area :deep(.q-field__control-container) { height: 100%; }
.edit-area :deep(.edit-area-input) {
  height: 100% !important;
  font-family: monospace; font-size: 12px; line-height: 1.5; resize: none;
}
</style>

<template>
  <q-page class="q-pa-md">

    <!-- ── Page descriptions ────────────────────────────────────────────── -->
    <div class="row q-col-gutter-md q-mb-lg">
      <div class="col-12">
        <div class="text-h5 text-weight-medium q-mb-xs">GNSS Positions</div>
        <div class="text-body2 text-grey-7 q-mb-md">
          Download, store, process, visualize, and export EarthScope GNSS PPP position data.
          Use the tabs above to navigate between tools.
        </div>
      </div>

      <div v-for="page in pages" :key="page.route" class="col-12 col-sm-6 col-lg-4">
        <q-card flat bordered class="page-card full-height">
          <q-card-section class="q-pb-xs">
            <div class="row items-center no-wrap q-gutter-sm">
              <q-icon :name="page.icon" size="22px" :color="page.color" />
              <router-link :to="page.route" class="text-subtitle1 text-weight-medium nav-link">
                {{ page.label }}
              </router-link>
            </div>
          </q-card-section>
          <q-card-section class="text-body2 text-grey-8 q-pt-xs">
            {{ page.description }}
          </q-card-section>
          <q-card-section v-if="page.tips.length" class="q-pt-none">
            <ul class="tips-list text-caption text-grey-7">
              <li v-for="tip in page.tips" :key="tip">{{ tip }}</li>
            </ul>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-separator class="q-mb-lg" />

    <!-- ── Data directory (read-only mirror of `es-pos config show`) ────── -->
    <div class="text-h6 text-weight-medium q-mb-sm">Data directory</div>
    <q-card flat bordered class="q-mb-lg">
      <q-card-section v-if="cfgLoading" class="text-caption text-grey-5">Loading…</q-card-section>
      <q-card-section v-else-if="!cfg" class="text-caption text-negative">
        Could not read the data-directory configuration.
      </q-card-section>
      <template v-else>
        <q-card-section class="q-pb-none">
          <div class="row items-baseline no-wrap q-gutter-sm">
            <q-icon name="folder" size="20px" color="primary" />
            <div class="text-subtitle1 text-weight-medium" style="word-break: break-all">
              {{ cfg.data_directory }}
            </div>
            <q-badge v-if="!cfg.exists" color="orange-8" label="not created yet" />
          </div>
          <div class="text-caption text-grey-7 q-mt-xs">
            Set by {{ cfg.source_label }}
            <q-badge v-if="cfg.in_docker" color="blue-grey-6" class="q-ml-sm" label="in Docker" />
          </div>

          <!-- Environment is a property of this directory, not of the server,
               so it belongs beside the path rather than in the table below. -->
          <q-banner
            v-if="cfg.environment_badge"
            dense
            class="bg-amber-2 text-amber-10 q-mt-sm"
            style="max-width: 720px"
          >
            <template #avatar><q-icon name="science" color="amber-9" /></template>
            <div class="text-body2">
              This data directory pulls from <strong>{{ cfg.environment_label }}</strong>
              (<code>{{ cfg.api_url }}</code>).
            </div>
            <div class="text-caption q-mt-xs">
              EDIDs differ from production, so streams and positions here are not
              interchangeable with a production directory. Tokens come from the
              <code>{{ cfg.es_profile }}</code> es profile
              (<code>es user login --profile {{ cfg.es_profile }}</code>).
            </div>
          </q-banner>

          <!-- Inside a container the path above is the container path, which does
               not exist on the host; show what it is actually mounted from. -->
          <div v-if="cfg.in_docker" class="q-mt-sm">
            <q-markup-table flat dense class="cfg-table" style="max-width: 720px">
              <tbody>
                <tr>
                  <td class="text-grey-7" style="width: 34%">Inside the container</td>
                  <td><code>{{ cfg.data_directory }}</code></td>
                </tr>
                <tr>
                  <td class="text-grey-7">Mounted from the host</td>
                  <td>
                    <code v-if="cfg.host_data_directory">{{ cfg.host_data_directory }}</code>
                    <span v-else class="text-orange-9">
                      not reported — started without <code>es-pos-docker.sh run</code>?
                    </span>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
            <div class="text-caption text-grey-6 q-mt-xs">
              Change the host side with
              <code>./es-pos-docker.sh run --data-dir PATH</code>; with no flag it uses the
              same directory the host CLI would.
            </div>
          </div>
        </q-card-section>

        <q-card-section class="q-pt-sm">
          <q-markup-table flat dense class="cfg-table" style="max-width: 720px">
            <tbody>
              <tr>
                <td class="text-grey-7" style="width: 34%">Config file</td>
                <td>
                  {{ cfg.config_file }}
                  <span v-if="!cfg.config_file_exists" class="text-grey-5"> (not created yet)</span>
                </td>
              </tr>
              <tr>
                <td class="text-grey-7">Configured directory</td>
                <td>{{ cfg.configured_data_directory ?? "(not set)" }}</td>
              </tr>
              <tr>
                <td class="text-grey-7">{{ cfg.env_var }}</td>
                <td>{{ cfg.env_value ?? "(not set)" }}</td>
              </tr>
              <tr>
                <td class="text-grey-7">Environment</td>
                <td>
                  {{ cfg.environment_label }} ({{ cfg.environment }})
                  <span class="text-grey-5"> — set by {{ cfg.environment_source_label }}</span>
                </td>
              </tr>
              <tr>
                <td class="text-grey-7">API</td>
                <td><code>{{ cfg.api_url }}</code></td>
              </tr>
              <tr>
                <td class="text-grey-7">es profile</td>
                <td><code>{{ cfg.es_profile }}</code></td>
              </tr>
            </tbody>
          </q-markup-table>

          <q-banner v-if="cfg.mismatch" dense class="bg-orange-1 text-orange-9 q-mt-sm">
            {{ cfg.env_var }} is overriding the configured directory for this server.
            <div class="text-caption">
              Files written here will not be where <code>{{ cfg.config_file }}</code> points.
            </div>
          </q-banner>
        </q-card-section>

        <q-card-section class="q-pt-none">
          <div class="text-subtitle2 q-mb-xs">Contents</div>
          <q-markup-table flat bordered dense style="max-width: 720px">
            <thead>
              <tr>
                <th class="text-left">Sub-directory</th>
                <th class="text-left">Path</th>
                <th class="text-right">Entries</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in cfg.subdirectories" :key="d.name">
                <td>{{ d.name }}</td>
                <td class="text-grey-7" style="word-break: break-all">{{ d.path }}</td>
                <td class="text-right">
                  <span v-if="d.entries != null">{{ d.entries.toLocaleString() }}</span>
                  <span v-else class="text-grey-5">—</span>
                </td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>

        <q-card-section v-if="cfg.known_data_directories.length > 1" class="q-pt-none">
          <div class="text-subtitle2 q-mb-xs">Other known data directories</div>
          <q-list dense bordered class="rounded-borders" style="max-width: 720px">
            <q-item v-for="d in cfg.known_data_directories" :key="d.path" dense>
              <q-item-section avatar style="min-width: 26px">
                <q-icon :name="d.active ? 'radio_button_checked' : 'radio_button_unchecked'"
                        :color="d.active ? 'primary' : 'grey-5'" size="16px" />
              </q-item-section>
              <q-item-section>
                <q-item-label class="text-caption" style="word-break: break-all">{{ d.path }}</q-item-label>
              </q-item-section>
              <q-item-section v-if="d.environment !== 'prod'" side>
                <q-badge color="amber-8" text-color="black" :label="d.environment_label" />
              </q-item-section>
              <q-item-section v-if="!d.exists" side>
                <q-badge color="grey-5" label="missing" />
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>

        <q-card-section class="q-pt-none">
          <q-banner dense class="bg-blue-grey-1 text-blue-grey-9">
            <template #avatar><q-icon name="terminal" color="blue-grey-7" /></template>
            <div class="text-body2">Switching directories is a command-line operation.</div>
            <div class="text-caption q-mt-xs">
              The server resolves its data directory once at startup and every open tab is
              backed by it, so it deliberately cannot be changed from the browser. Use the
              CLI, then restart <code>es-pos webserver</code>:
            </div>
            <pre class="cfg-cmd">es-pos config show
es-pos config list-data-dirs
es-pos config use-data-dir 2
es-pos config set-data-dir /path/to/data
es-pos config move-data-dir /new/path

# Point a directory at the stage deployment (api.dev.earthscope.org).
# This is the only command that can; it is refused for a directory that
# already holds production data.
es-pos config use-data-dir --stage ~/earthscope-positions-stage</pre>
          </q-banner>
        </q-card-section>
      </template>
    </q-card>

    <!-- ── README ───────────────────────────────────────────────────────── -->
    <div class="text-h6 text-weight-medium q-mb-sm">README</div>
    <div v-if="readmeHtml" class="readme-body" v-html="readmeHtml" />
    <div v-else-if="loadingReadme" class="text-grey-5 text-caption">Loading…</div>

  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { marked } from "marked";
import axios from "axios";

interface DataDirConfig {
  data_directory: string;
  exists: boolean;
  source: string;
  source_label: string;
  config_file: string;
  config_file_exists: boolean;
  configured_data_directory: string | null;
  env_var: string;
  env_value: string | null;
  mismatch: boolean;
  in_docker: boolean;
  host_data_directory: string | null;
  environment: string;
  environment_label: string;
  environment_badge: boolean;
  environment_source: string;
  environment_source_label: string;
  environment_marker_file: string;
  api_url: string;
  es_profile: string;
  known_data_directories: {
    path: string; active: boolean; exists: boolean;
    environment: string; environment_label: string;
  }[];
  subdirectories: { name: string; path: string; exists: boolean; entries: number | null }[];
}

// Read-only by design: the server resolves its data directory once at startup,
// so switching it is `es-pos config use-data-dir` + a restart, not a click.
const cfg = ref<DataDirConfig | null>(null);
const cfgLoading = ref(true);

async function loadConfig() {
  try {
    cfg.value = (await axios.get<DataDirConfig>("/api/config/data-directory")).data;
  } catch {
    cfg.value = null;
  } finally {
    cfgLoading.value = false;
  }
}

const pages = [
  {
    route: "/station-list-builder",
    label: "Station List Builder",
    icon: "map",
    color: "teal",
    description:
      "Interactively down-select stations by clicking on a map, and save them as named station lists (station codes only). These feed the Stream List Builder's include/exclude sets.",
    tips: [
      "Draw a rectangle (Shift + drag) on the map to select stations in an area.",
      "Hover a station for its 4-character code; zoom in to also see its streams.",
      "Click a station's popup to Select/Deselect it, or launch a Radial Search centered on it.",
      "Save your selection as a named list (e.g. \"ShakeAlert\") for reuse.",
    ],
  },
  {
    route: "/stream-list-builder",
    label: "Stream List Builder",
    icon: "share_location",
    color: "deep-purple",
    description:
      "Pick individual streams from stations in your include/exclude station lists, and save them as named stream lists used by Fetch, Completeness, Positions, PPSD, Export and Replay.",
    tips: [
      "Choose Include/Exclude Station Lists to control which stations' streams appear on the map.",
      "Click a station to toggle all its streams, or open its panel to toggle individual streams.",
      "Use the Select Streams chips (processing center / stream type) or a regex with Only /",
      "Add matching / Remove matching to bulk-adjust the current selection.",
      "Preview / edit before saving to trim the pending list before it is written.",
    ],
  },
  {
    route: "/fetch-data",
    label: "Fetch Data",
    icon: "cloud_download",
    color: "cyan",
    description:
      "Download GNSS position data for your stream lists — a guided, three-step walkthrough (choose lists → date range & filters → fetch) with a live progress bar and log.",
    tips: [
      "Only missing (stream, day) pairs are downloaded; existing or previously-attempted data is skipped.",
      "Optionally narrow by processing center or stream type before fetching.",
      "Only one fetch runs at a time — you can switch tabs and it keeps going; when it finishes, click Restart fetch to run the same configuration again.",
    ],
  },
  {
    route: "/completeness",
    label: "Completeness & Latency",
    icon: "grid_on",
    color: "blue",
    description:
      "Heatmap view of data completeness and ingest latency across streams and time. Identify gaps, coverage issues, and high-latency streams at a glance.",
    tips: [
      "Select a stream list and date range, then click a time-window button.",
      "In the calendar picker, click once for the start day and again for the end day, or drag across days.",
      "Hover over cells to see row counts and latency values.",
      "Use the Fetch Missing button to download any missing Arrow files.",
    ],
  },
  {
    route: "/positions",
    label: "Positions",
    icon: "show_chart",
    color: "indigo",
    description:
      "Time-series plots of East, North, and Up position components for one or more streams over a selected date range.",
    tips: [
      "Type or paste comma-separated geosncl codes to overlay multiple streams.",
      "Zoom and pan the chart; use the reset button to restore the full range.",
      "Select 2 or more streams and click Coherence for a per-pair spectrum + a density heatmap of shared signal.",
      "Karhunen-Loève and PCA both decompose the selection into shared modes (with each mode's own reconstructed time series); Common mode (None/PCA/KLE) can subtract the dominant one(s).",
    ],
  },
  {
    route: "/ppsd",
    label: "PPSD",
    icon: "graphic_eq",
    color: "deep-orange",
    description:
      "Compute Probabilistic Power Spectral Density plots from locally stored Arrow files. Generate one plot per processing center, solution type, or individual stream.",
    tips: [
      "\"By Processing Center\" groups all streams from a center into a single 3-panel PNG.",
      "\"By Stream\" produces one PNG per geosncl — useful for comparing individual streams.",
      "Common mode (None/PCA/KLE) can remove shared clock/orbit noise per center+solution subgroup before computing.",
      "Output PNGs are organized under data/plots/ppsd/<mode>/ and are viewable in File Explorer.",
    ],
  },
  {
    route: "/plots",
    label: "File Explorer",
    icon: "folder_open",
    color: "green",
    description:
      "Browse and view PNG plots stored under data/plots/. Navigate the directory tree with collapsible folders and click any image to view it full-size.",
    tips: [
      "PPSD plots are grouped by type (by-stream, by-center, …), then by plot, with one dated file per run.",
      "Click a folder caret to expand it — children are loaded on first open.",
      "Click an image name to display it in the viewer panel.",
    ],
  },
  {
    route: "/export",
    label: "Export",
    icon: "sync_alt",
    color: "brown",
    description:
      "Convert downloaded Arrow position data into MiniSEED or GeoJSON files. Edit the output path-spec (directory structure & filenames) and regenerate on demand.",
    tips: [
      "Choose MiniSEED or GeoJSON (compact / full / both) and a stream list + date range.",
      "Edit the path-spec TOML in the editor, Save spec, then Convert to remake files.",
      "Enable overwrite to regenerate files that already exist under the new layout.",
    ],
  },
  {
    route: "/replay",
    label: "Replay",
    icon: "replay",
    color: "purple",
    description:
      "Replay archived position data to a Kafka topic at any speed. Select a stream list, set a 6-hour (or longer) window, preload the data, then start the replay.",
    tips: [
      "Preload resolves which Arrow files cover the time window before replay starts.",
      "Time scale > 1× speeds up the replay; apply_latency re-introduces original ingest delays.",
      "The stream count summary shows how many streams have data in the selected window.",
    ],
  },
];

const readmeHtml = ref("");
const loadingReadme = ref(false);

onMounted(async () => {
  loadConfig();
  loadingReadme.value = true;
  try {
    const res = await fetch("/api/readme");
    const data = await res.json();
    if (data.content) {
      readmeHtml.value = await marked(data.content);
    }
  } catch {
    // ignore
  } finally {
    loadingReadme.value = false;
  }
});
</script>

<style scoped>
.cfg-table td { padding-left: 0; word-break: break-all; }
.cfg-cmd {
  font-family: monospace; font-size: 11.5px; line-height: 1.6;
  background: rgba(0, 0, 0, 0.05); border-radius: 4px;
  padding: 8px 10px; margin: 8px 0 0; overflow-x: auto; white-space: pre;
}
.page-card {
  transition: box-shadow 0.15s ease;
}
.page-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.nav-link {
  color: inherit;
  text-decoration: none;
}
.nav-link:hover {
  text-decoration: underline;
}
.tips-list {
  margin: 0;
  padding-left: 1.2em;
}
.tips-list li + li {
  margin-top: 2px;
}

/* README prose */
.readme-body :deep(h1) { font-size: 1.5rem; font-weight: 600; margin: 1.2em 0 0.4em; }
.readme-body :deep(h2) { font-size: 1.25rem; font-weight: 600; margin: 1.1em 0 0.35em; }
.readme-body :deep(h3) { font-size: 1.05rem; font-weight: 600; margin: 1em 0 0.3em; }
.readme-body :deep(p)  { margin: 0.5em 0; line-height: 1.65; }
.readme-body :deep(ul),
.readme-body :deep(ol) { padding-left: 1.4em; margin: 0.4em 0; }
.readme-body :deep(li) { margin: 0.2em 0; line-height: 1.55; }
.readme-body :deep(code) {
  background: #f3f4f6;
  border-radius: 3px;
  padding: 0.1em 0.35em;
  font-size: 0.85em;
  font-family: ui-monospace, monospace;
}
.readme-body :deep(pre) {
  background: #f3f4f6;
  border-radius: 6px;
  padding: 0.8em 1em;
  overflow-x: auto;
  font-size: 0.82rem;
  line-height: 1.5;
  margin: 0.6em 0;
}
.readme-body :deep(pre code) {
  background: none;
  padding: 0;
}
.readme-body :deep(hr) {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 1.2em 0;
}
.readme-body :deep(a) { color: #1976d2; }
.readme-body :deep(blockquote) {
  border-left: 3px solid #d1d5db;
  margin: 0.6em 0;
  padding: 0.3em 0.8em;
  color: #6b7280;
}
.readme-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
  font-size: 0.88rem;
}
.readme-body :deep(th),
.readme-body :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 0.4em 0.7em;
  text-align: left;
}
.readme-body :deep(th) { background: #f9fafb; font-weight: 600; }
</style>

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

    <!-- ── README ───────────────────────────────────────────────────────── -->
    <div class="text-h6 text-weight-medium q-mb-sm">README</div>
    <div v-if="readmeHtml" class="readme-body" v-html="readmeHtml" />
    <div v-else-if="loadingReadme" class="text-grey-5 text-caption">Loading…</div>

  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { marked } from "marked";

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
      "Use the Filter Streams chips (processing center / stream type) with Only matching /",
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
      "Output PNGs are organized under data/plots/ppsd/<mode>/ and are viewable in File Plots.",
    ],
  },
  {
    route: "/plots",
    label: "File Plots",
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

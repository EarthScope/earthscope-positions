<template>
  <ESLayout app-name="GNSS Positions" :hide-login="true">
    <template #pre-page>
      <!--
        ESLayout's QHeader is position:fixed (~50px tall).
        The #pre-page slot renders in the document flow at y=0, hidden under
        the fixed header. Fix: make the nav bar fixed at top:50px and force
        the page container to account for both header + nav bar height.
      -->
      <div class="nav-bar row items-center no-wrap">
        <q-tabs dense align="left" class="nav-tabs col" no-caps>
          <q-route-tab to="/overview"            label="Overview" />
          <q-route-tab to="/station-list-builder" label="Station List Builder" />
          <q-route-tab to="/stream-list-builder"  label="Stream List Builder" />
          <q-route-tab to="/fetch-data"          label="Fetch Data" />
          <q-route-tab to="/completeness"    label="Completeness" />
          <q-route-tab to="/positions"       label="Positions" />
          <q-route-tab to="/ppsd"            label="PPSD Generation" />
          <q-route-tab to="/plots"           label="File Plots" />
          <q-route-tab to="/export"          label="Export" />
          <q-route-tab to="/replay"          label="Replay" />
        </q-tabs>
        <q-btn
          v-if="currentHelp"
          flat dense round
          icon="help_outline"
          size="sm"
          class="help-btn q-mr-sm"
          @click="helpOpen = true"
        >
          <q-tooltip anchor="bottom right" self="top right">How to use this page</q-tooltip>
        </q-btn>
      </div>
    </template>
  </ESLayout>

  <q-dialog v-model="helpOpen">
    <q-card style="min-width: 360px; max-width: 540px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ currentHelp?.title }}</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>
      <q-card-section class="help-body" v-html="currentHelp?.html" />
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useRoute } from "vue-router";
import { ESLayout } from "@earthscope/spa-lib";

const helpOpen = ref(false);
const route = useRoute();

interface HelpEntry { title: string; html: string }

const HELP: Record<string, HelpEntry> = {
  "/station-list-builder": {
    title: "Station List Builder",
    html: `
      <p>Down-select <strong>stations</strong> on the map and save them as <em>station lists</em>
      (station codes only). These lists feed the Stream List Builder's include/exclude sets.</p>
      <div class="help-section-label">Selecting stations</div>
      <ul>
        <li><strong>Click</strong> a dot to select/deselect a station (blue = selected, grey = not)</li>
        <li><strong>Shift&nbsp;+&nbsp;drag</strong> to rectangle-select an area</li>
        <li><strong>Radial Search</strong> — enter lat/lon/km and choose Only / Add / Exclude
            (Exclude carves out rings)</li>
        <li><strong>Load Network</strong> — add all station names in a network (RTDB:* / SHAKE:*)</li>
      </ul>
      <div class="help-section-label">Station popup</div>
      <ul>
        <li>Hover a station to see its 4-character code; zoom in close enough and the tooltip
            also lists its streams</li>
        <li>Click a station to open its popup — <strong>Select/Deselect</strong> toggles it,
            and the location icon opens <strong>Radial Search</strong> pre-filled with that
            station's coordinates as the center</li>
      </ul>
      <div class="help-section-label">Coordinates</div>
      <ul>
        <li><strong>Update Coordinates</strong> — upload a CSV to add/replace stations</li>
        <li><strong>Edit Coordinates</strong> — edit the coordinates file directly</li>
      </ul>`,
  },
  "/stream-list-builder": {
    title: "Stream List Builder",
    html: `
      <p>Pick individual <strong>streams</strong> and save them as <em>stream lists</em> (geosncls)
      used by Fetch, Completeness, Positions, PPSD, Export and Replay.</p>
      <div class="help-section-label">Choosing which stations appear</div>
      <ul>
        <li><strong>Include Station Lists</strong> — only these stations are shown</li>
        <li><strong>Exclude Station Lists</strong> — these are hidden</li>
        <li>Changes apply automatically and reset the current stream selection</li>
      </ul>
      <div class="help-section-label">Selecting streams</div>
      <ul>
        <li><strong>Click</strong> a station to toggle all its streams; open the panel to toggle individual streams</li>
      </ul>
      <div class="help-section-label">Filter Streams</div>
      <ul>
        <li>Chips list the processing centers and stream types present among the currently
            visible stations' streams — click to include/exclude a chip from the filter</li>
        <li><strong>Add matching</strong> adds every stream matching the current chip
            selection to your working set; <strong>Remove matching</strong> removes them</li>
      </ul>
      <div class="help-section-label">Saving</div>
      <ul>
        <li>Enter a name and <strong>Save</strong> to store the stream list</li>
      </ul>`,
  },
  "/fetch-data": {
    title: "Fetch Data",
    html: `
      <p>Download GNSS position data for your stream lists — a guided, three-step walkthrough.</p>
      <div class="help-section-label">Steps</div>
      <ul>
        <li><strong>Choose streams</strong> — pick one or more stream lists (built in the
            Stream List Builder)</li>
        <li><strong>Date range &amp; filters</strong> — set the range and optionally narrow by processing center / stream type</li>
        <li><strong>Fetch</strong> — review the plan, start the download, and watch live progress</li>
      </ul>
      <div class="help-section-label">Notes</div>
      <ul>
        <li>Only missing (geosncl, day) pairs are fetched — data already present or previously attempted is skipped</li>
        <li>Only one fetch runs at a time; the job (and its live log) keeps running and stays
            visible if you switch to other tabs and come back</li>
        <li>Once a fetch finishes, the button becomes <strong>Restart fetch</strong> — click it
            to run the same configuration again (e.g. to pick up newly-attempted days)</li>
        <li>Newly downloaded data appears in the Completeness and Positions tabs</li>
      </ul>`,
  },
  "/completeness": {
    title: "Completeness &amp; Latency",
    html: `
      <p>Color-coded heatmap of data availability per stream per time window.</p>
      <div class="help-section-label">Color scale</div>
      <ul>
        <li><strong>White</strong> — not yet attempted</li>
        <li><strong>Grey</strong> — fetch error (API unreachable or no data)</li>
        <li><strong>Red&nbsp;→&nbsp;Yellow&nbsp;→&nbsp;Green</strong> — 0&nbsp;%&nbsp;→&nbsp;50&nbsp;%&nbsp;→&nbsp;100&nbsp;% completeness</li>
      </ul>
      <div class="help-section-label">Usage</div>
      <ul>
        <li>Select a stream list and date range, then click <strong>Load</strong></li>
        <li>In the calendar picker, click one day to set the start, then click another to set
            the end — or drag across days in one motion</li>
        <li>Results are paginated; use the arrows to step through streams</li>
        <li>Click <strong>Fetch Missing</strong> to download data for streams that have never been tried</li>
        <li>The <em>Latency</em> heatmap below shows ingest delay in seconds</li>
      </ul>`,
  },
  "/positions": {
    title: "Positions",
    html: `
      <p>East / North / Up position time series for one or more streams.</p>
      <div class="help-section-label">Controls</div>
      <ul>
        <li>Select a stream list and date range; use the search box to filter by stream name</li>
        <li>In the calendar picker, click one day to set the start, then click another to set
            the end — or drag across days in one motion</li>
        <li><strong>Shift&nbsp;+&nbsp;drag</strong> on any chart to zoom a time range; <strong>right-click</strong> to reset zoom</li>
        <li><strong>Shift-click</strong> a legend entry to remove that stream from all plots</li>
        <li>All three position charts share the same x-axis when zooming</li>
      </ul>
      <div class="help-section-label">Power spectra</div>
      <ul>
        <li>Charts below show frequency content per component (periods 5&nbsp;min to full-record length)</li>
        <li>Y-axis is in scientific notation (m²/Hz)</li>
      </ul>`,
  },
  "/ppsd": {
    title: "PPSD Generation",
    html: `
      <p>Compute Probabilistic Power Spectral Density plots from position time series.</p>
      <div class="help-section-label">Setup</div>
      <ul>
        <li>Select one or more stream lists and a date range</li>
        <li>In the calendar picker, click one day to set the start, then click another to set
            the end — or drag across days in one motion</li>
        <li>Filter by processing center and stream type using the chips (all selected = no filter)</li>
      </ul>
      <div class="help-section-label">Grouping modes</div>
      <ul>
        <li><strong>By Processing Center</strong> — one plot per center (PB, PW, NC&nbsp;…)</li>
        <li><strong>By Solution Type</strong> — one plot per 2-char solution code</li>
        <li><strong>By Center × Solution</strong> — one plot per center+solution combination</li>
        <li><strong>By Stream</strong> — one plot per individual stream</li>
      </ul>
      <div class="help-section-label">Performance</div>
      <ul>
        <li>Cache files are built on first run; subsequent runs on the same data are nearly instant</li>
        <li>Pre-compute caches offline with <code>es-pos process ppsd</code></li>
      </ul>`,
  },
  "/plots": {
    title: "File Plots",
    html: `
      <p>Browse and view PPSD plot images generated from the PPSD Generation page.</p>
      <ul>
        <li>Navigate the folder tree on the left: top-level folders are the PPSD type
            (<code>by-stream</code>, <code>by-center</code>, <code>by-solution</code>,
            <code>by-center-solution</code>, <code>all</code>); each holds one sub-folder per
            plot, and each run adds a new dated file inside it</li>
        <li>Click any <strong>.png</strong> entry to display it in the right panel</li>
        <li>New plots generated by the PPSD page appear here automatically</li>
      </ul>`,
  },
  "/export": {
    title: "Export",
    html: `
      <p>Convert downloaded Arrow position data into MiniSEED or GeoJSON files.</p>
      <div class="help-section-label">Convert</div>
      <ul>
        <li>Pick a format (MiniSEED, or GeoJSON compact / full / both)</li>
        <li>Choose stream list(s) and a date range, then click <strong>Convert</strong></li>
        <li>In the calendar picker, click one day to set the start, then click another to set
            the end — or drag across days in one motion</li>
        <li>Enable <strong>Overwrite existing files</strong> to remake files that already exist</li>
      </ul>
      <div class="help-section-label">Output path template</div>
      <ul>
        <li>The editor shows the path-spec TOML that controls the output directory
            structure and filenames (<code>{network}</code>, <code>{station}</code>,
            <code>{year}</code>, <code>{julday}</code>, …)</li>
        <li>Edit it, click <strong>Save spec</strong>, then <strong>Convert</strong>
            (with overwrite) to regenerate files under the new layout</li>
        <li>Files are written under <code>data/miniseed/</code> or
            <code>data/geojson/</code> per the spec's <code>root</code></li>
      </ul>`,
  },
  "/replay": {
    title: "Replay",
    html: `
      <p>Stream historical GNSS position data into a Kafka topic at a controlled rate.</p>
      <div class="help-section-label">Setup</div>
      <ul>
        <li>Configure the bootstrap server, topic name, stream lists, time range, and stream filters</li>
        <li>In the calendar picker, click one day to set the start, then click another to set
            the end — or drag across days in one motion</li>
        <li>Click <strong>Preload</strong> to check data availability before committing to a full replay</li>
      </ul>
      <div class="help-section-label">Timing</div>
      <ul>
        <li><strong>Time scale</strong>: 1× = real-time;&nbsp; 10× = ten times faster</li>
        <li><strong>Apply latency</strong>: shifts each message's send time by its original ingest delay</li>
      </ul>
      <div class="help-section-label">Running</div>
      <ul>
        <li>Click <strong>Go</strong> to start, or run <code>curl -X POST .../api/replay/start</code></li>
        <li>The UI detects an external curl start automatically within ~1&nbsp;s</li>
        <li>Click <strong>Cancel</strong> to stop an in-progress replay</li>
      </ul>`,
  },
};

const currentHelp = computed<HelpEntry | null>(
  () => HELP[route.path] ?? null,
);
</script>

<style>
/*
 * ESLayout's QHeader uses Quasar's `reveal` prop, which animates
 * the header out with transform:translateY(-100%) on scroll-down.
 * We override both the hidden state and the transition so the header
 * is always pinned, and our nav bar (position:fixed at top:50px) stays
 * correctly anchored below it.
 * padding-top: 88px clears both the header (~50px) and nav bar (~38px).
 */
.q-header {
  position: fixed !important;
  top: 0 !important;
  transform: none !important;
  transition: none !important;
}
.q-header--hidden {
  transform: none !important;
  visibility: visible !important;
}
.q-page-container {
  padding-top: 88px !important;
}

/* Help dialog body */
.help-body ul { margin: 0; padding-left: 1.4em; }
.help-body li { margin-bottom: 4px; font-size: 0.875rem; line-height: 1.5; }
.help-body p  { margin: 0 0 8px; font-size: 0.875rem; line-height: 1.5; }
.help-body strong { font-weight: 600; }
.help-body code {
  font-family: monospace;
  font-size: 0.82em;
  background: rgba(0,0,0,0.07);
  padding: 1px 4px;
  border-radius: 3px;
}
.help-section-label {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #888;
  margin: 12px 0 4px;
}
</style>

<style scoped>
.nav-bar {
  position: fixed;
  top: 50px;
  left: 0;
  right: 0;
  z-index: 1999;
  background: #1a237e;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}
.nav-tabs :deep(.q-tab) {
  color: rgba(255, 255, 255, 0.8);
  min-height: 38px;
  font-size: 0.82rem;
}
.nav-tabs :deep(.q-tab--active) {
  color: #fff;
}
.nav-tabs :deep(.q-tab__indicator) {
  background: #fff;
}
.help-btn {
  color: rgba(255, 255, 255, 0.7);
  flex-shrink: 0;
}
.help-btn:hover {
  color: #fff;
}
</style>

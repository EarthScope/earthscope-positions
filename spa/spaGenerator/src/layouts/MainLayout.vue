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
          <q-route-tab to="/overview"        label="Overview" />
          <q-route-tab to="/station-builder" label="Station Builder" />
          <q-route-tab to="/completeness"    label="Completeness" />
          <q-route-tab to="/positions"       label="Positions" />
          <q-route-tab to="/ppsd"            label="PPSD Generation" />
          <q-route-tab to="/plots"           label="File Plots" />
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
  "/station-builder": {
    title: "Station Builder",
    html: `
      <p>Build reusable station lists by selecting stations on an interactive map.</p>
      <div class="help-section-label">Selecting stations</div>
      <ul>
        <li><strong>Click</strong> a dot to select or deselect a single station (turns blue when selected)</li>
        <li><strong>Shift&nbsp;+&nbsp;drag</strong> on the map to rectangle-select all stations in an area</li>
        <li>Toggle <strong>Union</strong> (add) vs <strong>Intersection</strong> (keep shared) to control how new selections combine</li>
      </ul>
      <div class="help-section-label">Filtering</div>
      <ul>
        <li>Use the center and stream-type checkboxes in the left panel to narrow visible stations</li>
        <li>Click <strong>Apply</strong> after changing filters</li>
      </ul>
      <div class="help-section-label">Saving</div>
      <ul>
        <li>Enter a name and click <strong>Save</strong> to store the selection as a reusable list</li>
        <li>Saved lists appear in all other pages (Completeness, Positions, PPSD, Replay)</li>
      </ul>`,
  },
  "/completeness": {
    title: "Completeness &amp; Latency",
    html: `
      <p>Color-coded heatmap of data availability per station per time window.</p>
      <div class="help-section-label">Color scale</div>
      <ul>
        <li><strong>White</strong> — not yet attempted</li>
        <li><strong>Grey</strong> — fetch error (API unreachable or no data)</li>
        <li><strong>Red&nbsp;→&nbsp;Yellow&nbsp;→&nbsp;Green</strong> — 0&nbsp;%&nbsp;→&nbsp;50&nbsp;%&nbsp;→&nbsp;100&nbsp;% completeness</li>
      </ul>
      <div class="help-section-label">Usage</div>
      <ul>
        <li>Select a station list and date range, then click <strong>Load</strong></li>
        <li>Results are paginated; use the arrows to step through stations</li>
        <li>Click <strong>Fetch Missing</strong> to download data for stations that have never been tried</li>
        <li>The <em>Latency</em> heatmap below shows ingest delay in seconds</li>
      </ul>`,
  },
  "/positions": {
    title: "Positions",
    html: `
      <p>East / North / Up position time series for one or more stations.</p>
      <div class="help-section-label">Controls</div>
      <ul>
        <li>Select a station list and date range; use the search box to filter by station name</li>
        <li><strong>Shift&nbsp;+&nbsp;drag</strong> on any chart to zoom a time range; <strong>right-click</strong> to reset zoom</li>
        <li><strong>Shift-click</strong> a legend entry to remove that station from all plots</li>
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
        <li>Select one or more station lists and a date range</li>
        <li>Filter by processing center and stream type using the chips (all selected = no filter)</li>
      </ul>
      <div class="help-section-label">Grouping modes</div>
      <ul>
        <li><strong>By Processing Center</strong> — one plot per center (PB, PW, NC&nbsp;…)</li>
        <li><strong>By Solution Type</strong> — one plot per 2-char solution code</li>
        <li><strong>By Center × Solution</strong> — one plot per center+solution combination</li>
        <li><strong>By Stream</strong> — one plot per individual station stream</li>
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
        <li>Navigate the folder tree on the left; folders are named by date range</li>
        <li>Click any <strong>.png</strong> entry to display it in the right panel</li>
        <li>New plots generated by the PPSD page appear here automatically</li>
      </ul>`,
  },
  "/replay": {
    title: "Replay",
    html: `
      <p>Stream historical GNSS position data into a Kafka topic at a controlled rate.</p>
      <div class="help-section-label">Setup</div>
      <ul>
        <li>Configure the bootstrap server, topic name, station lists, time range, and stream filters</li>
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

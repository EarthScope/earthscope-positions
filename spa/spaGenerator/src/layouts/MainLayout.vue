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
          <q-route-tab to="/plots"           label="File Explorer" />
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
        <li><strong>Add Network Stations</strong> — add all station names in a network
            (RTDB:* / SHAKE:*) to the selection, and save them as a station list named
            after the network. If that list already exists it is loaded from disk
            instead of re-querying the API, so your edits to it survive; use
            <strong>Re-query network</strong> to refetch and overwrite it</li>
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
      <div class="help-section-label">Select Streams</div>
      <ul>
        <li>Chips list the processing centers and stream types present among the currently
            visible stations' streams — click to include/exclude a chip from the filter.
            At least one processing center and one stream type always stay selected</li>
        <li><strong>Only matching</strong> replaces your working set with exactly the
            matching streams, ignoring what was selected before</li>
        <li><strong>Select by Regex</strong> does the same three operations against a
            regular expression matched (case-insensitively) anywhere in the full
            geosncl — e.g. <code>^P1</code>, <code>\.PB\.</code>,
            <code>\.(10|60)$</code> — over the same visible streams</li>
        <li><strong>Add matching</strong> adds every stream matching the current chip
            selection to your working set; <strong>Remove matching</strong> removes them</li>
      </ul>
      <div class="help-section-label">Saving</div>
      <ul>
        <li>Stream records need all four fields — <code>geosncl</code>, <code>edid</code>,
            <code>facility</code>, <code>software</code> — and must exist in
            <code>all-streams</code>. The editor rejects anything else, and loading a
            list reports entries dropped as unusable. <code>all-streams</code> is
            generated and cannot be edited, renamed, or deleted</li>
        <li>Enter a name and <strong>Save</strong> to store the stream list — the caption
            above the button shows how many streams it will contain</li>
        <li><strong>Preview / edit before saving</strong> opens the pending list as one
            geosncl per line, so you can trim it before it is written. Saving from there
            also updates the map selection to match</li>
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
        <li>Click the calendar icon inside the <strong>From</strong> or <strong>To</strong> box;
            click a day, then click it again to set just that field, or click a different
            day to set both at once</li>
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
        <li>Click the calendar icon inside the <strong>From</strong> or <strong>To</strong> box;
            click a day, then click it again to set just that field, or click a different
            day to set both at once</li>
        <li><strong>Shift&nbsp;+&nbsp;drag</strong> on any chart to zoom a time range; <strong>right-click</strong> to reset zoom</li>
        <li><strong>Shift-click</strong> a legend entry to remove that stream from all plots</li>
        <li>All three position charts share the same x-axis when zooming</li>
      </ul>
      <div class="help-section-label">Power spectra</div>
      <ul>
        <li>Charts below show frequency content per component (periods 5&nbsp;min to full-record length)</li>
        <li>Y-axis is in scientific notation (m²/Hz)</li>
      </ul>
      <div class="help-section-label">Coherence</div>
      <ul>
        <li>Select 2 or more streams, then click <strong>Coherence</strong> to see how much
            signal each pair shares, as a function of period — quantifies "common-mode"
            noise from shared processing software/clocks or nearby geography</li>
        <li>Top plot: coherence vs. period, one line per pair (legend hidden past 40 pairs);
            bottom plot: a density heatmap — for each period, the fraction of pairs
            whose coherence falls in each 0.05-wide bin (color = pair density, not
            any one pair's value) — hover either for exact values</li>
        <li>No cap on stream count — coherence is pairwise (N² pairs), so very large
            selections can take noticeably longer to compute and render</li>
        <li>Always computed fresh from full-resolution data for exactly the current
            selection — not the (possibly downsampled) chart cache — so it gives the
            same result whether streams were added one at a time or via Select All</li>
        <li>Defaults to the East component; switch via the radio buttons at the top</li>
      </ul>
      <div class="help-section-label">Karhunen-Loève decomposition</div>
      <ul>
        <li>Click <strong>Karhunen-Loève</strong> for a network PCA: each mode is a
            signal shared across the selection, ranked by how much of the total
            variance it explains, with a per-stream loading showing how strongly
            (and in which direction) each one participates</li>
        <li>East, North, and Up are decomposed independently and shown together —
            one clustered bar per mode/stream per component, one line per component —
            all using the same East/North/Up color throughout the popup</li>
        <li>Pick a mode to see its own reconstructed time series (what the shared
            signal actually looks like) alongside its spatial loadings, for all
            three components at once</li>
        <li>Builds its covariance matrix pairwise-complete, so every stream
            contributes even where the network's gaps don't align — see
            <strong>Principal Component Analysis</strong> for the exact-but-stricter
            sibling method</li>
        <li>Mode&nbsp;1 — the dominant common mode — is what <strong>Common mode</strong>
            below can subtract</li>
      </ul>
      <div class="help-section-label">Principal Component Analysis (PCA)</div>
      <ul>
        <li>Click <strong>PCA</strong> for the classical sibling of Karhunen-Loève:
            same variance-explained / mode-series / loadings layout — East, North, and
            Up together, same colors — but built only from epochs where
            <strong>every</strong> selected stream has simultaneous data — an exact
            decomposition, at the cost of only speaking for the time span where the
            whole network overlaps</li>
        <li>If a component's streams never all overlap at once, that component
            simply contributes no bars/line for it; if none of the three do, PCA has
            nothing to decompose — use Karhunen-Loève instead for gappy,
            loosely-overlapping networks</li>
      </ul>
      <div class="help-section-label">Common mode (None / PCA / KLE)</div>
      <ul>
        <li>Click <strong>Common mode: …</strong> to pick which method — if any —
            removes the leading mode(s) before plotting a second East/North/Up set;
            <strong>Modes to remove</strong> controls how many (1-5)</li>
        <li>Computed independently per component, since the shared signal need not
            look the same in East, North, and Up</li>
        <li>Each stream keeps its own mean/offset — only the shared time-varying part
            is removed, so it's a direct visual comparison against the originals</li>
        <li>With PCA, any epoch where the network doesn't fully overlap is left as
            raw data (no common-mode estimate exists there) — KLE instead estimates
            through those gaps using whichever streams are available</li>
      </ul>`,
  },
  "/ppsd": {
    title: "PPSD Generation",
    html: `
      <p>Compute Probabilistic Power Spectral Density plots from position time series.</p>
      <div class="help-section-label">Setup</div>
      <ul>
        <li>Select one or more stream lists and a date range</li>
        <li>Click the calendar icon inside the <strong>Start date</strong> or <strong>End date</strong>
            box; click a day, then click it again to set just that field, or click a different
            day to set both at once</li>
        <li>Filter by processing center and stream type using the chips (all selected = no filter)</li>
      </ul>
      <div class="help-section-label">Grouping modes</div>
      <ul>
        <li><strong>By Processing Center</strong> — one plot per center (PB, PW, NC&nbsp;…)</li>
        <li><strong>By Solution Type</strong> — one plot per 2-char solution code</li>
        <li><strong>By Center × Solution</strong> — one plot per center+solution combination</li>
        <li><strong>By Stream</strong> — one plot per individual stream</li>
      </ul>
      <div class="help-section-label">Common mode (None / PCA / KLE)</div>
      <ul>
        <li>Optionally remove the leading PCA or KLE common mode(s) before computing
            each PSD — set <strong>Modes to remove</strong> when enabled</li>
        <li>Always computed per processing-center + solution/software subgroup (the
            shared source of clock/orbit corrections), regardless of which grouping
            mode above is used for the final plots</li>
        <li>Subgroups with only one stream have nothing to remove and use raw data;
            with PCA, a subgroup also needs its streams to overlap simultaneously —
            where they don't, raw data is used there too</li>
      </ul>
      <div class="help-section-label">Performance</div>
      <ul>
        <li>Cache files are built on first run; subsequent runs on the same data are nearly instant</li>
        <li>Pre-compute caches offline with <code>es-pos process ppsd</code></li>
        <li>Common-mode removal bypasses that cache (its result depends on which
            streams are grouped together), so it's recomputed each run</li>
      </ul>`,
  },
  "/plots": {
    title: "File Explorer",
    html: `
      <p>Browse everything under the data directory — the Arrow tree, stream and station
         lists, exports, and generated plots — with a summary of whatever you select.</p>
      <div class="help-section-label">Browsing</div>
      <ul>
        <li>The tree is rooted at the data directory (its path is shown at the top left)
            and loads one folder at a time</li>
        <li><strong>↑ / ↓</strong> move between files</li>
        <li>Plots generated by the PPSD page appear under <code>plots/</code>, and the
            PPSD page's links open them here</li>
      </ul>
      <div class="help-section-label">What you get per file</div>
      <ul>
        <li><strong>.arrow</strong> — row and column counts, first/last sample, span,
            nominal rate, and the column schema with null counts</li>
        <li><strong>MiniSEED</strong> — records, samples, channels, format version,
            encoding, time span, and a per-source-ID sample count</li>
        <li><strong>GeoJSON</strong> — shape (FeatureCollection or NDJSON), feature and
            station counts, time range, and the lat/lon bounds</li>
        <li><strong>.jsonl</strong> — whether it is a stream or station list, entry
            counts, the fields present, and the first few lines</li>
        <li><strong>Images</strong> — displayed as before</li>
      </ul>
      <div class="help-section-label">Managing files</div>
      <ul>
        <li><strong>Edit</strong> — text files only (.jsonl, .json, .csv, .toml, .txt,
            .md, up to 8 MB). JSONL is validated line by line before saving, so a typo
            is rejected rather than written</li>
        <li><strong>Rename</strong> — name only; the file stays in its directory</li>
        <li><strong>Delete</strong> — one file at a time, after a confirmation.
            Directories cannot be deleted from here</li>
      </ul>`,
  },
  "/export": {
    title: "Export",
    html: `
      <p>Convert downloaded Arrow position data into MiniSEED or GeoJSON files.</p>
      <div class="help-section-label">Convert</div>
      <ul>
        <li>Pick a format (MiniSEED, or GeoJSON compact / full / both)</li>
        <li>For MiniSEED, pick the <strong>version</strong>: 3 (default, the current
            FDSN standard) or 2 (classic SEED, for tooling that cannot read v3).
            Version 2 needs <code>max_record_length</code> in the path spec to be a
            power of two</li>
        <li>Choose stream list(s) and a date range, then click <strong>Convert</strong></li>
        <li>Click the calendar icon inside the <strong>Start date</strong> or <strong>End date</strong>
            box; click a day, then click it again to set just that field, or click a different
            day to set both at once</li>
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
        <li>Click the calendar icon; click a day, then click it again to set both
            <strong>Start date</strong> and <strong>Stop date</strong> to that day, or click a
            different day to set differing start/stop dates</li>
        <li>Use the <strong>Start time</strong> / <strong>Stop time</strong> boxes below to set
            the time-of-day for each (defaults 00:00:00 / 01:00:00)</li>
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

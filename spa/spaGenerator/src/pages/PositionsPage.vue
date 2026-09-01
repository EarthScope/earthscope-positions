<template>
  <q-page class="q-pa-md column no-wrap" style="height: calc(100vh - 50px)">

    <!-- ── Controls ─────────────────────────────────────────────────────── -->
    <div class="row items-center q-gutter-sm q-mb-xs flex-shrink-0">
      <q-select
        v-model="selectedList"
        :options="listOptions"
        label="Stream list"
        dense outlined emit-value map-options
        style="min-width: 180px"
        @update:model-value="reloadStations"
      >
        <template #option="scope">
          <q-item v-bind="scope.itemProps">
            <q-item-section>
              <q-item-label>{{ scope.opt.label }}</q-item-label>
            </q-item-section>
            <q-menu v-if="scope.opt.value !== 'all'" context-menu>
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
      <q-input
        v-model="searchText"
        label="Filter streams"
        dense outlined clearable
        style="min-width: 220px"
        placeholder="e.g. (*.PB.* | *.CI.*) & LY_"
        @blur="reloadStations"
        @keyup.enter="reloadStations"
        @clear="reloadStations"
      >
        <template #prepend><q-icon name="search" size="xs" /></template>
      </q-input>
      <q-input v-model="startDate" label="From" dense outlined style="width: 136px"
        mask="####-##-##" placeholder="YYYY-MM-DD" @change="onFromChange">
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
      <q-input v-model="endDate" label="To" dense outlined style="width: 136px"
        mask="####-##-##" placeholder="YYYY-MM-DD" @change="onToChange">
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
      <div class="row items-center q-gutter-xs">
        <q-btn v-for="w in TIME_WINDOWS" :key="w.label" :label="w.label"
          :color="activeWindow === w.label ? 'primary' : 'grey-5'"
          :flat="activeWindow !== w.label" :unelevated="activeWindow === w.label"
          dense size="sm" no-caps @click="applyWindow(w)" />
      </div>
      <q-checkbox v-model="downsampleEnabled" label="Downsample" dense size="sm" />
      <q-btn label="Fetch Missing" icon="cloud_download" color="primary" dense outline no-caps
        size="sm" class="self-center" @click="openFetchDialog" />
      <q-checkbox v-model="removeMean" label="Remove mean" dense size="sm" />
      <q-input v-model.number="outlierThreshold" label="Outlier (m)" type="number"
        dense outlined style="width: 95px" :min="0.01" :step="0.5">
        <q-tooltip>
          Samples more than this far from a stream's own median are dropped —
          from the plots, and from Coherence/Karhunen-Loève/PCA/common-mode-removed,
          so a single bad fix can't dominate variance-based analysis
        </q-tooltip>
      </q-input>
    </div>

    <!-- ── Selection controls ────────────────────────────────────────────── -->
    <div class="row items-center q-gutter-sm q-mb-xs flex-shrink-0">
      <q-btn label="Clear"            dense flat no-caps size="sm" icon="clear_all"   @click="clearSelection" />
      <q-btn label="Select All"       dense flat no-caps size="sm" icon="select_all"  @click="selectAll" />
      <q-btn label="Save Selection"   dense flat no-caps size="sm" icon="save"
        :disable="selected.size === 0" @click="openSaveDialog" />
      <q-btn label="Save To File"     dense flat no-caps size="sm" icon="image"
        :disable="selected.size === 0" @click="openSavePlotDialog">
        <q-tooltip>Write the current plots to a PNG in File Explorer</q-tooltip>
      </q-btn>
      <q-btn label="Coherence"        dense flat no-caps size="sm" icon="grid_on"
        :disable="selected.size < 2 || selected.size > COHERENCE_MAX_STREAMS" @click="openCoherenceDialog">
        <q-tooltip>
          Pairwise coherence across the selected streams (2-{{ COHERENCE_MAX_STREAMS }}) —
          how much common-mode signal they share at different timescales.
          Capped here since it's pairwise (N² pairs); Karhunen-Loève and PCA have no cap.
        </q-tooltip>
      </q-btn>
      <q-btn label="Karhunen-Loève"   dense flat no-caps size="sm" icon="hub"
        :disable="selected.size < 2" @click="openKleDialog">
        <q-tooltip>
          Network PCA (pairwise-complete covariance) — decompose the selected
          streams into shared ("common-mode") modes and see how strongly each
          stream participates
        </q-tooltip>
      </q-btn>
      <q-btn label="PCA"              dense flat no-caps size="sm" icon="scatter_plot"
        :disable="selected.size < 2" @click="openPcaDialog">
        <q-tooltip>
          Classical PCA — same idea as Karhunen-Loève, but built only from
          epochs where every selected stream has simultaneous data
        </q-tooltip>
      </q-btn>
      <q-btn :label="`Common mode: ${cmrMethodLabel}`" dense flat no-caps size="sm" icon="layers_clear">
        <q-menu anchor="bottom left" self="top left">
          <div class="q-pa-sm" style="min-width: 240px">
            <div class="text-caption text-grey-7 q-mb-xs">Remove common mode using</div>
            <q-option-group
              v-model="cmrMethod" :options="CMR_METHOD_OPTIONS"
              type="radio" dense
            />
            <q-input
              v-if="cmrMethod !== 'none'" v-model.number="cmrNModesRemoved" label="Modes to remove"
              type="number" dense outlined class="q-mt-sm" :min="1" :max="5"
            />
            <div v-if="cmrMethod !== 'none'" class="text-caption text-grey-6 q-mt-xs">
              Adds a second East/North/Up plot set with the dominant mode(s) subtracted.
            </div>
          </div>
        </q-menu>
      </q-btn>
      <q-spinner v-if="cmrLoading" size="16px" color="primary" />
      <span class="text-caption text-grey-6 self-center">
        · Shift+click to add · Shift+click line to deselect
      </span>
      <span class="text-caption text-grey-6 self-center">
        · Time series: drag = zoom Y, Shift+drag = zoom time, click = reset
      </span>
      <span class="text-caption text-grey-6 self-center">
        · Scatter: Shift+drag = zoom box, click = reset
      </span>
      <q-space />
      <span class="text-caption text-grey-6 self-center">
        {{ selected.size }} stream{{ selected.size === 1 ? "" : "s" }} selected
        <span v-if="positionsLoading"> · loading…</span>
        <span v-else-if="selected.size > 0">
          · {{ totalPointsLoaded.toLocaleString() }} pts
          <span v-if="anyDownsampled">(downsampled)</span>
        </span>
      </span>
    </div>

    <!-- ── Main split ────────────────────────────────────────────────────── -->
    <div class="row col no-wrap" style="min-height: 0">

      <!-- Station tree -->
      <div
        class="tree-panel q-pr-sm"
        style="width: 260px; min-width: 200px; overflow-y: auto; flex-shrink: 0"
        tabindex="0"
        @keydown="onTreeKeydown"
      >
        <div v-if="stationsLoading" class="flex flex-center q-pa-md">
          <q-spinner size="24px" color="primary" />
        </div>
        <template v-else>
          <div
            v-for="item in flatItems"
            :key="item.key"
            class="tree-row"
            :class="{ 'tree-focused': item.key === focusedKey }"
          >
            <div v-if="item.type === 'group'" class="row items-center no-wrap tree-item"
              @click.stop="onItemClick(item, $event)">
              <q-btn flat dense round
                :icon="expandedSet.has(item.id) ? 'expand_more' : 'chevron_right'"
                size="xs" color="grey-7" @click.stop="toggleExpand(item.id)" />
              <q-checkbox :model-value="groupCheckState(item.id)" dense size="sm"
                @update:model-value="onGroupCheck(item.id, $event)" @click.stop />
              <span class="tree-label text-weight-medium" style="font-size:12px">
                {{ item.id }}
                <span class="text-grey-6 text-caption">({{ item.children.length }})</span>
              </span>
            </div>
            <div v-else class="row items-center no-wrap tree-item tree-child"
              @click.stop="onItemClick(item, $event)">
              <q-checkbox :model-value="selected.has(item.geosncl)" dense size="sm"
                @update:model-value="onStationCheck(item.geosncl, $event)" @click.stop />
              <span class="tree-label" style="font-size:11px; font-family: monospace">
                {{ item.geosncl }}
              </span>
            </div>
          </div>
        </template>
      </div>

      <!-- Charts -->
      <div class="col column no-wrap q-pl-sm" style="min-width: 0; overflow-y: auto">
        <div v-if="selected.size === 0" class="flex flex-center text-grey-5" style="height: 100%">
          <div class="text-center">
            <q-icon name="show_chart" size="48px" class="q-mb-sm" />
            <div>Select stations on the left to plot positions.</div>
          </div>
        </div>
        <template v-else>
          <div v-if="noDataForRange" class="flex flex-center text-grey-6" style="min-height:80px">
            <div class="text-center">
              <q-icon name="event_busy" size="32px" class="q-mb-xs" />
              <div class="text-caption">No data for <b>{{ startDate }}</b> → <b>{{ endDate }}</b>. Adjust the date range.</div>
            </div>
          </div>
          <!-- Position time-series -->
          <div v-for="comp in COMPONENTS" :key="comp.key" class="chart-block q-mb-sm">
            <div class="text-caption text-grey-7 q-mb-xs">{{ comp.label }}</div>
            <canvas :ref="el => setCanvas(comp.key, el)" class="chart-canvas" />
          </div>

          <!-- Common-mode-removed time-series (optional second set) -->
          <template v-if="cmrMethod !== 'none'">
            <q-separator class="q-my-sm" />
            <q-banner v-if="cmrError" dense class="bg-red-1 text-negative q-mb-sm">{{ cmrError }}</q-banner>
            <template v-else-if="cmrResult">
              <div class="text-caption text-grey-7 q-mb-xs">
                Common-mode removed ({{ cmrResult.method.toUpperCase() }}, {{ cmrNModesRemoved }}
                mode{{ cmrNModesRemoved === 1 ? "" : "s" }}) ·
                variance explained — E {{ (cmrResult.varianceExplainedPct.east[0] ?? 0).toFixed(0) }}%,
                N {{ (cmrResult.varianceExplainedPct.north[0] ?? 0).toFixed(0) }}%,
                U {{ (cmrResult.varianceExplainedPct.up[0] ?? 0).toFixed(0) }}%
                <span v-if="cmrResult.method === 'pca' && cmrResult.nCompleteEpochs">
                  · complete epochs — E {{ cmrResult.nCompleteEpochs.east.toLocaleString() }},
                  N {{ cmrResult.nCompleteEpochs.north.toLocaleString() }},
                  U {{ cmrResult.nCompleteEpochs.up.toLocaleString() }}
                </span>
              </div>
              <div v-for="comp in COMPONENTS" :key="comp.key + '_cmr'" class="chart-block q-mb-sm">
                <div class="text-caption text-grey-7 q-mb-xs">
                  {{ comp.label }} — common-mode removed ({{ cmrResult.method.toUpperCase() }})
                </div>
                <canvas :ref="el => setCanvas(comp.key + '_cmr', el)" class="chart-canvas" />
              </div>
            </template>
          </template>

          <!-- Scatter plots: E-N, N-U, U-E -->
          <div class="text-caption text-grey-7 q-mb-xs">Scatter — as measured</div>
          <div class="row no-wrap q-col-gutter-xs q-mb-sm" style="flex-shrink: 0">
            <div v-for="sc in SCATTER_DEFS" :key="'sc_' + sc.key" class="col chart-block-sq">
              <canvas :ref="el => setScatterCanvas(sc.key, el)" class="chart-canvas-full" />
            </div>
          </div>

          <!-- Histograms: E, N, U -->
          <div class="text-caption text-grey-7 q-mb-xs">Distribution — as measured</div>
          <div class="row no-wrap q-col-gutter-xs q-mb-sm" style="flex-shrink: 0">
            <div v-for="h in HIST_DEFS" :key="'h_' + h.key" class="col chart-block-sm">
              <canvas :ref="el => setHistCanvas(h.key, el)" class="chart-canvas-full" />
            </div>
          </div>

          <!-- The same scatters and histograms over the common-mode-removed
               series.  Removing a common mode is meant to tighten the cloud and
               narrow the distribution, and that is only visible side by side
               with the "as measured" pair above. -->
          <template v-if="cmrMethod !== 'none' && cmrResult">
            <q-separator class="q-my-sm" />
            <div class="text-caption text-grey-7 q-mb-xs">
              Scatter — common-mode removed ({{ cmrResult.method.toUpperCase() }})
            </div>
            <div class="row no-wrap q-col-gutter-xs q-mb-sm" style="flex-shrink: 0">
              <div v-for="sc in SCATTER_DEFS" :key="'sccmr_' + sc.key" class="col chart-block-sq">
                <canvas :ref="el => setScatterCanvas(sc.key + '_cmr', el)" class="chart-canvas-full" />
              </div>
            </div>

            <div class="text-caption text-grey-7 q-mb-xs">
              Distribution — common-mode removed ({{ cmrResult.method.toUpperCase() }})
            </div>
            <div class="row no-wrap q-col-gutter-xs q-mb-sm" style="flex-shrink: 0">
              <div v-for="h in HIST_DEFS" :key="'hcmr_' + h.key" class="col chart-block-sm">
                <canvas :ref="el => setHistCanvas(h.key + '_cmr', el)" class="chart-canvas-full" />
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>

    <!-- ── Fetch Missing dialog ──────────────────────────────────────────── -->
    <q-dialog v-model="fetchOpen" persistent>
      <q-card style="min-width: 620px; max-width: 90vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Fetch Missing Data</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="fetchRunning" />
        </q-card-section>
        <q-card-section class="q-pt-sm">
          <div class="text-caption text-grey-7">
            List: <b>{{ selectedList === "all" ? "All (select a specific list)" : selectedList }}</b>
            &nbsp;·&nbsp; {{ startDate }} → {{ endDate }}
          </div>
          <div v-if="selectedList === 'all'" class="text-warning q-mt-xs text-caption">
            ⚠ Select a specific stream list before fetching.
          </div>
        </q-card-section>
        <q-card-section v-if="fetchLog.length" style="max-height: 42vh; overflow-y: auto" class="q-pt-none">
          <div class="q-pa-sm rounded-borders"
            style="background:#1a1a2e; font-family:monospace; font-size:12px; line-height:1.5"
            ref="fetchLogEl">
            <div v-for="(line, i) in fetchLog" :key="i"
              :style="{ color: line.type==='error' ? '#ef9a9a' : line.type==='done' ? '#a5d6a7' : '#e0e0e0' }">
              {{ line.msg }}
            </div>
          </div>
        </q-card-section>
        <q-card-actions align="right" class="q-pa-md">
          <q-select v-model="fetchWorkers" :options="[5,10,20,30,50]" label="Workers"
            dense outlined style="width:90px" />
          <q-btn v-if="!fetchRunning && !fetchDone" label="Fetch" color="primary" unelevated no-caps
            :disable="selectedList === 'all'" @click="startFetch" />
          <q-btn v-if="fetchDone" label="Close" color="primary" flat no-caps v-close-popup
            @click="fetchLog = []; fetchDone = false" />
          <q-btn v-if="fetchRunning" label="Running…" flat no-caps disable />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Save Selection dialog ────────────────────────────────────────── -->
    <q-dialog v-model="saveOpen" persistent>
      <q-card style="min-width: 400px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Save Stream List</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="saveRunning" />
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">{{ selected.size }} stream(s) will be saved.</div>
          <q-input v-model="saveListName" label="List name" dense outlined autofocus
            :error="!!saveError" :error-message="saveError"
            placeholder="e.g. my-streams"
            @keyup.enter="doSave"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pa-md">
          <q-btn label="Cancel" flat no-caps v-close-popup :disable="saveRunning" />
          <q-btn label="Save" color="primary" unelevated no-caps
            :loading="saveRunning" :disable="!saveListName.trim()"
            @click="doSave" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Save To File (PNG) dialog ─────────────────────────────────────── -->
    <q-dialog v-model="savePlotOpen" persistent>
      <q-card style="min-width: 460px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Save Plots To File</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="savePlotSaving" />
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">
            Writes the current plots (time-series, scatter, histograms) as a PNG to
            <code>data/plots/positions/</code> — viewable in the <b>File Explorer</b> tab.
          </div>
          <q-input v-model="savePlotName" label="File name" dense outlined autofocus
            suffix=".png"
            :error="!!savePlotError" :error-message="savePlotError"
            @keyup.enter="doSavePlot" />
        </q-card-section>
        <q-card-actions align="right" class="q-pa-md">
          <q-btn label="Cancel" flat no-caps v-close-popup :disable="savePlotSaving" />
          <q-btn label="Save" color="primary" unelevated no-caps
            :loading="savePlotSaving" :disable="!savePlotName.trim()"
            @click="doSavePlot" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Pairwise Coherence dialog ────────────────────────────────────── -->
    <q-dialog v-model="coherenceOpen">
      <q-card style="min-width: 960px; max-width: 96vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Pairwise Coherence</div>
          <q-space />
          <q-option-group
            v-model="coherenceComponent" :options="COMPONENT_OPTIONS"
            type="radio" inline dense :disable="coherenceLoading"
            @update:model-value="loadCoherence" class="q-mr-md"
          />
          <q-btn icon="save" flat round dense class="q-mr-xs"
            :disable="coherenceLoading || !coherenceResult?.pairs.length"
            @click="saveCoherencePlot">
            <q-tooltip>Save to file (PNG)</q-tooltip>
          </q-btn>
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>
        <q-card-section class="text-caption text-grey-7 q-pt-none">
          Magnitude-squared coherence vs. period for every pair of selected streams —
          how much signal they share at a given timescale, regardless of sign or scale.
          1.0 = fully shared; 0 = independent.  Computed fresh from full-resolution
          data for exactly this selection (not the downsampled chart cache).
        </q-card-section>
        <q-separator />

        <q-card-section v-if="coherenceLoading" class="flex flex-center" style="min-height: 200px">
          <q-spinner size="36px" color="primary" />
        </q-card-section>

        <q-banner v-else-if="coherenceError" dense class="bg-red-1 text-negative">
          {{ coherenceError }}
        </q-banner>

        <q-card-section v-else-if="coherenceResult" style="max-height: 78vh; overflow-y: auto">
          <div v-if="coherenceResult.pairs_skipped.length" class="text-caption text-warning q-mb-sm">
            ⚠ {{ coherenceResult.pairs_skipped.length }} pair(s) skipped for insufficient overlapping data
          </div>
          <div v-if="!coherenceResult.pairs.length" class="text-caption text-grey-6">
            No pair had enough overlapping data to compute coherence.
          </div>

          <template v-else>
            <div class="text-overline text-grey-7">
              Coherence vs. period
              <span v-if="coherenceResult.pairs.length > MAX_LEGEND_LINES" class="text-grey-5">
                (legend hidden — {{ coherenceResult.pairs.length }} pairs)
              </span>
            </div>
            <div style="position: relative; height: 320px">
              <canvas ref="coherenceLineCanvas"></canvas>
            </div>

            <div class="text-overline text-grey-7 q-mt-md">Coherence distribution across pairs</div>
            <div class="text-caption text-grey-6 q-mb-xs">
              For each period, the fraction of pairs whose coherence falls in each 0.05-wide
              bin — color is pair density, not any one pair's value (see the plot above for
              that per-pair).
            </div>
            <div style="overflow: auto; max-height: 440px; position: relative">
              <canvas
                ref="coherenceHeatmapCanvas"
                @mousemove="onHeatmapMouseMove"
                @mouseleave="onHeatmapMouseLeave"
              ></canvas>
              <div
                v-if="coherenceHeatmapTip"
                class="heatmap-tip"
                :style="{ left: (coherenceHeatmapTip.x + 12) + 'px', top: (coherenceHeatmapTip.y + 12) + 'px' }"
              >{{ coherenceHeatmapTip.text }}</div>
            </div>
            <div class="row items-center q-gutter-xs q-mt-sm">
              <span class="text-caption text-grey-6">low</span>
              <div class="coh-legend-bar"></div>
              <span class="text-caption text-grey-6">high density of pairs</span>
            </div>
          </template>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- ── Karhunen-Loeve dialog ────────────────────────────────────────── -->
    <q-dialog v-model="kleOpen">
      <q-card style="min-width: 820px; max-width: 96vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Karhunen-Loève Decomposition</div>
          <q-space />
          <q-btn icon="save" flat round dense class="q-mr-xs"
            :disable="kleLoading || !kleResults"
            @click="saveKlePlot">
            <q-tooltip>Save to file (PNG)</q-tooltip>
          </q-btn>
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>
        <q-card-section class="text-caption text-grey-7 q-pt-none">
          Network PCA over the selected streams, computed independently for East, North,
          and Up and shown together — each mode is a shared signal, its "variance
          explained" is how much of that component's total variance it accounts for, and
          its loadings show how strongly (and in what direction) each stream participates.
          Mode&nbsp;1 is what <strong>Coherence</strong> and <strong>common-mode
          removed</strong> use.
        </q-card-section>
        <q-separator />

        <q-card-section v-if="kleLoading" class="flex flex-center" style="min-height: 200px">
          <q-spinner size="36px" color="primary" />
        </q-card-section>

        <q-banner v-else-if="kleError" dense class="bg-red-1 text-negative">
          {{ kleError }}
        </q-banner>

        <q-card-section v-else-if="kleResults" style="max-height: 76vh; overflow-y: auto">
          <div
            v-if="_ENU.some(c => kleResults![c].min_pair_overlap < 100)"
            class="text-caption text-warning q-mb-sm"
          >
            ⚠ Smallest pairwise overlap — E: {{ kleResults.east.min_pair_overlap }},
            N: {{ kleResults.north.min_pair_overlap }}, U: {{ kleResults.up.min_pair_overlap }}
            sample(s) — some covariance entries may be noisy.
          </div>

          <div class="text-overline text-grey-7">Variance explained per mode</div>
          <div class="kle-bar-wrap"><canvas ref="kleVarianceCanvas"></canvas></div>

          <div class="row items-center q-mt-md q-mb-xs">
            <div class="text-overline text-grey-7 col">Mode</div>
            <q-select
              v-model="kleLoadingMode" :options="kleModeOptions"
              dense outlined emit-value map-options style="width: 140px"
            />
          </div>

          <div class="text-caption text-grey-6 q-mb-xs">
            Reconstructed time series — what this mode's shared signal actually looks like.
          </div>
          <div class="kle-bar-wrap"><canvas ref="kleModeSeriesCanvas"></canvas></div>

          <div class="text-overline text-grey-7 q-mt-md">Stream loadings (spatial pattern)</div>
          <div class="kle-bar-wrap"><canvas ref="kleLoadingsCanvas"></canvas></div>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- ── PCA dialog ───────────────────────────────────────────────────── -->
    <q-dialog v-model="pcaOpen">
      <q-card style="min-width: 820px; max-width: 96vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Principal Component Analysis</div>
          <q-space />
          <q-btn icon="save" flat round dense class="q-mr-xs"
            :disable="pcaLoading || !pcaResults || !pcaHasAnyModes"
            @click="savePcaPlot">
            <q-tooltip>Save to file (PNG)</q-tooltip>
          </q-btn>
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>
        <q-card-section class="text-caption text-grey-7 q-pt-none">
          Classical PCA over the selected streams, computed independently for East, North,
          and Up and shown together — the sibling of Karhunen-Loève, but built only from
          epochs where <strong>every</strong> selected stream has simultaneous data (no
          pairwise-complete approximation), so each mode's time series is an exact
          projection rather than a fitted reconstruction.
        </q-card-section>
        <q-separator />

        <q-card-section v-if="pcaLoading" class="flex flex-center" style="min-height: 200px">
          <q-spinner size="36px" color="primary" />
        </q-card-section>

        <q-banner v-else-if="pcaError" dense class="bg-red-1 text-negative">
          {{ pcaError }}
        </q-banner>

        <q-card-section v-else-if="pcaResults" style="max-height: 76vh; overflow-y: auto">
          <div class="text-caption text-grey-7 q-mb-sm">
            Complete epochs (every stream present simultaneously) —
            E: {{ pcaResults.east.n_complete_epochs.toLocaleString() }},
            N: {{ pcaResults.north.n_complete_epochs.toLocaleString() }},
            U: {{ pcaResults.up.n_complete_epochs.toLocaleString() }}
          </div>
          <div v-if="!pcaHasAnyModes" class="text-caption text-warning">
            ⚠ No epochs where all {{ pcaResults.east.geosncls.length }} streams overlapped
            simultaneously in any component — PCA has nothing to decompose. Try
            Karhunen-Loève instead, which tolerates gaps that don't align across streams.
          </div>
          <template v-else>
            <div class="text-overline text-grey-7">Variance explained per mode</div>
            <div class="kle-bar-wrap"><canvas ref="pcaVarianceCanvas"></canvas></div>

            <div class="row items-center q-mt-md q-mb-xs">
              <div class="text-overline text-grey-7 col">Mode</div>
              <q-select
                v-model="pcaLoadingMode" :options="pcaModeOptions"
                dense outlined emit-value map-options style="width: 140px"
              />
            </div>

            <div class="text-caption text-grey-6 q-mb-xs">
              Reconstructed time series — exact at the complete epochs above, blank elsewhere.
            </div>
            <div class="kle-bar-wrap"><canvas ref="pcaModeSeriesCanvas"></canvas></div>

            <div class="text-overline text-grey-7 q-mt-md">Stream loadings (spatial pattern)</div>
            <div class="kle-bar-wrap"><canvas ref="pcaLoadingsCanvas"></canvas></div>
          </template>
        </q-card-section>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useQuasar } from "quasar";
import { Chart, registerables } from "chart.js";
import {
  getStreamLists, getStations, getPositions, getDataRange, openFetchMissingStream,
  saveStreamList, savePlotImage, getCoherence, getKle, getPca, getCommonModeRemoved,
} from "../api";
import type {
  PositionTrace, FetchEvent, CoherenceResponse, KleResponse, PcaResponse,
  CommonModeRemovedResponse, CmrMethod,
} from "../types";
import { useSharedControls } from "../composables/useSharedControls";
import { useListDelete } from "../composables/useListDelete";
import { createBoxRangeSelectHandler } from "../utils/dateRangePicker";

const $q = useQuasar();

Chart.register(...registerables);

// ─── Constants ────────────────────────────────────────────────────────────────

const TIME_WINDOWS = [
  { label: "24h",  hours: 24   },
  { label: "3d",   hours: 72   },
  { label: "7d",   hours: 168  },
  { label: "30d",  hours: 720  },
  { label: "90d",  hours: 2160 },
] as const;

const COMPONENTS = [
  { key: "east",  label: "East (mm)"  },
  { key: "north", label: "North (mm)" },
  { key: "up",    label: "Up (mm)"    },
] as const;

const SCATTER_DEFS = [
  { key: "en", xComp: "east"  as const, yComp: "north" as const, xLabel: "E (mm)", yLabel: "N (mm)" },
  { key: "nu", xComp: "north" as const, yComp: "up"    as const, xLabel: "N (mm)", yLabel: "U (mm)" },
  { key: "ue", xComp: "up"    as const, yComp: "east"  as const, xLabel: "U (mm)", yLabel: "E (mm)" },
] as const;

const HIST_DEFS = [
  { key: "east",  comp: "east"  as const, label: "E (mm)" },
  { key: "north", comp: "north" as const, label: "N (mm)" },
  { key: "up",    comp: "up"    as const, label: "U (mm)" },
] as const;

const COLORS = [
  "#1565C0","#2E7D32","#C62828","#F57F17","#6A1B9A",
  "#00838F","#AD1457","#4E342E","#37474F","#558B2F",
  "#0288D1","#388E3C","#E53935","#FB8C00","#8E24AA",
  "#00ACC1","#D81B60","#6D4C41","#546E7A","#689F38",
];

// ─── State ────────────────────────────────────────────────────────────────────

const listOptions = ref<{ label: string; value: string }[]>([]);
const { selectedList, searchText, startDate, endDate, rangeDays, activeWindow } = useSharedControls();
const { confirmDeleteList } = useListDelete(loadListOptions);
const stationsLoading = ref(false);

const downsampleEnabled  = ref(true);
const removeMean         = ref(true);
const outlierThreshold   = ref(5); // metres

type TreeGroup   = { type: "group";   key: string; id: string; children: string[] };
type TreeStation = { type: "station"; key: string; geosncl: string; groupId: string };
type TreeItem    = TreeGroup | TreeStation;

const stationGroups = ref<Map<string, string[]>>(new Map());
const expandedSet   = ref<Set<string>>(new Set());
const selected      = ref<Set<string>>(new Set());
const focusedKey    = ref<string | null>(null);

const positionCache    = ref<Map<string, PositionTrace>>(new Map());
const positionsLoading = ref(false);

// Common-mode-removed second plot set (optional) — a network-wide quantity,
// so unlike positionCache it can't be cached per-stream; it's recomputed
// whenever the selection, date range, method, or mode count changes.
const CMR_METHOD_OPTIONS = [
  { label: "None", value: "none" as const },
  { label: "PCA",  value: "pca"  as const },
  { label: "KLE",  value: "kle"  as const },
];
const cmrMethod = ref<CmrMethod>("none");
const cmrMethodLabel = computed(() =>
  cmrMethod.value === "none" ? "None" : cmrMethod.value.toUpperCase()
);
const cmrNModesRemoved = ref(1);
const cmrLoading = ref(false);
const cmrError = ref("");
const cmrResult = ref<CommonModeRemovedResponse | null>(null);

// ── Chart objects (plain, not reactive – Vue proxy breaks Chart.js) ──────────
// The "_cmr" keys are the common-mode-removed counterparts of east/north/up.
const _canvas:        Record<string, HTMLCanvasElement | null> = {
  east: null, north: null, up: null, east_cmr: null, north_cmr: null, up_cmr: null,
};
const _chart:         Record<string, Chart | null>             = {
  east: null, north: null, up: null, east_cmr: null, north_cmr: null, up_cmr: null,
};
// Keyed by SCATTER_DEFS/HIST_DEFS key, plus a "_cmr" suffixed twin for the
// common-mode-removed series.  Open-ended records rather than fixed keys so the
// CMR panels mount and unmount with the CMR method without a second set of
// declarations to keep in step.
const _scatterCanvas: Record<string, HTMLCanvasElement | null> = {};
const _scatterChart:  Record<string, Chart | null>             = {};
const _histCanvas:    Record<string, HTMLCanvasElement | null> = {};
const _histChart:     Record<string, Chart | null>             = {};
const _histStats:     Record<string, { mean: number; std: number } | null> = {};

// Cleanup functions for canvas event listeners
const _canvasCleanup: Record<string, (() => void) | null> = {
  east: null, north: null, up: null, east_cmr: null, north_cmr: null, up_cmr: null,
};

// ── Zoom state (reactive, watched to sync charts) ───────────────────────────
const _posZoom = ref<{ min: number; max: number } | null>(null);

// ── Interaction state (plain, not reactive – updated on every mouse event) ───
const _posDragState = {
  active: false, chartKey: "", justZoomed: false,
  startPx: 0, currentPx: 0, startPy: 0, currentPy: 0,
  // "x" = shift-drag (time window, shared by every chart), "y" = plain drag
  // (value range, this chart only -- east/north/up are on unrelated scales, so
  // a shared y-zoom would be meaningless).
  mode: "x" as "x" | "y",
};

//: Per-chart y-axis zoom, keyed the same way _chart is.
const _posYZoom = ref<Record<string, { min: number; max: number } | null>>({});
const _crosshair    = { posX: null as number | null };

// ── Save Selection dialog ────────────────────────────────────────────────────
const saveOpen     = ref(false);
const saveRunning  = ref(false);
const saveListName = ref("");
const saveError    = ref("");

function openSaveDialog() {
  saveListName.value = "";
  saveError.value    = "";
  saveRunning.value  = false;
  saveOpen.value     = true;
}

async function doSave() {
  const name = saveListName.value.trim();
  if (!name) { saveError.value = "Name is required."; return; }
  if (/[/\\.]\./.test(name)) { saveError.value = "Invalid characters in name."; return; }
  saveError.value   = "";
  saveRunning.value = true;
  try {
    await saveStreamList(name, [...selected.value]);
    // Refresh list options, keeping current selection
    const currentList = selectedList.value;
    await loadListOptions();
    selectedList.value = currentList;
    saveOpen.value = false;
  } catch (e: any) {
    saveError.value = e?.response?.data?.error ?? "Failed to save.";
  } finally {
    saveRunning.value = false;
  }
}

// ── Save To File (PNG) dialog ─────────────────────────────────────────────────
const savePlotOpen   = ref(false);
const savePlotSaving = ref(false);
const savePlotName   = ref("");
const savePlotError  = ref("");

function _cleanName(s: string): string {
  return s.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
}

function _defaultPlotName(): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const d = new Date();
  const ts = `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`
    + `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
  const list = selectedList.value === "all" ? "All" : selectedList.value;
  return _cleanName(
    `${list}_${startDate.value}_${rangeDays.value}d_${selected.value.size}streams_${ts}`,
  );
}

/** Default filename for coherence/KLE saves (a lighter-weight variant of
 *  _defaultPlotName() — those popups aren't tied to the list/range picker UI
 *  the same way, just the current selection + component). */
function _defaultAnalysisName(kind: string, component?: string): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const d = new Date();
  const ts = `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`
    + `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
  const parts = [kind, component, `${selected.value.size}streams`, ts].filter(Boolean);
  return _cleanName(parts.join("_"));
}

function openSavePlotDialog() {
  savePlotName.value  = _defaultPlotName();
  savePlotError.value = "";
  savePlotSaving.value = false;
  savePlotOpen.value  = true;
}

/** Composite all current chart canvases (only the plots — no controls) into one
 *  white-background PNG canvas.  Returns null if there's nothing to draw. */
function _buildCompositeCanvas(): HTMLCanvasElement | null {
  const ts = COMPONENTS.map(c => _chart[c.key]?.canvas).filter(Boolean) as HTMLCanvasElement[];
  const sc = SCATTER_DEFS.map(s => _scatterChart[s.key]?.canvas).filter(Boolean) as HTMLCanvasElement[];
  const hi = HIST_DEFS.map(h => _histChart[h.key]?.canvas).filter(Boolean) as HTMLCanvasElement[];
  if (!ts.length && !sc.length && !hi.length) return null;

  const dpr = window.devicePixelRatio || 1;
  const gap = 10;
  const titleH = 46;
  const fullW = ts[0]?.clientWidth
    || sc.reduce((s, c) => s + c.clientWidth, 0)
    || 900;

  let totalH = titleH;
  for (const c of ts) totalH += c.clientHeight + gap;
  if (sc.length) totalH += Math.max(...sc.map(c => c.clientHeight)) + gap;
  if (hi.length) totalH += Math.max(...hi.map(c => c.clientHeight)) + gap;
  totalH += gap;

  const canvas = document.createElement("canvas");
  canvas.width  = Math.round(fullW * dpr);
  canvas.height = Math.round(totalH * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, fullW, totalH);

  // Title / metadata
  const list = selectedList.value === "all" ? "All" : selectedList.value;
  ctx.textBaseline = "top";
  ctx.fillStyle = "#222";
  ctx.font = "bold 14px sans-serif";
  ctx.fillText(`${list}   ${startDate.value} → ${endDate.value}   ${selected.value.size} stream(s)`, 8, 10);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#666";
  ctx.fillText(
    `Generated ${new Date().toISOString().replace("T", " ").slice(0, 19)} UTC`
      + (removeMean.value ? "  ·  mean removed" : ""),
    8, 28,
  );

  let y = titleH;
  for (const c of ts) { ctx.drawImage(c, 0, y, fullW, c.clientHeight); y += c.clientHeight + gap; }
  if (sc.length) {
    let x = 0; const h = Math.max(...sc.map(c => c.clientHeight));
    for (const c of sc) { ctx.drawImage(c, x, y, c.clientWidth, c.clientHeight); x += c.clientWidth; }
    y += h + gap;
  }
  if (hi.length) {
    let x = 0; const h = Math.max(...hi.map(c => c.clientHeight));
    for (const c of hi) { ctx.drawImage(c, x, y, c.clientWidth, c.clientHeight); x += c.clientWidth; }
    y += h + gap;
  }
  return canvas;
}

async function doSavePlot() {
  const name = savePlotName.value.trim();
  if (!name) { savePlotError.value = "Name is required."; return; }
  savePlotError.value = "";
  savePlotSaving.value = true;
  try {
    const canvas = _buildCompositeCanvas();
    if (!canvas) { savePlotError.value = "No plots to save."; savePlotSaving.value = false; return; }
    const dataUrl = canvas.toDataURL("image/png");
    const res = await savePlotImage(_cleanName(name), dataUrl);
    savePlotOpen.value = false;
    $q.notify({ type: "positive", message: `Saved ${res.name} — see File Explorer (positions/).` });
  } catch (e: any) {
    savePlotError.value = e?.response?.data?.error ?? "Failed to save.";
  } finally {
    savePlotSaving.value = false;
  }
}

// ── Pairwise Coherence dialog ────────────────────────────────────────────────
// Deliberately independent of positionCache: whether the current `selected`
// set was built up one checkbox at a time or via a bulk action (Select All /
// group check), this always issues one fresh combined request for exactly
// what's selected right now, so the two access patterns can't produce
// different (or partially-loaded / differently-downsampled) results here.

const COMPONENT_OPTIONS = [
  { label: "East",  value: "east"  as const },
  { label: "North", value: "north" as const },
  { label: "Up",    value: "up"    as const },
];

const coherenceOpen      = ref(false);
const coherenceLoading   = ref(false);
const coherenceError     = ref("");
const coherenceComponent = ref<"east" | "north" | "up">("east");
const coherenceResult    = ref<CoherenceResponse | null>(null);
const coherenceLineCanvas = ref<HTMLCanvasElement | null>(null);
const coherenceHeatmapCanvas = ref<HTMLCanvasElement | null>(null);
const coherenceHeatmapTip = ref<{ x: number; y: number; text: string } | null>(null);
let _coherenceLineChart: Chart | null = null;

const MAX_LEGEND_LINES = 40;
// Pairwise -> O(n^2) pairs, so (unlike KLE/PCA) coherence is capped.
const COHERENCE_MAX_STREAMS = 35;

function openCoherenceDialog() {
  coherenceOpen.value = true;
  loadCoherence();
}

async function loadCoherence() {
  if (selected.value.size < 2) { coherenceError.value = "Select at least 2 streams."; return; }
  if (selected.value.size > COHERENCE_MAX_STREAMS) {
    coherenceError.value = `Select at most ${COHERENCE_MAX_STREAMS} streams.`;
    return;
  }
  coherenceError.value = "";
  coherenceLoading.value = true;
  coherenceResult.value = null;
  let result: CoherenceResponse;
  try {
    result = await getCoherence({
      geosncls: [...selected.value].join(","),
      start: startDate.value,
      end: endDate.value,
      component: coherenceComponent.value,
      outlierM: outlierThreshold.value,
    });
  } catch (e: any) {
    coherenceError.value = e?.response?.data?.error ?? "Failed to compute coherence.";
    coherenceLoading.value = false;
    return;
  }
  coherenceResult.value = result;
  // Loading must flip to false — and the DOM must update — BEFORE we grab the
  // canvas refs below: they only mount once the v-else-if="coherenceResult"
  // branch replaces the spinner, so building charts while still "loading"
  // silently no-ops against a null ref.
  coherenceLoading.value = false;
  await nextTick();
  buildCoherenceLineChart();
  drawCoherenceHeatmap();
}

function pairLabel(a: string, b: string): string {
  return `${a} × ${b}`;
}

/** Human-friendly period label for a value in seconds (used on both the line
 *  chart's x-axis and the heatmap's frequency axis — same underlying list). */
function formatPeriod(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

function buildCoherenceLineChart() {
  const canvas = coherenceLineCanvas.value;
  const result = coherenceResult.value;
  if (!canvas || !result) return;
  _coherenceLineChart?.destroy();

  const showLegend = result.pairs.length <= MAX_LEGEND_LINES;
  const datasets = result.pairs.map((p, i) => ({
    label: pairLabel(p.a, p.b),
    data: result.frequencies.map((f, idx) => ({ x: 1 / f, y: p.coherence[idx] })),
    borderColor: COLORS[i % COLORS.length],
    borderWidth: 1.25, pointRadius: 0, tension: 0,
  }));

  _coherenceLineChart = new Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      scales: {
        x: {
          type: "logarithmic", reverse: true,
          title: { display: true, text: "Period", font: { size: 11 } },
          ticks: { callback: v => formatPeriod(Number(v)), maxTicksLimit: 10 },
          grid: { color: "#e0e0e0" },
        },
        y: {
          min: 0, max: 1,
          title: { display: true, text: "Coherence", font: { size: 11 } },
          grid: { color: "#e0e0e0" },
        },
      },
      plugins: {
        legend: {
          display: showLegend, position: "right",
          labels: { font: { size: 9 }, boxWidth: 10 },
        },
        tooltip: {
          callbacks: {
            title: items => formatPeriod(1 / Number(items[0].parsed.x)),
            label: item => `${item.dataset.label}: ${Number(item.parsed.y).toFixed(3)}`,
          },
        },
      },
    },
  });
}

// Sequential density colormap (dark navy -> cyan -> green -> yellow -> red),
// matching the PPSD probability-density plots elsewhere in this app — color
// here means "fraction of pairs", not a coherence value.
const _DENSITY_STOPS: [number, number, number][] = [
  [0, 0, 102],
  [0, 153, 204],
  [0, 255, 0],
  [255, 255, 0],
  [255, 0, 0],
];
function densityColor(t: number): [number, number, number] {
  const k = Math.min(1, Math.max(0, t)) * (_DENSITY_STOPS.length - 1);
  const i = Math.min(_DENSITY_STOPS.length - 2, Math.floor(k));
  const f = k - i;
  const [r0, g0, b0] = _DENSITY_STOPS[i];
  const [r1, g1, b1] = _DENSITY_STOPS[i + 1];
  return [Math.round(r0 + (r1 - r0) * f), Math.round(g0 + (g1 - g0) * f), Math.round(b0 + (b1 - b0) * f)];
}

const HEATMAP_YAXIS_W = 40;
const HEATMAP_PLOT_W  = 720;
const HEATMAP_HEADER_H = 22;
const HEATMAP_ROW_H   = 16;
const HEATMAP_BOTTOM_PAD = 10;  // room for the "0.0" tick label's own height, so it isn't clipped by the canvas edge
const N_COH_BINS = 20;              // coherence-value bins, 0..1
const COH_BIN_SIZE = 1 / N_COH_BINS;

// Per-period, per-coherence-bin density (fraction of pairs) — kept around
// after drawing so the mouse tooltip can hit-test without recomputing.
let _coherenceHeatmapDensity: number[][] | null = null;

/** Build the 2D density histogram: density[col][bin] = fraction of pairs
 *  whose coherence at that period falls in that bin.  This is what lets the
 *  heatmap scale to any pair count — individual pair identity is dropped
 *  here (that's what the line plot above is for); the heatmap instead shows
 *  the *distribution* of coherence across all pairs, at each period. */
function _buildCoherenceDensity(result: CoherenceResponse): number[][] {
  const { frequencies, pairs } = result;
  const nCols = frequencies.length;
  const density: number[][] = Array.from({ length: nCols }, () => new Array(N_COH_BINS).fill(0));
  for (const p of pairs) {
    for (let c = 0; c < nCols; c++) {
      const v = Math.min(1, Math.max(0, p.coherence[c]));
      const bin = Math.min(N_COH_BINS - 1, Math.floor(v * N_COH_BINS));
      density[c][bin] += 1;
    }
  }
  const nPairs = pairs.length || 1;
  for (let c = 0; c < nCols; c++)
    for (let b = 0; b < N_COH_BINS; b++)
      density[c][b] /= nPairs;
  return density;
}

function drawCoherenceHeatmap() {
  const canvas = coherenceHeatmapCanvas.value;
  const result = coherenceResult.value;
  if (!canvas || !result || !result.pairs.length) return;

  const { frequencies } = result;
  const nCols = frequencies.length;
  const density = _buildCoherenceDensity(result);
  _coherenceHeatmapDensity = density;

  let vmax = 0;
  for (const col of density) for (const v of col) vmax = Math.max(vmax, v);
  if (vmax <= 0) vmax = 1;

  const width = HEATMAP_YAXIS_W + HEATMAP_PLOT_W;
  const height = HEATMAP_HEADER_H + N_COH_BINS * HEATMAP_ROW_H + HEATMAP_BOTTOM_PAD;

  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = width + "px";
  canvas.style.height = height + "px";
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#fcfcfb";
  ctx.fillRect(0, 0, width, height);

  // Header: a handful of period ticks (frequencies increase -> periods decrease).
  ctx.fillStyle = "#52514e";
  ctx.font = "10px monospace";
  ctx.textAlign = "center";
  const nTicks = 7;
  for (let t = 0; t < nTicks; t++) {
    const frac = t / (nTicks - 1);
    const idx = Math.min(nCols - 1, Math.round(frac * (nCols - 1)));
    const x = HEATMAP_YAXIS_W + frac * HEATMAP_PLOT_W;
    ctx.fillText(formatPeriod(1 / frequencies[idx]), x, 14);
  }

  // Y-axis: coherence value, 0.0 at the bottom -> 1.0 at the top.  "middle"
  // baseline (rather than the default "alphabetic") keeps every label —
  // including "0.0", whose tick sits exactly on the canvas's bottom edge —
  // centered on its tick instead of drawn below it and clipped off.
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.font = "9px monospace";
  for (let tick = 0; tick <= 5; tick++) {
    const v = tick / 5;
    const y = HEATMAP_HEADER_H + (1 - v) * N_COH_BINS * HEATMAP_ROW_H;
    ctx.fillStyle = "#52514e";
    ctx.fillText(v.toFixed(1), HEATMAP_YAXIS_W - 6, y);
  }
  ctx.textBaseline = "alphabetic";

  const colW = HEATMAP_PLOT_W / nCols;
  for (let b = 0; b < N_COH_BINS; b++) {
    const y = HEATMAP_HEADER_H + (N_COH_BINS - 1 - b) * HEATMAP_ROW_H;
    for (let c = 0; c < nCols; c++) {
      const [r8, g8, b8] = densityColor(density[c][b] / vmax);
      ctx.fillStyle = `rgb(${r8},${g8},${b8})`;
      ctx.fillRect(HEATMAP_YAXIS_W + c * colW, y, colW + 1, HEATMAP_ROW_H);
    }
  }
}

function onHeatmapMouseMove(e: MouseEvent) {
  const result = coherenceResult.value;
  if (!result || !result.pairs.length || !_coherenceHeatmapDensity) { coherenceHeatmapTip.value = null; return; }
  const canvas = e.currentTarget as HTMLCanvasElement;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left, y = e.clientY - rect.top;
  if (x < HEATMAP_YAXIS_W || y < HEATMAP_HEADER_H) { coherenceHeatmapTip.value = null; return; }

  const rowIdx = Math.floor((y - HEATMAP_HEADER_H) / HEATMAP_ROW_H);
  const b = N_COH_BINS - 1 - rowIdx;
  const colW = HEATMAP_PLOT_W / result.frequencies.length;
  const col = Math.floor((x - HEATMAP_YAXIS_W) / colW);
  if (b < 0 || b >= N_COH_BINS || col < 0 || col >= result.frequencies.length) {
    coherenceHeatmapTip.value = null;
    return;
  }
  const period = formatPeriod(1 / result.frequencies[col]);
  const frac = _coherenceHeatmapDensity[col][b];
  const lo = (b * COH_BIN_SIZE).toFixed(2);
  const hi = ((b + 1) * COH_BIN_SIZE).toFixed(2);
  coherenceHeatmapTip.value = {
    x, y,
    text: `${period} · coherence ${lo}–${hi}: ${(frac * 100).toFixed(1)}% of pairs`,
  };
}
function onHeatmapMouseLeave() { coherenceHeatmapTip.value = null; }

/** Stack the line chart + heatmap canvases into one white-background PNG. */
function _buildCoherenceCompositeCanvas(): HTMLCanvasElement | null {
  const result = coherenceResult.value;
  const lineCanvas = _coherenceLineChart?.canvas;
  const heatCanvas = coherenceHeatmapCanvas.value;
  if (!result || (!lineCanvas && !heatCanvas)) return null;

  const dpr = window.devicePixelRatio || 1;
  const gap = 14;
  const titleH = 46;
  const fullW = Math.max(lineCanvas?.clientWidth ?? 0, heatCanvas?.clientWidth ?? 0, 900);
  let totalH = titleH;
  if (lineCanvas) totalH += lineCanvas.clientHeight + gap;
  if (heatCanvas) totalH += heatCanvas.clientHeight + gap;

  const canvas = document.createElement("canvas");
  canvas.width = Math.round(fullW * dpr);
  canvas.height = Math.round(totalH * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, fullW, totalH);

  ctx.textBaseline = "top";
  ctx.fillStyle = "#222";
  ctx.font = "bold 14px sans-serif";
  ctx.fillText(
    `Pairwise Coherence — ${coherenceComponent.value}   ${startDate.value} → ${endDate.value}   ${result.geosncls.length} stream(s)`,
    8, 10,
  );
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#666";
  ctx.fillText(`Generated ${new Date().toISOString().replace("T", " ").slice(0, 19)} UTC`, 8, 28);

  let y = titleH;
  if (lineCanvas) { ctx.drawImage(lineCanvas, 0, y, lineCanvas.clientWidth, lineCanvas.clientHeight); y += lineCanvas.clientHeight + gap; }
  if (heatCanvas) { ctx.drawImage(heatCanvas, 0, y, heatCanvas.clientWidth, heatCanvas.clientHeight); y += heatCanvas.clientHeight + gap; }
  return canvas;
}

function saveCoherencePlot() {
  const canvas = _buildCoherenceCompositeCanvas();
  if (!canvas) { $q.notify({ type: "warning", message: "Nothing to save yet." }); return; }
  $q.dialog({
    title: "Save coherence plot",
    message: "File name",
    prompt: { model: _defaultAnalysisName("coherence", coherenceComponent.value), type: "text" },
    cancel: true,
    persistent: true,
  }).onOk(async (name: string) => {
    const clean = _cleanName(name.trim());
    if (!clean) return;
    try {
      const res = await savePlotImage(clean, canvas.toDataURL("image/png"), "coherence");
      $q.notify({ type: "positive", message: `Saved ${res.name} — see File Explorer (coherence/).` });
    } catch (e: any) {
      $q.notify({ type: "negative", message: e?.response?.data?.error ?? "Failed to save." });
    }
  });
}

// ── Shared decomposition chart builders (KLE + PCA share this rendering) ──
// Both dialogs show all three components (E/N/U) together — one clustered
// bar per mode/stream per component, one line per component — using the
// same fixed color per component everywhere (bars, loadings, and lines).

type PerComponent<T> = Record<"east" | "north" | "up", T>;
const _ENU = ["east", "north", "up"] as const;
const COMPONENT_COLORS: PerComponent<string> = { east: "#1E88E5", north: "#43A047", up: "#FB8C00" };
const COMPONENT_LABELS: PerComponent<string> = { east: "East", north: "North", up: "Up" };

function _buildVarianceClusterChart(
  canvas: HTMLCanvasElement, results: PerComponent<{ variance_explained_pct: number[] }>,
): Chart {
  const maxModes = Math.max(..._ENU.map(c => results[c].variance_explained_pct.length));
  const labels = Array.from({ length: maxModes }, (_, i) => `Mode ${i + 1}`);
  const datasets = _ENU.map(c => ({
    label: COMPONENT_LABELS[c],
    data: Array.from({ length: maxModes }, (_, i) => results[c].variance_explained_pct[i] ?? null),
    backgroundColor: COMPONENT_COLORS[c] + "CC",
    borderColor: COMPONENT_COLORS[c],
    borderWidth: 1,
  }));
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: "%", font: { size: 11 } } },
      },
      plugins: {
        legend: { display: true, position: "top", labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: item => `${item.dataset.label}: ${Number(item.parsed.y).toFixed(1)}%` } },
      },
    },
  });
}

function _buildLoadingsClusterChart(
  canvas: HTMLCanvasElement, geosncls: string[],
  results: PerComponent<{ loadings: number[][] }>, modeIndex: number,
): Chart {
  const datasets = _ENU.map(c => {
    const loadings = results[c].loadings[modeIndex] ?? [];
    return {
      label: COMPONENT_LABELS[c],
      data: geosncls.map((_, i) => loadings[i] ?? null),
      backgroundColor: COMPONENT_COLORS[c] + "CC",
      borderColor: COMPONENT_COLORS[c],
      borderWidth: 1,
    };
  });
  return new Chart(canvas, {
    type: "bar",
    data: { labels: geosncls, datasets },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { font: { size: 9 }, maxRotation: 60, minRotation: 40 } },
        y: { title: { display: true, text: "Loading", font: { size: 11 } } },
      },
      plugins: {
        legend: { display: true, position: "top", labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: item => `${item.dataset.label}: ${Number(item.parsed.y).toFixed(3)}` } },
      },
    },
  });
}

/** All 3 components' reconstructed mode series overlaid on one chart, each
 *  its own (same everywhere in this dialog) color — what the shared signal
 *  actually looks like, as opposed to the loadings chart which only shows
 *  which streams it's concentrated in. */
function _buildModeSeriesOverlayChart(
  canvas: HTMLCanvasElement,
  results: PerComponent<{ modeTimes: number[]; modeSeries: (number | null)[][] }>,
  modeIndex: number,
): Chart {
  const datasets = _ENU.map(c => {
    const r = results[c];
    const series = r.modeSeries[modeIndex] ?? [];
    return {
      label: COMPONENT_LABELS[c],
      data: r.modeTimes.map((t, i) => ({ x: t, y: series[i] ?? null })),
      borderColor: COMPONENT_COLORS[c], borderWidth: 1.25, pointRadius: 0, tension: 0, spanGaps: false,
    };
  });
  return new Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      scales: {
        x: { type: "linear", ticks: { maxTicksLimit: 8, callback: v => _epochLabel(Number(v)) }, grid: { color: "#e0e0e0" } },
        y: { title: { display: true, text: "m", font: { size: 11 } }, grid: { color: "#e0e0e0" } },
      },
      plugins: {
        legend: { display: true, position: "top", labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            title: items => _epochLabel(Number(items[0].parsed.x)),
            label: item => `${item.dataset.label}: ${Number(item.parsed.y).toFixed(4)} m`,
          },
        },
      },
    },
  });
}

/** Stack up to 3 canvases (variance / mode-series / loadings) into one
 *  white-background PNG with a title bar — shared by KLE and PCA saves. */
function _buildDecompositionCompositeCanvas(
  title: string,
  varCanvas: HTMLCanvasElement | undefined, seriesCanvas: HTMLCanvasElement | undefined,
  loadCanvas: HTMLCanvasElement | undefined,
): HTMLCanvasElement | null {
  if (!varCanvas && !seriesCanvas && !loadCanvas) return null;

  const dpr = window.devicePixelRatio || 1;
  const gap = 14;
  const titleH = 46;
  const fullW = Math.max(
    varCanvas?.clientWidth ?? 0, seriesCanvas?.clientWidth ?? 0, loadCanvas?.clientWidth ?? 0, 700,
  );
  let totalH = titleH;
  if (varCanvas) totalH += varCanvas.clientHeight + gap;
  if (seriesCanvas) totalH += seriesCanvas.clientHeight + gap;
  if (loadCanvas) totalH += loadCanvas.clientHeight + gap;

  const canvas = document.createElement("canvas");
  canvas.width = Math.round(fullW * dpr);
  canvas.height = Math.round(totalH * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, fullW, totalH);

  ctx.textBaseline = "top";
  ctx.fillStyle = "#222";
  ctx.font = "bold 14px sans-serif";
  ctx.fillText(title, 8, 10);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#666";
  ctx.fillText(`Generated ${new Date().toISOString().replace("T", " ").slice(0, 19)} UTC`, 8, 28);

  let y = titleH;
  if (varCanvas) { ctx.drawImage(varCanvas, 0, y, varCanvas.clientWidth, varCanvas.clientHeight); y += varCanvas.clientHeight + gap; }
  if (seriesCanvas) { ctx.drawImage(seriesCanvas, 0, y, seriesCanvas.clientWidth, seriesCanvas.clientHeight); y += seriesCanvas.clientHeight + gap; }
  if (loadCanvas) { ctx.drawImage(loadCanvas, 0, y, loadCanvas.clientWidth, loadCanvas.clientHeight); y += loadCanvas.clientHeight + gap; }
  return canvas;
}

// ── Karhunen-Loeve dialog ─────────────────────────────────────────────────────
// Shows all three components (E/N/U) together — fetched in parallel — rather
// than one at a time behind a radio button, so the shared common-mode
// structure across components is visible in one view.

const kleOpen      = ref(false);
const kleLoading    = ref(false);
const kleError      = ref("");
const kleResults    = ref<PerComponent<KleResponse> | null>(null);
const kleLoadingMode = ref(0);  // 0-based index into loadings/modeSeries
const kleVarianceCanvas = ref<HTMLCanvasElement | null>(null);
const kleLoadingsCanvas = ref<HTMLCanvasElement | null>(null);
const kleModeSeriesCanvas = ref<HTMLCanvasElement | null>(null);
let _kleVarianceChart: Chart | null = null;
let _kleLoadingsChart: Chart | null = null;
let _kleModeSeriesChart: Chart | null = null;

const kleModeOptions = computed(() => {
  const r = kleResults.value;
  if (!r) return [];
  const maxModes = Math.max(..._ENU.map(c => r[c].eigenvalues.length));
  return Array.from({ length: maxModes }, (_, i) => ({ label: `Mode ${i + 1}`, value: i }));
});

function openKleDialog() {
  kleOpen.value = true;
  kleLoadingMode.value = 0;
  loadKle();
}

async function loadKle() {
  if (selected.value.size < 2) { kleError.value = "Select at least 2 streams."; return; }
  kleError.value = "";
  kleLoading.value = true;
  kleResults.value = null;
  let results: PerComponent<KleResponse>;
  try {
    const [east, north, up] = await Promise.all(_ENU.map(component => getKle({
      geosncls: [...selected.value].join(","),
      start: startDate.value,
      end: endDate.value,
      component,
      outlierM: outlierThreshold.value,
    })));
    results = { east, north, up };
  } catch (e: any) {
    kleError.value = e?.response?.data?.error ?? "Failed to compute the decomposition.";
    kleLoading.value = false;
    return;
  }
  kleResults.value = results;
  kleLoadingMode.value = 0;
  // Same ordering fix as loadCoherence(): flip loading false (mounting the
  // canvases) before nextTick(), not in a finally that runs after the build.
  kleLoading.value = false;
  await nextTick();
  buildKleCharts();
}

function buildKleCharts() {
  const results = kleResults.value;
  if (!results) return;
  if (kleVarianceCanvas.value) {
    _kleVarianceChart?.destroy();
    _kleVarianceChart = _buildVarianceClusterChart(kleVarianceCanvas.value, results);
  }
  rebuildKleLoadingsChart();
  rebuildKleModeSeriesChart();
}

function rebuildKleLoadingsChart() {
  const results = kleResults.value;
  const canvas = kleLoadingsCanvas.value;
  if (!results || !canvas) return;
  _kleLoadingsChart?.destroy();
  _kleLoadingsChart = _buildLoadingsClusterChart(canvas, results.east.geosncls, results, kleLoadingMode.value);
}

function rebuildKleModeSeriesChart() {
  const results = kleResults.value;
  const canvas = kleModeSeriesCanvas.value;
  if (!results || !canvas) return;
  _kleModeSeriesChart?.destroy();
  _kleModeSeriesChart = _buildModeSeriesOverlayChart(canvas, results, kleLoadingMode.value);
}

watch(kleLoadingMode, () => { rebuildKleLoadingsChart(); rebuildKleModeSeriesChart(); });

function saveKlePlot() {
  const results = kleResults.value;
  if (!results) { $q.notify({ type: "warning", message: "Nothing to save yet." }); return; }
  const canvas = _buildDecompositionCompositeCanvas(
    `Karhunen-Loève — E/N/U   mode ${kleLoadingMode.value + 1}   ${results.east.geosncls.length} stream(s)`,
    _kleVarianceChart?.canvas, _kleModeSeriesChart?.canvas, _kleLoadingsChart?.canvas,
  );
  if (!canvas) { $q.notify({ type: "warning", message: "Nothing to save yet." }); return; }
  $q.dialog({
    title: "Save Karhunen-Loève plot",
    message: "File name",
    prompt: { model: _defaultAnalysisName("kle"), type: "text" },
    cancel: true,
    persistent: true,
  }).onOk(async (name: string) => {
    const clean = _cleanName(name.trim());
    if (!clean) return;
    try {
      const res = await savePlotImage(clean, canvas.toDataURL("image/png"), "kle");
      $q.notify({ type: "positive", message: `Saved ${res.name} — see File Explorer (kle/).` });
    } catch (e: any) {
      $q.notify({ type: "negative", message: e?.response?.data?.error ?? "Failed to save." });
    }
  });
}

// ── Principal Component Analysis (PCA) dialog ────────────────────────────────
// Sibling of the KLE dialog above — same shared chart builders, same shape
// of result, and same all-3-components-together display, but PCA only
// speaks for epochs where every stream overlaps simultaneously
// (n_complete_epochs), vs. KLE's pairwise-complete covariance which uses
// every stream's data even where the network doesn't fully align.

const pcaOpen      = ref(false);
const pcaLoading   = ref(false);
const pcaError     = ref("");
const pcaResults   = ref<PerComponent<PcaResponse> | null>(null);
const pcaLoadingMode = ref(0);
const pcaVarianceCanvas = ref<HTMLCanvasElement | null>(null);
const pcaLoadingsCanvas = ref<HTMLCanvasElement | null>(null);
const pcaModeSeriesCanvas = ref<HTMLCanvasElement | null>(null);
let _pcaVarianceChart: Chart | null = null;
let _pcaLoadingsChart: Chart | null = null;
let _pcaModeSeriesChart: Chart | null = null;

const pcaHasAnyModes = computed(() => {
  const r = pcaResults.value;
  return !!r && _ENU.some(c => r[c].n_modes > 0);
});

const pcaModeOptions = computed(() => {
  const r = pcaResults.value;
  if (!r) return [];
  const maxModes = Math.max(..._ENU.map(c => r[c].eigenvalues.length));
  return Array.from({ length: maxModes }, (_, i) => ({ label: `Mode ${i + 1}`, value: i }));
});

function openPcaDialog() {
  pcaOpen.value = true;
  pcaLoadingMode.value = 0;
  loadPca();
}

async function loadPca() {
  if (selected.value.size < 2) { pcaError.value = "Select at least 2 streams."; return; }
  pcaError.value = "";
  pcaLoading.value = true;
  pcaResults.value = null;
  let results: PerComponent<PcaResponse>;
  try {
    const [east, north, up] = await Promise.all(_ENU.map(component => getPca({
      geosncls: [...selected.value].join(","),
      start: startDate.value,
      end: endDate.value,
      component,
      outlierM: outlierThreshold.value,
    })));
    results = { east, north, up };
  } catch (e: any) {
    pcaError.value = e?.response?.data?.error ?? "Failed to compute the decomposition.";
    pcaLoading.value = false;
    return;
  }
  pcaResults.value = results;
  pcaLoadingMode.value = 0;
  pcaLoading.value = false;
  await nextTick();
  buildPcaCharts();
}

function buildPcaCharts() {
  const results = pcaResults.value;
  if (!results || !pcaHasAnyModes.value) return;
  if (pcaVarianceCanvas.value) {
    _pcaVarianceChart?.destroy();
    _pcaVarianceChart = _buildVarianceClusterChart(pcaVarianceCanvas.value, results);
  }
  rebuildPcaLoadingsChart();
  rebuildPcaModeSeriesChart();
}

function rebuildPcaLoadingsChart() {
  const results = pcaResults.value;
  const canvas = pcaLoadingsCanvas.value;
  if (!results || !canvas || !pcaHasAnyModes.value) return;
  _pcaLoadingsChart?.destroy();
  _pcaLoadingsChart = _buildLoadingsClusterChart(canvas, results.east.geosncls, results, pcaLoadingMode.value);
}

function rebuildPcaModeSeriesChart() {
  const results = pcaResults.value;
  const canvas = pcaModeSeriesCanvas.value;
  if (!results || !canvas || !pcaHasAnyModes.value) return;
  _pcaModeSeriesChart?.destroy();
  _pcaModeSeriesChart = _buildModeSeriesOverlayChart(canvas, results, pcaLoadingMode.value);
}

watch(pcaLoadingMode, () => { rebuildPcaLoadingsChart(); rebuildPcaModeSeriesChart(); });

function savePcaPlot() {
  const results = pcaResults.value;
  if (!results) { $q.notify({ type: "warning", message: "Nothing to save yet." }); return; }
  const canvas = _buildDecompositionCompositeCanvas(
    `PCA — E/N/U   mode ${pcaLoadingMode.value + 1}   ${results.east.geosncls.length} stream(s)`,
    _pcaVarianceChart?.canvas, _pcaModeSeriesChart?.canvas, _pcaLoadingsChart?.canvas,
  );
  if (!canvas) { $q.notify({ type: "warning", message: "Nothing to save yet." }); return; }
  $q.dialog({
    title: "Save PCA plot",
    message: "File name",
    prompt: { model: _defaultAnalysisName("pca"), type: "text" },
    cancel: true,
    persistent: true,
  }).onOk(async (name: string) => {
    const clean = _cleanName(name.trim());
    if (!clean) return;
    try {
      const res = await savePlotImage(clean, canvas.toDataURL("image/png"), "pca");
      $q.notify({ type: "positive", message: `Saved ${res.name} — see File Explorer (pca/).` });
    } catch (e: any) {
      $q.notify({ type: "negative", message: e?.response?.data?.error ?? "Failed to save." });
    }
  });
}

// ── Fetch dialog ─────────────────────────────────────────────────────────────
const fetchOpen    = ref(false);
const fetchRunning = ref(false);
const fetchDone    = ref(false);
const fetchWorkers = ref(10);
const fetchLog     = ref<FetchEvent[]>([]);
const fetchLogEl   = ref<HTMLElement | null>(null);

let loadTimer: ReturnType<typeof setTimeout> | null = null;

// ─── Computed ─────────────────────────────────────────────────────────────────

const flatItems = computed((): TreeItem[] => {
  const items: TreeItem[] = [];
  for (const [id, children] of stationGroups.value) {
    items.push({ type: "group", key: id, id, children });
    if (expandedSet.value.has(id))
      for (const g of children) items.push({ type: "station", key: g, geosncl: g, groupId: id });
  }
  return items;
});

const totalPointsLoaded = computed(() => {
  let n = 0;
  for (const g of selected.value) n += positionCache.value.get(g)?.times.length ?? 0;
  return n;
});

const anyDownsampled = computed(() =>
  [...selected.value].some(g => (positionCache.value.get(g)?.downsampleFactor ?? 1) > 1)
);

const noDataForRange = computed(() =>
  !positionsLoading.value &&
  selected.value.size > 0 &&
  [...selected.value].every(g => {
    const t = positionCache.value.get(g);
    return t !== undefined && t.times.length === 0;
  })
);

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadListOptions();
  if (!startDate.value) {
    try {
      const range = await getDataRange();
      if (range.max) {
        // Default to the last 7 days of available data, not today
        const maxDate = new Date(range.max + "T12:00:00Z");
        const minDate = new Date(maxDate.getTime() - 7 * 86_400_000);
        endDate.value   = range.max;
        startDate.value = dateStr(minDate);
        rangeDays.value = 7;
        activeWindow.value = "7d";
      } else {
        applyWindow(TIME_WINDOWS.find(w => w.label === "7d")!);
      }
    } catch {
      applyWindow(TIME_WINDOWS.find(w => w.label === "7d")!);
    }
  }
  await reloadStations();
});

onBeforeUnmount(() => {
  [...Object.values(_chart), ...Object.values(_scatterChart), ...Object.values(_histChart)].forEach(c => c?.destroy());
  Object.values(_canvasCleanup).forEach(fn => fn?.());
});

// ─── Stream lists ─────────────────────────────────────────────────────────────

async function loadListOptions() {
  try {
    const r = await getStreamLists();
    listOptions.value = [{ label: "All", value: "all" }, ...r.lists.map(l => ({ label: l, value: l }))];
  } catch { listOptions.value = [{ label: "All", value: "all" }]; }
}

//: In-flight reloadStations(), so a bulk action can wait for the filter it
//: just triggered instead of acting on the pre-filter list.
let _stationsReload: Promise<void> | null = null;

/** Resolve once any in-flight station reload has landed. */
function pendingStations(): Promise<void> {
  return _stationsReload ?? Promise.resolve();
}

function reloadStations(): Promise<void> {
  _stationsReload = _reloadStations().finally(() => { _stationsReload = null; });
  return _stationsReload;
}

async function _reloadStations() {
  stationsLoading.value = true;
  try {
    const r = await getStations({ list: selectedList.value, search: searchText.value || undefined });
    const groups = new Map<string, string[]>();
    for (const { geosncl } of r.stations) {
      const id = geosncl.split(".")[0];
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id)!.push(geosncl);
    }
    stationGroups.value = groups;
  } catch (e) { console.error(e); }
  finally { stationsLoading.value = false; }
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

function dateStr(d: Date) { return d.toISOString().slice(0, 10); }
function parseDateStr(s: string) {
  const d = new Date(s + "T00:00:00Z"); return isNaN(d.getTime()) ? null : d;
}
function applyWindow(w: { label: string; hours: number }) {
  const end = new Date(), start = new Date(end.getTime() - w.hours * 3_600_000);
  startDate.value = dateStr(start); endDate.value = dateStr(end);
  rangeDays.value = Math.round(w.hours / 24);
  activeWindow.value = w.label;
  positionCache.value.clear(); scheduleLoad();
}
function onFromChange() {
  const from = parseDateStr(startDate.value);
  if (from) endDate.value = dateStr(new Date(from.getTime() + rangeDays.value * 86_400_000));
  activeWindow.value = null; positionCache.value.clear(); scheduleLoad();
}
function onToChange() {
  const from = parseDateStr(startDate.value), to = parseDateStr(endDate.value);
  if (from && to && to > from) rangeDays.value = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  activeWindow.value = null; positionCache.value.clear(); scheduleLoad();
}
function _afterRangeEdit() {
  const fromD = parseDateStr(startDate.value), toD = parseDateStr(endDate.value);
  if (fromD && toD && toD > fromD) rangeDays.value = Math.round((toD.getTime() - fromD.getTime()) / 86_400_000);
  activeWindow.value = null; positionCache.value.clear(); scheduleLoad();
}
const fromPopup = ref<{ hide?: () => void } | null>(null);
const toPopup   = ref<{ hide?: () => void } | null>(null);
const onFromBoxSelect = createBoxRangeSelectHandler(
  (date) => { startDate.value = date; if (!endDate.value) endDate.value = date; _afterRangeEdit(); },
  (from, to) => { startDate.value = from; endDate.value = to; _afterRangeEdit(); },
  () => fromPopup.value?.hide?.(),
);
const onToBoxSelect = createBoxRangeSelectHandler(
  (date) => { endDate.value = date; if (!startDate.value) startDate.value = date; _afterRangeEdit(); },
  (from, to) => { startDate.value = from; endDate.value = to; _afterRangeEdit(); },
  () => toPopup.value?.hide?.(),
);

// ─── Tree interaction ─────────────────────────────────────────────────────────

function toggleExpand(id: string) {
  const s = new Set(expandedSet.value); s.has(id) ? s.delete(id) : s.add(id); expandedSet.value = s;
}
function groupCheckState(id: string): boolean | null {
  const ch = stationGroups.value.get(id) ?? [];
  const n = ch.filter(g => selected.value.has(g)).length;
  return n === 0 ? false : n === ch.length ? true : null;
}
function _setSelected(next: Set<string>) { selected.value = next; scheduleLoad(); }

function onGroupCheck(id: string, checked: boolean) {
  const ch = stationGroups.value.get(id) ?? [], next = new Set(selected.value);
  if (checked) ch.forEach(g => next.add(g)); else ch.forEach(g => next.delete(g));
  _setSelected(next);
}
function onStationCheck(geosncl: string, checked: boolean) {
  const next = new Set(selected.value);
  checked ? next.add(geosncl) : next.delete(geosncl);
  _setSelected(next);
}
function onItemClick(item: TreeItem, event: MouseEvent) {
  focusedKey.value = item.key;
  const adding = event.shiftKey;
  const next = new Set(adding ? selected.value : new Set<string>());
  if (item.type === "group") {
    const ch = stationGroups.value.get(item.id) ?? [];
    const allSel = ch.every(g => selected.value.has(g));
    if (adding && allSel) ch.forEach(g => next.delete(g)); else ch.forEach(g => next.add(g));
  } else {
    if (adding && selected.value.has(item.geosncl)) next.delete(item.geosncl);
    else next.add(item.geosncl);
  }
  _setSelected(next);
}
function clearSelection() { _setSelected(new Set()); }

//: Bulk selection cap.  Past a few hundred series the three charts are
//: unreadable anyway, and the request behind them (one Arrow read per stream,
//: thousands of points each) locks the tab up for minutes.  Explicitly ticking
//: streams is left uncapped — that is a deliberate choice by the user.
const SELECT_ALL_MAX = 250;

async function selectAll() {
  // Clicking this button blurs the filter box, which is what *starts* the
  // filtered reload.  Without waiting for it, Select All reads the pre-filter
  // station list and selects every stream in the list rather than the handful
  // the filter shows — which then stalls the page loading them and looks like
  // "nothing plotted".
  await pendingStations();

  const all: string[] = [];
  for (const ch of stationGroups.value.values()) all.push(...ch);

  if (all.length > SELECT_ALL_MAX) {
    $q.notify({
      type: "warning",
      timeout: 6000,
      message: `${all.length.toLocaleString()} streams match — selecting the first `
             + `${SELECT_ALL_MAX}. Narrow the filter to choose which.`,
    });
  }
  _setSelected(new Set(all.slice(0, SELECT_ALL_MAX)));
}
function onTreeKeydown(e: KeyboardEvent) {
  const items = flatItems.value; if (!items.length) return;
  const idx = items.findIndex(i => i.key === focusedKey.value);
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const next = e.key === "ArrowDown" ? Math.min(items.length - 1, idx < 0 ? 0 : idx + 1)
                                     : Math.max(0, idx < 0 ? 0 : idx - 1);
  const item = items[next]; focusedKey.value = item.key;
  const nextSel = new Set(e.shiftKey ? selected.value : new Set<string>());
  if (item.type === "group") (stationGroups.value.get(item.id) ?? []).forEach(g => nextSel.add(g));
  else nextSel.add(item.geosncl);
  _setSelected(nextSel);
}

// ─── Canvas management ────────────────────────────────────────────────────────

function setCanvas(key: string, el: unknown) {
  const canvas = el as HTMLCanvasElement | null;
  if (!canvas) {
    _chart[key]?.destroy(); _chart[key] = null;
    _canvasCleanup[key]?.(); _canvasCleanup[key] = null;
    // Also drop the (now-detached) element itself — otherwise the next
    // updateCharts() call that runs while this block is unmounted (e.g. the
    // debounced loadPositions() triggered by the Clear that unmounted it)
    // sees a stale-but-truthy _canvas[key], happily builds a Chart bound to
    // a canvas no longer in the DOM, and — since _chart[key] is then
    // non-null — never rebuilds it against the real canvas once one remounts.
    _canvas[key] = null;
  } else {
    _canvas[key] = canvas;
    _canvasCleanup[key] = _attachListeners(canvas, key);
  }
}
function setScatterCanvas(key: string, el: unknown) {
  const canvas = el as HTMLCanvasElement | null;
  if (!canvas) {
    _scatterChart[key]?.destroy(); _scatterChart[key] = null; _scatterCanvas[key] = null;
    _scatterCleanup[key]?.(); _scatterCleanup[key] = null;
  } else {
    _scatterCanvas[key] = canvas;
    _scatterCleanup[key]?.();
    _scatterCleanup[key] = _attachScatterListeners(canvas, key);
  }
}

//: Per-scatter box zoom.  Unlike the time-series charts these are not on a
//: shared axis -- each panel plots a different pair of components -- so zooming
//: one leaves the others alone.
const _scatterZoom = ref<Record<string, { xMin: number; xMax: number; yMin: number; yMax: number } | null>>({});
const _scatterDrag = {
  active: false, key: "", startPx: 0, startPy: 0, currentPx: 0, currentPy: 0,
};
const _scatterCleanup: Record<string, (() => void) | null> = {};

/**
 * Shift-drag a box to zoom into it; a plain click zooms back out.
 *
 * Shift (rather than a plain drag, as on the time series) because these panels
 * are square scatters where a drag has no single obvious axis — the box is the
 * gesture, and reserving plain click for "reset" keeps one unmodified action
 * per plot type.
 */
function _attachScatterListeners(canvas: HTMLCanvasElement, key: string): () => void {
  const drag = _scatterDrag;
  const chart = () => _scatterChart[key];

  const onMousedown = (e: MouseEvent) => {
    if (!e.shiftKey) return;
    e.preventDefault();
    drag.active = true; drag.key = key;
    drag.startPx = e.offsetX; drag.startPy = e.offsetY;
    drag.currentPx = e.offsetX; drag.currentPy = e.offsetY;
  };

  const onMousemove = (e: MouseEvent) => {
    if (!drag.active || drag.key !== key) return;
    drag.currentPx = e.offsetX; drag.currentPy = e.offsetY;
    chart()?.render();
  };

  const onMouseup = (e: MouseEvent) => {
    const c = chart();
    if (drag.active && drag.key === key) {
      drag.currentPx = e.offsetX; drag.currentPy = e.offsetY;
      const dx = Math.abs(drag.currentPx - drag.startPx);
      const dy = Math.abs(drag.currentPy - drag.startPy);
      drag.active = false;
      if (c && dx > DRAG_SLOP && dy > DRAG_SLOP) {
        const xs = c.scales["x"], ys = c.scales["y"];
        const xMin = xs?.getValueForPixel(Math.min(drag.startPx, drag.currentPx));
        const xMax = xs?.getValueForPixel(Math.max(drag.startPx, drag.currentPx));
        // Pixels grow downward, so the top of the box is the larger value.
        const yMax = ys?.getValueForPixel(Math.min(drag.startPy, drag.currentPy));
        const yMin = ys?.getValueForPixel(Math.max(drag.startPy, drag.currentPy));
        if (xMin !== undefined && xMax !== undefined && yMin !== undefined && yMax !== undefined
            && xMax > xMin && yMax > yMin) {
          _scatterZoom.value = { ..._scatterZoom.value, [key]: { xMin, xMax, yMin, yMax } };
        }
        return;
      }
      return;
    }
    // Plain click, no box: back to the full range.
    if (!e.shiftKey && _scatterZoom.value[key]) {
      _scatterZoom.value = { ..._scatterZoom.value, [key]: null };
    }
  };

  const onMouseleave = () => { if (drag.active && drag.key === key) { drag.active = false; chart()?.render(); } };
  const onContextmenu = (e: MouseEvent) => {
    e.preventDefault();
    _scatterZoom.value = { ..._scatterZoom.value, [key]: null };
  };

  canvas.addEventListener("mousedown", onMousedown);
  canvas.addEventListener("mousemove", onMousemove);
  canvas.addEventListener("mouseup", onMouseup);
  canvas.addEventListener("mouseleave", onMouseleave);
  canvas.addEventListener("contextmenu", onContextmenu);
  return () => {
    canvas.removeEventListener("mousedown", onMousedown);
    canvas.removeEventListener("mousemove", onMousemove);
    canvas.removeEventListener("mouseup", onMouseup);
    canvas.removeEventListener("mouseleave", onMouseleave);
    canvas.removeEventListener("contextmenu", onContextmenu);
  };
}

/** Draws the shift-drag box while it is being dragged. */
function _scatterDragPlugin(key: string): object {
  return {
    id: `scatter-drag-${key}`,
    afterDraw(chart: Chart) {
      const drag = _scatterDrag;
      if (!drag.active || drag.key !== key) return;
      const { left, right, top, bottom } = chart.chartArea;
      const x1 = Math.max(left, Math.min(drag.startPx, drag.currentPx));
      const x2 = Math.min(right, Math.max(drag.startPx, drag.currentPx));
      const y1 = Math.max(top, Math.min(drag.startPy, drag.currentPy));
      const y2 = Math.min(bottom, Math.max(drag.startPy, drag.currentPy));
      if (x2 <= x1 || y2 <= y1) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.fillStyle = "rgba(33,150,243,0.12)";
      ctx.strokeStyle = "rgba(33,150,243,0.7)";
      ctx.lineWidth = 1;
      ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.restore();
    },
  };
}
function setHistCanvas(key: string, el: unknown) {
  const canvas = el as HTMLCanvasElement | null;
  if (!canvas) { _histChart[key]?.destroy(); _histChart[key] = null; _histCanvas[key] = null; }
  else { _histCanvas[key] = canvas; }
}

//: Pixels of movement below which a press counts as a click, not a drag.
const DRAG_SLOP = 5;

/** Back to the full view on every chart — both axes. */
function resetPosZoom() {
  _posZoom.value = null;
  _posYZoom.value = {};
}

function _attachListeners(canvas: HTMLCanvasElement, chartKey: string): () => void {
  const drag = _posDragState;
  const zoomRef = _posZoom;
  const getChart = () => _chart[chartKey];
  const renderPeers = () => { Object.values(_chart).forEach(c => c?.render()); };

  const onMousedown = (e: MouseEvent) => {
    e.preventDefault();
    drag.active = true; drag.chartKey = chartKey;
    drag.mode = e.shiftKey ? "x" : "y";
    drag.startPx = e.offsetX; drag.currentPx = e.offsetX;
    drag.startPy = e.offsetY; drag.currentPy = e.offsetY;
  };

  const onMousemove = (e: MouseEvent) => {
    const chart = getChart();
    if (chart) {
      _crosshair.posX = chart.scales["x"]?.getValueForPixel(e.offsetX) ?? null;
      renderPeers();
    }
    if (drag.active && drag.chartKey === chartKey) {
      drag.currentPx = e.offsetX;
      drag.currentPy = e.offsetY;
      getChart()?.render();
    }
  };

  const onMouseup = (e: MouseEvent) => {
    if (!drag.active || drag.chartKey !== chartKey) return;
    drag.currentPx = e.offsetX;
    drag.currentPy = e.offsetY;
    const chart = getChart();
    const dx = Math.abs(drag.currentPx - drag.startPx);
    const dy = Math.abs(drag.currentPy - drag.startPy);

    if (chart && drag.mode === "x" && dx > DRAG_SLOP) {
      const dMin = chart.scales["x"]?.getValueForPixel(Math.min(drag.startPx, drag.currentPx));
      const dMax = chart.scales["x"]?.getValueForPixel(Math.max(drag.startPx, drag.currentPx));
      if (dMin !== undefined && dMax !== undefined && dMax > dMin) {
        zoomRef.value = { min: dMin, max: dMax };
        drag.justZoomed = true;
      }
    } else if (chart && drag.mode === "y" && dy > DRAG_SLOP) {
      // Pixels grow downward, so the *top* of the band is the larger value.
      const vTop = chart.scales["y"]?.getValueForPixel(Math.min(drag.startPy, drag.currentPy));
      const vBottom = chart.scales["y"]?.getValueForPixel(Math.max(drag.startPy, drag.currentPy));
      if (vTop !== undefined && vBottom !== undefined && vTop > vBottom) {
        _posYZoom.value = { ..._posYZoom.value, [chartKey]: { min: vBottom, max: vTop } };
        drag.justZoomed = true;
      }
    } else if (dx <= DRAG_SLOP && dy <= DRAG_SLOP && !e.shiftKey) {
      // A plain click with no drag: back to the full view.  Both axes, since
      // the time axis is shared across the charts anyway — resetting only the
      // one you clicked would leave the others zoomed to a window that is no
      // longer visible anywhere.
      resetPosZoom();
    }
    drag.active = false;
  };

  const onMouseleave = () => {
    _crosshair.posX = null;
    if (drag.active && drag.chartKey === chartKey) drag.active = false;
    renderPeers();
  };

  const onContextmenu = (e: MouseEvent) => { e.preventDefault(); resetPosZoom(); };

  canvas.addEventListener("mousedown",    onMousedown);
  canvas.addEventListener("mousemove",    onMousemove);
  canvas.addEventListener("mouseup",      onMouseup);
  canvas.addEventListener("mouseleave",   onMouseleave);
  canvas.addEventListener("contextmenu",  onContextmenu);
  return () => {
    canvas.removeEventListener("mousedown",   onMousedown);
    canvas.removeEventListener("mousemove",   onMousemove);
    canvas.removeEventListener("mouseup",     onMouseup);
    canvas.removeEventListener("mouseleave",  onMouseleave);
    canvas.removeEventListener("contextmenu", onContextmenu);
  };
}

// ─── Chart helpers ────────────────────────────────────────────────────────────

function _colorFor(geosncl: string): string {
  const all = [...stationGroups.value.values()].flat();
  return COLORS[(Math.max(0, all.indexOf(geosncl))) % COLORS.length];
}

function _epochLabel(ms: number): string {
  const d = new Date(ms);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
    + " " + d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
}

function _interactionPlugin(chartKey: string): object {
  const drag  = _posDragState;
  const xhair = () => _crosshair.posX;

  return {
    id: `iact-pos-${chartKey}`,
    afterDraw(chart: Chart) {
      const ctx = chart.ctx;
      const { left, right, top, bottom } = chart.chartArea;

      // Crosshair
      const xData = xhair();
      if (xData !== null) {
        const xPx = chart.scales["x"]?.getPixelForValue(xData);
        if (xPx !== undefined && xPx >= left && xPx <= right) {
          ctx.save();
          ctx.strokeStyle = "rgba(80,80,80,0.5)";
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 3]);
          ctx.beginPath(); ctx.moveTo(xPx, top); ctx.lineTo(xPx, bottom); ctx.stroke();
          ctx.restore();
        }
      }

      // Drag selection band (only on the chart being dragged).  Vertical band
      // for a shift-drag (time window), horizontal for a plain drag (values),
      // so the gesture's axis is obvious before you let go.
      if (drag.active && drag.chartKey === chartKey) {
        ctx.save();
        ctx.fillStyle   = "rgba(33,150,243,0.12)";
        ctx.strokeStyle = "rgba(33,150,243,0.7)";
        ctx.lineWidth = 1;
        if (drag.mode === "x") {
          const x1 = Math.max(left,  Math.min(drag.startPx, drag.currentPx));
          const x2 = Math.min(right, Math.max(drag.startPx, drag.currentPx));
          if (x2 > x1) {
            ctx.fillRect(x1, top, x2 - x1, bottom - top);
            ctx.strokeRect(x1, top, x2 - x1, bottom - top);
          }
        } else {
          const y1 = Math.max(top,    Math.min(drag.startPy, drag.currentPy));
          const y2 = Math.min(bottom, Math.max(drag.startPy, drag.currentPy));
          if (y2 > y1) {
            ctx.fillRect(left, y1, right - left, y2 - y1);
            ctx.strokeRect(left, y1, right - left, y2 - y1);
          }
        }
        ctx.restore();
      }
    },
  };
}

function _makeOnClick(): (e: any, elems: any[], chart: Chart) => void {
  return (event, elements, chart) => {
    if (!event.native?.shiftKey) return;
    if (_posDragState.justZoomed) { _posDragState.justZoomed = false; return; }
    let dsIdx = elements.length > 0 ? elements[0].datasetIndex : -1;
    if (dsIdx < 0) {
      const nearest = chart.getElementsAtEventForMode(event.native, "nearest", { intersect: false }, false);
      if (nearest.length) dsIdx = nearest[0].datasetIndex;
    }
    if (dsIdx < 0) return;
    const geosncl = chart.data.datasets[dsIdx]?.label;
    if (!geosncl) return;
    const next = new Set(selected.value); next.delete(geosncl); _setSelected(next);
  };
}

function _makePosChart(key: string, label: string): Chart | null {
  const canvas = _canvas[key]; if (!canvas) return null;
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: { mode: "nearest", intersect: false, axis: "xy" },
      scales: {
        x: { type: "linear", ticks: { maxTicksLimit: 8, callback: v => _epochLabel(Number(v)) }, grid: { color: "#e0e0e0" } },
        y: { title: { display: true, text: label, font: { size: 11 } }, grid: { color: "#e0e0e0" }, ticks: { callback: (v: number | string) => Number(v).toExponential(1) } },
      },
      plugins: {
        legend: { position: "right", labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            title: items => _epochLabel(Number(items[0].parsed.x)),
            label: item  => `${item.dataset.label}: ${item.parsed.y?.toExponential(2) ?? "—"} mm`,
          },
        },
      },
      onClick: _makeOnClick(),
    },
    plugins: [_interactionPlugin(key)] as any,
  });
}

// ─── Zoom watchers ────────────────────────────────────────────────────────────

watch(_posZoom, zoom => {
  for (const c of Object.values(_chart)) {
    if (!c) continue;
    const xs = (c.options.scales as any)?.x;
    if (!xs) continue;
    if (zoom) { xs.min = zoom.min; xs.max = zoom.max; } else { delete xs.min; delete xs.max; }
    c.update("none");
  }
});

watch(_scatterZoom, () => updateCharts(), { deep: true });

// Per-chart, unlike the shared x zoom: east/north/up (and their
// common-mode-removed twins) are on unrelated value scales.
watch(_posYZoom, zooms => {
  for (const [key, c] of Object.entries(_chart)) {
    if (!c) continue;
    const ys = (c.options.scales as any)?.y;
    if (!ys) continue;
    const z = zooms[key];
    if (z) { ys.min = z.min; ys.max = z.max; } else { delete ys.min; delete ys.max; }
    c.update("none");
  }
}, { deep: true });

// ─── Data processing ─────────────────────────────────────────────────────────

function _median(arr: number[]): number {
  const s = [...arr].sort((a, b) => a - b), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
type Processed = { chartData: Array<{ x: number; y: number | null }>; specTimes: number[]; specVals: number[] };
// Structural — satisfied by both PositionTrace and CommonModeRemovedTrace.
type ComponentSource = Pick<PositionTrace, "times" | "east" | "north" | "up">;

function processComponent(trace: ComponentSource, comp: "east" | "north" | "up"): Processed {
  const raw = trace[comp] as (number | null)[];
  const times = trace.times;
  const validRaw = raw.filter((v): v is number => v !== null);
  if (!validRaw.length) return { chartData: [], specTimes: [], specVals: [] };

  const med = _median(validRaw);
  const thresh = outlierThreshold.value;
  const filtered: (number | null)[] = raw.map(v => v !== null && Math.abs(v - med) <= thresh ? v : null);

  const inliers = filtered.filter((v): v is number => v !== null);
  const mean = inliers.length ? inliers.reduce((s, v) => s + v, 0) / inliers.length : 0;

  const displayed: (number | null)[] = filtered.map(v =>
    v !== null ? (removeMean.value ? v - mean : v) * 1000 : null
  );

  // Gap detection: median consecutive dt among valid points
  const dts: number[] = [];
  for (let i = 1; i < times.length; i++)
    if (displayed[i] !== null && displayed[i-1] !== null) dts.push(times[i] - times[i-1]);
  const medDt = dts.length ? _median(dts) : 0;
  const gapThresh = 3 * medDt;

  const chartData: Array<{ x: number; y: number | null }> = [];
  for (let i = 0; i < times.length; i++) {
    chartData.push({ x: times[i], y: displayed[i] });
    if (medDt > 0 && i < times.length - 1 && times[i+1] - times[i] > gapThresh)
      chartData.push({ x: (times[i] + times[i+1]) / 2, y: null });
  }

  const specTimes: number[] = [], specVals: number[] = [];
  times.forEach((t, i) => { if (displayed[i] !== null) { specTimes.push(t); specVals.push(displayed[i] as number); } });

  return { chartData, specTimes, specVals };
}

// ─── Scatter / histogram chart factories ─────────────────────────────────────

function _makeScatterChart(key: string, xLabel: string, yLabel: string): Chart | null {
  const canvas = _scatterCanvas[key]; if (!canvas) return null;
  return new Chart(canvas, {
    type: "scatter",
    data: { datasets: [] },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      scales: {
        x: { grid: { color: "#e0e0e0" },
             title: { display: true, text: xLabel, font: { size: 10 } },
             ticks: { font: { size: 9 }, maxTicksLimit: 5 } },
        y: { grid: { color: "#e0e0e0" },
             title: { display: true, text: yLabel, font: { size: 10 } },
             ticks: { font: { size: 9 }, maxTicksLimit: 5 } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: item => `${item.dataset.label}: (${Number(item.parsed.x).toFixed(2)}, ${Number(item.parsed.y).toFixed(2)}) mm`,
        }},
      },
    },
    plugins: [_scatterDragPlugin(key)] as any,
  });
}

function _histStatsPlugin(key: string): object {
  return {
    id: `hist-stats-${key}`,
    afterDraw(chart: any) {
      const stats = _histStats[key];
      const labels = chart.data.labels as string[] | undefined;
      if (!stats || !labels?.length || labels.length < 2) return;
      const ctx = chart.ctx;
      const xScale = chart.scales["x"];
      if (!xScale) return;
      const { top, bottom, left } = chart.chartArea;
      // Categorical scale: equally-spaced bins.
      // Bin centers are labels[0], labels[1], … labels[n-1].
      // Left edge of first bin = labels[0] - binW/2; right edge of last = labels[n-1] + binW/2.
      const n = labels.length;
      const v0 = parseFloat(labels[0]), vN = parseFloat(labels[n - 1]);
      if (isNaN(v0) || isNaN(vN)) return;
      const binW = (vN - v0) / (n - 1);
      const dataMin = v0 - binW / 2;
      const dataRange = binW * n;
      const chartW = xScale.right - xScale.left;
      const dataToPx = (v: number) => xScale.left + ((v - dataMin) / dataRange) * chartW;

      const drawLine = (v: number, color: string, dash: number[]) => {
        const px = dataToPx(v);
        if (px < xScale.left - 1 || px > xScale.right + 1) return;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash(dash);
        ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, bottom); ctx.stroke();
        ctx.restore();
      };

      drawLine(stats.mean,             "rgba(20,20,20,0.85)", []);
      drawLine(stats.mean - stats.std, "rgba(20,20,20,0.45)", [5, 3]);
      drawLine(stats.mean + stats.std, "rgba(20,20,20,0.45)", [5, 3]);

      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,0.78)";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(`μ = ${stats.mean.toFixed(2)}`, left + 4, top + 12);
      ctx.fillText(`σ = ${stats.std.toFixed(2)}`, left + 4, top + 24);
      ctx.restore();
    },
  };
}

function _makeHistChart(key: string, label: string): Chart | null {
  const canvas = _histCanvas[key]; if (!canvas) return null;
  return new Chart(canvas, {
    type: "bar",
    data: { labels: [], datasets: [] },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false,
      scales: {
        x: { grid: { color: "#e0e0e0" },
             title: { display: true, text: label, font: { size: 10 } },
             ticks: { font: { size: 9 }, maxTicksLimit: 6 } },
        y: { grid: { color: "#e0e0e0" }, ticks: { font: { size: 9 }, maxTicksLimit: 4 } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: item => `${item.dataset.label}: ${item.parsed.y} pts`,
        }},
      },
    },
    plugins: [_histStatsPlugin(key)] as any,
  });
}

function _histBins(allVals: number[][], numBins: number): { labels: string[]; counts: number[][] } {
  const flat = allVals.flat();
  if (!flat.length) return { labels: [], counts: allVals.map(() => []) };
  const lo = flat.reduce((a, b) => Math.min(a, b), Infinity);
  const hi = flat.reduce((a, b) => Math.max(a, b), -Infinity);
  if (lo === hi) return { labels: [lo.toFixed(1)], counts: allVals.map(v => [v.length]) };
  const w = (hi - lo) / numBins;
  const labels = Array.from({ length: numBins }, (_, i) => (lo + (i + 0.5) * w).toFixed(1));
  const counts = allVals.map(vals => {
    const cnt = new Array(numBins).fill(0);
    for (const v of vals) { const b = Math.min(Math.floor((v - lo) / w), numBins - 1); cnt[b]++; }
    return cnt;
  });
  return { labels, counts };
}

// ─── Chart update ─────────────────────────────────────────────────────────────

function updateCharts() {
  // Process all selected stations once; reuse across time-series, scatter, histogram
  const processed = new Map<string, Record<"east" | "north" | "up", Processed>>();
  for (const geosncl of selected.value) {
    const trace = positionCache.value.get(geosncl);
    if (!trace) continue;
    processed.set(geosncl, {
      east:  processComponent(trace, "east"),
      north: processComponent(trace, "north"),
      up:    processComponent(trace, "up"),
    });
  }

  // ── Time-series ──────────────────────────────────────────────────────────────
  for (const { key, label } of COMPONENTS) {
    if (!_chart[key]) _chart[key] = _makePosChart(key, label);
    const datasets: object[] = [];
    for (const [geosncl, comps] of processed) {
      const color = _colorFor(geosncl);
      const base = { label: geosncl, borderColor: color, backgroundColor: color + "22",
                     borderWidth: 1, pointRadius: 0, tension: 0, spanGaps: false };
      datasets.push({ ...base, data: comps[key as "east" | "north" | "up"].chartData });
    }
    const pc = _chart[key];
    if (pc) { pc.data.datasets = datasets as any; pc.update("none"); }
  }

  // ── Common-mode-removed series (optional second set) ─────────────────────────
  // Processed once and reused by both the time-series charts and the scatter /
  // histogram pair below.
  let cmrProcessed: Map<string, Record<"east" | "north" | "up", Processed>> | null = null;
  if (cmrMethod.value !== "none" && cmrResult.value) {
    cmrProcessed = new Map<string, Record<"east" | "north" | "up", Processed>>();
    for (const station of cmrResult.value.stations) {
      cmrProcessed.set(station.geosncl, {
        east:  processComponent(station, "east"),
        north: processComponent(station, "north"),
        up:    processComponent(station, "up"),
      });
    }
    for (const { key, label } of COMPONENTS) {
      const cmrKey = `${key}_cmr`;
      if (!_chart[cmrKey]) _chart[cmrKey] = _makePosChart(cmrKey, `${label} — common-mode removed`);
      const datasets: object[] = [];
      for (const [geosncl, comps] of cmrProcessed) {
        const color = _colorFor(geosncl);
        const base = { label: geosncl, borderColor: color, backgroundColor: color + "22",
                       borderWidth: 1, pointRadius: 0, tension: 0, spanGaps: false };
        datasets.push({ ...base, data: comps[key as "east" | "north" | "up"].chartData });
      }
      const pc = _chart[cmrKey];
      if (pc) { pc.data.datasets = datasets as any; pc.update("none"); }
    }
  }

  // ── Scatter plots and histograms ─────────────────────────────────────────────
  // Rendered twice when a common mode is being removed: once for the measured
  // series and once for the residual.  Removing a common mode is supposed to
  // tighten the cloud and narrow the distribution, which is only readable with
  // the two side by side — hence one function, called with each set.
  _drawScatterAndHistograms(processed, "");
  if (cmrProcessed) _drawScatterAndHistograms(cmrProcessed, "_cmr");
}

/**
 * Draw the three scatter panels and three histograms for one set of processed
 * traces.  *suffix* keys the chart registries, so "" is the measured series and
 * "_cmr" its common-mode-removed twin; the two never share a chart instance.
 *
 * Axis ranges are computed per set rather than shared: the residual is by
 * construction much tighter than the input, and forcing both onto the measured
 * data's range would collapse the residual to a dot.
 */
function _drawScatterAndHistograms(
  processed: Map<string, Record<"east" | "north" | "up", Processed>>,
  suffix: string,
) {
  // Global min/max across all components so all scatter axes share one scale
  let gMin = Infinity, gMax = -Infinity;
  for (const comps of processed.values())
    for (const c of ["east", "north", "up"] as const)
      for (const v of comps[c].specVals) { if (v < gMin) gMin = v; if (v > gMax) gMax = v; }
  const scatterPad = isFinite(gMin) ? Math.max((gMax - gMin) * 0.05, 0.1) : 1;
  const scatterMin = isFinite(gMin) ? gMin - scatterPad : undefined;
  const scatterMax = isFinite(gMax) ? gMax + scatterPad : undefined;

  for (const def of SCATTER_DEFS) {
    const key = def.key + suffix;
    if (!_scatterChart[key])
      _scatterChart[key] = _makeScatterChart(key, def.xLabel, def.yLabel);
    const datasets: object[] = [];
    for (const [geosncl, comps] of processed) {
      const color = _colorFor(geosncl);
      const xVals = comps[def.xComp], yVals = comps[def.yComp];
      const xMap = new Map<number, number>();
      for (let i = 0; i < xVals.specTimes.length; i++) xMap.set(xVals.specTimes[i], xVals.specVals[i]);
      const pts: Array<{ x: number; y: number }> = [];
      for (let i = 0; i < yVals.specTimes.length; i++) {
        const x = xMap.get(yVals.specTimes[i]);
        if (x !== undefined) pts.push({ x, y: yVals.specVals[i] });
      }
      datasets.push({ label: geosncl, data: pts, borderColor: color, backgroundColor: color + "66",
                      pointRadius: 2, pointHoverRadius: 4 });
    }
    const sc = _scatterChart[key];
    if (sc) {
      sc.data.datasets = datasets as any;
      // A zoom, once set, has to survive every later updateCharts() — otherwise
      // the next redraw (a stream toggled, the mean removed) silently snaps the
      // panel back to the full range.
      const z = _scatterZoom.value[key];
      const sx = (sc.options.scales as any)?.x, sy = (sc.options.scales as any)?.y;
      if (sx) { sx.min = z ? z.xMin : scatterMin; sx.max = z ? z.xMax : scatterMax; }
      if (sy) { sy.min = z ? z.yMin : scatterMin; sy.max = z ? z.yMax : scatterMax; }
      sc.update("none");
    }
  }

  for (const def of HIST_DEFS) {
    const key = def.key + suffix;
    if (!_histChart[key]) _histChart[key] = _makeHistChart(key, def.label);

    // Combined mean & std, drawn by the afterDraw plugin
    const allFlat = [...processed.values()].flatMap(comps => comps[def.comp].specVals);
    if (allFlat.length) {
      const mean = allFlat.reduce((s, v) => s + v, 0) / allFlat.length;
      const std  = Math.sqrt(allFlat.reduce((s, v) => s + (v - mean) ** 2, 0) / Math.max(1, allFlat.length - 1));
      _histStats[key] = { mean, std };
    } else {
      _histStats[key] = null;
    }

    const allVals = [...processed.values()].map(comps => comps[def.comp].specVals);
    const { labels, counts } = _histBins(allVals, 30);
    const hc = _histChart[key];
    if (!hc) continue;
    hc.data.labels = labels;
    const geosncls = [...processed.keys()];
    hc.data.datasets = geosncls.map((g, i) => {
      const color = _colorFor(g);
      return { label: g, data: counts[i], backgroundColor: color + "88", borderColor: color,
               borderWidth: 0.5, barPercentage: 1.0, categoryPercentage: 0.9 };
    }) as any;
    hc.update("none");
  }
}

// ─── Position loading ─────────────────────────────────────────────────────────

function scheduleLoad() {
  if (loadTimer) clearTimeout(loadTimer);
  loadTimer = setTimeout(loadPositions, 300);
}

async function loadPositions() {
  if (!selected.value.size || !startDate.value || !endDate.value) { updateCharts(); return; }
  const needed = [...selected.value].filter(g => !positionCache.value.has(g));
  if (needed.length > 0) {
    positionsLoading.value = true;
    try {
      const r = await getPositions({
        geosncls: needed.join(","), start: startDate.value, end: endDate.value,
        downsample: downsampleEnabled.value,
      });
      for (const trace of r.stations) positionCache.value.set(trace.geosncl, trace);
    } catch (e) { console.error("Failed to load positions", e); }
    finally { positionsLoading.value = false; }
  }
  if (cmrMethod.value !== "none") loadCommonModeRemoved();
  updateCharts();
}

async function loadCommonModeRemoved() {
  cmrError.value = "";
  if (cmrMethod.value === "none") return;
  if (selected.value.size < 2) {
    cmrError.value = "Select at least 2 streams to compute a common mode.";
    cmrResult.value = null; updateCharts(); return;
  }
  if (!startDate.value || !endDate.value) return;
  cmrLoading.value = true;
  try {
    cmrResult.value = await getCommonModeRemoved({
      geosncls: [...selected.value].join(","),
      start: startDate.value, end: endDate.value,
      method: cmrMethod.value === "pca" ? "pca" : "kle",
      nModesRemoved: cmrNModesRemoved.value,
      downsample: downsampleEnabled.value,
      outlierM: outlierThreshold.value,
    });
  } catch (e: any) {
    cmrError.value = e?.response?.data?.error ?? "Failed to compute common-mode-removed series.";
    cmrResult.value = null;
  } finally {
    cmrLoading.value = false;
  }
  // The _cmr canvases only mount once cmrResult is set (v-else-if="cmrResult"
  // in the template) — wait for that DOM update before updateCharts() reads
  // _canvas[cmrKey], or the very first render after enabling CMR silently
  // finds no canvas yet and never draws anything (only a later, unrelated
  // updateCharts() call — e.g. from selecting another stream — would).
  await nextTick();
  updateCharts();
}

// ─── Watches ─────────────────────────────────────────────────────────────────

watch(selected,                        () => scheduleLoad(),                          { deep: false });
watch([removeMean, outlierThreshold],  () => updateCharts());
watch(downsampleEnabled,               () => { positionCache.value.clear(); scheduleLoad(); });
watch(cmrMethod, (method) => {
  if (method !== "none") loadCommonModeRemoved();
  else { cmrResult.value = null; cmrError.value = ""; updateCharts(); }
});
watch(cmrNModesRemoved, () => { if (cmrMethod.value !== "none") loadCommonModeRemoved(); });

// ─── Fetch missing ────────────────────────────────────────────────────────────

function openFetchDialog() {
  fetchLog.value = []; fetchDone.value = false; fetchRunning.value = false; fetchOpen.value = true;
}
function startFetch() {
  fetchRunning.value = true; fetchLog.value = [];
  openFetchMissingStream(
    { list: selectedList.value, start: startDate.value, end: endDate.value, workers: fetchWorkers.value },
    async (evt) => {
      fetchLog.value.push(evt);
      await nextTick();
      if (fetchLogEl.value) fetchLogEl.value.scrollTop = fetchLogEl.value.scrollHeight;
      if (evt.type === "done") { fetchRunning.value = false; fetchDone.value = true; await reloadStations(); }
    },
  );
}
</script>

<style scoped>
.tree-panel:focus { outline: none; }
.tree-row { min-height: 26px; }
.tree-row.tree-focused > .tree-item { background: rgba(21,101,192,0.12); border-radius: 4px; }
.tree-item { cursor: pointer; padding: 2px 4px; border-radius: 4px; user-select: none; }
.tree-item:hover { background: rgba(0,0,0,0.06); }
.tree-child { padding-left: 28px; }
.tree-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }

.chart-block    { position: relative; height: 230px; flex-shrink: 0; }
.chart-canvas   { position: absolute; inset: 18px 0 0 0; height: calc(100% - 18px) !important; }
.chart-block-sm { position: relative; height: 160px; flex-shrink: 0; }
.chart-block-sq { position: relative; height: 260px; flex-shrink: 0; }
.chart-canvas-full { position: absolute; inset: 0; width: 100% !important; height: 100% !important; }

.coh-legend-bar {
  width: 200px; height: 12px; border-radius: 2px;
  background: linear-gradient(to right,
    rgb(0,0,102), rgb(0,153,204), rgb(0,255,0), rgb(255,255,0), rgb(255,0,0));
}
.heatmap-tip {
  position: absolute; z-index: 10; pointer-events: none;
  background: rgba(11,11,11,0.85); color: #fff; font-size: 11px;
  padding: 3px 6px; border-radius: 4px; white-space: nowrap;
}
.kle-bar-wrap { position: relative; height: 220px; }
</style>

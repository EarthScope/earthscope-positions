<template>
  <q-page class="q-pa-md">

    <!-- ── Two-column layout ────────────────────────────────────────────── -->
    <div class="row q-col-gutter-md">

      <!-- ── Left: configuration panel ─────────────────────────────────── -->
      <div class="col-12 col-md-5 col-lg-4">
        <q-card flat bordered class="config-card">
          <q-card-section class="q-pb-xs">
            <div class="text-subtitle1 text-weight-medium">Configuration</div>
          </q-card-section>
          <q-separator />
          <q-card-section class="q-gutter-sm">

            <!-- Stream lists (multi-select) -->
            <q-select
              v-model="selectedLists"
              :options="listOptions"
              label="Stream list(s)"
              multiple
              use-chips
              dense
              outlined
              emit-value
              map-options
              :disable="isActive"
            >
              <template #option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section>
                    <q-item-label>{{ scope.opt.label }}</q-item-label>
                  </q-item-section>
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

            <!-- Date range -->
            <div class="row q-gutter-xs">
              <q-input
                v-model="startDate"
                label="Start date"
                dense
                outlined
                class="col"
                mask="####-##-##"
                placeholder="YYYY-MM-DD"
                :disable="isActive"
              />
              <q-input
                v-model="stopDate"
                label="Stop date"
                dense
                outlined
                class="col"
                mask="####-##-##"
                placeholder="YYYY-MM-DD"
                :disable="isActive"
              />
              <q-btn flat dense round icon="date_range" size="sm" class="self-center" :disable="isActive">
                <q-popup-proxy ref="dateRangePopup" cover transition-show="scale" transition-hide="scale">
                  <q-date :model-value="null" range mask="YYYY-MM-DD" @update:model-value="onRangeSelect">
                    <div class="row items-center justify-end">
                      <q-btn v-close-popup label="Close" color="primary" flat />
                    </div>
                  </q-date>
                </q-popup-proxy>
              </q-btn>
            </div>

            <!-- Time-of-day range -->
            <div class="row q-gutter-xs">
              <q-input
                v-model="startTime"
                label="Start time"
                dense
                outlined
                class="col"
                mask="##:##:##"
                placeholder="HH:MM:SS"
                :disable="isActive"
              />
              <q-input
                v-model="stopTime"
                label="Stop time"
                dense
                outlined
                class="col"
                mask="##:##:##"
                placeholder="HH:MM:SS"
                :disable="isActive"
              />
            </div>

            <!-- Stream filters -->
            <div class="text-caption text-grey-6 q-mt-xs">Processing centers</div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="c in availableCenters"
                :key="c"
                :selected="filterCenters.includes(c)"
                clickable
                dense
                size="sm"
                :color="filterCenters.includes(c) ? 'primary' : 'grey-3'"
                :text-color="filterCenters.includes(c) ? 'white' : 'black'"
                :disable="isActive"
                @click="toggleItem(filterCenters, c)"
              >{{ c }}</q-chip>
            </div>

            <div class="text-caption text-grey-6">Stream type</div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="code in availableSolTypes"
                :key="code"
                :selected="filterSolTypes.includes(code)"
                clickable
                dense
                size="sm"
                :color="filterSolTypes.includes(code) ? 'primary' : 'grey-3'"
                :text-color="filterSolTypes.includes(code) ? 'white' : 'black'"
                :disable="isActive"
                @click="toggleItem(filterSolTypes, code)"
              >{{ code }} {{ solTypeLabel(code) }}</q-chip>
            </div>

            <q-separator class="q-my-xs" />

            <!-- Replay settings -->
            <div class="text-caption text-grey-6">Replay settings</div>
            <div class="row q-gutter-sm items-center">
              <q-input
                v-model.number="timeScale"
                label="Time scale"
                type="number"
                step="0.1"
                min="0.01"
                dense
                outlined
                style="width: 110px"
                :disable="isActive"
              />
              <q-toggle
                v-model="applyLatency"
                label="Apply latency"
                dense
                :disable="isActive"
              />
            </div>
            <div class="row items-center">
              <q-toggle
                v-model="selectByArrival"
                label="Select by arrival time"
                dense
                :disable="isActive || !applyLatency"
              />
              <q-icon name="help_outline" size="16px" color="grey-6" class="q-ml-xs">
                <q-tooltip max-width="320px">
                  Windows the replay by <b>arrival</b> time (data time + latency) instead of
                  data time. Reads ~30&nbsp;s before the start so late records that would have
                  arrived inside the window are included, and drops records that would have
                  arrived after the stop. Requires “Apply latency”.
                </q-tooltip>
              </q-icon>
            </div>
            <q-select
              v-model="outputFormat"
              :options="OUTPUT_FORMAT_OPTIONS"
              label="Message format"
              dense
              outlined
              emit-value
              map-options
              :disable="isActive"
            />
            <div class="text-caption text-grey-6">
              {{ outputFormat === 'geojson'
                 ? 'One GeoJSON Feature per sample.'
                 : 'Compact one-line record per sample.' }}
            </div>

            <q-separator class="q-my-xs" />

            <!-- Kafka settings -->
            <div class="text-caption text-grey-6">Kafka</div>
            <q-input
              v-model="bootstrapServer"
              label="Bootstrap server"
              dense
              outlined
              :disable="isActive"
            />
            <q-input
              v-model="topic"
              label="Topic"
              dense
              outlined
              :disable="isActive"
            />

          </q-card-section>
          <q-card-actions class="q-pa-md q-pt-xs">
            <q-btn
              v-if="!isActive"
              label="Preload"
              icon="inventory"
              color="primary"
              unelevated
              no-caps
              :loading="replayStatus === 'preloading'"
              :disable="!canPreload"
              @click="doPreload"
            />
            <q-btn
              v-if="replayStatus !== 'idle' && !isRunning"
              label="Reset"
              flat
              no-caps
              color="grey-7"
              icon="restart_alt"
              @click="doReset"
            />
          </q-card-actions>
        </q-card>
      </div>

      <!-- ── Right: status panel ────────────────────────────────────────── -->
      <div class="col-12 col-md-7 col-lg-8">

        <!-- idle -->
        <div v-if="replayStatus === 'idle'" class="flex flex-center text-grey-5 q-pa-xl" style="min-height:200px">
          <div class="text-center">
            <q-icon name="play_circle_outline" size="48px" class="q-mb-sm" />
            <div>Configure a stream list and date range, then click Preload.</div>
          </div>
        </div>

        <!-- preloading -->
        <div v-else-if="replayStatus === 'preloading'" class="flex flex-center q-pa-xl" style="min-height:200px">
          <div class="text-center">
            <q-spinner size="40px" color="primary" class="q-mb-md" />
            <div class="text-grey-6">Scanning Arrow files and counting messages…</div>
          </div>
        </div>

        <!-- preloaded -->
        <template v-else-if="replayStatus === 'preloaded'">
          <q-card flat bordered class="q-mb-md">
            <q-card-section class="q-pb-xs">
              <div class="text-subtitle1 text-weight-medium">Preload Summary</div>
            </q-card-section>
            <q-separator />
            <q-card-section>
              <div class="row q-gutter-md">
                <div>
                  <div class="text-h5 text-primary">{{ fmtNum(replayState.total_messages) }}</div>
                  <div class="text-caption text-grey-6">Total messages</div>
                </div>
                <div>
                  <div class="text-h5">{{ replayState.files_count ?? replayState.files?.length ?? 0 }}</div>
                  <div class="text-caption text-grey-6">Arrow files</div>
                </div>
                <div v-if="replayState.config">
                  <div class="text-h5">{{ replayState.config.time_scale }}×</div>
                  <div class="text-caption text-grey-6">Time scale</div>
                </div>
              </div>
              <div class="row q-gutter-md q-mt-xs">
                <div>
                  <div class="text-subtitle1 text-weight-medium">{{ replayState.total_geosncls ?? "—" }}</div>
                  <div class="text-caption text-grey-6">Streams loaded</div>
                </div>
                <div>
                  <div class="text-subtitle1 text-weight-medium"
                       :class="(replayState.found_geosncls ?? 0) < (replayState.total_geosncls ?? 0) ? 'text-orange-9' : 'text-positive'">
                    {{ replayState.found_geosncls ?? "—" }}
                  </div>
                  <div class="text-caption text-grey-6">Have data</div>
                </div>
              </div>

              <!-- Not fetched yet -->
              <template v-if="replayState.missing_not_fetched?.length">
                <q-banner class="bg-orange-1 text-orange-10 q-mt-md rounded-borders" dense>
                  <template #avatar><q-icon name="cloud_download" color="orange" /></template>
                  <strong>{{ replayState.missing_not_fetched.length }} stream(s)</strong> have not been fetched for this date range.
                  <div class="text-caption q-mt-xs">
                    {{ replayState.missing_not_fetched.slice(0, 5).join(", ") }}
                    <span v-if="replayState.missing_not_fetched.length > 5">… and {{ replayState.missing_not_fetched.length - 5 }} more</span>
                  </div>
                  <template #action>
                    <q-btn flat no-caps label="Fetch Missing" icon="cloud_download" color="orange-9" @click="openFetchDialog" />
                  </template>
                </q-banner>
              </template>

              <!-- API returned no data -->
              <template v-if="replayState.missing_no_data?.length">
                <q-banner class="bg-grey-2 text-grey-8 q-mt-sm rounded-borders" dense>
                  <template #avatar><q-icon name="block" color="grey-6" /></template>
                  <strong>{{ replayState.missing_no_data.length }} stream(s)</strong> were previously fetched but the API returned no data.
                  <div class="text-caption q-mt-xs">
                    {{ replayState.missing_no_data.slice(0, 5).join(", ") }}
                    <span v-if="replayState.missing_no_data.length > 5">… and {{ replayState.missing_no_data.length - 5 }} more</span>
                  </div>
                </q-banner>
              </template>
            </q-card-section>

            <q-card-actions class="q-pa-md q-pt-xs row q-gutter-sm items-start">
              <q-btn
                label="Go"
                icon="play_arrow"
                color="positive"
                unelevated
                no-caps
                :disable="!replayState.job_id"
                @click="doGo"
              />
              <q-btn
                label="Cancel"
                icon="stop"
                color="negative"
                outline
                no-caps
                disable
              />
              <div class="col-12 row q-gutter-sm q-mt-xs">
                <div class="curl-block q-pa-sm rounded-borders">
                  <div class="text-caption text-grey-6 q-mb-xs">start via curl:</div>
                  <code class="text-caption">{{ curlGo }}</code>
                  <q-btn flat dense round icon="content_copy" size="xs" class="q-ml-xs" @click="copy(curlGo)" />
                </div>
                <div class="curl-block q-pa-sm rounded-borders">
                  <div class="text-caption text-grey-6 q-mb-xs">cancel via curl:</div>
                  <code class="text-caption">{{ curlCancel }}</code>
                  <q-btn flat dense round icon="content_copy" size="xs" class="q-ml-xs" @click="copy(curlCancel)" />
                </div>
              </div>
            </q-card-actions>
          </q-card>
        </template>

        <!-- running / starting -->
        <template v-else-if="replayStatus === 'running' || replayStatus === 'starting'">
          <q-card flat bordered class="q-mb-md">
            <q-card-section class="q-pb-xs">
              <div class="row items-center">
                <div class="text-subtitle1 text-weight-medium">Replay in Progress</div>
                <q-space />
                <q-spinner size="20px" color="positive" />
              </div>
            </q-card-section>
            <q-separator />
            <q-card-section>
              <!-- Stats row -->
              <div class="row q-gutter-md q-mb-sm">
                <div>
                  <div class="text-h5 text-positive">{{ fmtNum(replayState.sent) }}</div>
                  <div class="text-caption text-grey-6">Messages sent</div>
                </div>
                <div>
                  <div class="text-h5">{{ fmtNum(replayState.total_messages) }}</div>
                  <div class="text-caption text-grey-6">Total</div>
                </div>
                <div>
                  <div class="text-h5">{{ fmtElapsed(replayState.elapsed_ms) }}</div>
                  <div class="text-caption text-grey-6">Elapsed (wall)</div>
                </div>
                <div v-if="sendRate !== null">
                  <div class="text-h5">{{ sendRate }}/s</div>
                  <div class="text-caption text-grey-6">Send rate</div>
                </div>
                <div v-if="replayState.startup_delay_ms != null">
                  <div class="text-h5">{{ replayState.startup_delay_ms }} ms</div>
                  <div class="text-caption text-grey-6">Startup delay (Go→write)</div>
                </div>
              </div>

              <!-- Data time row -->
              <div class="row q-gutter-md q-mb-md items-end">
                <div>
                  <div class="text-subtitle2 text-blue-grey-7">{{ fmtDataTime(replayState.current_data_time_ms) }}</div>
                  <div class="text-caption text-grey-6">Current data time</div>
                </div>
                <div>
                  <div class="text-subtitle2">{{ fmtSeconds(replayState.replay_elapsed_s) }}</div>
                  <div class="text-caption text-grey-6">Into replay</div>
                </div>
                <div>
                  <div class="text-subtitle2">{{ fmtSeconds(replayState.replay_remaining_s) }}</div>
                  <div class="text-caption text-grey-6">Remaining</div>
                </div>
              </div>

              <!-- Progress bar -->
              <q-linear-progress
                :value="progressFraction"
                color="positive"
                track-color="grey-3"
                rounded
                size="8px"
                class="q-mb-md"
              />
              <div class="text-caption text-grey-6 text-right">
                {{ progressPct }}
              </div>

              <!-- Line chart -->
              <div style="height: 180px; position: relative" class="q-mt-sm">
                <canvas ref="chartCanvas" />
              </div>
            </q-card-section>

            <q-card-actions class="q-pa-md q-pt-xs row q-gutter-sm items-start">
              <q-btn
                label="Go"
                icon="play_arrow"
                color="positive"
                unelevated
                no-caps
                disable
              />
              <q-btn
                label="Cancel"
                icon="stop"
                color="negative"
                outline
                no-caps
                @click="doCancel"
              />
              <div class="col-12 row q-gutter-sm q-mt-xs">
                <div class="curl-block q-pa-sm rounded-borders">
                  <div class="text-caption text-grey-6 q-mb-xs">start via curl:</div>
                  <code class="text-caption">{{ curlGo }}</code>
                  <q-btn flat dense round icon="content_copy" size="xs" class="q-ml-xs" @click="copy(curlGo)" />
                </div>
                <div class="curl-block q-pa-sm rounded-borders">
                  <div class="text-caption text-grey-6 q-mb-xs">cancel via curl:</div>
                  <code class="text-caption">{{ curlCancel }}</code>
                  <q-btn flat dense round icon="content_copy" size="xs" class="q-ml-xs" @click="copy(curlCancel)" />
                </div>
              </div>
            </q-card-actions>
          </q-card>
        </template>

        <!-- done -->
        <template v-else-if="replayStatus === 'done'">
          <q-card flat bordered class="q-mb-md">
            <q-card-section>
              <div class="row items-center q-gutter-sm">
                <q-icon name="check_circle" color="positive" size="32px" />
                <div>
                  <div class="text-subtitle1 text-weight-medium">Replay Complete</div>
                  <div class="text-caption text-grey-6">
                    {{ fmtNum(replayState.sent) }} messages sent in {{ fmtElapsed(replayState.elapsed_ms) }}
                    <span v-if="replayState.startup_delay_ms != null">
                      · startup delay {{ replayState.startup_delay_ms }} ms
                    </span>
                  </div>
                </div>
              </div>
            </q-card-section>
            <q-card-actions class="q-pa-md q-pt-xs">
              <q-btn label="New Replay" icon="replay" color="primary" flat no-caps @click="doReset" />
            </q-card-actions>
          </q-card>
        </template>

        <!-- canceled -->
        <template v-else-if="replayStatus === 'canceled'">
          <q-card flat bordered class="q-mb-md">
            <q-card-section>
              <div class="row items-center q-gutter-sm">
                <q-icon name="cancel" color="warning" size="32px" />
                <div>
                  <div class="text-subtitle1 text-weight-medium">Replay Canceled</div>
                  <div class="text-caption text-grey-6">
                    {{ fmtNum(replayState.sent) }} messages sent before cancel
                    <span v-if="replayState.startup_delay_ms != null">
                      · startup delay {{ replayState.startup_delay_ms }} ms
                    </span>
                    <span v-if="replayState.cancel_delay_ms != null">
                      · stop took {{ replayState.cancel_delay_ms }} ms
                    </span>
                  </div>
                </div>
              </div>
            </q-card-section>
            <q-card-actions class="q-pa-md q-pt-xs">
              <q-btn label="New Replay" icon="replay" color="primary" flat no-caps @click="doReset" />
            </q-card-actions>
          </q-card>
        </template>

        <!-- error -->
        <template v-else-if="replayStatus === 'error'">
          <q-card flat bordered class="q-mb-md bg-red-1">
            <q-card-section>
              <div class="row items-center q-gutter-sm">
                <q-icon name="error" color="negative" size="32px" />
                <div>
                  <div class="text-subtitle1 text-weight-medium text-negative">Error</div>
                  <div class="text-caption q-mt-xs">{{ replayState.error }}</div>
                </div>
              </div>
            </q-card-section>
            <q-card-actions class="q-pa-md q-pt-xs">
              <q-btn label="Reset" icon="restart_alt" color="negative" flat no-caps @click="doReset" />
            </q-card-actions>
          </q-card>
        </template>

        <!-- ── Delivery check (read-back consumer) ─────────────────────────── -->
        <q-card
          v-if="replayState.consumer_read !== undefined &&
                ['running','starting','done','canceled','error'].includes(replayStatus)"
          flat bordered class="q-mb-md"
          :class="deliveryClass"
        >
          <q-card-section class="q-pb-xs row items-center">
            <div class="text-subtitle2 text-weight-medium">Delivery check</div>
            <q-space />
            <q-icon :name="deliveryIcon" :color="deliveryColor" size="20px" />
          </q-card-section>
          <q-separator />
          <q-card-section>
            <div class="row q-gutter-md">
              <div>
                <div class="text-h6">{{ fmtNum(replayState.sent) }}</div>
                <div class="text-caption text-grey-6">Written</div>
              </div>
              <div>
                <div class="text-h6">{{ fmtNum(replayState.consumer_read) }}</div>
                <div class="text-caption text-grey-6">Read back</div>
              </div>
              <div>
                <div class="text-h6" :class="matchedClass">
                  {{ fmtNum(replayState.consumer_matched) }} / {{ fmtNum(replayState.sent) }}
                </div>
                <div class="text-caption text-grey-6">Matched</div>
              </div>
              <div>
                <div class="text-h6">{{ meanRt }}</div>
                <div class="text-caption text-grey-6">Mean round-trip</div>
              </div>
            </div>
            <div
              v-if="replayState.consumer_message"
              class="q-mt-sm text-caption"
              :class="deliveryColor === 'negative' ? 'text-negative' : 'text-orange-9'"
            >{{ replayState.consumer_message }}</div>
          </q-card-section>
        </q-card>

        <!-- ── Live status log (visible across preload/replay/terminal states) ── -->
        <q-card v-if="replayState.log?.length" flat bordered class="q-mb-md">
          <q-card-section class="q-pb-xs row items-center">
            <div class="text-subtitle2 text-weight-medium">Status log</div>
            <q-space />
            <q-btn flat dense round icon="content_copy" size="sm" @click="copyLog">
              <q-tooltip>Copy log</q-tooltip>
            </q-btn>
          </q-card-section>
          <q-separator />
          <q-card-section class="q-pt-sm">
            <div ref="logEl" class="replay-log q-pa-sm rounded-borders">
              <div
                v-for="(l, i) in replayState.log"
                :key="i"
                :style="{ color: logColor(l.level) }"
              ><span class="log-ts">{{ fmtLogTs(l.ts) }}</span> {{ l.msg }}</div>
            </div>
          </q-card-section>
        </q-card>

      </div>
    </div>

    <!-- ── Fetch Missing dialog (reuse completeness pattern) ──────────────── -->
    <q-dialog v-model="fetchOpen" persistent>
      <q-card style="min-width: 620px; max-width: 90vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Fetch Missing Data</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup :disable="fetchRunning" />
        </q-card-section>
        <q-card-section class="q-pt-sm">
          <div class="text-caption text-grey-7">
            Lists: <b>{{ selectedLists.join(", ") || "none selected" }}</b>
            &nbsp;·&nbsp; {{ startDate }} → {{ stopDate }}
          </div>
          <div class="text-caption text-grey-6 q-mt-xs">
            Only the {{ replayState.missing_not_fetched?.length ?? 0 }} stream(s) with no prior fetch attempt will be downloaded.
          </div>
        </q-card-section>
        <q-card-section v-if="fetchLog.length" style="max-height: 40vh; overflow-y:auto" class="q-pt-none">
          <div
            class="q-pa-sm rounded-borders"
            ref="fetchLogEl"
            style="background:#1a1a2e; font-family:monospace; font-size:12px; line-height:1.5"
          >
            <div
              v-for="(line, i) in fetchLog"
              :key="i"
              :style="{ color: line.type === 'error' ? '#ef9a9a' : line.type === 'done' ? '#a5d6a7' : '#e0e0e0' }"
            >{{ line.msg }}</div>
          </div>
        </q-card-section>
        <q-card-actions align="right" class="q-pa-md">
          <q-select
            v-model="fetchWorkers"
            :options="[5,10,20,30,50]"
            label="Workers"
            dense outlined style="width:90px"
          />
          <q-btn
            v-if="!fetchRunning && !fetchDone"
            label="Fetch"
            color="primary"
            unelevated no-caps
            :disable="!selectedLists.length"
            @click="startFetch"
          />
          <q-btn
            v-if="fetchDone"
            label="Close"
            color="primary"
            flat no-caps
            v-close-popup
            @click="fetchLog=[]; fetchDone=false"
          />
          <q-btn v-if="fetchRunning" label="Running…" flat no-caps disable />
        </q-card-actions>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated, onDeactivated, watch, nextTick } from "vue";
import type { Chart as ChartType } from "chart.js";
import {
  getStreamLists,
  replayPreload,
  getReplayStatus,
  replayGo,
  replayStart,
  replayCancel,
  replayReset,
  openFetchMissingStream,
  getServerConfig,
} from "../api";
import type { ReplayState, FetchEvent } from "../types";
import { useListDelete } from "../composables/useListDelete";
import {
  PROC_CENTERS, STREAM_TYPE_CODES, solTypeLabel, sortSolTypes,
  defaultSelectedCenters, defaultSelectedStreamTypes,
} from "../constants/streamTypes";

// ─── Constants ────────────────────────────────────────────────────────────────

const ALL_CENTERS   = Object.keys(PROC_CENTERS);
const ALL_SOL_TYPES = [...STREAM_TYPE_CODES];

const DEFAULT_BOOTSTRAP = "localhost:9092";
const DEFAULT_TOPIC     = "protected.gnss.positions.shakealert.geojson.compact";

// ─── State ────────────────────────────────────────────────────────────────────

const listOptions  = ref<{ label: string; value: string }[]>([]);
const selectedLists = ref<string[]>([]);

const startDate = ref("");
const stopDate  = ref("");
const startTime = ref("00:00:00");
const stopTime  = ref("01:00:00");

// Filters — populated from API; all selected by default (empty = all on backend)
const availableCenters  = ref<string[]>([]);
const availableSolTypes = ref<string[]>([]);
const filterCenters     = ref<string[]>([]);
const filterSolTypes    = ref<string[]>([]);

const timeScale    = ref(1.0);
const applyLatency = ref(true);
const selectByArrival = ref(false);
const outputFormat = ref<"compact" | "geojson">("compact");
const OUTPUT_FORMAT_OPTIONS = [
  { label: "Compact GeoJSON", value: "compact" },
  { label: "GeoJSON (Feature per sample)", value: "geojson" },
];
const bootstrapServer = ref(DEFAULT_BOOTSTRAP);
const topic        = ref(DEFAULT_TOPIC);

const replayState  = ref<ReplayState>({ status: "idle" });
const replayStatus = computed(() => replayState.value.status);

// Chart
const chartCanvas  = ref<HTMLCanvasElement | null>(null);
let   chart: ChartType | null = null;
let   chartIniting = false;
// IMPORTANT: chart data is a PLAIN, non-reactive array.  Passing a Vue reactive
// array/ref to Chart.js makes Chart.js write internal metadata (`_meta`, parsed
// values, …) onto reactive objects, which retriggers Vue's reactivity on every
// frame — a feedback loop that pegs the main thread and freezes the whole page
// (the "something fundamentally blocking the webpage" symptom).  Keep it raw.
let   chartData: { x: number; y: number }[] = []; // x=elapsed_s, y=sent
const sendRate  = ref<string | null>(null);

// Fetch dialog
const fetchOpen    = ref(false);
const fetchRunning = ref(false);
const fetchDone    = ref(false);
const fetchWorkers = ref(10);
const fetchLog     = ref<FetchEvent[]>([]);
const fetchLogEl   = ref<HTMLElement | null>(null);

// Status-log panel
const logEl        = ref<HTMLElement | null>(null);

// Polling — a self-rescheduling setTimeout chain (not setInterval) so requests
// never overlap and a hung request can't silently pile up and stall the UI.
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollAbort: AbortController | null = null;
let pollStopped = true;

// ─── Computed ─────────────────────────────────────────────────────────────────

const isActive  = computed(() =>
  ["preloading", "running", "starting"].includes(replayStatus.value)
);
const isRunning = computed(() =>
  ["running", "starting"].includes(replayStatus.value)
);

const canPreload = computed(() =>
  selectedLists.value.length > 0
  && startDate.value.length === 10
  && stopDate.value.length === 10
  && startTime.value.length === 8
  && stopTime.value.length === 8
);

const startDateTime = computed(() => `${startDate.value}T${startTime.value}`);
const stopDateTime  = computed(() => `${stopDate.value}T${stopTime.value}`);

const progressFraction = computed(() => {
  const total = replayState.value.total_messages ?? 0;
  const sent  = replayState.value.sent ?? 0;
  return total > 0 ? Math.min(1, sent / total) : 0;
});

const progressPct = computed(() => {
  if (!replayState.value.total_messages) return "";
  return `${(progressFraction.value * 100).toFixed(1)}%  (${fmtNum(replayState.value.sent ?? 0)} / ${fmtNum(replayState.value.total_messages)})`;
});

// Recompute the recent send rate from the raw (non-reactive) chart data and
// publish it via a ref (called from applyStatus, not a computed, because
// chartData is intentionally non-reactive).
function computeSendRate() {
  if (chartData.length < 2) { sendRate.value = null; return; }
  const last = chartData[chartData.length - 1];
  const prev = chartData[Math.max(0, chartData.length - 6)];
  const dt = last.x - prev.x;
  const ds = last.y - prev.y;
  sendRate.value = dt > 0 ? fmtNum(Math.round(ds / dt)) : null;
}

// ── Delivery check (read-back consumer) ──────────────────────────────────────
const deliveryColor = computed(() => {
  const s = replayState.value.consumer_status;
  return s === "error" ? "negative" : s === "warn" ? "warning" : "positive";
});
const deliveryIcon = computed(() => {
  const s = replayState.value.consumer_status;
  return s === "error" ? "error" : s === "warn" ? "warning" : "check_circle";
});
const deliveryClass = computed(() => {
  const s = replayState.value.consumer_status;
  return s === "error" ? "bg-red-1" : s === "warn" ? "bg-orange-1" : "";
});
const matchedClass = computed(() => {
  const written = replayState.value.sent ?? 0;
  const matched = replayState.value.consumer_matched ?? 0;
  if (!written) return "";
  return matched >= written ? "text-positive" : "text-orange-9";
});
const meanRt = computed(() => {
  const rt = replayState.value.consumer_mean_rt_ms;
  return typeof rt === "number" ? `${rt.toFixed(1)} ms` : "—";
});

// Server-provided base URL (from `--hostname`), used for the callback curl
// commands so they work when the server runs on a remote machine.  Falls back
// to the browser's origin.
const serverBase = ref("");
const origin = computed(() =>
  serverBase.value
  || (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000")
);
const curlGo = computed(() =>
  `curl -X POST ${origin.value}/api/replay/start`
);
const curlCancel = computed(() =>
  `curl -X POST ${origin.value}/api/replay/cancel`
);

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtNum(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  return n.toLocaleString();
}

function fmtElapsed(ms: number | undefined): string {
  if (!ms) return "0s";
  const s = Math.floor(ms / 1000);
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m ${s%60}s`;
  return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`;
}

function fmtSeconds(s: number | undefined): string {
  if (s === undefined || s === null) return "—";
  const sec = Math.round(s);
  if (sec < 60)   return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec/60)}m ${sec%60}s`;
  return `${Math.floor(sec/3600)}h ${Math.floor((sec%3600)/60)}m`;
}

function fmtDataTime(ms: number | undefined): string {
  if (!ms) return "—";
  return new Date(ms).toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function toggleItem(list: string[], item: string): void {
  const i = list.indexOf(item);
  if (i >= 0) list.splice(i, 1);
  else list.push(item);
}

const dateRangePopup = ref<{ hide?: () => void } | null>(null);

function onRangeSelect(val: { from: string; to: string } | string | null): void {
  if (!val) return;
  if (typeof val === "string") {
    // Same day clicked twice — start and stop both land on that date.
    startDate.value = val;
    stopDate.value  = val;
    dateRangePopup.value?.hide?.();
    return;
  }
  // Two different days clicked — a genuine range.
  if (!val.from || !val.to) return;
  startDate.value = val.from;
  stopDate.value  = val.to;
  dateRangePopup.value?.hide?.();
}

async function copy(text: string) {
  try { await navigator.clipboard.writeText(text); } catch { /* ignore */ }
}

// ─── Status log ─────────────────────────────────────────────────────────────

function logColor(level: string): string {
  if (level === "error") return "#ef9a9a";
  if (level === "warn")  return "#ffcc80";
  return "#e0e0e0";
}

function fmtLogTs(ms: number): string {
  return new Date(ms).toISOString().slice(11, 19); // HH:MM:SS
}

function scrollLogToBottom() {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
  });
}

async function copyLog() {
  const lines = (replayState.value.log ?? [])
    .map((l) => `${fmtLogTs(l.ts)} ${l.msg}`)
    .join("\n");
  await copy(lines);
}

// ─── Stream lists ─────────────────────────────────────────────────────────────

const { confirmDeleteList } = useListDelete(loadListOptions);

async function loadListOptions() {
  try {
    const resp = await getStreamLists();
    listOptions.value = resp.lists.map((l) => ({ label: l, value: l }));
  } catch {
    listOptions.value = [];
  }
}

// ─── Filter options ───────────────────────────────────────────────────────────

async function fetchFilterOptions() {
  try {
    const params = new URLSearchParams();
    for (const l of selectedLists.value) params.append("lists", l);
    const res = await fetch(`/api/stream-lists/filter-options?${params}`);
    if (!res.ok) {
      availableCenters.value  = ALL_CENTERS;
      availableSolTypes.value = ALL_SOL_TYPES;
      filterCenters.value     = defaultSelectedCenters(ALL_CENTERS);
      filterSolTypes.value    = defaultSelectedStreamTypes(ALL_SOL_TYPES);
      return;
    }
    const data = await res.json();
    availableCenters.value  = data.centers?.length  ? data.centers  : ALL_CENTERS;
    availableSolTypes.value = sortSolTypes(data.sol_types?.length ? data.sol_types : ALL_SOL_TYPES);
    filterCenters.value  = defaultSelectedCenters(availableCenters.value);
    filterSolTypes.value = defaultSelectedStreamTypes(availableSolTypes.value);
  } catch {
    availableCenters.value  = ALL_CENTERS;
    availableSolTypes.value = ALL_SOL_TYPES;
    filterCenters.value     = defaultSelectedCenters(ALL_CENTERS);
    filterSolTypes.value    = defaultSelectedStreamTypes(ALL_SOL_TYPES);
  }
}

// ─── Polling ──────────────────────────────────────────────────────────────────

const ACTIVE_STATES = ["preloading", "preloaded", "running", "starting"];

function startPolling() {
  if (!pollStopped) return;
  pollStopped = false;
  scheduleNextPoll(0);
}

function stopPolling() {
  pollStopped = true;
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  if (pollAbort) {
    pollAbort.abort();
    pollAbort = null;
  }
}

function scheduleNextPoll(delayMs: number) {
  if (pollStopped) return;
  pollTimer = setTimeout(runPoll, delayMs);
}

/** Fetch status with a hard timeout so a stalled request can never hang the
 *  poll loop (that was the cause of the "updates once then freezes" symptom). */
async function fetchStatusWithTimeout(ms: number): Promise<ReplayState> {
  pollAbort = new AbortController();
  const t = setTimeout(() => pollAbort?.abort(), ms);
  try {
    const r = await fetch("/api/replay/status", {
      signal: pollAbort.signal,
      headers: { "Cache-Control": "no-cache" },
    });
    return (await r.json()) as ReplayState;
  } finally {
    clearTimeout(t);
    pollAbort = null;
  }
}

/** Apply a status payload to reactive state.  Chart updates are isolated so a
 *  chart error (e.g. a failed chart.js chunk import) can never break polling. */
function applyStatus(s: ReplayState) {
  const prevLogLen = replayState.value.log?.length ?? 0;
  replayState.value = s;
  if ((s.log?.length ?? 0) !== prevLogLen) scrollLogToBottom();

  if (s.status === "running" || s.status === "starting") {
    try {
      chartData.push({ x: (s.elapsed_ms ?? 0) / 1000, y: s.sent ?? 0 });
      computeSendRate();
      updateChart();
      // Chart may not exist yet if the replay was started externally via curl.
      if (!chart) nextTick().then(initChart).catch(() => { /* ignore */ });
    } catch { /* never let chart errors stop the poll loop */ }
  }
}

async function runPoll() {
  if (pollStopped) return;
  let keepGoing = true;
  try {
    const s = await fetchStatusWithTimeout(5000);
    applyStatus(s);
    keepGoing = ACTIVE_STATES.includes(s.status);
  } catch {
    // Network error / timeout / abort — keep polling; a transient blip must not
    // permanently stall the live display.
    keepGoing = true;
  } finally {
    if (keepGoing && !pollStopped) scheduleNextPoll(1000);
    else stopPolling();
  }
}

// ─── Chart.js ────────────────────────────────────────────────────────────────

async function initChart() {
  // Guard re-entrancy: initChart is triggered from both the canvas watcher and
  // the poll loop, which could otherwise `new Chart()` the same canvas twice.
  if (!chartCanvas.value || chartIniting) return;
  chartIniting = true;
  try {
    if (chart) { chart.destroy(); chart = null; }

    const { Chart, LineController, LineElement, PointElement, LinearScale, Title, Tooltip } =
      await import("chart.js");

    // Component may have unmounted while the dynamic import was in flight.
    if (!chartCanvas.value) return;

    Chart.register(LineController, LineElement, PointElement, LinearScale, Title, Tooltip);

    chart = new Chart(chartCanvas.value, {
      type: "line",
      data: {
        datasets: [{
          label: "Messages sent",
          data: chartData,
          borderColor: "#21ba45",
          backgroundColor: "rgba(33,186,69,0.08)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            type: "linear",
            title: { display: true, text: "Elapsed (s)", font: { size: 10 } },
            ticks: { maxTicksLimit: 8 },
          },
          y: {
            type: "linear",
            title: { display: true, text: "Sent", font: { size: 10 } },
            ticks: { maxTicksLimit: 6 },
          },
        },
      },
    }) as ChartType;
  } finally {
    chartIniting = false;
  }
}

function updateChart() {
  if (!chart) return;
  (chart.data.datasets[0] as any).data = chartData;
  chart.update("none");
}

// ─── Replay actions ───────────────────────────────────────────────────────────

async function doPreload() {
  chartData = [];
  sendRate.value = null;
  replayState.value = { status: "preloading" };
  startPolling();
  try {
    await replayPreload({
      stream_lists:     selectedLists.value,
      all_stations:     false,
      start_time:       startDateTime.value,
      stop_time:        stopDateTime.value,
      filter_centers:   filterCenters.value.length < availableCenters.value.length
                          ? filterCenters.value : [],
      filter_sol_types: filterSolTypes.value.length < availableSolTypes.value.length
                          ? filterSolTypes.value : [],
      time_scale:       timeScale.value,
      apply_latency:    applyLatency.value,
      select_by_arrival: applyLatency.value && selectByArrival.value,
      output_format:    outputFormat.value,
      bootstrap_server: bootstrapServer.value,
      topic:            topic.value,
    });
  } catch (e: any) {
    const msg = e?.response?.data?.error ?? String(e);
    replayState.value = { status: "error", error: msg };
    stopPolling();
  }
}

async function doGo() {
  chartData = [];
  sendRate.value = null;
  // Start the replay (returns immediately; schedule is anchored to this call),
  // then poll for live status.
  try {
    await replayStart();
  } catch (e: any) {
    replayState.value = { ...replayState.value, status: "error", error: e?.response?.data?.error ?? String(e) };
    return;
  }
  startPolling();
  await nextTick();
  initChart();
}

async function doCancel() {
  try {
    await replayCancel();
    // Poll will detect status="canceled" within ~1s and stop itself.
  } catch {
    // 409 = already in a terminal state — poll will pick it up.
  }
}

async function doReset() {
  stopPolling();
  if (chart) { chart.destroy(); chart = null; }
  chartData = [];
  sendRate.value = null;
  try { await replayReset(); } catch { /* ignore */ }
  replayState.value = { status: "idle" };
}

// ─── Fetch Missing dialog ─────────────────────────────────────────────────────

function openFetchDialog() {
  fetchLog.value = [];
  fetchDone.value = false;
  fetchRunning.value = false;
  fetchOpen.value = true;
}

function startFetch() {
  if (!selectedLists.value.length) return;
  fetchRunning.value = true;
  fetchLog.value = [];
  const fetchStart = startDate.value;
  const fetchEnd   = stopDate.value;
  // Target only the streams that haven't been fetched at all
  const notFetched = replayState.value.missing_not_fetched ?? [];
  openFetchMissingStream(
    {
      list: selectedLists.value[0],
      start: fetchStart,
      end: fetchEnd,
      workers: fetchWorkers.value,
      geosncls: notFetched.length ? notFetched : undefined,
    },
    async (evt) => {
      fetchLog.value.push(evt);
      await nextTick();
      if (fetchLogEl.value) fetchLogEl.value.scrollTop = fetchLogEl.value.scrollHeight;
      if (evt.type === "done") {
        fetchRunning.value = false;
        fetchDone.value = true;
      }
    },
  );
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadListOptions();
  await fetchFilterOptions();
  try {
    const cfg = await getServerConfig();
    if (cfg.base_url) serverBase.value = cfg.base_url;
  } catch { /* fall back to window.location.origin */ }
  // Sync with any in-progress server state (e.g. user navigated away and back)
  try {
    const s = await getReplayStatus();
    replayState.value = s;
    if (["preloading", "preloaded", "running", "starting"].includes(s.status)) {
      startPolling();
    }
    if (s.status === "running" || s.status === "starting") {
      await nextTick();
      initChart();
    }
    // Restore config fields if available
    if (s.config) {
      bootstrapServer.value = s.config.bootstrap_server;
      topic.value           = s.config.topic;
      timeScale.value       = s.config.time_scale;
      applyLatency.value    = s.config.apply_latency;
      selectByArrival.value = s.config.select_by_arrival ?? false;
      outputFormat.value    = s.config.output_format ?? "compact";
      startDate.value       = s.config.start_time.slice(0, 10);
      startTime.value       = s.config.start_time.slice(11) || "00:00:00";
      stopDate.value        = s.config.stop_time.slice(0, 10);
      stopTime.value        = s.config.stop_time.slice(11) || "01:00:00";
      selectedLists.value   = s.config.stream_lists ?? [];
    }
  } catch { /* server not ready yet */ }
});

onUnmounted(() => {
  stopPolling();
  if (chart) { chart.destroy(); chart = null; }
});

// If ESLayout uses <keep-alive>, onMounted/onUnmounted only fire once.
// onActivated/onDeactivated fire on every route switch in that case.
onActivated(() => {
  if (["preloading", "preloaded", "running", "starting"].includes(replayStatus.value)) {
    startPolling();
  }
});
onDeactivated(() => {
  stopPolling();
  if (chart) { chart.destroy(); chart = null; }
});

// Re-init chart when canvas is mounted (status transitions to running)
watch(chartCanvas, (el) => {
  if (el && isRunning.value) initChart();
});

// Refresh filter options when stream lists change
watch(selectedLists, () => {
  fetchFilterOptions();
});
</script>

<style scoped>
.config-card {
}
.curl-block {
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  font-size: 12px;
  max-width: 100%;
  overflow-x: auto;
  white-space: nowrap;
}
code {
  font-family: monospace;
}
.replay-log {
  background: #1a1a2e;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
  max-height: 260px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.replay-log .log-ts {
  color: #6c7a89;
  margin-right: 6px;
}
</style>

// ─── Bucket / heatmap ────────────────────────────────────────────────────────

export type BucketState =
  | "has-data"   // completeness > 0
  | "no-data"    // attempted, 0 rows in this bin
  | "not-tried"  // no arrow file and not in no_data.jsonl
  | "error";

export interface BucketData {
  bucketStartMs: number;
  rowCount: number;
  expectedCount: number;
  completeness: number | null;
  meanIngestLatencyS: number | null;
  meanProcessingDelayS: number | null;
  state: BucketState;
}

export interface StationCompleteness {
  geosncl: string;
  buckets: BucketData[];
}

export interface CompletenessResponse {
  bucketMs: number;
  binMinutes: number;
  bucketStarts: number[];
  stations: StationCompleteness[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// ─── Positions ───────────────────────────────────────────────────────────────

export interface PositionTrace {
  geosncl: string;
  times: number[];       // epoch ms
  east: (number | null)[];  // metres
  north: (number | null)[];
  up: (number | null)[];
  sigE: (number | null)[];
  sigN: (number | null)[];
  sigU: (number | null)[];
  downsampleFactor: number;
}

export interface PositionsResponse {
  stations: PositionTrace[];
}

// ─── Fetch-missing SSE events ─────────────────────────────────────────────────

export interface FetchEvent {
  type: "log" | "error" | "done";
  msg?: string;
  code?: number;
  current?: number;   // day-level progress (0-based → total)
  total?: number;
}

export interface FetchMissingBody {
  lists?: string[];
  geosncls?: string[];
  filter_centers?: string[];
  filter_sol_types?: string[];
  start: string;
  end: string;
  workers?: number;
}

// ─── Station list ─────────────────────────────────────────────────────────────

export interface StationEntry {
  geosncl: string;
}

export interface StationsResponse {
  stations: StationEntry[];
  total: number;
}

export interface StreamListsResponse {
  lists: string[];
}

// ─── Replay ───────────────────────────────────────────────────────────────────

export type ReplayStatus =
  | "idle"
  | "preloading"
  | "preloaded"
  | "starting"
  | "running"
  | "canceled"
  | "done"
  | "error";

export interface ReplayConfig {
  bootstrap_server: string;
  topic: string;
  time_scale: number;
  apply_latency: boolean;
  select_by_arrival?: boolean;
  output_format?: "compact" | "geojson";
  start_data_ms: number;
  start_time: string;
  stop_time: string;
  stream_lists: string[];
  all_stations: boolean;
  start_replay_wall_ms?: number;
}

export interface ReplayLogLine {
  ts: number;      // epoch milliseconds
  level: "info" | "warn" | "error";
  msg: string;
}

export interface ReplayState {
  status: ReplayStatus;
  job_id?: string;
  log?: ReplayLogLine[];
  config?: ReplayConfig;
  files?: [string, string][];
  files_count?: number;
  missing_stations?: string[];
  total_messages?: number;
  total_geosncls?: number;
  found_geosncls?: number;
  missing_no_data?: string[];
  missing_not_fetched?: string[];
  sent?: number;
  elapsed_ms?: number;
  current_data_time_ms?: number;
  replay_elapsed_s?: number;
  replay_remaining_s?: number;
  error?: string;
  // Delivery-check consumer (reads back the topic we write to)
  consumer_read?: number;
  consumer_matched?: number;
  consumer_unmatched?: number;
  consumer_mean_rt_ms?: number | null;
  consumer_status?: "ok" | "warn" | "error";
  consumer_message?: string | null;
  // Start / cancel timing (for synchronization)
  start_requested_ms?: number;
  first_write_ms?: number | null;
  startup_delay_ms?: number | null;
  cancel_requested_ms?: number;
  stopped_ms?: number;
  cancel_delay_ms?: number | null;
}

// ─── PPSD ─────────────────────────────────────────────────────────────────────

export type PpsdMode = "by-stream" | "by-center" | "by-solution" | "by-center-solution" | "all";

export interface PpsdRunParams {
  lists: string[];
  start: string;
  end: string;
  mode: PpsdMode;
  centers?: string;
  sol_types?: string;
}

export interface PpsdEvent {
  type: "log" | "progress" | "file" | "error" | "done";
  msg?: string;
  code?: number;
  current?: number;
  total?: number;
  path?: string;
  label?: string;
}

export interface ReplayPreloadBody {
  stream_lists: string[];
  all_stations: boolean;
  start_time: string;
  stop_time: string;
  filter_centers: string[];
  filter_sol_types: string[];
  time_scale: number;
  apply_latency: boolean;
  select_by_arrival: boolean;
  output_format: "compact" | "geojson";
  bootstrap_server: string;
  topic: string;
}

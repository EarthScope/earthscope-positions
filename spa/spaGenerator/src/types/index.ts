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
}

// ─── Station list ─────────────────────────────────────────────────────────────

export interface StationEntry {
  geosncl: string;
}

export interface StationsResponse {
  stations: StationEntry[];
  total: number;
}

export interface StationListsResponse {
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
  start_data_ms: number;
  start_time: string;
  stop_time: string;
  station_lists: string[];
  all_stations: boolean;
  start_replay_wall_ms?: number;
}

export interface ReplayState {
  status: ReplayStatus;
  job_id?: string;
  config?: ReplayConfig;
  files?: [string, string][];
  missing_stations?: string[];
  total_messages?: number;
  total_geosncls?: number;
  found_geosncls?: number;
  missing_no_data?: string[];
  missing_not_fetched?: string[];
  sent?: number;
  elapsed_ms?: number;
  error?: string;
}

// ─── PPSD ─────────────────────────────────────────────────────────────────────

export type PpsdMode = "by-stream" | "by-center" | "by-solution" | "by-center-solution";

export interface PpsdRunParams {
  lists: string[];
  start: string;
  end: string;
  mode: PpsdMode;
  centers?: string;
  solutions?: string;
  types?: string;
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
  station_lists: string[];
  all_stations: boolean;
  start_time: string;
  stop_time: string;
  filter_centers: string[];
  filter_solutions: string[];
  filter_types: string[];
  time_scale: number;
  apply_latency: boolean;
  bootstrap_server: string;
  topic: string;
}

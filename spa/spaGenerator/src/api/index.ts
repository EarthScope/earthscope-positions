import axios from "axios";
import type {
  CompletenessResponse, StationsResponse, StreamListsResponse,
  PositionsResponse, FetchEvent, FetchMissingBody,
  ReplayState, ReplayPreloadBody, CoherenceResponse, KleResponse, PcaResponse,
  CommonModeRemovedResponse,
} from "../types";

const http = axios.create({ baseURL: "/api" });

export async function getStreamLists(): Promise<StreamListsResponse> {
  const r = await http.get<StreamListsResponse>("/stream-lists");
  return r.data;
}

export async function getStations(params: {
  list?: string;
  search?: string;
}): Promise<StationsResponse> {
  const r = await http.get<StationsResponse>("/stations", { params });
  return r.data;
}

export async function getCompleteness(params: {
  list: string;
  search: string;
  start: string;
  end: string;
  page: number;
  size: number;
}): Promise<CompletenessResponse> {
  const r = await http.get<CompletenessResponse>("/completeness", { params });
  return r.data;
}

export async function getPositions(params: {
  geosncls: string;  // comma-separated
  start: string;
  end: string;
  maxPoints?: number;
  downsample?: boolean;
}): Promise<PositionsResponse> {
  const r = await http.get<PositionsResponse>("/positions", {
    params: {
      geosncls: params.geosncls,
      start: params.start,
      end: params.end,
      max_points: params.maxPoints ?? 2000,
      downsample: params.downsample ?? true,
    },
  });
  return r.data;
}

/** Always issues one fresh, combined request for exactly the geosncls passed —
 *  independent of the Positions page's incremental positionCache, so it
 *  behaves identically whether the current selection was built up one stream
 *  at a time or via a bulk action (Select All / group check). */
export async function getCoherence(params: {
  geosncls: string;  // comma-separated, 2-35
  start: string;
  end: string;
  component: "east" | "north" | "up";
  outlierM?: number;
}): Promise<CoherenceResponse> {
  const r = await http.get<CoherenceResponse>("/coherence", {
    params: {
      geosncls: params.geosncls,
      start: params.start,
      end: params.end,
      component: params.component,
      outlier_m: params.outlierM,
    },
  });
  return r.data;
}

/** Karhunen-Loeve (network PCA) decomposition — same access-pattern
 *  independence as getCoherence above. */
export async function getKle(params: {
  geosncls: string;
  start: string;
  end: string;
  component: "east" | "north" | "up";
  nModes?: number;
  outlierM?: number;
}): Promise<KleResponse> {
  const r = await http.get<KleResponse>("/kle", {
    params: {
      geosncls: params.geosncls,
      start: params.start,
      end: params.end,
      component: params.component,
      n_modes: params.nModes ?? 5,
      outlier_m: params.outlierM,
    },
  });
  return r.data;
}

/** Classical PCA (network decomposition) — sibling of getKle, same
 *  access-pattern independence. */
export async function getPca(params: {
  geosncls: string;
  start: string;
  end: string;
  component: "east" | "north" | "up";
  nModes?: number;
  outlierM?: number;
}): Promise<PcaResponse> {
  const r = await http.get<PcaResponse>("/pca", {
    params: {
      geosncls: params.geosncls,
      start: params.start,
      end: params.end,
      component: params.component,
      n_modes: params.nModes ?? 5,
      outlier_m: params.outlierM,
    },
  });
  return r.data;
}

/** Each selected stream's E/N/U with the leading common-mode(s) removed (via
 *  KLE or classical PCA), in the same shape as getPositions (drop-in for a
 *  parallel chart set). */
export async function getCommonModeRemoved(params: {
  geosncls: string;
  start: string;
  end: string;
  method: "kle" | "pca";
  nModesRemoved?: number;
  maxPoints?: number;
  downsample?: boolean;
  outlierM?: number;
}): Promise<CommonModeRemovedResponse> {
  const r = await http.get<CommonModeRemovedResponse>("/positions/common-mode-removed", {
    params: {
      geosncls: params.geosncls,
      start: params.start,
      end: params.end,
      method: params.method,
      n_modes_removed: params.nModesRemoved ?? 1,
      max_points: params.maxPoints ?? 2000,
      downsample: params.downsample ?? true,
      outlier_m: params.outlierM,
    },
  });
  return r.data;
}

export async function getDataRange(): Promise<{ min: string | null; max: string | null }> {
  const r = await http.get<{ min: string | null; max: string | null }>("/data-range");
  return r.data;
}

export async function saveStreamList(name: string, geosncls: string[]): Promise<{ name: string; count: number }> {
  const r = await http.post<{ name: string; count: number }>(`/stream-lists/${encodeURIComponent(name)}`, { geosncls });
  return r.data;
}

/** Stream /api/fetch-missing using fetch() (avoids EventSource auto-reconnect).
 *  Returns a cancel function that aborts the request. */
export function openFetchMissingStream(
  params: { list?: string; start: string; end: string; workers?: number; geosncls?: string[] },
  onEvent: (e: FetchEvent) => void,
): () => void {
  const q = new URLSearchParams({
    list: params.list ?? "all",
    start: params.start,
    end: params.end,
    workers: String(params.workers ?? 10),
  });
  if (params.geosncls?.length) q.set("geosncls", params.geosncls.join(","));

  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`/api/fetch-missing?${q}`, { signal: controller.signal });
      if (!resp.body) throw new Error("No response body");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            onEvent(JSON.parse(line.slice(5).trim()) as FetchEvent);
          } catch { /* ignore */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", msg: String(err) });
        onEvent({ type: "done", code: 1 });
      }
    }
  })();

  return () => controller.abort();
}

/** POST variant of fetch-missing: resolves lists + stream filters server-side.
 *  Streams SSE via fetch(); returns a cancel function that aborts the request. */
export function openFetchMissingPost(
  body: FetchMissingBody,
  onEvent: (e: FetchEvent) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch("/api/fetch-missing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.body) throw new Error("No response body");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            onEvent(JSON.parse(line.slice(5).trim()) as FetchEvent);
          } catch { /* ignore */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", msg: String(err) });
        onEvent({ type: "done", code: 1 });
      }
    }
  })();

  return () => controller.abort();
}

/** Save a client-rendered PNG (data URL) to data/plots/<folder>/. */
export async function savePlotImage(
  filename: string,
  dataUrl: string,
  folder?: string,
): Promise<{ path: string; name: string }> {
  const r = await http.post<{ path: string; name: string }>("/plots/save", {
    filename,
    data_url: dataUrl,
    folder: folder ?? "positions",
  });
  return r.data;
}

// ─── Export / convert (Arrow → MiniSEED / GeoJSON) ─────────────────────────────

export async function getExportSpec(
  format: "miniseed" | "geojson",
): Promise<{ format: string; path: string; content: string }> {
  const r = await http.get("/export/spec", { params: { format } });
  return r.data;
}

export async function saveExportSpec(
  format: "miniseed" | "geojson",
  content: string,
): Promise<{ ok: boolean; path: string }> {
  const r = await http.put("/export/spec", { format, content });
  return r.data;
}

/** Stream /api/export/run via fetch(); returns a cancel function. */
export function openExportStream(
  params: {
    format: "miniseed" | "geojson";
    lists: string[];
    start: string;
    end: string;
    gj_format?: "compact" | "full" | "both";
    ms_version?: 2 | 3;
    force?: boolean;
  },
  onEvent: (e: FetchEvent) => void,
): () => void {
  const q = new URLSearchParams();
  q.set("format", params.format);
  for (const l of params.lists) q.append("lists", l);
  q.set("start", params.start);
  q.set("end", params.end);
  if (params.gj_format) q.set("gj_format", params.gj_format);
  if (params.ms_version) q.set("ms_version", String(params.ms_version));
  if (params.force) q.set("force", "true");

  const controller = new AbortController();
  (async () => {
    try {
      const resp = await fetch(`/api/export/run?${q}`, { signal: controller.signal });
      if (!resp.body) throw new Error("No response body");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try { onEvent(JSON.parse(line.slice(5).trim()) as FetchEvent); } catch { /* ignore */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", msg: String(err) });
        onEvent({ type: "done", code: 1 });
      }
    }
  })();
  return () => controller.abort();
}

// ─── Server config ─────────────────────────────────────────────────────────────

export interface ServerConfig {
  base_url: string;
  hostname: string;
  port: number;
  /** Deployment this server pulls from: "prod" | "stage". */
  environment: string;
  environment_label: string;
  /**
   * Whether the UI should announce the environment.  The server decides, not
   * the client — production is the unremarkable case and stays unlabelled.
   */
  environment_badge: boolean;
  api_url: string;
  es_profile: string;
}

export async function getServerConfig(): Promise<ServerConfig> {
  const r = await http.get<ServerConfig>("/config");
  return r.data;
}

// ─── Completeness precache ────────────────────────────────────────────────────

export interface PrecacheEvent {
  type: "start" | "streams" | "progress" | "error" | "done";
  total?: number;
  done?: number;
  generated?: number;
  failed?: number;
  count?: number;
  name?: string;
  msg?: string;
  code?: number;
}

/**
 * Build every completeness file the given selection needs, up front.
 *
 * Same selection the heatmap uses, but across every page — the point is to pay
 * the build cost once instead of on each page you happen to open.
 * Returns an abort function.
 */
export function openPrecacheStream(
  body: {
    lists?: string[];
    geosncls?: string[];
    filter_centers?: string[];
    filter_sol_types?: string[];
    search?: string;
    start: string;
    end: string;
  },
  onEvent: (e: PrecacheEvent) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch("/api/completeness/precache", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.body) throw new Error("No response body");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data: "));
          if (line) onEvent(JSON.parse(line.slice(6)) as PrecacheEvent);
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      onEvent({ type: "error", msg: String(err) });
      onEvent({ type: "done", code: 1 });
    }
  })();

  return () => controller.abort();
}

/**
 * Source .arrow file backing one heatmap cell, as a File Explorer path.
 * Resolved on click rather than shipped with every bucket — a page carries
 * thousands of cells and almost none are clicked.
 */
export async function locateArrowFile(
  geosncl: string,
  startMs: number,
  endMs: number,
): Promise<{ path: string; name: string }> {
  const r = await http.get<{ path: string; name: string }>("/files/locate", {
    params: { geosncl, start_ms: startMs, end_ms: endMs },
  });
  return r.data;
}

// ─── Replay ───────────────────────────────────────────────────────────────────

export async function replayPreload(body: ReplayPreloadBody): Promise<{ status: string }> {
  const r = await http.post<{ status: string }>("/replay/preload", body);
  return r.data;
}

export async function getReplayStatus(): Promise<ReplayState> {
  const r = await http.get<ReplayState>("/replay/status");
  return r.data;
}

export async function replayGo(jobId: string): Promise<{ status: string }> {
  const r = await http.post<{ status: string }>(`/replay/${encodeURIComponent(jobId)}/go`);
  return r.data;
}

/** Start the currently-preloaded replay without supplying a job_id. Used for external curl triggers. */
export async function replayStart(): Promise<{ status: string }> {
  const r = await http.post<{ status: string }>("/replay/start");
  return r.data;
}

export async function replayCancel(): Promise<{ status: string }> {
  const r = await http.post<{ status: string }>("/replay/cancel");
  return r.data;
}

export async function replayReset(): Promise<{ status: string }> {
  const r = await http.post<{ status: string }>("/replay/reset");
  return r.data;
}

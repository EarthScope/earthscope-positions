import axios from "axios";
import type {
  CompletenessResponse, StationsResponse, StationListsResponse,
  PositionsResponse, FetchEvent, FetchMissingBody,
  ReplayState, ReplayPreloadBody,
} from "../types";

const http = axios.create({ baseURL: "/api" });

export async function getStationLists(): Promise<StationListsResponse> {
  const r = await http.get<StationListsResponse>("/station-lists");
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

export async function getDataRange(): Promise<{ min: string | null; max: string | null }> {
  const r = await http.get<{ min: string | null; max: string | null }>("/data-range");
  return r.data;
}

export async function saveStationList(name: string, geosncls: string[]): Promise<{ name: string; count: number }> {
  const r = await http.post<{ name: string; count: number }>(`/station-lists/${encodeURIComponent(name)}`, { geosncls });
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

/** Save a client-rendered PNG (data URL) to data/plots/positions/. */
export async function savePlotImage(
  filename: string,
  dataUrl: string,
): Promise<{ path: string; name: string }> {
  const r = await http.post<{ path: string; name: string }>("/plots/save", {
    filename,
    data_url: dataUrl,
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

export async function getServerConfig(): Promise<{ base_url: string; hostname: string; port: number }> {
  const r = await http.get<{ base_url: string; hostname: string; port: number }>("/config");
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

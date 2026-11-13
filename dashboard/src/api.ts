export type ArtifactKind =
  | "datasets"
  | "research"
  | "models"
  | "discovery"
  | "validation"
  | "backtests"
  | "portfolios"
  | "paper"
  | "agent"
  | "live";
export interface Artifact {
  id: string;
  kind: ArtifactKind;
  label: string;
  mode: string;
  status: string;
  summary: Record<string, unknown>;
  updated_at: string;
}
export interface Page {
  items: Artifact[];
  total: number;
  offset: number;
  limit: number;
}
export interface Point {
  at: string;
  equity: number;
  benchmark?: number;
  drawdown?: number;
  gross?: number;
  margin?: number;
}
export interface Detail {
  record: Artifact;
  data: Record<string, unknown>;
  series: Point[];
}
export interface Health {
  status: string;
  live_enabled: boolean;
  streaming_verified: boolean;
  eligible_strategies: number;
  warnings: string[];
  jobs: Record<string, unknown>[];
  paper_accounts: number;
  catalog_errors: string[];
  holdout_state: string;
}
let bearer = "";
export function setToken(value: string) {
  bearer = value.trim();
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(bearer ? { Authorization: "Bearer " + bearer } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const d = await response.json();
      message = d.error?.message || d.detail || message;
    } catch {
      /* preserve status */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const listArtifacts = (kind: string, search: string, offset = 0) =>
  request<Page>(
    `/artifacts?kind=${encodeURIComponent(kind)}&search=${encodeURIComponent(search)}&offset=${offset}&limit=20&sort=updated_at`,
  );
export async function downloadReport(id: string) {
  const d = await request<Detail>("/artifacts/" + encodeURIComponent(id));
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = id + ".json";
  a.click();
  URL.revokeObjectURL(url);
}
export async function monitorUpdates(
  onRefresh: () => void,
  signal: AbortSignal,
) {
  const response = await fetch("/api/v1/events", {
    headers: bearer ? { Authorization: "Bearer " + bearer } : {},
    signal,
  });
  if (
    !response.ok ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  )
    return;
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) return;
    if (decoder.decode(value).includes("event: refresh")) onRefresh();
  }
}
export function csvText(rows: Record<string, unknown>[]) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  const cell = (v: unknown) => {
    let s = typeof v === "object" ? JSON.stringify(v) : String(v ?? "");
    if (/^[=+@-]/.test(s) && typeof v === "string") s = "'" + s;
    return '"' + s.replaceAll('"', '""') + '"';
  };
  return [
    keys.map(cell).join(","),
    ...rows.map((r) => keys.map((k) => cell(r[k])).join(",")),
  ].join("\r\n");
}
export function downloadCSV(name: string, rows: Record<string, unknown>[]) {
  const url = URL.createObjectURL(
    new Blob([csvText(rows)], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name + ".csv";
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadProfitabilityBundle(identity: string) {
  const response = await fetch(
    `/api/v1/workflows/jobs/${encodeURIComponent(identity)}/profitability.zip`,
    {
      headers: bearer ? { Authorization: `Bearer ${bearer}` } : {},
    },
  );
  if (!response.ok)
    throw new Error(
      `Unable to download profitability artifacts (HTTP ${response.status})`,
    );
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `profitability-${identity}.zip`;
  anchor.click();
  URL.revokeObjectURL(url);
}

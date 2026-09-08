import type { Channel, Member, Page, Pin, Server, TimeseriesPoint } from "../types";

/** An API error carrying the server's error envelope (message + trace id). */
export class ApiError extends Error {
  status: number;
  traceId?: string;
  constructor(status: number, message: string, traceId?: string) {
    super(message);
    this.status = status;
    this.traceId = traceId;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = body?.error;
    throw new ApiError(res.status, err?.message ?? `Request failed (${res.status})`, err?.trace_id);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => request<{ dataset_now: string | null }>("/api/meta"),
  servers: () => request<Server[]>("/api/servers"),
  channels: (serverId: string) =>
    request<Channel[]>(`/api/channels?server_id=${encodeURIComponent(serverId)}`),
  members: (serverId: string, limit = 25, offset = 0) =>
    request<Page<Member>>(
      `/api/members?server_id=${encodeURIComponent(serverId)}&limit=${limit}&offset=${offset}`,
    ),
  activity: (serverId: string) =>
    request<TimeseriesPoint[]>(
      `/api/timeseries/activity?server_id=${encodeURIComponent(serverId)}&bucket=day`,
    ),

  listPins: () => request<Pin[]>("/api/pins"),
  createPin: (pin: { title?: string; spec: unknown; sql: string }) =>
    request<Pin>("/api/pins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pin),
    }),
  deletePin: (id: string) => request<{ deleted: string }>(`/api/pins/${id}`, { method: "DELETE" }),
  pinData: (id: string) =>
    request<{ columns: string[]; rows: unknown[][] }>(`/api/pins/${id}/data`),
};

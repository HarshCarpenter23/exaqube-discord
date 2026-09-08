export interface Server {
  server_id: string;
  server_name: string;
  region?: string | null;
  approximate_member_count?: number | null;
  creation_date?: string | null;
}

export interface Channel {
  channel_id: string;
  channel_name?: string | null;
  channel_type?: string | null;
  position?: number | null;
}

export interface Member {
  user_id: string;
  username?: string | null;
  display_name?: string | null;
  is_bot: boolean;
  messages_sent?: number | null;
  join_date?: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TimeseriesPoint {
  channel_id: string;
  period: string;
  message_count: number;
}

/** A chart spec, produced by the chart plugin or reconstructed for a pin. */
export interface ChartSpec {
  type: "line" | "bar" | "distribution";
  x: string;
  y?: string | null;
  series?: string | null;
  title?: string | null;
  columns: string[];
  rows: unknown[][];
  sql?: string | null;
}

export interface Pin {
  id: string;
  title?: string | null;
  spec: ChartSpec;
  sql: string;
  created_at: string;
}

/** One SSE stage event from the chat endpoint. */
export interface StageEvent {
  event: string;
  data: Record<string, unknown>;
}

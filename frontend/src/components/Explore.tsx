import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ChartSpec, Member, Page, Server, TimeseriesPoint } from "../types";
import { ChartView } from "./ChartView";
import { DataTable } from "./DataTable";
import { Empty, ErrorBanner, Loading } from "./states";

/** Aggregate per-channel-per-day points into a total-per-day line chart spec. */
function activityToSpec(points: TimeseriesPoint[]): ChartSpec {
  const byDay = new Map<string, number>();
  for (const p of points) {
    const day = p.period.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + p.message_count);
  }
  const rows = [...byDay.entries()].sort().map(([day, total]) => [day, total]);
  return { type: "line", x: "day", y: "messages", columns: ["day", "messages"], rows };
}

export function Explore() {
  const [servers, setServers] = useState<Server[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [serverId, setServerId] = useState<string>("");

  const [members, setMembers] = useState<Page<Member> | null>(null);
  const [activity, setActivity] = useState<TimeseriesPoint[] | null>(null);
  const [dataError, setDataError] = useState<unknown>(null);

  useEffect(() => {
    api
      .servers()
      .then((s) => {
        setServers(s);
        if (s.length) setServerId(s[0].server_id);
      })
      .catch(setError);
  }, []);

  function loadServerData(id: string) {
    setMembers(null);
    setActivity(null);
    setDataError(null);
    Promise.all([api.members(id, 25), api.activity(id)])
      .then(([m, a]) => {
        setMembers(m);
        setActivity(a);
      })
      .catch(setDataError);
  }

  useEffect(() => {
    if (serverId) loadServerData(serverId);
  }, [serverId]);

  if (error) return <ErrorBanner error={error} onRetry={() => window.location.reload()} />;
  if (!servers) return <Loading label="Loading servers…" />;
  if (servers.length === 0) return <Empty>No servers loaded.</Empty>;

  return (
    <div className="stack">
      <div className="row" style={{ alignItems: "center" }}>
        <label className="subtle">Server</label>
        <select value={serverId} onChange={(e) => setServerId(e.target.value)}>
          {servers.map((s) => (
            <option key={s.server_id} value={s.server_id}>
              {s.server_name}
            </option>
          ))}
        </select>
      </div>

      {dataError && <ErrorBanner error={dataError} onRetry={() => loadServerData(serverId)} />}

      <div className="chart-card">
        <div className="head">
          <h4>Messages per day</h4>
          <span className="pill-kind">time series</span>
        </div>
        {!activity ? (
          <Loading />
        ) : activity.length === 0 ? (
          <Empty>No message activity in range.</Empty>
        ) : (
          <ChartView spec={activityToSpec(activity)} />
        )}
      </div>

      <div className="card">
        <h4 style={{ marginTop: 0 }}>Top members</h4>
        {!members ? (
          <Loading />
        ) : members.items.length === 0 ? (
          <Empty>No members.</Empty>
        ) : (
          <DataTable
            columns={["username", "display_name", "is_bot", "messages_sent"]}
            rows={members.items.map((m) => [m.username, m.display_name, m.is_bot, m.messages_sent])}
          />
        )}
      </div>
    </div>
  );
}

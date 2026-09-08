import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ChartSpec, Pin } from "../types";
import { ChartView } from "./ChartView";
import { Empty, ErrorBanner, Loading } from "./states";

export function Dashboard() {
  const [pins, setPins] = useState<Pin[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  function load() {
    setError(null);
    api.listPins().then(setPins).catch(setError);
  }

  useEffect(load, []);

  async function remove(id: string) {
    await api.deletePin(id);
    load();
  }

  if (error) return <ErrorBanner error={error} onRetry={load} />;
  if (!pins) return <Loading label="Loading dashboard…" />;
  if (pins.length === 0)
    return <Empty>No pinned charts yet. Pin a chart from the chat to see it here.</Empty>;

  return (
    <div className="stack">
      {pins.map((pin) => (
        <PinnedChart key={pin.id} pin={pin} onDelete={() => remove(pin.id)} />
      ))}
    </div>
  );
}

/** Re-runs the pin's query for fresh rows, then renders the stored encoding. */
function PinnedChart({ pin, onDelete }: { pin: Pin; onDelete: () => void }) {
  const [spec, setSpec] = useState<ChartSpec | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api
      .pinData(pin.id)
      .then((data) => setSpec({ ...pin.spec, columns: data.columns, rows: data.rows }))
      .catch(setError);
  }, [pin.id]);

  return (
    <div className="chart-card">
      <div className="head">
        <h4>{pin.title ?? "Chart"}</h4>
        <button className="btn ghost small" onClick={onDelete}>Remove</button>
      </div>
      {error ? (
        <ErrorBanner error={error} />
      ) : !spec ? (
        <Loading />
      ) : (
        <ChartView spec={spec} />
      )}
    </div>
  );
}

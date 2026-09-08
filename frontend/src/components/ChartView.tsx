import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec } from "../types";

const NAVY = "#0a2540";
const BLUE = "#3b82f6";

/** Turn columns + row arrays into the objects Recharts expects. */
function toRecords(spec: ChartSpec): Record<string, unknown>[] {
  return spec.rows.map((row) => {
    const rec: Record<string, unknown> = {};
    spec.columns.forEach((col, i) => (rec[col] = row[i]));
    return rec;
  });
}

export function ChartView({ spec }: { spec: ChartSpec }) {
  if (!spec.y) {
    return <div className="subtle">This chart needs a numeric y column.</div>;
  }
  const data = toRecords(spec);
  const y = spec.y;

  return (
    <ResponsiveContainer width="100%" height={260}>
      {spec.type === "line" ? (
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="rgba(10,10,10,0.06)" vertical={false} />
          <XAxis dataKey={spec.x} tick={{ fontSize: 11, fill: "#6e6e73" }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11, fill: "#6e6e73" }} width={40} />
          <Tooltip />
          <Line type="monotone" dataKey={y} stroke={NAVY} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      ) : (
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="rgba(10,10,10,0.06)" vertical={false} />
          <XAxis dataKey={spec.x} tick={{ fontSize: 11, fill: "#6e6e73" }} minTickGap={8} />
          <YAxis tick={{ fontSize: 11, fill: "#6e6e73" }} width={40} />
          <Tooltip />
          <Bar dataKey={y} fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      )}
    </ResponsiveContainer>
  );
}

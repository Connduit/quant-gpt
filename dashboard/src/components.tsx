import { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { Point } from "./api";
export function Badge({ text }: { text: string }) {
  const lower = text.toLowerCase();
  const cls = /reject|failed|blocked|halt|kill|not_ready/.test(lower)
    ? "danger"
    : /replay|research|synthetic|unverified|insufficient|stale/.test(lower)
      ? "warn"
      : "neutral";
  return <span className={"badge " + cls}>{text.replaceAll("_", " ")}</span>;
}
export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
export function JsonView({
  data,
  label = "Artifact details",
}: {
  data: unknown;
  label?: string;
}) {
  return (
    <details className="json">
      <summary>{label}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
export function Curve({
  points,
  title = "Selected run · Eastern time for intraday observations",
}: {
  points: Point[];
  title?: string;
}) {
  const [metric, setMetric] = useState<"equity" | "drawdown" | "gross">(
    "equity",
  );
  return (
    <section className="panel chart">
      <div className="panel-title">
        <h3>{title}</h3>
        <select
          aria-label="Chart metric"
          value={metric}
          onChange={(e) => setMetric(e.target.value as typeof metric)}
        >
          <option value="equity">Equity (USD)</option>
          <option value="drawdown">Drawdown</option>
          <option value="gross">Gross exposure</option>
        </select>
      </div>
      {points.length ? (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={points}>
            <CartesianGrid stroke="#222e3d" vertical={false} />
            <XAxis
              dataKey="at"
              tickFormatter={(x) =>
                points.length > 1 &&
                new Date(points[points.length - 1].at).getTime() -
                  new Date(points[0].at).getTime() <
                  3 * 86400000
                  ? new Intl.DateTimeFormat("en-US", {
                      timeZone: "America/New_York",
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    }).format(new Date(x))
                  : String(x).slice(0, 10)
              }
              minTickGap={70}
              stroke="#718096"
            />
            <YAxis
              domain={["auto", "auto"]}
              width={75}
              stroke="#718096"
              tickFormatter={(x) =>
                Number(x).toLocaleString(undefined, {
                  maximumFractionDigits: 2,
                })
              }
            />
            <Tooltip
              contentStyle={{
                background: "#141d29",
                border: "1px solid #344155",
              }}
            />
            <Line
              type="linear"
              dataKey={metric}
              stroke="#6baaff"
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
            />
            {metric === "equity" && (
              <Line
                dataKey="benchmark"
                stroke="#d6a552"
                dot={false}
                isAnimationActive={false}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="empty">
          No measured time series is available for this artifact.
        </p>
      )}
    </section>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error">
      {error.message}
      {retry && <button onClick={retry}>Retry</button>}
    </div>
  );
}
export function Table({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="empty">No records available.</p>;
  const keys = Object.keys(rows[0]).slice(0, 10);
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {keys.map((k) => (
              <th key={k}>{k.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 100).map((row, i) => (
            <tr key={i}>
              {keys.map((k) => (
                <td key={k}>
                  {typeof row[k] === "object"
                    ? JSON.stringify(row[k])
                    : String(row[k] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 100 && (
        <p>Showing 100 of {rows.length}. Export the report for all rows.</p>
      )}
    </div>
  );
}

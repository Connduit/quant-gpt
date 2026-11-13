import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, Metric } from "./components";
import { downloadProfitabilityBundle } from "./api";
const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const rows = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.map(obj) : [];
const number = (value: unknown) =>
  value === null || value === undefined ? NaN : Number(value);
const fmt = (value: unknown, digits = 2) =>
  Number.isFinite(number(value))
    ? number(value).toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : "Not available";
const pct = (value: unknown) =>
  Number.isFinite(number(value))
    ? `${fmt(number(value) * 100)}%`
    : "Not available";
const usd = (value: unknown) =>
  Number.isFinite(number(value)) ? `$${fmt(value)}` : "Not available";
const names: Record<string, string> = {
  ml: "ML strategy",
  spy_buy_hold: "SPY buy and hold",
  equal_weight: "Equal-weight stocks",
  momentum: "Momentum",
  mean_reversion: "Mean reversion",
  cash: "Cash (0% interest)",
};

export function ProfitabilityReport({
  data,
  identity,
}: {
  data: Record<string, unknown>;
  identity: string;
}) {
  const report = obj(data.report),
    scenarios = obj(report.scenarios);
  const [scenario, setScenario] = useState("baseline"),
    [error, setError] = useState("");
  const selected = obj(scenarios[scenario]),
    strategies = obj(selected.strategies),
    primary = obj(strategies.ml);
  const net = obj(primary.net),
    gross = obj(primary.gross_zero_cost_rerun),
    costs = obj(primary.costs);
  const curves = rows(
    obj(report.equity_curves)[scenario] ?? report.equity_curve,
  );
  const validation = obj(report.statistical_validation),
    uncertainty = obj(validation.active_return_uncertainty);
  const intervals = obj(uncertainty.percentile_intervals);
  const meanInterval = Array.isArray(intervals.mean_daily_return)
    ? intervals.mean_daily_return
    : [];
  const assumptions = obj(selected.assumptions);
  async function download() {
    try {
      await downloadProfitabilityBundle(identity);
    } catch (error) {
      setError((error as Error).message);
    }
  }
  if (!Object.keys(scenarios).length)
    return (
      <section className="result-section">
        <h3>Strategy evaluation did not complete</h3>
        <p role="alert">
          {String(
            data.reason ?? "Check the job details for the blocking reason.",
          )}
        </p>
      </section>
    );
  return (
    <div className="readable-report profitability-report">
      <div className="result-intro">
        <Badge text="NOT VALIDATED" />
        <Badge text={String(report.performance_kind)} />
        <h3>Strategy profitability evaluation</h3>
        <p>
          Saved out-of-sample signals, next-open executions and shared cash
          accounting. These are simulated returns under stated assumptions, not
          live results or approval to trade.
        </p>
        <p>
          Evaluation: {String(report.evaluation_start)} –{" "}
          {String(report.evaluation_end)} · Model: {String(report.model)}
        </p>
        {typeof obj(report.screening_summary).conclusion === "string" && (
          <p>
            Baseline-cost screening:{" "}
            {String(obj(report.screening_summary).conclusion)} Strongest simple
            baseline:{" "}
            {names[
              String(obj(report.screening_summary).strongest_simple_baseline)
            ] ?? "Not available"}
            . {String(obj(report.screening_summary).exposure_caveat ?? "")}
          </p>
        )}
        <label>
          Cost scenario{" "}
          <select
            aria-label="Cost scenario"
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
          >
            {Object.keys(scenarios).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <button onClick={() => void download()}>
          Download trade logs and reports
        </button>
        {error && <p role="alert">{error}</p>}
      </div>
      <div className="metrics result-metrics">
        <Metric
          label="Net simulated return"
          value={pct(net.total_return)}
          note="After modeled commissions, spread, slippage, impact and final liquidation."
        />
        <Metric
          label="Annualized return"
          value={pct(net.annualized_return)}
          note="Historical annualized growth; not a forecast."
        />
        <Metric
          label="Maximum drawdown"
          value={pct(net.maximum_drawdown)}
          note="Largest peak-to-trough decline in marked net equity."
        />
        <Metric
          label="Sharpe ratio"
          value={fmt(net.sharpe_ratio)}
          note="Annualized daily-return ratio; zero cash interest assumed."
        />
        <Metric
          label="Sortino ratio"
          value={fmt(net.sortino_ratio)}
          note="Daily downside deviation; undefined ratios stay unavailable."
        />
        <Metric
          label="Trading costs"
          value={usd(costs.total)}
          note="Executed commissions + half-spread + slippage + assumed market impact."
        />
      </div>
      <section className="result-section" aria-label="Net equity curve">
        <h4>Net equity versus benchmarks · {scenario} costs</h4>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={curves} margin={{ left: 20, right: 20 }}>
            <CartesianGrid stroke="#293649" vertical={false} />
            <XAxis dataKey="date" minTickGap={70} stroke="#9aa8ba" />
            <YAxis
              stroke="#9aa8ba"
              tickFormatter={(value) => `$${fmt(Number(value) / 1000, 0)}k`}
            />
            <Tooltip
              formatter={(value) => usd(value)}
              contentStyle={{ background: "#152030" }}
            />
            <Legend />
            <Line
              isAnimationActive={false}
              type="linear"
              dataKey="net_equity"
              name="ML net equity"
              stroke="#65c7dc"
              dot={false}
            />
            <Line
              isAnimationActive={false}
              type="linear"
              dataKey="spy_equity"
              name="SPY net equity"
              stroke="#a899ef"
              dot={false}
            />
            <Line
              isAnimationActive={false}
              type="linear"
              dataKey="equal_weight_equity"
              name="Equal-weight net equity"
              stroke="#e3b76a"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
        <h4>ML drawdown · {scenario} costs</h4>
        <ResponsiveContainer width="100%" height={170}>
          <LineChart data={curves} margin={{ left: 20, right: 20 }}>
            <XAxis dataKey="date" minTickGap={70} stroke="#9aa8ba" />
            <YAxis tickFormatter={(value) => pct(value)} stroke="#9aa8ba" />
            <Tooltip
              formatter={(value) => pct(value)}
              contentStyle={{ background: "#152030" }}
            />
            <Line
              isAnimationActive={false}
              dataKey="drawdown"
              name="Net drawdown"
              stroke="#ee9b94"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </section>
      <section
        className="result-section"
        aria-label="Trading benchmark comparison"
      >
        <h4>Net benchmark comparison</h4>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Net return</th>
                <th>Versus SPY</th>
                <th>Drawdown</th>
                <th>Sharpe</th>
                <th>Average exposure</th>
                <th>Trading costs</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(strategies).map(([name, value]) => {
                const strategy = obj(value),
                  metrics = obj(strategy.net);
                return (
                  <tr key={name}>
                    <td>{names[name] ?? name}</td>
                    <td>{pct(metrics.total_return)}</td>
                    <td>{pct(strategy.excess_total_return_vs_spy)}</td>
                    <td>{pct(metrics.maximum_drawdown)}</td>
                    <td>{fmt(metrics.sharpe_ratio)}</td>
                    <td>{pct(metrics.average_gross_exposure)}</td>
                    <td>{usd(obj(strategy.costs).total)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p>
          SPY and equal-weight use the same cash reserve but no single-stock cap
          or active drawdown stop. Exposure differs; a higher return alone does
          not establish superior risk-adjusted performance.
        </p>
        <p>
          ML zero-cost rerun: {pct(gross.total_return)}; net replay:{" "}
          {pct(net.total_return)}. The zero-cost path is simulated separately,
          so holdings may differ. Gross is not reported as net.
        </p>
      </section>
      <section className="result-section">
        <h4>Costs, turnover and trades</h4>
        <p>
          Assumptions for this cost scenario: commission $
          {fmt(assumptions.commission_per_share, 4)}/share, full spread{" "}
          {fmt(assumptions.spread_bps)} bps, slippage{" "}
          {fmt(assumptions.slippage_bps)} bps, impact{" "}
          {fmt(assumptions.market_impact_bps)} bps. Impact is assumed, not
          calibrated capacity.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Commissions</th>
                <th>Spread</th>
                <th>Slippage</th>
                <th>Impact</th>
                <th>Two-way turnover</th>
                <th>Exit fills</th>
                <th>Win rate</th>
                <th>Profit factor</th>
                <th>Average exit P&amp;L</th>
                <th>Calmar</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{usd(costs.commissions)}</td>
                <td>{usd(costs.spread_cost)}</td>
                <td>{usd(costs.slippage_cost)}</td>
                <td>{usd(costs.market_impact_cost)}</td>
                <td>{fmt(net.gross_turnover)}×</td>
                <td>{fmt(net.exit_fill_count, 0)}</td>
                <td>{pct(net.win_rate)}</td>
                <td>{fmt(net.profit_factor)}</td>
                <td>{usd(net.average_exit_pnl)}</td>
                <td>{fmt(net.calmar_ratio)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          Trade statistics count sell fills (including partial exits), not
          independent round trips. Turnover is absolute executed notional
          divided by mean equity, without halving. Rejections:{" "}
          {String(obj(primary.order_status_counts).rejected ?? 0)}; risk-reduced
          orders: {String(primary.risk_reduced_orders ?? 0)}.
        </p>
      </section>
      <section className="result-section">
        <h4>Performance by calendar period · {scenario} costs</h4>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Net return</th>
                <th>Sessions</th>
              </tr>
            </thead>
            <tbody>
              {rows(primary.monthly_returns).map((row) => (
                <tr key={String(row.period)}>
                  <td>{String(row.period)}</td>
                  <td>{pct(row.net_return)}</td>
                  <td>{fmt(row.sessions, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Yearly returns:{" "}
          {rows(primary.yearly_returns)
            .map((row) => `${row.period}: ${pct(row.net_return)}`)
            .join(" · ")}
        </p>
        <details>
          <summary>Market-regime breakdown (descriptive)</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>SPY regime</th>
                  <th>Sessions</th>
                  <th>Mean daily net return</th>
                </tr>
              </thead>
              <tbody>
                {rows(primary.regimes).map((row) => (
                  <tr key={String(row.regime)}>
                    <td>{String(row.regime)}</td>
                    <td>{fmt(row.sessions, 0)}</td>
                    <td>{pct(row.conditional_mean_daily_return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Regimes use ex-post daily SPY path direction. They are descriptive
            groups and never inform trades.
          </p>
        </details>
      </section>
      <section className="result-section">
        <h4>Validation and data readiness</h4>
        <Badge text={String(validation.status ?? "NOT VALIDATED")} />
        <p>
          No automatic qualification, paper promotion or live deployment.
          Protected holdout: {String(validation.final_holdout)}. Independent
          confirmation: {String(validation.independent_confirmation)}.
        </p>
        {meanInterval.length === 2 && (
          <p>
            Baseline-cost 95% block-bootstrap interval for mean daily return
            minus SPY: {pct(meanInterval[0])} to {pct(meanInterval[1])}.
            Conditional historical uncertainty, not independent proof.
          </p>
        )}
        <p>
          {String(
            validation.multiple_testing ??
              "Complete search history has not been established.",
          )}{" "}
          Recorded simulation variants (lower bound):{" "}
          {fmt(validation.recorded_variants_lower_bound, 0)}.
        </p>
        <ul>
          {[
            ...(Array.isArray(report.data_limitations)
              ? report.data_limitations
              : []),
            ...(Array.isArray(report.limitations) ? report.limitations : []),
          ].map((value, i) => (
            <li key={i}>{String(value)}</li>
          ))}
        </ul>
      </section>
      <details className="result-section">
        <summary>Explicit strategy policy and parameter stability</summary>
        <pre>{JSON.stringify(report.policy, null, 2)}</pre>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Nearby setting</th>
                <th>Net return</th>
                <th>Drawdown</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(obj(report.parameter_sensitivity)).map(
                ([name, value]) => (
                  <tr key={name}>
                    <td>{name.replaceAll("_", " ")}</td>
                    <td>{pct(obj(obj(value).net).total_return)}</td>
                    <td>{pct(obj(obj(value).net).maximum_drawdown)}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </details>
      <details className="result-section">
        <summary>Executed trade preview · baseline costs</summary>
        <p>
          First {rows(report.trade_preview).length} of{" "}
          {fmt(report.trade_count, 0)} fills. Download all CSV logs above.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Execution time</th>
                <th>Stock</th>
                <th>Side</th>
                <th>Quantity</th>
                <th>Fill price</th>
                <th>Commission</th>
              </tr>
            </thead>
            <tbody>
              {rows(report.trade_preview).map((trade, i) => (
                <tr key={i}>
                  <td>{String(trade.timestamp)}</td>
                  <td>{String(trade.symbol)}</td>
                  <td>{String(trade.side)}</td>
                  <td>{fmt(trade.quantity, 4)}</td>
                  <td>{usd(trade.price)}</td>
                  <td>{usd(trade.commission)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details className="result-section">
        <summary>Prediction diagnostics (supporting information)</summary>
        <pre>{JSON.stringify(report.prediction_diagnostics, null, 2)}</pre>
      </details>
    </div>
  );
}

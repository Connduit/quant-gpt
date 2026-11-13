import { useState } from "react";
import { request } from "./api";

export function StrategyEvaluation({
  sourceId,
  source,
  queued,
}: {
  sourceId: string;
  source: Record<string, unknown>;
  queued: (id: string) => void;
}) {
  const report = (source.report ?? {}) as Record<string, unknown>;
  const range = (source.research_range ?? {}) as Record<string, string>;
  const models = Object.keys(
    (report.predictive_performance ?? {}) as Record<string, unknown>,
  );
  const [values, setValues] = useState({
    source_job_id: sourceId,
    model: models[0] ?? "ridge",
    start: range.start ?? "",
    end: range.end ?? "",
    research_mode:
      report.research_mode === "exploratory" ? "exploratory" : "strict",
    initial_cash: 100000,
    top_n: 2,
    minimum_prediction: 0,
    probability_threshold: 0.55,
    volatility_adjusted: false,
    rebalance_sessions: 5,
    holding_sessions: 20,
    cash_allocation: 0.2,
    maximum_position_weight: 0.4,
    maximum_drawdown: 0.2,
    maximum_daily_loss: 0.05,
    minimum_dollar_volume: 1000000,
    whole_shares: true,
    commission_per_share: 0.005,
    spread_bps: 2,
    slippage_bps: 5,
    market_impact_bps: 1,
  });
  const [pending, setPending] = useState(false),
    [error, setError] = useState("");
  const numeric = (
    name: keyof typeof values,
    label: string,
    min: number,
    max: number,
    step = 1,
  ) => (
    <label key={name}>
      {label}
      <input
        type="number"
        required
        min={min}
        max={max}
        step={step}
        value={String(values[name])}
        onChange={(event) =>
          setValues({ ...values, [name]: Number(event.target.value) })
        }
      />
    </label>
  );
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const job = await request<{ id: string }>("/workflows/profitability", {
        method: "POST",
        body: JSON.stringify({ ...values, confirmed: true }),
      });
      queued(job.id);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <section
      className="result-section strategy-evaluation"
      aria-label="Evaluate saved ML strategy"
    >
      <h3>Evaluate strategy profitability</h3>
      <p>
        Turn this saved out-of-sample prediction run into next-open, long-only
        trades. Compare net returns with SPY, equal-weight, momentum, mean
        reversion and cash. Low and high costs are 0.5× and 2× your baseline
        assumptions. Final liquidation costs are included.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <div className="workflow-fields">
          <label>
            Strategy model
            <select
              aria-label="Strategy model"
              value={values.model}
              onChange={(e) => setValues({ ...values, model: e.target.value })}
            >
              {models.map((model) => (
                <option key={model}>{model}</option>
              ))}
            </select>
          </label>
          <label>
            Backtest evidence mode
            <select
              aria-label="Backtest evidence mode"
              value={values.research_mode}
              onChange={(e) =>
                setValues({ ...values, research_mode: e.target.value })
              }
            >
              <option value="strict">Strict evidence</option>
              <option value="exploratory">
                Exploratory backtest — incomplete evidence
              </option>
            </select>
          </label>
          <label>
            Backtest start date
            <input
              type="date"
              required
              min={range.start}
              max={values.end}
              value={values.start}
              onChange={(e) => setValues({ ...values, start: e.target.value })}
            />
          </label>
          <label>
            Backtest end date
            <input
              type="date"
              required
              min={values.start}
              max={range.end}
              value={values.end}
              onChange={(e) => setValues({ ...values, end: e.target.value })}
            />
          </label>
          {numeric(
            "initial_cash",
            "Starting capital (USD)",
            100,
            100000000,
            100,
          )}
          {numeric("top_n", "Strategy top holdings", 1, 11)}
          {values.model === "logistic"
            ? numeric(
                "probability_threshold",
                "Entry probability threshold",
                0,
                1,
                0.01,
              )
            : numeric(
                "minimum_prediction",
                "Minimum predicted excess return",
                -1,
                1,
                0.001,
              )}
          {numeric("rebalance_sessions", "Rebalance every (sessions)", 1, 126)}
          {numeric(
            "holding_sessions",
            "Maximum holding period (sessions)",
            1,
            252,
          )}
          {numeric("cash_allocation", "Cash reserve fraction", 0, 0.95, 0.01)}
          {numeric(
            "maximum_position_weight",
            "Maximum stock target weight fraction",
            0.01,
            1,
            0.01,
          )}
        </div>
        <label className="workflow-check">
          <input
            type="checkbox"
            checked={values.volatility_adjusted}
            onChange={(e) =>
              setValues({ ...values, volatility_adjusted: e.target.checked })
            }
          />
          Rank signals by prediction divided by known volatility
        </label>
        <label className="workflow-check">
          <input
            type="checkbox"
            checked={values.whole_shares}
            onChange={(e) =>
              setValues({ ...values, whole_shares: e.target.checked })
            }
          />
          Use whole-share orders
        </label>
        <details>
          <summary>Risk limits and baseline costs</summary>
          <div className="workflow-fields">
            {numeric(
              "maximum_drawdown",
              "Drawdown stop fraction",
              0.01,
              1,
              0.01,
            )}
            {numeric(
              "maximum_daily_loss",
              "Daily loss stop fraction",
              0.01,
              1,
              0.01,
            )}
            {numeric(
              "minimum_dollar_volume",
              "Minimum known dollar volume",
              0,
              1e12,
              100000,
            )}
            {numeric(
              "commission_per_share",
              "Commission per share (USD)",
              0,
              1,
              0.0005,
            )}
            {numeric("spread_bps", "Full bid/ask spread (bps)", 0, 100, 0.5)}
            {numeric("slippage_bps", "Slippage per fill (bps)", 0, 100, 0.5)}
            {numeric(
              "market_impact_bps",
              "Assumed impact per fill (bps)",
              0,
              100,
              0.5,
            )}
          </div>
        </details>
        <p className="warning-line">
          Exploratory results are not validated profitability. Missing action or
          membership evidence is disclosed, never certified. Raw executable
          prices are required. Saved runs containing protected 2019 data cannot
          be evaluated; train a physically separate permitted-date run.
        </p>
        <button disabled={pending || !models.length} type="submit">
          {pending ? "Submitting…" : "Evaluate strategy"}
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </section>
  );
}

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

type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as ObjectValue)
    : {};
const records = (value: unknown): ObjectValue[] =>
  Array.isArray(value) ? value.map(object) : [];
const finite = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;
const numeric = (value: unknown, digits = 2) => {
  const number = finite(value);
  return number === undefined
    ? "Not available"
    : number.toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
};
const percentage = (value: unknown) =>
  finite(value) === undefined
    ? "Not available"
    : `${numeric(Number(value) * 100, 1)}%`;
const points = (value: unknown) =>
  finite(value) === undefined
    ? "Not available"
    : `${numeric(Number(value) * 100)} pp`;
const date = (value: unknown) =>
  typeof value === "string" ? value.slice(0, 10) : "Not available";
const modelName = (name: string) =>
  ({
    ridge: "Ridge",
    logistic: "Logistic regression",
    random_forest: "Random Forest",
    lightgbm: "LightGBM",
    xgboost: "XGBoost",
  })[name] ?? name;

export function ResearchReport({ data }: { data: unknown }) {
  const root = object(data);
  const report = object(root.report ?? root);
  const dataset = object(report.dataset);
  const range = object(root.research_range);
  const request = object(root.request);
  const performance = object(report.predictive_performance);
  const models = Object.keys(performance);
  const [selection, setSelection] = useState("");
  const model = models.includes(selection) ? selection : models[0];
  const metrics = object(performance[model]);
  const classification =
    model === "logistic" ||
    String(metrics.error_target).includes("probability");
  const exploratory =
    report.research_mode === "exploratory" ||
    root.research_status === "EXPLORATORY_ML";
  const folds = records(report.folds);
  const snapshots = object(dataset.snapshots ?? dataset.snapshot_ids);
  const symbols = Object.keys(snapshots);
  const limitations = Array.isArray(report.limitations)
    ? report.limitations.filter((v): v is string => typeof v === "string")
    : [];
  const [chartMetric, setChartMetric] = useState("directional_accuracy");
  const chart = folds.map((fold, index) => {
    const result = object(object(fold.models)[model]);
    const validation = finite(object(result.validation)[chartMetric]);
    const evaluation = finite(object(result.out_of_sample)[chartMetric]);
    const multiplier = chartMetric === "directional_accuracy" ? 100 : 1;
    return {
      name: `Period ${index + 1}`,
      validation: validation === undefined ? null : validation * multiplier,
      evaluation: evaluation === undefined ? null : evaluation * multiplier,
    };
  });
  const outcomes = records(report.snapshots);
  const failed = typeof root.status === "string" && root.status !== "COMPLETED";
  const [importancePeriod, setImportancePeriod] = useState("");
  const importanceIndex =
    importancePeriod && Number(importancePeriod) < folds.length
      ? Number(importancePeriod)
      : folds.length - 1;
  const importance = object(
    object(object(folds[importanceIndex]).models)[model],
  ).feature_importance;
  const influential = Object.entries(object(importance))
    .filter(([, value]) => finite(value) !== undefined)
    .sort((a, b) => Math.abs(Number(b[1])) - Math.abs(Number(a[1])))
    .slice(0, 10);

  return (
    <div className="readable-report">
      <div className="result-intro">
        <div className="result-badges">
          <Badge text={String(root.status ?? "RESULTS")} />
          {exploratory && <Badge text="EXPLORATORY · PREDICTION ONLY" />}
        </div>
        <h3>
          {String(
            report.name ??
              (root.workflow === "download"
                ? "Historical data download"
                : "Research results"),
          )}
        </h3>
        {typeof root.reason === "string" && (
          <p className="warning-line">{root.reason}</p>
        )}
        {typeof root.note === "string" && <p>{root.note}</p>}
        {failed && !root.reason && (
          <p>
            Check the job details and per-symbol outcomes below for the reason
            this run did not complete.
          </p>
        )}
      </div>
      {models.length > 0 && (
        <>
          <dl className="result-context">
            <div>
              <dt>Research dates</dt>
              <dd>
                {date(dataset.start ?? range.start ?? request.start)} –{" "}
                {date(dataset.end ?? range.end ?? request.end)}
              </dd>
            </div>
            <div>
              <dt>Prediction horizon</dt>
              <dd>
                {numeric(dataset.horizon ?? request.horizon, 0)} trading
                sessions
              </dd>
            </div>
            <div>
              <dt>Stocks</dt>
              <dd>
                {symbols.filter((s) => s !== "SPY").join(", ") ||
                  "Not available"}
              </dd>
            </div>
            <div>
              <dt>Benchmark</dt>
              <dd>{symbols.includes("SPY") ? "SPY" : "Not available"}</dd>
            </div>
          </dl>
          <div className="result-model-picker">
            <label>
              Result model{" "}
              <select
                value={model}
                onChange={(event) => setSelection(event.target.value)}
              >
                {models.map((name) => (
                  <option key={name} value={name}>
                    {modelName(name)}
                  </option>
                ))}
              </select>
            </label>
            <p>
              Evaluation metrics use later data that was excluded from model
              fitting. They do not establish a trading edge.
            </p>
          </div>
          <div className="metrics result-metrics">
            <Metric
              label="Direction accuracy"
              value={percentage(metrics.directional_accuracy)}
              note="How often the model correctly predicted outperformance or underperformance versus SPY."
            />
            <Metric
              label={
                classification
                  ? "Probability error"
                  : "Average prediction error"
              }
              value={
                classification
                  ? numeric(metrics.mean_absolute_error, 3)
                  : points(metrics.mean_absolute_error)
              }
              note={
                classification
                  ? "Mean absolute error of predicted probabilities versus 0/1 outcomes. Lower is better."
                  : exploratory
                    ? "Mean absolute error in excess price change; pp means percentage points. Lower is better."
                    : "Mean absolute error in excess return; pp means percentage points. Lower is better."
              }
            />
            <Metric
              label="Stock ranking correlation"
              value={numeric(metrics.rank_information_coefficient, 3)}
              note="Average daily rank correlation. Positive means better ranking; 0 means no average relationship."
            />
            <Metric
              label="Evaluation samples"
              value={numeric(metrics.samples, 0)}
              note={`${numeric(metrics.rank_ic_sessions, 0)} sessions used for ranking. Samples are stock-date observations; overlapping targets are not independent.`}
            />
          </div>
          <div className="result-explanation">
            <h4>How to read these results</h4>
            <p>
              {finite(metrics.directional_accuracy) !== undefined
                ? `${modelName(model)} predicted the correct side of SPY's price change in ${percentage(metrics.directional_accuracy)} of evaluation samples.`
                : "Directional accuracy was not recorded for this model."}{" "}
              A result above 50% is not automatically an improvement: compare it
              with always predicting the more common outcome.
            </p>
            <p>
              {exploratory
                ? "The target is a stock's quoted price change minus SPY's over the prediction horizon, starting at the next eligible market open. It is not verified total return or portfolio profit."
                : "Prediction metrics describe forecasts. Any trading simulation results are separate from predictive accuracy."}{" "}
              {numeric(dataset.samples ?? dataset.rows, 0)} usable dataset
              samples include training and validation; the evaluation count
              above is the tested subset.
            </p>
            <p>
              Simple predictive baselines are not included in this report.
              Accuracy and prediction errors alone do not show improvement over
              a naive forecast.
            </p>
          </div>
          {models.length > 1 && (
            <section aria-label="Model comparison" className="result-section">
              <h4>Model comparison</h4>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Direction accuracy</th>
                      <th>Mean absolute error</th>
                      <th>Rank correlation</th>
                      <th>Samples</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((name) => {
                      const metric = object(performance[name]);
                      const probability =
                        name === "logistic" ||
                        String(metric.error_target).includes("probability");
                      return (
                        <tr key={name}>
                          <td>{modelName(name)}</td>
                          <td>{percentage(metric.directional_accuracy)}</td>
                          <td>
                            {probability
                              ? `${numeric(metric.mean_absolute_error, 3)} probability units`
                              : points(metric.mean_absolute_error)}
                          </td>
                          <td>
                            {numeric(metric.rank_information_coefficient, 3)}
                          </td>
                          <td>{numeric(metric.samples, 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="subtle">
                Probability errors and return errors use different units and
                should not be compared directly.
              </p>
            </section>
          )}
          {folds.length > 0 && (
            <section
              className="result-section"
              aria-label="Results by time period"
            >
              <div className="panel-title">
                <h4>Results by time period</h4>
                <label>
                  Chart metric{" "}
                  <select
                    aria-label="Chart metric"
                    value={chartMetric}
                    onChange={(event) => setChartMetric(event.target.value)}
                  >
                    <option value="directional_accuracy">
                      Direction accuracy
                    </option>
                    <option value="rank_information_coefficient">
                      Stock ranking correlation
                    </option>
                  </select>
                </label>
              </div>
              <p className="subtle">
                Each period is a chronological fold. Compare validation with
                later evaluation to check consistency. Scroll the table
                horizontally on smaller screens to see all metrics.
              </p>
              <div
                className="result-chart"
                role="img"
                aria-label={`${modelName(model)} validation and evaluation ${chartMetric === "directional_accuracy" ? "direction accuracy" : "ranking correlation"} by period; values are listed in the table below`}
              >
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart
                    data={chart}
                    margin={{ top: 12, right: 20, bottom: 10, left: 0 }}
                  >
                    <CartesianGrid stroke="#293649" vertical={false} />
                    <XAxis dataKey="name" stroke="#9aa8ba" />
                    <YAxis
                      stroke="#9aa8ba"
                      domain={
                        chartMetric === "directional_accuracy"
                          ? [0, 100]
                          : [-1, 1]
                      }
                      tickFormatter={(value) =>
                        chartMetric === "directional_accuracy"
                          ? `${value}%`
                          : String(value)
                      }
                    />
                    <Tooltip
                      formatter={(value) =>
                        chartMetric === "directional_accuracy"
                          ? `${numeric(value, 1)}%`
                          : numeric(value, 3)
                      }
                      contentStyle={{
                        background: "#152030",
                        borderColor: "#40536d",
                      }}
                    />
                    <Legend />
                    <Line
                      type="linear"
                      isAnimationActive={false}
                      dataKey="validation"
                      name="Validation"
                      stroke="#a899ef"
                      strokeWidth={2}
                      connectNulls={false}
                    />
                    <Line
                      type="linear"
                      isAnimationActive={false}
                      dataKey="evaluation"
                      name="Later evaluation"
                      stroke="#65c7dc"
                      strokeWidth={2}
                      connectNulls={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Evaluation dates</th>
                      <th>Samples</th>
                      <th>Validation accuracy</th>
                      <th>Evaluation accuracy</th>
                      <th>Evaluation error</th>
                      <th>Evaluation ranking</th>
                    </tr>
                  </thead>
                  <tbody>
                    {folds.map((fold, index) => {
                      const result = object(object(fold.models)[model]);
                      const validation = object(result.validation),
                        evaluation = object(result.out_of_sample);
                      return (
                        <tr key={index}>
                          <td>{index + 1}</td>
                          <td>
                            {date(fold.test_start)} – {date(fold.test_end)}
                          </td>
                          <td>
                            {numeric(evaluation.samples ?? fold.test_rows, 0)}
                          </td>
                          <td>{percentage(validation.directional_accuracy)}</td>
                          <td>{percentage(evaluation.directional_accuracy)}</td>
                          <td>
                            {classification
                              ? numeric(evaluation.mean_absolute_error, 3)
                              : points(evaluation.mean_absolute_error)}
                          </td>
                          <td>
                            {numeric(
                              evaluation.rank_information_coefficient,
                              3,
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {influential.length > 0 && (
            <details className="result-section result-importance">
              <summary>Which features influenced this model?</summary>
              <label>
                Feature importance period{" "}
                <select
                  value={importanceIndex}
                  onChange={(event) => setImportancePeriod(event.target.value)}
                >
                  {folds.map((_, index) => (
                    <option key={index} value={index}>
                      Period {index + 1}
                    </option>
                  ))}
                </select>
              </label>
              <p className="subtle">
                Top ten features by absolute reported importance for this
                period. Linear models show signed coefficients on standardized
                inputs; trees use importance scores. Correlated features can
                share or cancel importance. These values do not establish
                causation or profitability.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Feature</th>
                      <th>Reported value</th>
                      <th>Meaning</th>
                    </tr>
                  </thead>
                  <tbody>
                    {influential.map(([name, value]) => (
                      <tr key={name}>
                        <td>{name.replaceAll("_", " ")}</td>
                        <td>{numeric(value, 4)}</td>
                        <td>
                          {String(
                            object(dataset.feature_definitions)[name] ??
                              "Not recorded",
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          <section className="result-section" aria-label="Data and limitations">
            <h4>Data and limitations</h4>
            {exploratory && (
              <p className="warning-line">
                Prediction experiment only. No trading simulation, profitability
                claim, strategy qualification or deployment approval.
              </p>
            )}
            {symbols.length > 0 && (
              <p>
                Price basis:{" "}
                {[
                  ...new Set(
                    symbols.map((symbol) =>
                      String(
                        object(snapshots[symbol]).price_basis ?? "not recorded",
                      ),
                    ),
                  ),
                ].join(", ")}
                .
              </p>
            )}
            {limitations.length > 0 && (
              <ul>
                {limitations.map((limitation, index) => (
                  <li key={index}>{limitation}</li>
                ))}
              </ul>
            )}
            {Object.keys(object(dataset.large_close_price_changes)).length >
              0 && (
              <p>
                Large close-price changes (at least 40%):{" "}
                {Object.entries(object(dataset.large_close_price_changes))
                  .map(([symbol, count]) => `${symbol}: ${numeric(count, 0)}`)
                  .join(" · ")}
                . Zero does not certify that corporate-action records are
                complete.
              </p>
            )}
          </section>
        </>
      )}
      {outcomes.length > 0 && (
        <section className="result-section" aria-label="Download outcomes">
          <h4>Per-symbol outcomes</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {outcomes.map((outcome, index) => (
                  <tr key={index}>
                    <td>{String(outcome.symbol ?? "Unknown")}</td>
                    <td>
                      <Badge text={String(outcome.status ?? "UNKNOWN")} />
                    </td>
                    <td>{numeric(outcome.rows, 0)}</td>
                    <td>
                      {String(outcome.reason ?? outcome.price_basis ?? "")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {!models.length && !outcomes.length && !root.reason && (
        <p className="result-explanation">
          This report has no predictive metrics to summarize. Open the raw
          report below for detailed results.
        </p>
      )}
    </div>
  );
}

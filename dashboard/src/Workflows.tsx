import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "./api";
import { Badge, ErrorBox, JsonView } from "./components";
import { ResearchReport } from "./ResearchReport";
import { QuickDatasetDownload } from "./QuickDatasetDownload";
import { DEFAULT_EQUITY_SYMBOLS } from "./equityDefaults";
import { StrategyEvaluation } from "./StrategyEvaluation";
import { ProfitabilityReport } from "./ProfitabilityReport";

interface Snapshot {
  id: string;
  symbol: string;
  start: string;
  end: string;
  rows: number;
  retrieved_at?: string;
  provider: string;
  price_basis: string;
  eligible: boolean;
  blockers: string[];
  strict_blockers?: string[];
  dataset_role?: string;
}
interface Job {
  id: string;
  name: string;
  status: string;
  detail: string;
  created: string;
}
const modelNames = [
  "ridge",
  "logistic",
  "random_forest",
  "lightgbm",
  "xgboost",
];

function daysBefore(date: string, days: number) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
}

export function EquityWorkflows({ page }: { page: string }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const focusedJob = searchParams.get("job");
  const mode =
    page === "backtests"
      ? "backtest"
      : page === "datasets"
        ? "download"
        : page === "discovery"
          ? "discovery"
          : "training";
  const query = useQueryClient();
  const [symbols, setSymbols] = useState(DEFAULT_EQUITY_SYMBOLS);
  const [provider, setProvider] = useState("alpaca");
  const [feed, setFeed] = useState("sip");
  const [dataset, setDataset] = useState("XNAS.ITCH");
  const [cost, setCost] = useState(0);
  const latestCompletedDate = daysBefore(
    new Date().toISOString().slice(0, 10),
    1,
  );
  const [start, setStart] = useState(() =>
    daysBefore(latestCompletedDate, 365),
  );
  const [end, setEnd] = useState(latestCompletedDate);
  const [refresh, setRefresh] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [researchMode, setResearchMode] = useState("strict");
  const exploratory = mode === "training" && researchMode === "exploratory";
  const [researchStart, setResearchStart] = useState("");
  const [researchEnd, setResearchEnd] = useState("");
  const [models, setModels] = useState(["ridge"]);
  const [name, setName] = useState("Equity research");
  const [horizon, setHorizon] = useState(5);
  const [train, setTrain] = useState(504);
  const [validation, setValidation] = useState(126);
  const [test, setTest] = useState(126);
  const [top, setTop] = useState(1);
  const [trials, setTrials] = useState(4);
  const [seed, setSeed] = useState(42);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [reportId, setReportId] = useState("");
  const providers = useQuery({
    queryKey: ["historical-providers"],
    queryFn: () =>
      request<{
        items: {
          id: string;
          configured: boolean;
          host: string;
          required_secrets: string[];
        }[];
      }>("/workflows/providers"),
    refetchInterval: 15000,
  });
  const rangeQuery =
    mode !== "download" &&
    researchStart &&
    researchEnd &&
    researchStart <= researchEnd
      ? `?start=${researchStart}&end=${researchEnd}&research_mode=${exploratory ? "exploratory" : "strict"}`
      : exploratory
        ? "?research_mode=exploratory"
        : "";
  const inventory = useQuery({
    queryKey: ["workflow-snapshots", rangeQuery],
    placeholderData: (previous) => previous,
    queryFn: () =>
      request<{ items: Snapshot[]; errors: { id: string; error: string }[] }>(
        `/workflows/snapshots${rangeQuery}`,
      ),
    enabled: mode !== "backtest",
    refetchInterval: 5000,
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => request<{ items: Job[]; approved: string[] }>("/jobs"),
    refetchInterval: 3000,
  });
  useEffect(() => {
    if (mode !== "backtest" || !focusedJob || reportId === focusedJob) return;
    const job = jobs.data?.items.find(
      (item) =>
        item.id === focusedJob && item.name.startsWith("profitability-"),
    );
    if (job && !["QUEUED", "RUNNING"].includes(job.status)) void inspect(job);
  }, [mode, focusedJob, jobs.data, reportId]);
  const items = inventory.data?.items ?? [];
  const chosen = items.filter((s) => selected.includes(s.id));
  const readinessProblems: string[] = [];
  if (!chosen.length)
    readinessProblems.push(
      "Select training snapshots below, or click Use training snapshots.",
    );
  else {
    if (!chosen.some((s) => s.symbol === "SPY"))
      readinessProblems.push("Select a SPY benchmark snapshot.");
    if (!chosen.some((s) => s.symbol !== "SPY"))
      readinessProblems.push(
        "Select at least one stock snapshot in addition to SPY.",
      );
    if (new Set(chosen.map((s) => s.symbol)).size !== chosen.length)
      readinessProblems.push("Select only one snapshot per symbol.");
    chosen
      .filter((s) => !s.eligible)
      .forEach((s) =>
        readinessProblems.push(`${s.symbol}: ${s.blockers.join("; ")}`),
      );
    if (exploratory && new Set(chosen.map((s) => s.price_basis)).size > 1)
      readinessProblems.push(
        "Selected snapshots must use the same price basis.",
      );
    if (!researchStart || !researchEnd)
      readinessProblems.push("Choose both research dates.");
    else if (researchStart > researchEnd)
      readinessProblems.push(
        "Research start must be on or before research end.",
      );
    else if (chosen.some((s) => researchStart < s.start || researchEnd > s.end))
      readinessProblems.push(
        "Research dates must be covered by every selected snapshot. Use training snapshots to reset the range.",
      );
  }
  if (chosen.length > 12)
    readinessProblems.push("Select at most 12 snapshots.");
  if (!models.length) readinessProblems.push("Select at least one model.");
  const ready = readinessProblems.length === 0 && !inventory.error;
  async function useTrainingSnapshots() {
    setMessage("");
    try {
      const data = await request<{ items: Snapshot[] }>(
        `/workflows/snapshots?research_mode=${exploratory ? "exploratory" : "strict"}`,
      );
      const candidates = data.items
        .filter((s) => s.eligible && s.dataset_role !== "protected_test")
        .sort(
          (a, b) =>
            Number(b.dataset_role === "training") -
              Number(a.dataset_role === "training") ||
            (b.retrieved_at ?? "").localeCompare(a.retrieved_at ?? ""),
        );
      const benchmark = candidates.find((s) => s.symbol === "SPY");
      if (!benchmark)
        throw new Error(
          "No eligible SPY training snapshot. Download a training pair in Data library, or inspect the SPY row's blocker below.",
        );
      const bySymbol = new Map<string, Snapshot>();
      bySymbol.set("SPY", benchmark);
      candidates
        .filter(
          (s) =>
            s.price_basis === benchmark.price_basis &&
            s.start <= benchmark.end &&
            s.end >= benchmark.start,
        )
        .forEach((s) => {
          if (!bySymbol.has(s.symbol) && bySymbol.size < 12)
            bySymbol.set(s.symbol, s);
        });
      const snapshots = [...bySymbol.values()];
      const first = snapshots
        .map((s) => s.start)
        .sort()
        .at(-1)!;
      const last = snapshots.map((s) => s.end).sort()[0];
      if (snapshots.length < 2 || first > last)
        throw new Error(
          "No shared training range for SPY and a stock. Select compatible snapshots below or download a training pair.",
        );
      setSelected(snapshots.map((s) => s.id));
      setResearchStart(first);
      setResearchEnd(last);
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  const toggle = (values: string[], value: string) =>
    values.includes(value)
      ? values.filter((v) => v !== value)
      : [...values, value];

  function selectSnapshot(id: string) {
    const next = toggle(selected, id);
    setSelected(next);
    const snapshots = items.filter((s) => next.includes(s.id));
    if (!snapshots.length) return;
    const first = snapshots
      .map((s) => s.start)
      .sort()
      .at(-1)!;
    const last = snapshots.map((s) => s.end).sort()[0];
    setResearchStart((current) =>
      current && current >= first && current <= last ? current : first,
    );
    setResearchEnd((current) =>
      current && current <= last && current >= first ? current : last,
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage("");
    try {
      const body =
        mode === "download"
          ? {
              provider,
              alpaca_feed: feed,
              databento_dataset: dataset,
              maximum_download_cost: provider === "databento" ? cost : 0,
              symbols: symbols.split(/[\s,]+/).filter(Boolean),
              start,
              end,
              refresh,
              confirmed: true,
            }
          : {
              workflow: mode,
              research_mode: exploratory ? "exploratory" : "strict",
              name,
              snapshot_ids: selected,
              start: researchStart,
              end: researchEnd,
              models,
              horizon,
              training_sessions: train,
              validation_sessions: validation,
              test_sessions: test,
              top_n: top,
              max_trials: trials,
              seed,
              confirmed: true,
            };
      const job = await request<{ id: string }>(
        `/workflows/${mode === "download" ? "download" : "research"}`,
        {
          method: "POST",
          body: JSON.stringify(body),
        },
      );
      setMessage(`Queued ${job.id}. Follow its progress below.`);
      await query.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  async function inspect(job: Job) {
    try {
      const data = await request<{ result: Record<string, unknown> | null }>(
        `/workflows/jobs/${job.id}`,
      );
      setReport(data.result);
      setReportId(job.id);
      if (!data.result)
        setMessage(
          "Report is not available yet. Check the job status and try again.",
        );
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  async function cancel(job: Job) {
    try {
      await request(`/jobs/${job.id}/cancel`, {
        method: "POST",
        body: JSON.stringify({ name: job.name, confirmed: true }),
      });
      setMessage("Cancellation requested.");
      await jobs.refetch();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `equity-${reportId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  const workflowJobs = (jobs.data?.items ?? []).filter((j) =>
    mode === "backtest"
      ? j.name.startsWith("profitability-")
      : /^(download|download_pair|training|discovery)-/.test(j.name),
  );
  return (
    <>
      {mode === "download" && (
        <QuickDatasetDownload
          latest={latestCompletedDate}
          queued={(id) => {
            setMessage(`Queued ${id}. Follow both dataset downloads below.`);
            void query.invalidateQueries({ queryKey: ["jobs"] });
          }}
        />
      )}
      {mode !== "backtest" && (
        <>
          <section className="panel equity-workflow">
            <h3>
              {mode === "download"
                ? "Download historical data & create snapshots"
                : mode === "discovery"
                  ? "Start equity discovery"
                  : "Train equity ML models"}
            </h3>
            <p className="subtle">
              Researcher access required. Downloads support completed historical
              dates. Downloads can include dates after 2018. Training and
              discovery use only the selected research date range; dates outside
              it are excluded before features, labels or models are computed.
            </p>
            <form onSubmit={(event) => void submit(event)}>
              {mode === "download" ? (
                <>
                  <div className="workflow-fields">
                    <label>
                      Historical data provider
                      <select
                        value={provider}
                        onChange={(e) => {
                          setProvider(e.target.value);
                          setStart(
                            e.target.value === "databento"
                              ? daysBefore(end, 30)
                              : daysBefore(end, 365),
                          );
                        }}
                      >
                        <option value="alpaca">Alpaca</option>
                        <option value="databento">Databento</option>
                      </select>
                    </label>
                    {provider === "alpaca" ? (
                      <label>
                        Alpaca feed
                        <select
                          value={feed}
                          onChange={(e) => setFeed(e.target.value)}
                        >
                          <option value="sip">SIP — consolidated</option>
                          <option value="iex">IEX — single venue</option>
                        </select>
                      </label>
                    ) : (
                      <>
                        <label>
                          Databento dataset
                          <select
                            value={dataset}
                            onChange={(e) => setDataset(e.target.value)}
                          >
                            <option value="XNAS.ITCH">
                              XNAS.ITCH — Nasdaq venue
                            </option>
                            <option value="DBEQ.BASIC">
                              DBEQ.BASIC — check historical coverage
                            </option>
                          </select>
                        </label>
                        <label>
                          Maximum estimated download cost (USD)
                          <input
                            type="number"
                            min={0}
                            max={100}
                            step="0.01"
                            required
                            value={cost}
                            onChange={(e) => setCost(Number(e.target.value))}
                          />
                        </label>
                      </>
                    )}
                    <label>
                      US equity symbols
                      <input
                        required
                        value={symbols}
                        onChange={(e) => setSymbols(e.target.value)}
                        placeholder={DEFAULT_EQUITY_SYMBOLS}
                      />
                    </label>
                    <label>
                      Start date
                      <input
                        required
                        type="date"
                        min="1990-01-01"
                        max={end}
                        value={start}
                        onChange={(e) => setStart(e.target.value)}
                      />
                    </label>
                    <label>
                      End date
                      <input
                        required
                        type="date"
                        min={start}
                        max={latestCompletedDate}
                        value={end}
                        onChange={(e) => setEnd(e.target.value)}
                      />
                    </label>
                  </div>
                  <p className="subtle">
                    Download through {latestCompletedDate}. Today and future
                    dates are unavailable; weekends and exchange holidays have
                    no bars.
                  </p>
                  <label className="workflow-check">
                    <input
                      type="checkbox"
                      checked={refresh}
                      onChange={(e) => setRefresh(e.target.checked)}
                    />
                    Fetch a fresh version instead of reusing an exact cached
                    request
                  </label>
                  <p className="subtle">
                    Raw minute bars aggregated over regular XNYS sessions. Up to
                    12 symbols; Alpaca permits ten years per request, Databento
                    31 calendar days. Downloads are validated before immutable
                    snapshots are saved. Existing versions are preserved.
                  </p>
                  {providers.error ? (
                    <ErrorBox error={providers.error} />
                  ) : (
                    providers.data?.items
                      ?.filter((p) => p.id === provider)
                      .map((p) => (
                        <p key={p.id} className="subtle">
                          {p.configured
                            ? "Server credentials configured; access and entitlements are verified when downloading."
                            : `API keys required: ${p.required_secrets.join(", ")}.`}{" "}
                          Data host: {p.host}.{" "}
                          <Link
                            to="/provider-settings"
                            className="provider-settings-link"
                          >
                            Manage API keys
                          </Link>
                        </p>
                      ))
                  )}
                  {provider === "databento" && (
                    <p className="warning-line">
                      The cost limit applies across all symbols in this job.
                      Zero permits only zero-cost estimates. Estimates are
                      checked before each stream; final vendor billing may
                      differ. Dataset dates must be completed historical dates.
                    </p>
                  )}
                  <button type="submit" disabled={pending}>
                    {pending ? "Submitting…" : "Download & create snapshots"}
                  </button>
                </>
              ) : (
                <>
                  {mode === "training" && (
                    <label>
                      Research mode
                      <select
                        value={researchMode}
                        onChange={(e) => {
                          setResearchMode(e.target.value);
                          setSelected([]);
                        }}
                      >
                        <option value="strict">Strict research</option>
                        <option value="exploratory">
                          Exploratory ML — prediction only
                        </option>
                      </select>
                    </label>
                  )}
                  {exploratory && (
                    <p className="warning-line">
                      Exploratory ML accepts downloaded prices without
                      corporate-action or historical-membership evidence. Splits
                      and dividends can distort features and targets, and a
                      fixed stock list can introduce selection bias. Reports
                      contain prediction metrics only, with no portfolio
                      backtest, strategy qualification or deployment approval.
                    </p>
                  )}
                  <div className="workflow-fields">
                    <label>
                      Run name
                      <input
                        required
                        pattern="[a-zA-Z0-9 _-]+"
                        minLength={3}
                        maxLength={80}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </label>
                    <label>
                      Research start date
                      <input
                        type="date"
                        required
                        value={researchStart}
                        max={researchEnd || latestCompletedDate}
                        onChange={(e) => setResearchStart(e.target.value)}
                      />
                    </label>
                    <label>
                      Research end date
                      <input
                        type="date"
                        required
                        value={researchEnd}
                        min={researchStart}
                        max={latestCompletedDate}
                        onChange={(e) => setResearchEnd(e.target.value)}
                      />
                    </label>
                    <label>
                      Prediction horizon
                      <select
                        value={horizon}
                        onChange={(e) => setHorizon(Number(e.target.value))}
                      >
                        {[1, 5, 10].map((n) => (
                          <option key={n} value={n}>
                            {n} sessions
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Training sessions
                      <input
                        type="number"
                        min={60}
                        max={1500}
                        required
                        value={train}
                        onChange={(e) => setTrain(Number(e.target.value))}
                      />
                    </label>
                    <label>
                      Validation sessions
                      <input
                        type="number"
                        min={20}
                        max={252}
                        required
                        value={validation}
                        onChange={(e) => setValidation(Number(e.target.value))}
                      />
                    </label>
                    <label>
                      Evaluation sessions per fold
                      <input
                        type="number"
                        min={20}
                        max={252}
                        required
                        value={test}
                        onChange={(e) => setTest(Number(e.target.value))}
                      />
                    </label>
                    {!exploratory && (
                      <label>
                        Top holdings
                        <input
                          type="number"
                          min={1}
                          max={10}
                          required
                          value={top}
                          onChange={(e) => setTop(Number(e.target.value))}
                        />
                      </label>
                    )}
                    <label>
                      Random seed
                      <input
                        type="number"
                        min={0}
                        max={4294967295}
                        required
                        value={seed}
                        onChange={(e) => setSeed(Number(e.target.value))}
                      />
                    </label>
                    {mode === "discovery" && (
                      <label>
                        Maximum search trials
                        <input
                          type="number"
                          min={1}
                          max={8}
                          required
                          value={trials}
                          onChange={(e) => setTrials(Number(e.target.value))}
                        />
                      </label>
                    )}
                  </div>
                  <fieldset>
                    <legend>Models</legend>
                    <div className="workflow-models">
                      {modelNames.map((model) => (
                        <label key={model} className="workflow-check">
                          <input
                            type="checkbox"
                            checked={models.includes(model)}
                            onChange={() => setModels(toggle(models, model))}
                          />
                          {model.replaceAll("_", " ")}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <p>
                    Select one eligible snapshot per equity and a SPY benchmark
                    below, covering the research date range. Snapshots may
                    contain earlier or later dates; the dashboard extracts only
                    the requested range.
                  </p>
                  <p className="subtle">
                    Training, validation and evaluation folds stay inside the
                    research range. Later snapshot data is excluded from this
                    run; this does not certify an untouched holdout or release a
                    Phase 12 holdout. Purged chronological folds · CPU only · at
                    most eight folds.
                    {!exploratory && (
                      <>
                        {" "}
                        Fixed costs (0.5¢/share, 5 bps slippage, 2 bps spread).
                        Discovery searches momentum/reversion features and
                        bounded model parameters, including doubled-cost checks.
                      </>
                    )}
                  </p>
                  <button
                    type="button"
                    onClick={() => void useTrainingSnapshots()}
                    disabled={pending || inventory.isFetching}
                  >
                    Use training snapshots
                  </button>
                  {inventory.isFetching && (
                    <p role="status">Checking snapshot eligibility…</p>
                  )}
                  {!!readinessProblems.length && (
                    <ul
                      aria-label="Training requirements"
                      className="warning-line"
                    >
                      {readinessProblems.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  )}
                  {!ready && !exploratory && (
                    <p className="warning-line">
                      {exploratory
                        ? "Select one downloaded snapshot per stock plus SPY, choose a covered research date range, and select a model. A declared price basis is required."
                        : "Eligible raw-price snapshots with complete actions and point-in-time membership are required. Price downloads alone do not supply this evidence. For price-only experiments, use Exploratory ML in Machine learning."}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={pending || !ready || !models.length}
                  >
                    {pending
                      ? "Submitting…"
                      : mode === "discovery"
                        ? "Start bounded discovery"
                        : exploratory
                          ? "Start exploratory ML"
                          : "Start ML training"}
                  </button>
                </>
              )}
            </form>
            <p role="status" aria-live="polite">
              {message}
            </p>
          </section>
          <section className="panel">
            <div className="panel-title">
              <h3>Historical snapshot library</h3>
              <button onClick={() => void inventory.refetch()}>
                Refresh snapshots
              </button>
            </div>
            {inventory.error ? (
              <ErrorBox error={inventory.error} />
            ) : inventory.isPending ? (
              <p>Loading snapshots…</p>
            ) : (
              <>
                {!items.length && (
                  <p className="empty">
                    No historical snapshots yet. Download data from the Data
                    library to get started.
                  </p>
                )}
                {!!items.length && (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {mode !== "download" && <th>Select</th>}
                          <th>Symbol</th>
                          <th>Coverage</th>
                          <th>Rows</th>
                          <th>Price basis</th>
                          <th>Research eligibility</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((s) => (
                          <tr key={s.id}>
                            {mode !== "download" && (
                              <td>
                                <input
                                  type="checkbox"
                                  aria-label={`Select ${s.symbol} ${s.id.slice(0, 8)}`}
                                  disabled={!s.eligible}
                                  checked={selected.includes(s.id)}
                                  onChange={() => selectSnapshot(s.id)}
                                />
                              </td>
                            )}
                            <td>
                              <strong>{s.symbol}</strong>
                              {s.dataset_role &&
                                s.dataset_role !== "research" && (
                                  <small className="snapshot-id">
                                    {s.dataset_role === "protected_test"
                                      ? "Protected test · sealed"
                                      : "Training snapshot"}
                                  </small>
                                )}
                              <small className="snapshot-id" title={s.id}>
                                {s.id.slice(0, 12)}…
                              </small>
                            </td>
                            <td>
                              {s.start} – {s.end}
                            </td>
                            <td>{s.rows.toLocaleString()}</td>
                            <td>
                              {s.price_basis}
                              <small className="snapshot-id">
                                {s.provider}
                              </small>
                            </td>
                            <td>
                              <Badge
                                text={
                                  s.dataset_role === "protected_test"
                                    ? "PROTECTED TEST"
                                    : s.eligible
                                      ? exploratory
                                        ? "EXPLORATORY"
                                        : "ELIGIBLE"
                                      : "BLOCKED_DATA"
                                }
                              />
                              {exploratory &&
                                s.eligible &&
                                s.strict_blockers?.map((reason) => (
                                  <small
                                    className="snapshot-id"
                                    key={`limitation-${reason}`}
                                  >
                                    Strict research limitation: {reason}
                                  </small>
                                ))}
                              {s.blockers.map((reason) => (
                                <small className="snapshot-id" key={reason}>
                                  {reason}
                                </small>
                              ))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {inventory.data?.errors?.map((e) => (
                  <p className="warning-line" key={e.id}>
                    {e.id.slice(0, 12)}: {e.error}
                  </p>
                ))}
              </>
            )}
          </section>
        </>
      )}
      <section className="panel">
        <h3>
          {mode === "backtest"
            ? "ML strategy backtests"
            : "Equity workflow jobs"}
        </h3>
        {mode === "backtest" && (
          <>
            <p>
              Profitability evaluations are backtests of saved ML predictions,
              including trading costs and benchmark comparisons. Start one from
              a completed training report in{" "}
              <Link to="/models">Machine learning</Link>.
            </p>
            <p role="status" aria-live="polite">
              {message ||
                (focusedJob &&
                ["QUEUED", "RUNNING"].includes(
                  jobs.data?.items.find((job) => job.id === focusedJob)
                    ?.status ?? "",
                )
                  ? "Backtest in progress. You can cancel it below; the report opens when it finishes."
                  : "")}
            </p>
          </>
        )}
        {jobs.error ? (
          <ErrorBox error={jobs.error} />
        ) : !workflowJobs.length ? (
          <p className="empty">
            {mode === "backtest"
              ? "No ML strategy backtests submitted yet."
              : "No equity workflows submitted yet."}
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Workflow</th>
                  <th>Status</th>
                  <th>Details</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {workflowJobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      {job.name.split("-")[0]}
                      <small className="snapshot-id">
                        {job.id.slice(0, 12)}
                      </small>
                    </td>
                    <td>
                      <Badge text={job.status} />
                    </td>
                    <td>{job.detail}</td>
                    <td>
                      {["QUEUED", "RUNNING"].includes(job.status) ? (
                        <button onClick={() => void cancel(job)}>Cancel</button>
                      ) : (
                        <button
                          onClick={() => {
                            if (mode === "backtest")
                              navigate(
                                `/backtests?job=${encodeURIComponent(job.id)}`,
                              );
                            else void inspect(job);
                          }}
                        >
                          View report
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {report && (
          <div className="workflow-report">
            <div className="panel-title">
              <h4>Workflow report</h4>
              <button onClick={download}>Download report JSON</button>
            </div>
            {report.workflow === "profitability" ? (
              <ProfitabilityReport data={report} identity={reportId} />
            ) : (
              <>
                {report.workflow === "training" &&
                  report.status === "COMPLETED" && (
                    <StrategyEvaluation
                      key={reportId}
                      sourceId={reportId}
                      source={report}
                      queued={(id) => {
                        void query.invalidateQueries({ queryKey: ["jobs"] });
                        navigate(`/backtests?job=${encodeURIComponent(id)}`);
                      }}
                    />
                  )}
                <ResearchReport data={report} />
              </>
            )}
            <JsonView data={report} label="Raw report JSON" />
          </div>
        )}
      </section>
    </>
  );
}

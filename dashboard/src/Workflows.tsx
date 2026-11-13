import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "./api";
import { Badge, ErrorBox, JsonView } from "./components";

interface Snapshot {
  id: string;
  symbol: string;
  start: string;
  end: string;
  rows: number;
  provider: string;
  price_basis: string;
  eligible: boolean;
  blockers: string[];
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
  const mode =
    page === "datasets"
      ? "download"
      : page === "discovery"
        ? "discovery"
        : "training";
  const query = useQueryClient();
  const [symbols, setSymbols] = useState("AAPL, MSFT, SPY");
  const [provider, setProvider] = useState("alpaca");
  const [feed, setFeed] = useState("sip");
  const [dataset, setDataset] = useState("XNAS.ITCH");
  const [cost, setCost] = useState(0);
  const latestCompletedDate = daysBefore(new Date().toISOString().slice(0, 10), 1);
  const [start, setStart] = useState(() => daysBefore(latestCompletedDate, 365));
  const [end, setEnd] = useState(latestCompletedDate);
  const [refresh, setRefresh] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
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
  const inventory = useQuery({
    queryKey: ["workflow-snapshots"],
    queryFn: () =>
      request<{ items: Snapshot[]; errors: { id: string; error: string }[] }>(
        "/workflows/snapshots",
      ),
    refetchInterval: 5000,
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => request<{ items: Job[]; approved: string[] }>("/jobs"),
    refetchInterval: 3000,
  });
  const items = inventory.data?.items ?? [];
  const chosen = items.filter((s) => selected.includes(s.id));
  const ready =
    chosen.length >= 2 &&
    chosen.every((s) => s.eligible) &&
    chosen.some((s) => s.symbol === "SPY") &&
    new Set(chosen.map((s) => s.symbol)).size === chosen.length;
  const toggle = (values: string[], value: string) =>
    values.includes(value)
      ? values.filter((v) => v !== value)
      : [...values, value];

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
              name,
              snapshot_ids: selected,
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
    /^(download|training|discovery)-/.test(j.name),
  );
  return (
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
          Researcher access required. Downloads support completed historical dates.
          Downloads can include dates after 2018. Training and discovery currently
          require snapshots ending by December 31, 2018 to preserve the reserved
          holdout.
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
                    placeholder="AAPL, MSFT, SPY"
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
                Download through {latestCompletedDate}. Today and future dates
                are unavailable; weekends and exchange holidays have no bars.
              </p>
              <label className="workflow-check">
                <input
                  type="checkbox"
                  checked={refresh}
                  onChange={(e) => setRefresh(e.target.checked)}
                />
                Fetch a fresh version instead of reusing an exact cached request
              </label>
              <p className="subtle">
                Raw minute bars aggregated over regular XNYS sessions. Up to 12
                symbols; Alpaca permits ten years per request, Databento 31
                calendar days. Downloads are validated before immutable
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
                  The cost limit applies across all symbols in this job. Zero
                  permits only zero-cost estimates. Estimates are checked before
                  each stream; final vendor billing may differ. Dataset dates
                  must be completed historical dates.
                </p>
              )}
              <button type="submit" disabled={pending}>
                {pending ? "Submitting…" : "Download & create snapshots"}
              </button>
            </>
          ) : (
            <>
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
                below, with identical date coverage.
              </p>
              <p className="subtle">
                Purged chronological folds · fixed costs (0.5¢/share, 5 bps
                slippage, 2 bps spread) · CPU only · at most eight folds.
                Discovery searches momentum/reversion features and bounded model
                parameters, including doubled-cost checks.
              </p>
              {!ready && (
                <p className="warning-line">
                  Eligible raw-price snapshots with complete actions and
                  point-in-time membership are required. Price downloads alone
                  do not supply this evidence.
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
                No historical snapshots yet. Download data from the Data library
                to get started.
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
                              onChange={() =>
                                setSelected(toggle(selected, s.id))
                              }
                            />
                          </td>
                        )}
                        <td>
                          <strong>{s.symbol}</strong>
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
                          <small className="snapshot-id">{s.provider}</small>
                        </td>
                        <td>
                          <Badge
                            text={s.eligible ? "ELIGIBLE" : "BLOCKED_DATA"}
                          />
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
      <section className="panel">
        <h3>Equity workflow jobs</h3>
        {jobs.error ? (
          <ErrorBox error={jobs.error} />
        ) : !workflowJobs.length ? (
          <p className="empty">No equity workflows submitted yet.</p>
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
                      <button onClick={() => void inspect(job)}>
                        View report
                      </button>
                      {["QUEUED", "RUNNING"].includes(job.status) && (
                        <button onClick={() => void cancel(job)}>Cancel</button>
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
            <JsonView data={report} />
          </div>
        )}
      </section>
    </>
  );
}

import React, { useEffect, useState } from "react";
import { NavLink, Routes, Route, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  FlaskConical,
  Database,
  Layers,
  BrainCircuit,
  ChartNoAxesCombined,
  ShieldCheck,
  Radio,
  Settings,
  PanelLeft,
  Download,
  RefreshCw,
  LockKeyhole,
} from "lucide-react";
import {
  request,
  listArtifacts,
  setToken,
  downloadReport,
  downloadCSV,
  monitorUpdates,
  type ArtifactKind,
  type Health,
  type Detail,
  type Artifact,
} from "./api";
import { Badge, Metric, Curve, JsonView, Table, ErrorBox } from "./components";
import "./style.css";
import { EquityWorkflows } from "./Workflows";
import { ProviderSettings } from "./ProviderSettings";
const pages: [string, string, React.ElementType][] = [
  ["", "Overview", Activity],
  ["datasets", "Data library", Database],
  ["provider-settings", "API keys", LockKeyhole],
  ["research", "Research", FlaskConical],
  ["models", "Machine learning", BrainCircuit],
  ["discovery", "Discovery", ChartNoAxesCombined],
  ["validation", "Validation", ShieldCheck],
  ["backtests", "Backtests", ChartNoAxesCombined],
  ["portfolios", "Portfolios", Layers],
  ["paper", "Paper execution", Radio],
  ["agent", "Research agent", BrainCircuit],
  ["live", "Live readiness", LockKeyhole],
  ["system", "System health", Settings],
];
export function App() {
  const [menu, setMenu] = useState(false);
  const [token, setAuth] = useState("");
  const [connection, setConnection] = useState(0);
  const q = useQueryClient();
  useEffect(() => {
    const abort = new AbortController();
    void monitorUpdates(() => {
      void q.invalidateQueries();
    }, abort.signal).catch(() => {
      /* polling remains available */
    });
    const timer = setInterval(
      () => void q.invalidateQueries({ queryKey: ["health"] }),
      15000,
    );
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [q, connection]);
  return (
    <div className="app">
      <aside className={menu ? "open" : ""}>
        <div className="brand">
          <span className="brand-mark">Q</span>
          <div>
            QUANT LAB<small>RESEARCH WORKSPACE</small>
          </div>
        </div>
        <div className="workspace">
          <span className="dot" /> Local research <Badge text="SIMULATED" />
        </div>
        <nav aria-label="Main navigation">
          {pages.map(([path, label, Icon]) => (
            <NavLink
              key={path}
              to={"/" + path}
              end={path === ""}
              onClick={() => setMenu(false)}
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <LockKeyhole size={15} /> Live execution disabled
          <small>Research results are not deployment approval.</small>
        </div>
      </aside>
      <div className="main">
        <header>
          <button
            className="mobile-menu"
            aria-label="Toggle navigation"
            onClick={() => setMenu(!menu)}
          >
            <PanelLeft />
          </button>
          <span className="breadcrumb">
            WORKSPACE <span>/</span> QUANT RESEARCH LAB
          </span>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setToken(token);
              setConnection((c) => c + 1);
              void q.invalidateQueries();
            }}
          >
            <input
              type="password"
              aria-label="API access token"
              value={token}
              onChange={(e) => setAuth(e.target.value)}
              placeholder="Access token (optional locally)"
              autoComplete="off"
            />
            <button type="submit">Connect</button>
          </form>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/system" element={<System />} />
            <Route path="/provider-settings" element={<ProviderSettings />} />
            <Route path="/:kind" element={<Artifacts />} />
          </Routes>
        </main>
        <footer>
          QUANT RESEARCH LAB{" "}
          <span>
            Holdouts protected · Simulated execution · No automatic promotion
          </span>
        </footer>
      </div>
    </div>
  );
}
function Heading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <Badge text="RESEARCH ENVIRONMENT" />
    </div>
  );
}
function Overview() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => request<Health>("/health"),
  });
  const artifacts = useQuery({
    queryKey: ["overview"],
    queryFn: () =>
      request<{ items: Artifact[]; paper: Detail | null }>("/overview"),
  });
  if (health.error)
    return (
      <ErrorBox error={health.error} retry={() => void health.refetch()} />
    );
  const h = health.data;
  const paper = artifacts.data?.paper;
  const account = paper?.data.account as Record<string, unknown> | undefined;
  return (
    <>
      <Heading
        eyebrow="WORKSPACE OVERVIEW"
        title="Research, with evidence."
        description="Inspect experiments, validation and simulated execution in one place."
      />
      <div className="notice">
        <ShieldCheck size={19} />
        <div>
          <strong>No strategy is approved for live trading.</strong>
          <span>
            Historical research and replay results remain separate from
            real-time paper evidence.
          </span>
        </div>
      </div>
      <div className="metrics">
        <Metric
          label="Selected replay equity"
          value={
            account
              ? Number(account.equity).toLocaleString("en-US", {
                  style: "currency",
                  currency: "USD",
                })
              : "Unavailable"
          }
          note="Experimental historical replay only"
        />
        <Metric
          label="Eligible strategies"
          value={String(h?.eligible_strategies ?? "—")}
          note="Validated + explicitly approved"
        />
        <Metric
          label="Streaming verification"
          value={h?.streaming_verified ? "Verified" : "Unverified"}
          note="Credentials / entitlements unavailable"
        />
        <Metric
          label="Execution mode"
          value="SIMULATED"
          note="Real-money execution disabled"
        />
      </div>
      <div className="overview-grid">
        <Curve
          points={paper?.series ?? []}
          title="Experimental replay · selected account"
        />
        <section className="panel">
          <div className="panel-title">
            <h3>Research guardrails</h3>
            <Badge text="ENFORCED" />
          </div>
          <ul className="guardrails">
            <li>
              <span>Final holdout</span>
              <Badge text={h?.holdout_state ?? "UNKNOWN"} />
            </li>
            <li>
              <span>Strategy promotion</span>
              <span>Human approval required</span>
            </li>
            <li>
              <span>External streaming</span>
              <Badge text="UNVERIFIED" />
            </li>
            <li>
              <span>Live orders</span>
              <Badge text="DISABLED" />
            </li>
          </ul>
          <p className="subtle">
            A running process does not establish healthy data, statistical
            validity or trading readiness.
          </p>
        </section>
      </div>
      <section className="panel">
        <div className="panel-title">
          <h3>Recent research artifacts</h3>
          <span className="subtle">
            Stored results, including rejected candidates
          </span>
        </div>
        {artifacts.isPending ? (
          <p className="empty">Loading research artifacts…</p>
        ) : artifacts.error ? (
          <ErrorBox error={artifacts.error} />
        ) : (
          <ArtifactRows items={artifacts.data?.items ?? []} />
        )}
      </section>
      {h && <Warnings warnings={h.warnings} />}
    </>
  );
}
function ArtifactRows({
  items,
  onSelect,
}: {
  items: Artifact[];
  onSelect?: (id: string) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Artifact</th>
            <th>Category</th>
            <th>Data / execution</th>
            <th>Status</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              <td>
                {onSelect ? (
                  <button
                    className="text-button"
                    onClick={() => onSelect(a.id)}
                  >
                    {a.label}
                  </button>
                ) : (
                  <NavLink to={"/" + a.kind}>{a.label}</NavLink>
                )}
              </td>
              <td>{a.kind}</td>
              <td>
                <Badge text={a.mode} />
              </td>
              <td>
                <Badge text={a.status} />
              </td>
              <td>{new Date(a.updated_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && <p className="empty">No artifacts match this view.</p>}
    </div>
  );
}
function Artifacts() {
  const { kind = "research" } = useParams();
  const title = pages.find((p) => p[0] === kind)?.[1] ?? "Research artifacts";
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [comparison, setComparison] = useState<string[]>([]);
  const data = useQuery({
    queryKey: ["artifacts", kind, search, offset],
    queryFn: () => listArtifacts(kind, search, offset),
  });
  useEffect(() => {
    setSelected(null);
    setComparison([]);
    setOffset(0);
    setSearch("");
  }, [kind]);
  return (
    <>
      <Heading
        eyebrow="EVIDENCE LIBRARY"
        title={title}
        description="Inspect stored artifacts, provenance, limitations and rejection reasons."
      />
      {kind === "live" && (
        <div className="notice danger">
          <LockKeyhole />
          <div>
            <strong>Real-money execution remains disabled.</strong>
            <span>No live order-entry controls are available.</span>
          </div>
        </div>
      )}
      {kind === "live" && <LiveReadiness />}
      {["datasets", "research", "models", "discovery"].includes(kind) && (
        <EquityWorkflows key={kind} page={kind} />
      )}
      <section className="panel">
        <div className="panel-title">
          <h3>Saved {title.toLowerCase()}</h3>
          <input
            aria-label="Search artifacts"
            placeholder="Search name or status…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </div>
        {data.isPending ? (
          <p className="empty">Loading artifacts…</p>
        ) : data.error ? (
          <ErrorBox error={data.error} retry={() => void data.refetch()} />
        ) : (
          <>
            <ArtifactRows
              items={data.data.items}
              onSelect={(id) => {
                setSelected(id);
                setComparison((c) =>
                  c.includes(id) ? c : [...c.slice(-1), id],
                );
              }}
            />
            <div className="pagination">
              <span>{data.data.total} matching artifacts</span>
              <button
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Previous
              </button>
              <button
                disabled={offset + 20 >= data.data.total}
                onClick={() => setOffset(offset + 20)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
      {comparison.length === 2 && <Compare ids={comparison} />}
      <ArtifactDetail id={selected} kind={kind as ArtifactKind} />
      {kind === "discovery" && <Jobs />}
      {kind === "agent" && <AgentSessions />}
    </>
  );
}
function Compare({ ids }: { ids: string[] }) {
  const d = useQuery({
    queryKey: ["compare", ...ids],
    queryFn: () =>
      request<{ items: Artifact[] }>("/compare?ids=" + ids.join(",")),
  });
  return (
    <section className="panel">
      <h3>Selected artifact comparison</h3>
      {d.data ? (
        <Table
          rows={d.data.items.map((x) => ({
            artifact: x.label,
            mode: x.mode,
            status: x.status,
            ...x.summary,
          }))}
        />
      ) : d.error ? (
        <ErrorBox error={d.error} />
      ) : (
        <p>Loading comparison…</p>
      )}
    </section>
  );
}
function ArtifactDetail({
  id,
  kind,
}: {
  id: string | null;
  kind: ArtifactKind;
}) {
  const detail = useQuery({
    queryKey: ["detail", id],
    queryFn: () => request<Detail>("/artifacts/" + id),
    enabled: !!id,
  });
  if (!id)
    return (
      <p className="empty">
        Select an artifact to inspect its measured results.
      </p>
    );
  if (detail.error) return <ErrorBox error={detail.error} />;
  if (!detail.data) return <p className="empty">Loading artifact details…</p>;
  const d = detail.data;
  const lists = [
    "results",
    "candidates",
    "strategies",
    "orders",
    "fills",
    "predictions",
    "alerts",
    "trial_history",
    "rejected_or_failed",
    "failed",
    "windows",
  ];
  return (
    <>
      <section className="panel">
        <div className="panel-title">
          <h3>{d.record.label}</h3>
          <div className="controls">
            <button onClick={() => void downloadReport(id)}>
              <Download size={14} /> Export JSON
            </button>
            {Array.isArray(d.data.fills) && (
              <button
                onClick={() =>
                  downloadCSV(
                    id + "-fills",
                    d.data.fills as Record<string, unknown>[],
                  )
                }
              >
                Export fills CSV
              </button>
            )}
          </div>
        </div>
        <div className="tags">
          <Badge text={d.record.mode} />
          <Badge text={d.record.status} />
        </div>
        <Table rows={[d.record.summary]} />
      </section>
      <Curve points={d.series} />
      {d.series.length > 1 && (
        <section className="panel">
          <h3>Observed-window monthly changes</h3>
          <p className="subtle">
            First month may be partial; no annualized profitability inference.
          </p>
          <Table rows={monthlyReturns(d.series)} />
        </section>
      )}
      {kind === "portfolios" && <PortfolioAnalytics data={d.data} />}

      {kind === "paper" && <PaperControls accountId={id} />}
      <section className="panel">
        <h3>Evidence and diagnostics</h3>
        {d.data.feature_importance &&
        typeof d.data.feature_importance === "object" ? (
          <>
            <h3>Recorded feature importance</h3>
            <Table
              rows={Object.entries(
                d.data.feature_importance as Record<string, unknown>,
              ).map(([feature, value]) => ({ feature, value }))}
            />
            <p className="subtle">
              Descriptive model coefficients / importance; not causal effects or
              profitability evidence.
            </p>
          </>
        ) : null}
        {d.data.predictive && typeof d.data.predictive === "object" ? (
          <Table rows={[d.data.predictive as Record<string, unknown>]} />
        ) : null}

        {lists
          .filter((k) => Array.isArray(d.data[k]))
          .map((k) => (
            <details key={k}>
              <summary>
                {k.replaceAll("_", " ")} · {(d.data[k] as unknown[]).length}
              </summary>
              <Table
                rows={(d.data[k] as unknown[]).map((x) =>
                  typeof x === "object" && x !== null
                    ? (x as Record<string, unknown>)
                    : { value: x },
                )}
              />
            </details>
          ))}
        <JsonView
          data={d.data}
          label="Full artifact · configuration, metrics and limitations"
        />
      </section>
    </>
  );
}
function PaperControls({ accountId }: { accountId: string }) {
  const [reason, setReason] = useState("");
  const [strategy, setStrategy] = useState("");
  const [message, setMessage] = useState("");
  async function control(action: string) {
    if (!reason.trim()) {
      setMessage("An operator reason is required.");
      return;
    }
    if (
      !window.confirm(
        `Queue simulated ${action}? This changes only the selected paper account.`,
      )
    )
      return;
    try {
      await request("/paper/" + accountId + "/control", {
        method: "POST",
        body: JSON.stringify({
          action,
          strategy: strategy || null,
          reason,
          confirmed: true,
        }),
      });
      setMessage("Control queued. The account writer must apply and audit it.");
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <section className="panel">
      <h3>Authorized paper-only controls</h3>
      <p className="subtle">
        Operator authentication and confirmation required. RESEARCH strategies
        cannot be promoted here.
      </p>
      <div className="controls">
        <input
          aria-label="Strategy ID"
          placeholder="Strategy ID (for pause/resume/stop)"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
        />
        <input
          aria-label="Operator reason"
          placeholder="Operator reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        {["resume", "pause", "stop", "kill"].map((a) => (
          <button
            key={a}
            className={a === "kill" ? "danger-button" : ""}
            onClick={() => void control(a)}
          >
            {a === "resume" ? "Start / resume" : a}
          </button>
        ))}
      </div>
      <p role="status">{message}</p>
    </section>
  );
}
function Jobs() {
  const [message, setMessage] = useState("");
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () =>
      request<{ items: Record<string, unknown>[]; approved: string[] }>(
        "/jobs",
      ),
    refetchInterval: 5000,
  });
  async function launch(name: string) {
    if (
      !window.confirm(
        "Launch this approved bounded research job? Holdout restrictions remain enforced.",
      )
    )
      return;
    try {
      await request("/jobs", {
        method: "POST",
        body: JSON.stringify({ name, confirmed: true }),
      });
      setMessage("Research job queued.");
      void jobs.refetch();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <section className="panel">
      <h3>Controlled research jobs</h3>
      <p className="subtle">
        Researcher authorization required; only server-approved configurations.
      </p>
      {jobs.error ? (
        <ErrorBox error={jobs.error} />
      ) : (
        <>
          <Table rows={jobs.data?.items ?? []} />
          <div className="controls">
            {jobs.data?.approved.map((n) => (
              <button key={n} onClick={() => void launch(n)}>
                Run {n}
              </button>
            ))}
          </div>
        </>
      )}
      <p role="status">{message}</p>
    </section>
  );
}
function Warnings({ warnings }: { warnings: string[] }) {
  return (
    <section className="panel">
      <h3>Operational limitations</h3>
      {warnings.map((w) => (
        <p className="warning-line" key={w}>
          {w}
        </p>
      ))}
    </section>
  );
}
function System() {
  const h = useQuery({
    queryKey: ["health"],
    queryFn: () => request<Health>("/health"),
    refetchInterval: 15000,
  });
  return (
    <>
      <Heading
        eyebrow="OPERATIONS"
        title="System health"
        description="Data readiness, risk state and errors—not process uptime alone."
      />
      <button onClick={() => void h.refetch()}>
        <RefreshCw size={14} /> Refresh status
      </button>
      {h.error ? (
        <ErrorBox error={h.error} />
      ) : h.data ? (
        <>
          <div className="metrics">
            <Metric
              label="Readiness"
              value={h.data.status}
              note="Observed capability limitations"
            />
            <Metric
              label="Paper accounts"
              value={String(h.data.paper_accounts)}
              note="Cataloged simulated accounts"
            />
            <Metric
              label="Streaming"
              value="UNVERIFIED"
              note="No successful authenticated live observation"
            />
            <Metric
              label="Live execution"
              value="DISABLED"
              note="No authorized strategy or live orders"
            />
          </div>
          <Warnings warnings={[...h.data.warnings, ...h.data.catalog_errors]} />
          <section className="panel">
            <h3>Research job status</h3>
            <Table rows={h.data.jobs} />
          </section>
        </>
      ) : (
        <p className="empty">Checking system evidence…</p>
      )}
    </>
  );
}

function monthlyReturns(points: { at: string; equity: number }[]) {
  const ends = new Map<string, number>();
  for (const p of points) ends.set(p.at.slice(0, 7), p.equity);
  let previous = points[0].equity;
  return [...ends].map(([month, equity]) => {
    const change = previous > 0 ? equity / previous - 1 : null;
    previous = equity;
    return { month, ending_equity: equity, observed_return: change };
  });
}
function PortfolioAnalytics({ data }: { data: Record<string, unknown> }) {
  const runs = (data.runs ?? {}) as Record<string, Record<string, unknown>>;
  const names = Object.keys(runs);
  const [selected, setSelected] = useState(names[0] ?? "");
  const run = runs[selected];
  if (!run) return null;
  const d = (run.diversification ?? {}) as Record<string, unknown>;
  const matrix = (d.correlation ?? []) as number[][];
  const namesOfStrategies = (
    (data.strategies ?? []) as Record<string, unknown>[]
  ).map((x) => String(x.name));
  return (
    <section className="panel">
      <div className="panel-title">
        <h3>Portfolio risk and attribution</h3>
        <select
          aria-label="Portfolio allocation method"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {names.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </div>
      <Table
        rows={[
          {
            allocation: selected,
            ...(run.performance as Record<string, unknown>),
          },
        ]}
      />
      <h3>Recorded strategy return correlations</h3>
      <Table
        rows={matrix.map((row, i) =>
          Object.fromEntries([
            ["strategy", namesOfStrategies[i] ?? i],
            ...row.map((v, j) => [namesOfStrategies[j] ?? j, v]),
          ]),
        )}
      />
      <h3>Recorded risk contributions</h3>
      <Table
        rows={((d.risk_contributions ?? []) as number[]).map((value, i) => ({
          strategy: namesOfStrategies[i] ?? i,
          risk_contribution: value,
        }))}
      />
      <JsonView
        data={run.strategy_pnl}
        label="Per-strategy P&L and attribution"
      />
      <JsonView data={run.risk_decision_counts} label="Risk decisions" />
    </section>
  );
}

function AgentSessions() {
  const data = useQuery({
    queryKey: ["agent-sessions"],
    queryFn: () =>
      request<{ items: Record<string, unknown>[] }>("/agent/sessions"),
    refetchInterval: 3000,
  });
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [objective, setObjective] = useState(
    "Evaluate bounded ES momentum after costs with chronological validation.",
  );
  const [message, setMessage] = useState("");
  const detail = useQuery({
    queryKey: ["agent-session", selected],
    queryFn: () =>
      request<Record<string, unknown>>("/agent/sessions/" + selected),
    enabled: !!selected,
    refetchInterval: 3000,
  });
  async function start() {
    if (
      !window.confirm(
        "Start a bounded SCRIPTED engineering workflow? This does not verify a real LLM or authorize trading.",
      )
    )
      return;
    try {
      await request("/agent/sessions", {
        method: "POST",
        body: JSON.stringify({
          name: "scripted-agent-engineering",
          objective,
          confirmed: true,
        }),
      });
      setMessage(
        "Research worker queued; all policy and budget gates remain active.",
      );
      void data.refetch();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  async function control(action: string) {
    if (!selected || !reason.trim()) {
      setMessage("Select a session and provide an operator reason.");
      return;
    }
    if (!window.confirm(`Record research ${action}?`)) return;
    try {
      await request("/agent/sessions/" + selected + "/control", {
        method: "POST",
        body: JSON.stringify({ action, reason, confirmed: true }),
      });
      setMessage(
        "Control recorded. Inspect worker status for acknowledgement.",
      );
      void data.refetch();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <section className="panel">
      <h3>Bounded research agent</h3>
      <p className="subtle">
        Current demonstration uses a scripted planner, not verified LLM
        reasoning. No trading, holdout, arbitrary-code or promotion permissions.
      </p>
      <div className="controls">
        <input
          aria-label="Research objective"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          maxLength={1200}
        />
        <button onClick={() => void start()}>Start scripted research</button>
      </div>
      {data.error ? (
        <ErrorBox error={data.error} />
      ) : (
        <Table rows={data.data?.items ?? []} />
      )}
      <div className="controls">
        <select
          aria-label="Research session"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Select session</option>
          {data.data?.items.map((s) => (
            <option key={String(s.id)} value={String(s.id)}>
              {String(s.id).slice(0, 12)} · {String(s.status)}
            </option>
          ))}
        </select>
        <input
          aria-label="Research control reason"
          placeholder="Operator reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        {["pause", "resume", "cancel", "emergency_stop"].map((a) => (
          <button key={a} onClick={() => void control(a)}>
            {a.replaceAll("_", " ")}
          </button>
        ))}
      </div>
      <p role="status">{message}</p>
      {detail.data && (
        <JsonView
          data={detail.data}
          label="Actual hypotheses, iterations, usage and findings"
        />
      )}
    </section>
  );
}

function LiveReadiness() {
  const data = useQuery({
    queryKey: ["execution-readiness"],
    queryFn: () =>
      request<{
        status: string;
        live_enabled: boolean;
        checks: Record<string, unknown>[];
        limits: string[];
      }>("/execution/readiness"),
    refetchInterval: 15000,
  });
  return (
    <section className="panel">
      <div className="panel-title">
        <h3>Go-live readiness</h3>
        <Badge text={data.data?.status ?? "CHECKING"} />
      </div>
      {data.error ? (
        <ErrorBox error={data.error} />
      ) : data.data ? (
        <>
          <Table rows={data.data.checks} />
          <Warnings warnings={data.data.limits} />
        </>
      ) : (
        <p className="empty">Checking recorded readiness evidence…</p>
      )}
      <p className="subtle">
        Read-only monitoring. No live order entry, activation, liquidation or
        strategy-promotion controls.
      </p>
    </section>
  );
}

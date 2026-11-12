# Dashboard operation

The [guided historical-data and equity workflows](dashboard-workflows.md) add
download/snapshot forms, ML training, bounded discovery, cancellation and job reports.
They retain researcher authorization, data eligibility and holdout protections.

The [full request](milestone-9-instructions.md) and [architecture plan](dashboard-architecture.md)
are saved. The dashboard uses React/TypeScript/Vite, React Router, TanStack Query,
Recharts and a FastAPI v1 API. Its [browser screenshot](dashboard-overview.png)
shows actual saved research/replay artifacts, not favorable demonstration fixtures.

## Start locally

```bash
uv sync --frozen --all-extras
npm --prefix dashboard ci
npm --prefix dashboard run build
uv run --frozen --all-extras quantlab dashboard --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. For development, run
`npm --prefix dashboard run dev -- --port 5173` and open that address; Vite proxies
`/api` to the local backend. Production serves the compiled frontend from FastAPI,
including browser-route refreshes. Python 3.12+ and Node 20.19+/22.12+ are required.
The repository lockfiles pin the verified Python/npm resolutions.

The [catalog](../configs/dashboard.catalog.yaml) explicitly lists reviewed JSON
reports, optional equity/benchmark CSV paths and simulated-account databases.
It does not search arbitrary filesystem paths or expose raw holdout data. Missing
artifacts appear as unavailable and health warnings; no synthetic fallback occurs.
Review/update catalog entries after creating new run directories. `data/` is
ignored, so a fresh clone must reproduce or provide the intended local artifacts.

## Views and evidence

Overview, dataset provenance, experiments, model analytics, discovery, validation,
backtests, portfolios, paper execution, agent artifacts, live readiness and system
health use the same typed artifact/detail protocol. Search, pagination, sorting,
side-by-side selected summaries, JSON export and paper-fill CSV export are available.
Full report inspection preserves parameters, features, predictive diagnostics,
fold dates, rejections, robustness, statistical uncertainty and coverage limitations.
Unavailable fields stay null/empty rather than invented. Short-sample annualized
metrics in legacy artifacts remain inspectable but do not establish significance.

Equity/drawdown/exposure charts use measured observations. The portfolio backtest
adds its recorded SPY equity benchmark. Intraday labels use US Eastern time.
Research, development backtest, archival data, experimental replay and unavailable
live capabilities have distinct labels. No aggregate combines simulated and actual
broker returns. Current model analytics include genuine standardized ridge
coefficients and recorded prediction/drift distributions, extracted offline using
the version-matching installed 0.8 wheel. APIs do not deserialize model files.

Paper views read a consistent SQLite snapshot, verify it against the journal's
last-state checksum and reconstruct the existing ledgers without taking over the
writer. They therefore reflect persisted orders/positions/kill state rather than
only an old report export. Missing/corrupt account state is not healthy. The final
holdout badge reads only ledger states, never protected bars/results. Health stays
LIMITED: no streaming verification, no eligible strategy and no live capability.
SSE refresh notices trigger cache updates; polling is retained if streaming fails.
These are monitoring refresh notices, not claims of live market observations.

## Authentication and writes

Default loopback access is read-only. Nonlocal hosting requires configured tokens:
`QUANTLAB_VIEWER_TOKEN`, `QUANTLAB_OPERATOR_TOKEN`, and/or
`QUANTLAB_RESEARCHER_TOKEN`. Each must be distinct and at least 24 characters;
store values in environment settings/managed secrets, never in Git or frontend
build variables. The UI accepts a bearer token into memory only. It never places
tokens in URLs, persistent browser storage or report exports.

Use the supported CLI `--host` option; it configures authentication requirements
before binding. If running the ASGI factory directly, set `QUANTLAB_BIND_HOST`
to the actual bind interface as well. Put any remote deployment behind reviewed
TLS, authentication and reverse-proxy configuration; do not expose an unauthenticated
loopback development proxy publicly. CORS is not wildcard-enabled. API responses
use no-store, no-sniff, no-referrer and frame-denial headers. React escapes report
text. CSV formula prefixes are escaped.

Only the operator role can enqueue confirmed paper pause/resume/stop/kill requests.
A reason is required. Resume rejects unvalidated/RESEARCH deployments. Responses
say queued, not applied; the single account writer must process and audit them.
No automatic strategy approval, model replacement or live order endpoint exists.

Only researchers can submit/cancel named, server-approved jobs. No shell, uploaded
Python, arbitrary SQL, arbitrary paths or user-supplied commands are accepted.
Jobs run outside HTTP handlers in one worker lane with a two-job queue, outer wall
time, existing CPU/memory/trial budgets and a minimal environment excluding broker
credentials. Reviewed configuration content is pinned at server startup; changes
require re-review/restart. All trial history, holdout isolation and rejections remain
in the underlying research framework. A restart marks uncertain work
RECOVERY_REQUIRED and blocks new launches until an operator reconciles retained
workers/artifacts. It never blindly retries. No such recovery was needed in this
verification. The initial agent view is an extension point; Milestone 10 implements
the actual bounded agent workflow.

## Tests

```bash
uv run --frozen --all-extras pytest -q
npm --prefix dashboard run test -- --environment jsdom
# With backend :8000 and frontend :5173 running:
cd dashboard
CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

Frontend unit tests mock API responses. API integration tests use actual saved
artifacts and durable test account databases. Browser tests use the real backend,
real reports and system Chromium, checking charts, rejected trials, models,
unauthorized controls, SSE/errors and mobile navigation. They submit no real orders.

Limitations: this is a single-machine operator UI, not a multi-tenant identity
platform. Tokens require external rotation/secret management. Advanced analytics
remain inspectable in full reports where a dedicated chart is not provided.
External feeds/brokers, production TLS/hosting and qualified paper strategies are
not verified by rendering a dashboard. Live controls stay unavailable.

Optional offline model analytics export (trusted artifacts only):

```bash
uv run --frozen --all-extras python examples/model_analytics.py \
  --model data/paper/NEW_RUN/model --report data/paper/NEW_RUN/report.json \
  --output data/paper/NEW_RUN/model-analytics.json
```

Run this in the exact environment/version that created the model; incompatible
versions fail closed. The original 0.8 artifact was exported using its installed
0.8 wheel. Newly reproduced experiments use their current package version.

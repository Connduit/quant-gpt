# Dashboard architecture and security plan

Implementation follows the [complete Milestone 9 request](milestone-9-instructions.md).
The existing application has CLI/research stores but no web API to preserve.
FastAPI will read a curated, operator-configured catalog of existing JSON artifacts
and paper SQLite accounts. It will not recursively expose the data directory,
reserved holdout bars, model deserialization, arbitrary paths, shell or credentials.

The React/TypeScript/Vite frontend uses React Router, TanStack Query, reusable
accessible tables, charts, loading/error/empty states, and dark default styling.
It separates research/backtest/replay/paper/live labels. Missing metrics remain
unavailable rather than made-up chart data. Drill-down JSON preserves available
parameters, feature importance, folds, rejection reasons and artifact provenance.

Versioned typed REST endpoints provide bounded pagination/filter/sort and curated
artifact detail/export. SSE supplies monitoring refresh notices. Local read access
is allowed only on loopback; nonlocal reads require bearer authentication. Operator
and researcher roles separately authorize confirmed paper controls and approved
bounded jobs. No frontend credential is embedded in the bundle. Same-origin
production and a Vite development proxy avoid permissive CORS configuration.

Long-running jobs run in separate bounded processes from a fixed server allowlist.
Client input selects an approved job name, never a path/command. Job storage and
restart recovery are durable. Research processes receive a minimal environment
without broker credentials; their existing sealed data and resource controls apply.
Paper controls enqueue audited actions for the single account writer; the API
reports queued versus applied status honestly. Live controls remain unavailable.

The end-to-end demonstration will use actual saved M4–M8 artifacts. Streaming,
external brokers and qualified strategies remain unavailable and must be shown
as such, including stale/replay state rather than green process-only health.

# Production-oriented deployment and operator procedures

**Real-money execution remains disabled.** These artifacts are reviewable initial
single-machine infrastructure, not a verified live deployment. See
[architecture](controlled-execution.md) and [readiness](go-live-readiness.md).

## Credentials, isolation and authentication

Use managed environment secrets or a protected operator environment file. Never
commit values, put them in frontend build variables, or expose them to research:

- `QUANTLAB_ALPACA_PAPER_KEY`, `QUANTLAB_ALPACA_PAPER_SECRET`: PAPER broker only.
- `QUANTLAB_SANDBOX_AUTHORIZATION_KEY`: separate private key, at least 32 bytes.
- `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`: reviewed market-data access/entitlements.
- `QUANTLAB_VIEWER_TOKEN`, `QUANTLAB_OPERATOR_TOKEN`: distinct 24+ character API roles.

The example file contains names only. Paper and live keys are never interchangeable;
there are no live credential variables or live broker path in the adapter. Rotate
keys in the secret manager; restart suspended, verify the exact account, and issue
new reviewed signatures. Rotation invalidates old authorizations. Back up private
authorization material separately using protected/encrypted secret storage.

Research workers receive a minimal environment without broker keys/API operator
tokens. Generated code is quarantined text, never executed.

## Build and start locally

Install Python 3.12+, uv, and Node.js with npm. From the repository root:

```bash
python build.py
python start.py
```

Create `.env` using `.env.example` as a template and set distinct
viewer, operator, and researcher tokens plus your provider credentials. Keep the
file private and out of Git. Open http://127.0.0.1:8000 and enter the appropriate
token. Existing shell variables take precedence over `.env` values.

After Python changes, restart the dashboard. After frontend changes, rerun
`npm run build` in `dashboard/` and restart. After dependency changes, rerun
`uv sync --frozen --all-extras` or `npm ci` as appropriate. After `.env` edits,
restart so the process loads the new settings.

Local state and research artifacts remain under `data/`. Back up these files
and secrets separately. The dashboard binds to loopback by default. The broker
sandbox is started separately and requires its own configuration, credentials,
and signed approval. Starting the dashboard does not start the broker service.
The optional `deploy/quantlab-paper.service` is a Linux systemd example for paper
simulation; it is not needed for local dashboard use.

## Explicit PAPER sandbox engineering test

Use a clean sandbox account, the exact account ID, official market-data entitlements
and current reviewed strategy definition. Obtain a signed approval:

```bash
uv run --env-file .env --frozen --all-extras quantlab execution approve-sandbox-test \
  --execution-config configs/OPERATOR_SANDBOX.yaml --actor OPERATOR_ID \
  --reason 'reviewed bounded PAPER test' --minutes 15 --output data/execution/reviewed-approval.json
uv run --env-file .env --frozen --all-extras quantlab execution service \
  --execution-config configs/OPERATOR_SANDBOX.yaml --arm-approved-sandbox-test
```

This can submit a **PAPER sandbox** order only after all gates pass; it is not a
research-qualified strategy deployment. It supports one durable fixed-target test
signal with 1–10 allowed equity shares. It never infers eligibility from mock or
historical P&L. A restarted account will not auto-arm. Explicit reviewed resume
requires the extra resume flag/reason plus fresh reconciliation/data; the old stable
signal cannot be submitted again. Changes to strategy/risk/code require a reviewed
state migration/new approval rather than silent parameter replacement.

Read-only external verification is opt-in with `QUANTLAB_LIVE_BROKER=1`, separate
PAPER keys, `QUANTLAB_PAPER_ACCOUNT_ID` and the private authorization key. The test
reads account/positions/orders and submits no orders. Current credentials and
permissions are missing, so external verification remains blocked.

## Backup and recovery

Use the SQLite backup API through `execution backup`, including during WAL writes.
The manifest records a checksum and that credentials/private signing keys are
excluded. Store encrypted off-machine copies and authorization secrets separately.
Test restore into a **new** destination; existing files are never overwritten.

```bash
uv run --env-file .env --frozen --all-extras quantlab execution restore \
  --database data/execution/verified-backup.sqlite --output data/execution/NEW_RESTORE.sqlite
```

Restart verifies journal/state integrity, rebuilds financial accounting and remains
suspended. Reconcile actual broker cash/positions/orders/executions, obtain a new
valid observation and explicitly review arming. Never delete a journal to make an
uncertain order disappear, regenerate an ID to retry it, or assume missing means
rejected. Resolve the broker order by stable client ID. Restore alone is not
permission to trade. Key/source changes invalidate old approvals.

## Remaining production risks

External broker/feed/fee behavior is unverified. Non-fill cash activities,
corporate actions, existing-account imports, late-fill reconstruction, coverage
caps, extreme market gaps, long-duration reliability, independent review,
regulatory/tax/operator preparation and qualified real-time paper evidence remain
open. Tokens are a single-operator initial mechanism, not an enterprise identity
system. No real-money capital, strategy activation or emergency liquidation is
authorized. Completing engineering tests does not guarantee profitability.

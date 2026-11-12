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
tokens. Generated code is quarantined text, never executed. The default Docker API
service has no broker or researcher credentials; the optional broker service has a
separate state volume and no published order-entry port. External identity/TLS,
host access controls and adversarial sandboxing require independent operator review.
No verified generated-code OS sandbox exists, so execution remains unavailable.

## Build and start

```bash
# Trust a managed proxy using a read-only public CA secret, never disabled TLS.
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f deploy/Dockerfile -t quantlab:0.11.0 .
# Supply a real viewer token through environment settings/protected local file.
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml up -d dashboard
```

In managed Cloud, add `-f deploy/compose.cloud.yaml` to mount the combined CA at
runtime. BuildKit uses the CA only during networked RUN steps; it is not copied
into image layers. Keep inherited proxy configuration. Do not use host networking,
TLS bypasses or alternate proxies to evade restrictions. The current attached
instance still blocks the requested market/broker hosts; see connectivity evidence.

The image runs as UID/GID 10001 with pinned Python/npm lockfiles. Compose applies a
read-only root filesystem, dropped capabilities, no-new-privileges, process/memory/
CPU limits, persistent state volumes, safe shutdown, restart policies and an
authenticated API liveness check. Liveness is not trading readiness: the dashboard
must continue to show LIMITED/NOT_READY evidence. The API binds on container
0.0.0.0 with authentication and publishes only host loopback. Remote use needs a
reviewed TLS reverse proxy and firewall; do not publicly expose a dev proxy.

Bind-mounted research reports are read-only. Named paper/dashboard/execution
volumes are separate. Existing artifacts must be migrated deliberately with correct
ownership for UID 10001; missing/mis-permissioned artifacts show unavailable, never
fake values. Do not copy credentials or raw reserved holdouts into the image.
`data/`, keys, environment files, caches and Git metadata are excluded from builds.

No broker container starts by default. The `sandbox` profile requires a reviewed
`deploy/operator-execution.yaml`, separate credentials and signed approval. Its
command is monitoring-only. No live service exists. Research loops do not
start automatically or restart indefinitely on completion. Review resources,
network destinations, software source SHA and risk settings before deployment.

## Explicit PAPER sandbox engineering test

Use a clean sandbox account, the exact account ID, official market-data entitlements
and current reviewed strategy definition. Obtain a signed approval:

```bash
uv run --frozen --all-extras quantlab execution approve-sandbox-test \
  --execution-config configs/OPERATOR_SANDBOX.yaml --actor OPERATOR_ID \
  --reason 'reviewed bounded PAPER test' --minutes 15 --output data/execution/reviewed-approval.json
uv run --frozen --all-extras quantlab execution service \
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
uv run --frozen --all-extras quantlab execution restore \
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

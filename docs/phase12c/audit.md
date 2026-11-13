# Phase 12C pipeline audit

Baseline before edits: `pytest -q`: **363 passed, 11 skipped**, 633 dependency warnings,
164.97 seconds. No live integration was requested by this check.

Reused: immutable CSV/Parquet snapshots; recorded `available_at`; saved out-of-sample
predictions with training-label, model-availability and execution timestamps; per-fold
model hashes; causal ranking strategies; shared decimal cash accounting; next-open
market fills; split/reverse-split and dividend receivables; risk sizing/limits;
benchmark reporting; bounded, registered Optuna searches; purging/embargo and the
statistical bootstrap/FDR/holdout-vault implementations.

Gaps: dashboard exploratory fitting deliberately has no trading simulation; no
server-side saved-job-to-execution action; predictions need per-row clock, model
artifact, source and content-hash checks; terminal liquidation, impact decomposition,
calendar-period/regime reporting and profitability-first presentation are incomplete.
Existing discovery already backtests after costs, but predictive skill can contribute
to ranking and positive absolute net returns are not an unconditional acceptance gate.

No retained `data/` library or saved prediction job exists in this checkout. A pasted
report is not a prediction artifact. The demonstration must create a fresh bounded
pre-2019 data/prediction run if valid provider observations are available. The canonical
2019 equity and 2013-10-14 futures holdouts are excluded; no vault authorization,
evaluation, release, promotion, broker order or live trading is permitted.

Symbol changes, terminal delisting payouts, historical membership and independent
corporate-event certification are absent from downloaded OHLCV. Such evidence is not
invented. Lifecycle-marked data the adapter cannot account for must fail closed.
Raw execution prices only; adjusted research snapshots cannot be replayed as cash
execution prices. An explicit exploratory simulation may report missing action/universe
evidence, but cannot certify validated profitability. Empty unknown event coverage is
marked incomplete, never a complete assertion that no events occurred.

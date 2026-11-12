# Additional real-data demonstration requirements

The user supplied these requirements during Milestone 4:

1. Inspect existing storage, manifests and research YAML; reuse suitable snapshots.
2. Automatically retrieve missing real historical equities/SPY data through the provider infrastructure.
3. Prefer approximately 10–20 liquid US stocks across sectors, plus SPY, with at least five years of daily OHLCV where available.
4. Verify unadjusted price semantics and corporate-action coverage rather than assuming sufficiency.
5. If complete ledgers are unavailable, identify missing coverage and use a supported, explicitly documented alternative. Do not fabricate records or silently assume no actions; do not claim full corporate-action awareness.
6. Generate reproducible research YAML identifying symbols, snapshots, periods, search spaces and validation settings.
7. Preserve an untouched final holdout; use earlier periods for training, validation and discovery.
8. Run a manageable real-data discovery demonstration and report snapshot IDs, configurations, sources, limitations, results and tests.
9. Do not wait for manually supplied IDs unless retrieval cannot work or requires credentials/a paid subscription.
10. Continue Milestone 4, without automatically beginning Milestone 5.

Implementation and observed data limitations are documented in [discovery](discovery.md).

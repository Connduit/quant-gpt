# Milestone 5 pipeline audit

Repository inventory covered the data/provider/storage, feature, ML, research,
discovery, strategy and backtesting modules, tests, examples and configuration.
The original blueprint and Milestones 1–4 implementations remain in place.

| Area | Existing protection | Statistical gap and response |
| --- | --- | --- |
| Ingestion | Schema/OHLC/volume checks, XNYS calendar completeness, immutable hashed snapshots | Real HTTPS access verified through LEAN; Stooq's CONNECT request is proxy-denied. Offline and opt-in live errors are distinct. |
| Actions | Raw-price execution checks, split accounting, ex-date entitlement, explicit coverage | Archive factor proxies lack certified completeness/pay dates. Keep those limitations in all reports; do not qualify data for independent certification. |
| Features | Publication-time histories, observed-split rebasing, current/past bars only | Static universes and conservative assumed bar availability are not point-in-time certification. Preserve these caveats. |
| Models | Seeded CPU estimators, train-only scaling, trusted artifact loading | Fit-time bookkeeping must remain causal; no validation/test transformations enter training. |
| Labels | Next eligible open to future open, explicit known-at timestamps | Validate full information intervals, purge using global cross-asset availability, and count gaps/embargo in trading sessions. |
| Chronology | Expanding/rolling purged training, inner validation, search-validation windows | Add independently configurable retraining frequency/gaps and prevent duplicate OOS sessions. Fold chronology alone does not make folds independent. |
| Discovery | Bounded Optuna, all attempts recorded, immutable data seals, separate robustness variants | The repeatedly optimized score is a heuristic. Include rejected/failed/pruned variants in recorded search complexity, add dependence-aware uncertainty and corrections, and retain reuse warnings. |
| Execution | Strictly later opening fills, cash/accounting constraints, transaction costs | Daily full fills omit intraday liquidity/impact. Add distinct commission/slippage/delay diagnostics without changing the execution engine. |
| Selection | Economic eligibility and strongest simple baseline comparison | Reused validation is not independent confirmation. Statistical diagnostics cannot automatically establish a durable edge. |
| Holdout | Development worker snapshots physically exclude final rows | Add immutable manifest/authorization/consumption/release ledger. Routine statistical jobs only receive pre-cutoff normalized inputs. |

The pre-change M4 suite had 170 passing tests. During connectivity edits, an
initial concurrent baseline run triggered a code-change integrity rejection
(169 passed, one failed). Repeating without source mutation passed all **170**;
three new opt-in live tests skipped in offline mode. The explicit live-provider
run passed all **three** real ingestion/reload tests. This confirms the integrity
guard was active; the failed concurrent run was not counted as successful.

The supported holdout controls are application capabilities and an audit ledger,
not an operating-system sandbox against a user with filesystem/SQLite access.
Bulk vendor ZIP/factor source archives can contain dates beyond the requested
interval; normalized development snapshots and workers exclude them. Statistical
validation never requests, constructs features from, evaluates or releases the
reserved final period. A future independent evaluator must be explicitly
configured and authorized; this milestone does not invoke one.

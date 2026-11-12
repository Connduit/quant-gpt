# Architecture audit after Milestone 1

This is the historical pre-Milestone 2 audit. Current Milestone 3 implementation
status and the targeted multi-stock replay extension are documented in
[ML research](ml-research.md) and [progress](progress.md); future-work entries below
describe the architecture at the time of this audit.

This audit uses the original [blueprint](blueprint.md) and the subsequent
[development instructions](development-instructions.md). The latter update the
roadmap to 11 milestones; the original blueprint remains unchanged.

## Findings and targeted decisions

The existing provider protocol, strict normalization, immutable snapshots,
checksums, TOML configuration, JSON logging, CLI and 47 tests form a working data
foundation. They are retained. There is no reason to replace Polars, Parquet,
DuckDB or uv, or to introduce a broker SDK, ML framework or GPU dependency now.

1. **Price adjustment is not an execution contract.** Stooq's recorded basis is
   unspecified, and Milestone 1 has no action ledger. Backtesting now requires
   synthetic prices or caller-declared unadjusted prices with a complete, sourced
   split/dividend ledger. A CSV provider/import command makes that raw-price path
   usable. Adjusted/unknown snapshots remain readable but cannot be executed.
   Declarations are not independent vendor verification.
2. **Close time differs from knowledge time.** The stored daily availability
   cutoff is conservative, not verified publication history. Replay separates
   opening prints, closes, bar availability, splits and dividend events. A strategy
   never receives the full dataset. Execution policies receive an `OpeningEvent`
   containing only the opening price and time, not the completed day's bar.
3. **Signals should not depend on a broker.** Immutable target-share `Signal`
   objects are separate from orders and fills. The strategy context contains
   available history and a read-only account view. Future execution adapters can
   consume the same targets while enforcing their own risk/authorization rules.
4. **Portfolio accounting needs its own state.** Decimal arithmetic, explicit
   average-cost positions, entry-fee allocation, realized/unrealized P&L, dividend
   receivables and cash reconciliation are implemented separately from strategies.
   No leverage or short selling is inferred from a negative target.
5. **Reproducibility needs more than a price file.** Reports capture the snapshot,
   action ledger, strategy parameters, cost configuration, code/dependency hashes,
   benchmark and output checksums. Built-in strategies are immutable configured
   dataclasses. Arbitrary custom Python strategy state is not automatically
   serializable; reports flag that limitation. Callbacks are not a security sandbox.
6. **The current adapter has a narrow scope.** DataRequest and normalization are
   daily US/XNYS-specific, and querying loads snapshots into memory. DailyData makes
   those assumptions explicit instead of spreading them into future data providers.
   Intraday events, futures contracts, margin/settlement and multi-instrument
   synchronization require new adapters/accounting policies at their milestones;
   today's cash-equity ledger must not be reused as futures accounting.

## Coverage of the blueprint's 12 capabilities

| Capability | Current implementation / extension boundary |
| --- | --- |
| 1. Historical and live data | Historical providers/storage work. Live streaming, lifecycle/universe and true publication/revision data remain future work; source adapters remain outside strategies. |
| 2. Hundreds of features | Available, split-rebased history is an input boundary. A versioned feature pipeline is not implemented. |
| 3. ML/deep learning | Model training/prediction remains separate from replay. No models or GPU requirements are introduced. |
| 4. Hypothesis generation | Configured strategies and reproducible result artifacts support later experiment definitions; no search engine exists yet. |
| 5. Bias-controlled optimization | Simulation timing safeguards exist now. Chronological ML splits, purging, holdouts and multiple-testing controls are required when training/search arrives. |
| 6. Realistic backtesting | Daily, one-instrument long-only cash replay with next-open execution, actions and explicit costs. Limits/partial fills, latency and futures are unsupported. |
| 7. Statistical/risk comparison | Basic performance metrics and a controlled buy-and-hold comparator work. Significance and robust strategy selection are not implied. |
| 8. Capital allocation | Explicit cash/position state and target signals provide a boundary. Multi-strategy allocation, multi-asset constraints and optimization are deferred. |
| 9. Paper trading | Shared signals/orders/fills can feed a future paper adapter. Scheduling, live state and reconciliation are not implemented. |
| 10. Authorized live trading | No broker or live-execution path exists. Future adapters must add independent authorization, reconciliation and mandatory risk checks. |
| 11. Monitoring/degradation | Structured logs and immutable run exports exist. Persistent monitoring, model drift and alerts are future work. |
| 12. Dashboard | CSV/JSON reports can be consumed independently of engine state. React/FastAPI services are not implemented in this milestone. |

This is an extension plan, not a claim that future capabilities already work.
No limit-order, ML, futures, broker or autonomous-agent placeholders were added.
Parallel experiments should create independent replay/strategy instances and
report directories; shared mutable strategy instances are not a supported
experiment isolation mechanism. Future AI agents require an actual restricted
execution environment, not just the read-only callback interface.

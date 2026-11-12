# Milestone 7 actual results

The reproducible run is `data/futures/milestone-7-final`, using the populated
`configs/futures-research.example.yaml`. This is archival research, not a live feed.

The [dataset manifest](milestone-7-datasets.json) identifies 1,950 complete RTH
one-minute ESZ13 observations, October 7–11, 2013, with quoted prices and open
interest. Fifteen HTTPS archive downloads succeeded through the application.
No reserved October 14 period was downloaded. The equity 2019 holdout also remains sealed.

Four ML trials and five separately recorded conventional controls completed with
zero failed attempts. Across all retained prototype/release/final registries, 27
hypotheses and 27 attempts were recorded; prototype results are not final financial
evidence. No strategies qualify for paper trading.

| Candidate | Mean OOS session return | Excess over contract control | Fills |
|---|---:|---:|---:|
| futures_trial direction | -1.0759% | -1.5189% | 68 |
| futures_trial direction | 0.0000% | -0.4680% | 0 |
| futures_trial forward_return | -0.7024% | -1.1454% | 44 |
| futures_trial forward_return | -0.8662% | -1.3091% | 66 |
| futures_baseline forward_return | -1.1131% | -1.5560% | 82 |
| futures_baseline forward_return | -0.4697% | -0.9126% | 68 |
| futures_baseline forward_return | -1.6605% | -2.1034% | 147 |
| futures_baseline forward_return | -1.1460% | -1.5889% | 117 |
| futures_baseline forward_return | 0.4430% | 0.0000% | 4 |

Returns average two separately funded OOS session folds (October 10 and 11),
with $100,000 starting capital per fold; they are not a compounded multi-year
performance estimate. BY q-values are 1. PSR/DSR are unavailable because there
are only two independent daily observations. Minute bootstrap diagnostics do not
create independent sessions. Fees and historical margins are explicit assumptions.

Full offline suite: **250 passed, 4 skipped**. Opt-in real provider suite:
**4 passed** (three equity downloads and one futures download). Package builds
and source lint checks passed. All earlier functionality remains covered.

See [methodology](futures.md), [audit](futures-audit.md), and
[machine-readable results](milestone-7-results.json).

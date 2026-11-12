# Milestone 4 verification results

The bounded real-data discovery demonstration completed with **four Optuna trials, six diagnostic robustness variants, and zero eligible strategies**. These are search-validation results, not evidence of a trading edge. Milestone 5 has not started.

## Data and limitations

The pinned QuantConnect LEAN archive supplied AAPL, AIG, BAC, FB, GOOGL, IBM, WM and SPY: 1,447 daily XNYS sessions each, April 3, 2014–December 31, 2019. Seven stocks across four sectors were available with suitable daily/factor files; the preferred 10–20 stock universe was unavailable in this archive. Stooq remained blocked by the cloud proxy and has unknown adjustment semantics.

Raw-price scaling was checked against LEAN source code, the Apple 7-for-1 split, and an independent 506-session Apple price comparison (99.802% within one cent). This does not certify every symbol or event. Source URLs, exact snapshot IDs, hashes and quality checks are recorded in [the dataset manifest](milestone-4-datasets.json). Raw vendor data is retained locally under ignored `data/`, not redistributed in Git.

**Corporate-action completeness is not certified.** The explicitly selected `factor_file_proxy` alternative represents supplied factor changes, reconstructs approximate distributions, and leaves unknown payment dates null. Distributions remain non-spendable receivables. Non-cash events may be cash-equivalent proxies. This demonstration is not fully corporate-action-aware; its static universe also carries survivorship bias.

## Protocol and results

The final 252 sessions (January 2–December 31, 2019) remain untouched and physically absent from worker snapshots. Four earlier chronological search-validation windows use purging, train-only transforms, later-open fills and commission/spread/slippage costs. All horizons use the same longest-horizon evaluation calendar.

| Attempt | Mean window net return | Mean window SPY excess | Score | Rejection reasons |
| --- | ---: | ---: | ---: | --- |
| `b31393bc502f3d03-1-bcdec00b` | 5.028% | 0.825% | -0.072680 | too_few_positive_excess_windows, weaker_than_simple_baselines |
| `38e6ed5aaaa07318-1-dd57d2b3` | 1.431% | -2.772% | -0.082855 | too_few_positive_excess_windows, insufficient_excess_return, weaker_than_simple_baselines |
| `6246e0bf1e87d7d4-1-d03e5136` | 4.227% | 0.023% | -0.085533 | weaker_than_simple_baselines |
| `b65a005cf94c0275-1-1beafe8a` | 1.860% | -2.344% | -0.115470 | too_few_positive_excess_windows, insufficient_excess_return, weaker_than_simple_baselines |

Returns are arithmetic means of individual validation-window returns, not a combined equity return or CAGR. All candidates lagged the strongest simple baseline. Eligibility thresholds and composite scores are transparent heuristics, not statistical significance tests. The top rejected candidate received six separate robustness diagnostics; none became eligible, and its original artifact was unchanged. Cost stress reuses fixed predictions in each original window.

The original run recorded 10 unique hypotheses, 10 attempts and four optimizer trials. Robustness variants count as hypotheses; they are not additional optimizer trials. An independently installed 0.4.0 wheel reproduced `b31393bc502f3d03-1-bcdec00b` as `b31393bc502f3d03-2-3eaee90f` with `summary_matches: true`. This raises audit attempts to 11 while retaining 10 hypotheses and four optimizer trials. Resume added no search trials. Reproduction is not new evidence. Local results and model artifacts are under `data/discovery/release/`; registry, Optuna and MLflow use separate SQLite databases.

## Reproduction and verification

Install with `uv sync --frozen --all-extras`. The populated recorded search configuration is [configs/discovery.example.yaml](../configs/discovery.example.yaml); it resolves to the retained input research YAML. [The research configuration copy](../configs/discovery-real-research.yaml) records the snapshot choices. Fresh ingestion may create different snapshot IDs while preserving source hashes.

```bash
uv run --frozen --all-extras python examples/discovery_demo.py --allow-factor-proxy
uv run --frozen --all-extras quantlab discovery list --root data/discovery/release
uv run --frozen --all-extras quantlab discovery resume --study data/discovery-real-verified-inputs/discovery-study.yaml --root data/discovery/release
```

The first command generates inputs/configuration and runs a bounded demonstration in its default directory; preserve existing reports or select a fresh root using the example options. The recorded release root uses the original generated configuration above. See [the discovery guide](discovery.md) for all CLI operations and resource semantics.

**170 tests passed**, including all 135 prior tests. Lint, formatting, wheel and source distribution builds passed. Tests cover physical holdout isolation, timing/purging, bounded spaces, deterministic proposals, duplicate/retry/recovery, CPU/wall/memory limits, MLflow persistence, pruning, reproduction, and explicit incomplete factor coverage. Pandas/calendar and SQLAlchemy deprecation warnings remain.

Milestone 5 must address multiple testing, statistical uncertainty and independent validation before any strategy promotion. No final holdout evaluation, broker integration or live trading was added.

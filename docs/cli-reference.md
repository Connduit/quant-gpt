# Complete QuantLab CLI reference

Generated from `quantlab.cli.parser()`; no command was executed. Global options
precede the command. Use the [usage guide](user-guide.md) for prerequisites,
workflows, evidence limits and deployment controls.

## Root

```text
usage: - [-h] [--config CONFIG] [--data-dir DATA_DIR]
         {download,import-csv,inspect,query,backtest,research,discovery,validate,portfolio,execution,agent,dashboard,paper,futures}
         ...

Quant Research Lab: daily equities data

positional arguments:
  {download,import-csv,inspect,query,backtest,research,discovery,validate,portfolio,execution,agent,dashboard,paper,futures}
    download            Download and validate inclusive daily dates
    import-csv          Import daily OHLCV with declared price basis
    inspect             Verify and describe a snapshot
    query               Run one SELECT against the bars relation
    backtest            Replay a verified daily-equity snapshot
    research            Run a configured CPU walk-forward ML experiment
    discovery           Bounded strategy discovery
    validate            Statistical research validation
    portfolio           Multi-strategy research portfolios
    execution           Controlled PAPER broker sandbox; LIVE disabled
    agent               Bounded research orchestration; no trading authority
    dashboard           Authenticated curated research dashboard
    paper               Simulated execution and experimental replay
    futures             Contract-aware futures research only

options:
  -h, --help            show this help message and exit
  --config CONFIG       TOML configuration file
  --data-dir DATA_DIR   Override snapshot storage location
```

## quantlab download

```text
usage: - download [-h] --start START --end END
                  [--provider {stooq,fixture,lean}] [--refresh]
                  [--extend EXTEND]
                  symbol

positional arguments:
  symbol

options:
  -h, --help            show this help message and exit
  --start START
  --end END
  --provider {stooq,fixture,lean}
  --refresh             Fetch a new vendor revision
  --extend EXTEND       Append new sessions to this parent snapshot
```

## quantlab import-csv

```text
usage: - import-csv [-h] --csv CSV --source SOURCE --price-basis
                    {unadjusted,adjusted} --start START --end END
                    symbol

positional arguments:
  symbol

options:
  -h, --help            show this help message and exit
  --csv CSV
  --source SOURCE       Dataset provenance label
  --price-basis {unadjusted,adjusted}
  --start START
  --end END
```

## quantlab inspect

```text
usage: - inspect [-h] snapshot_id

positional arguments:
  snapshot_id

options:
  -h, --help   show this help message and exit
```

## quantlab query

```text
usage: - query [-h] [--sql SQL] snapshot_id

positional arguments:
  snapshot_id

options:
  -h, --help   show this help message and exit
  --sql SQL
```

## quantlab backtest

```text
usage: - backtest [-h] [--strategy {momentum,mean-reversion,buy-hold}]
                  [--lookback LOOKBACK] [--threshold THRESHOLD]
                  [--shares SHARES] [--initial-cash INITIAL_CASH]
                  [--commission-per-share COMMISSION_PER_SHARE]
                  [--commission-fixed COMMISSION_FIXED]
                  [--minimum-commission MINIMUM_COMMISSION]
                  [--slippage-bps SLIPPAGE_BPS] [--spread-bps SPREAD_BPS]
                  [--actions ACTIONS] --output OUTPUT
                  snapshot_id

positional arguments:
  snapshot_id

options:
  -h, --help            show this help message and exit
  --strategy {momentum,mean-reversion,buy-hold}
  --lookback LOOKBACK
  --threshold THRESHOLD
                        Fraction, e.g. 0.02 (not a percentage)
  --shares SHARES       Fixed entry and benchmark share quantity
  --initial-cash INITIAL_CASH
  --commission-per-share COMMISSION_PER_SHARE
  --commission-fixed COMMISSION_FIXED
  --minimum-commission MINIMUM_COMMISSION
  --slippage-bps SLIPPAGE_BPS
  --spread-bps SPREAD_BPS
                        Full bid/ask spread in basis points
  --actions ACTIONS     Complete split/dividend JSON ledger
  --output OUTPUT       New report directory
```

## quantlab research

```text
usage: - research [-h] --experiment EXPERIMENT --output OUTPUT

options:
  -h, --help            show this help message and exit
  --experiment EXPERIMENT
                        YAML experiment definition
  --output OUTPUT       New research report directory
```

## quantlab discovery run

```text
usage: - discovery run [-h] --root ROOT --study STUDY
                       [--parameters PARAMETERS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --study STUDY
  --parameters PARAMETERS
```

## quantlab discovery batch

```text
usage: - discovery batch [-h] --root ROOT --study STUDY --parameters
                         PARAMETERS [PARAMETERS ...]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --study STUDY
  --parameters PARAMETERS [PARAMETERS ...]
```

## quantlab discovery study

```text
usage: - discovery study [-h] --root ROOT --study STUDY

options:
  -h, --help     show this help message and exit
  --root ROOT
  --study STUDY
```

## quantlab discovery resume

```text
usage: - discovery resume [-h] --root ROOT --study STUDY

options:
  -h, --help     show this help message and exit
  --root ROOT
  --study STUDY
```

## quantlab discovery list

```text
usage: - discovery list [-h] --root ROOT

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab discovery compare

```text
usage: - discovery compare [-h] --root ROOT

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab discovery reproduce

```text
usage: - discovery reproduce [-h] --root ROOT --study STUDY attempt_id

positional arguments:
  attempt_id

options:
  -h, --help     show this help message and exit
  --root ROOT
  --study STUDY
```

## quantlab discovery report

```text
usage: - discovery report [-h] --root ROOT

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab discovery rejected

```text
usage: - discovery rejected [-h] --root ROOT

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab validate run

```text
usage: - validate run [-h] --validation-config VALIDATION_CONFIG --output
                      OUTPUT

options:
  -h, --help            show this help message and exit
  --validation-config VALIDATION_CONFIG
  --output OUTPUT
```

## quantlab validate walk-forward

```text
usage: - validate walk-forward [-h] --validation-config VALIDATION_CONFIG
                               --output OUTPUT

options:
  -h, --help            show this help message and exit
  --validation-config VALIDATION_CONFIG
  --output OUTPUT
```

## quantlab validate robustness

```text
usage: - validate robustness [-h] --validation-config VALIDATION_CONFIG
                             --output OUTPUT

options:
  -h, --help            show this help message and exit
  --validation-config VALIDATION_CONFIG
  --output OUTPUT
```

## quantlab validate confidence-intervals

```text
usage: - validate confidence-intervals [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab validate multiple-testing

```text
usage: - validate multiple-testing [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab validate report

```text
usage: - validate report [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab validate compare

```text
usage: - validate compare [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab validate list

```text
usage: - validate list [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab validate rejected

```text
usage: - validate rejected [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab validate eligible

```text
usage: - validate eligible [-h] --reports REPORTS [REPORTS ...]

options:
  -h, --help            show this help message and exit
  --reports REPORTS [REPORTS ...]
```

## quantlab portfolio backtest

```text
usage: - portfolio backtest [-h] --portfolio-config PORTFOLIO_CONFIG --output
                            OUTPUT

options:
  -h, --help            show this help message and exit
  --portfolio-config PORTFOLIO_CONFIG
  --output OUTPUT
```

## quantlab portfolio stress

```text
usage: - portfolio stress [-h] --portfolio-config PORTFOLIO_CONFIG --output
                          OUTPUT

options:
  -h, --help            show this help message and exit
  --portfolio-config PORTFOLIO_CONFIG
  --output OUTPUT
```

## quantlab portfolio report

```text
usage: - portfolio report [-h] --report REPORT

options:
  -h, --help       show this help message and exit
  --report REPORT
```

## quantlab portfolio risk

```text
usage: - portfolio risk [-h] --report REPORT

options:
  -h, --help       show this help message and exit
  --report REPORT
```

## quantlab portfolio strategies

```text
usage: - portfolio strategies [-h] --report REPORT

options:
  -h, --help       show this help message and exit
  --report REPORT
```

## quantlab portfolio create

```text
usage: - portfolio create [-h] --output-config OUTPUT_CONFIG
                          --source-validation SOURCE_VALIDATION
                          --verified-inputs VERIFIED_INPUTS --start START
                          --end END

options:
  -h, --help            show this help message and exit
  --output-config OUTPUT_CONFIG
  --source-validation SOURCE_VALIDATION
  --verified-inputs VERIFIED_INPUTS
  --start START
  --end END
```

## quantlab portfolio register

```text
usage: - portfolio register [-h] --portfolio-config PORTFOLIO_CONFIG --name
                            NAME --strategy-id STRATEGY_ID

options:
  -h, --help            show this help message and exit
  --portfolio-config PORTFOLIO_CONFIG
  --name NAME
  --strategy-id STRATEGY_ID
```

## quantlab portfolio allocate

```text
usage: - portfolio allocate [-h] --portfolio-config PORTFOLIO_CONFIG --method
                            {equal,fixed,inverse_volatility,risk_parity,volatility_target}

options:
  -h, --help            show this help message and exit
  --portfolio-config PORTFOLIO_CONFIG
  --method {equal,fixed,inverse_volatility,risk_parity,volatility_target}
```

## quantlab execution sandbox-demo

```text
usage: - execution sandbox-demo [-h] --output OUTPUT

options:
  -h, --help       show this help message and exit
  --output OUTPUT
```

## quantlab execution readiness

```text
usage: - execution readiness [-h] [--workspace WORKSPACE] [--output OUTPUT]

options:
  -h, --help            show this help message and exit
  --workspace WORKSPACE
  --output OUTPUT
```

## quantlab execution inspect

```text
usage: - execution inspect [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab execution kill

```text
usage: - execution kill [-h] --database DATABASE --reason REASON
                        [--cancel-open]

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --reason REASON
  --cancel-open
```

## quantlab execution pause

```text
usage: - execution pause [-h] --database DATABASE --reason REASON --strategy
                         STRATEGY

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --reason REASON
  --strategy STRATEGY
```

## quantlab execution backup

```text
usage: - execution backup [-h] --database DATABASE --output OUTPUT

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --output OUTPUT
```

## quantlab execution restore

```text
usage: - execution restore [-h] --database DATABASE --output OUTPUT

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --output OUTPUT
```

## quantlab execution service

```text
usage: - execution service [-h] --execution-config EXECUTION_CONFIG
                           [--arm-approved-sandbox-test]
                           [--resume-reconciled-sandbox-test]
                           [--resume-reason RESUME_REASON]

options:
  -h, --help            show this help message and exit
  --execution-config EXECUTION_CONFIG
  --arm-approved-sandbox-test
  --resume-reconciled-sandbox-test
  --resume-reason RESUME_REASON
```

## quantlab execution approve-sandbox-test

```text
usage: - execution approve-sandbox-test [-h] --execution-config
                                        EXECUTION_CONFIG --actor ACTOR
                                        --reason REASON [--minutes MINUTES]
                                        --output OUTPUT

options:
  -h, --help            show this help message and exit
  --execution-config EXECUTION_CONFIG
  --actor ACTOR
  --reason REASON
  --minutes MINUTES
  --output OUTPUT
```

## quantlab agent run

```text
usage: - agent run [-h] [--root ROOT] --agent-config AGENT_CONFIG
                   [--objective OBJECTIVE] [--session SESSION]
                   [--scripted-engineering]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --agent-config AGENT_CONFIG
  --objective OBJECTIVE
  --session SESSION
  --scripted-engineering
```

## quantlab agent list

```text
usage: - agent list [-h] [--root ROOT]

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab agent report

```text
usage: - agent report [-h] [--root ROOT] --session SESSION

options:
  -h, --help         show this help message and exit
  --root ROOT
  --session SESSION
```

## quantlab agent pause

```text
usage: - agent pause [-h] [--root ROOT] --session SESSION --reason REASON

options:
  -h, --help         show this help message and exit
  --root ROOT
  --session SESSION
  --reason REASON
```

## quantlab agent resume

```text
usage: - agent resume [-h] [--root ROOT] --session SESSION --reason REASON

options:
  -h, --help         show this help message and exit
  --root ROOT
  --session SESSION
  --reason REASON
```

## quantlab agent cancel

```text
usage: - agent cancel [-h] [--root ROOT] --session SESSION --reason REASON

options:
  -h, --help         show this help message and exit
  --root ROOT
  --session SESSION
  --reason REASON
```

## quantlab agent emergency-stop

```text
usage: - agent emergency-stop [-h] [--root ROOT] --session SESSION --reason
                              REASON

options:
  -h, --help         show this help message and exit
  --root ROOT
  --session SESSION
  --reason REASON
```

## quantlab agent propose-code

```text
usage: - agent propose-code [-h] [--root ROOT] --text TEXT

options:
  -h, --help   show this help message and exit
  --root ROOT
  --text TEXT
```

## quantlab dashboard

```text
usage: - dashboard [-h] [--host HOST] [--port PORT]

options:
  -h, --help   show this help message and exit
  --host HOST
  --port PORT
```

## quantlab paper positions

```text
usage: - paper positions [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper orders

```text
usage: - paper orders [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper fills

```text
usage: - paper fills [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper equity

```text
usage: - paper equity [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper strategies

```text
usage: - paper strategies [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper logs

```text
usage: - paper logs [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper report

```text
usage: - paper report [-h] --database DATABASE

options:
  -h, --help           show this help message and exit
  --database DATABASE
```

## quantlab paper pause

```text
usage: - paper pause [-h] --database DATABASE [--strategy STRATEGY] --reason
                     REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper resume

```text
usage: - paper resume [-h] --database DATABASE [--strategy STRATEGY] --reason
                      REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper stop

```text
usage: - paper stop [-h] --database DATABASE [--strategy STRATEGY] --reason
                    REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper kill

```text
usage: - paper kill [-h] --database DATABASE [--strategy STRATEGY] --reason
                    REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper reset-kill

```text
usage: - paper reset-kill [-h] --database DATABASE [--strategy STRATEGY]
                          --reason REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper connect

```text
usage: - paper connect [-h] --database DATABASE [--strategy STRATEGY] --reason
                       REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper disconnect

```text
usage: - paper disconnect [-h] --database DATABASE [--strategy STRATEGY]
                          --reason REASON

options:
  -h, --help           show this help message and exit
  --database DATABASE
  --strategy STRATEGY
  --reason REASON
```

## quantlab paper start

```text
usage: - paper start [-h] --paper-config PAPER_CONFIG

options:
  -h, --help            show this help message and exit
  --paper-config PAPER_CONFIG
```

## quantlab paper replay

```text
usage: - paper replay [-h] --output OUTPUT

options:
  -h, --help       show this help message and exit
  --output OUTPUT
```

## quantlab futures specifications

```text
usage: - futures specifications [-h]

options:
  -h, --help  show this help message and exit
```

## quantlab futures import

```text
usage: - futures import [-h] --store STORE --contracts CONTRACTS --contract
                        CONTRACT --start START --end END --provider
                        {lean,databento,csv} [--csv CSV] [--source SOURCE]
                        [--synthetic] [--raw-contract-prices]
                        [--include-auxiliary] [--allow-sparse]
                        [--maximum-download-cost MAXIMUM_DOWNLOAD_COST]

options:
  -h, --help            show this help message and exit
  --store STORE
  --contracts CONTRACTS
  --contract CONTRACT
  --start START
  --end END
  --provider {lean,databento,csv}
  --csv CSV
  --source SOURCE
  --synthetic
  --raw-contract-prices
  --include-auxiliary
  --allow-sparse
  --maximum-download-cost MAXIMUM_DOWNLOAD_COST
```

## quantlab futures inspect

```text
usage: - futures inspect [-h] --store STORE snapshot

positional arguments:
  snapshot

options:
  -h, --help     show this help message and exit
  --store STORE
```

## quantlab futures query

```text
usage: - futures query [-h] --store STORE --sql SQL snapshot

positional arguments:
  snapshot

options:
  -h, --help     show this help message and exit
  --store STORE
  --sql SQL
```

## quantlab futures validate-history

```text
usage: - futures validate-history [-h] --store STORE snapshot

positional arguments:
  snapshot

options:
  -h, --help     show this help message and exit
  --store STORE
```

## quantlab futures research

```text
usage: - futures research [-h] --research-config RESEARCH_CONFIG --output
                          OUTPUT

options:
  -h, --help            show this help message and exit
  --research-config RESEARCH_CONFIG
  --output OUTPUT
```

## quantlab futures train

```text
usage: - futures train [-h] --research-config RESEARCH_CONFIG --output OUTPUT

options:
  -h, --help            show this help message and exit
  --research-config RESEARCH_CONFIG
  --output OUTPUT
```

## quantlab futures discover

```text
usage: - futures discover [-h] --research-config RESEARCH_CONFIG --output
                          OUTPUT

options:
  -h, --help            show this help message and exit
  --research-config RESEARCH_CONFIG
  --output OUTPUT
```

## quantlab futures resume

```text
usage: - futures resume [-h] --research-config RESEARCH_CONFIG --output OUTPUT

options:
  -h, --help            show this help message and exit
  --research-config RESEARCH_CONFIG
  --output OUTPUT
```

## quantlab futures report

```text
usage: - futures report [-h] --root ROOT

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab futures validation-report

```text
usage: - futures validation-report [-h] --root ROOT

options:
  -h, --help   show this help message and exit
  --root ROOT
```

## quantlab futures continuous

```text
usage: - futures continuous [-h] --store STORE --snapshots SNAPSHOTS
                            [SNAPSHOTS ...] --output OUTPUT
                            [--roll-method {calendar,volume}]
                            [--roll-days ROLL_DAYS] [--back-adjust]

options:
  -h, --help            show this help message and exit
  --store STORE
  --snapshots SNAPSHOTS [SNAPSHOTS ...]
  --output OUTPUT
  --roll-method {calendar,volume}
  --roll-days ROLL_DAYS
  --back-adjust
```

## quantlab futures backtest

```text
usage: - futures backtest [-h] --store STORE --snapshots SNAPSHOTS
                          [SNAPSHOTS ...] --output OUTPUT
                          [--family {momentum,vwap,opening_range,regime,buy_hold}]
                          --holdout-start HOLDOUT_START

options:
  -h, --help            show this help message and exit
  --store STORE
  --snapshots SNAPSHOTS [SNAPSHOTS ...]
  --output OUTPUT
  --family {momentum,vwap,opening_range,regime,buy_hold}
  --holdout-start HOLDOUT_START
```

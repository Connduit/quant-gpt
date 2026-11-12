# Milestone 8 actual verification

The [full request](milestone-8-instructions.md), [architecture and operation](paper-trading.md)
and [machine-readable results](milestone-8-results.json) are preserved.

Two RESEARCH strategies share one $100,000 simulated account. A new explicitly
experimental ridge model uses quote-event features, trained on October 7–9, 2013;
October 10–11 archived ESZ13 closing quotes drive execution. This is not a
validated model deployment, real-time paper trading, or independent holdout evidence.

The run `data/paper/milestone-8-final` recorded **99 fills**, **$348.48 fees**,
**$98,882.77 ending NAV (-1.11723%)** and **2.180% maximum observed drawdown**.
The daily loss limit halted trading at October 10, 16:36 UTC (12:36 ET).
The position remains one ES contract; kill stops orders, not automatic liquidation.
The loss limit was not reset to keep the demonstration trading. The later change
in equity includes mark-to-market on this retained position. Margins are research
assumptions. Quote depth is a disclosed historical volume proxy, not actual depth.

The account was restarted, both ledgers reconstructed, and the repeated event
produced no extra fill. The halt remained persisted through recovery. There are
360 matured quote-event direction observations (44.17% descriptive accuracy),
not independent session evidence. Sharpe is unavailable with only two days.

The comparison report records 147 M7 momentum-control fills versus 99 multi-strategy
replay fills; feature/model/timing/execution policies differ. This is an engineering
discrepancy diagnostic, not matched-strategy equivalence or proof of a causal reason.
Missing benchmark measurements remain null. No final holdout was accessed.

**278 tests passed**, with five opt-in network tests skipped. The independently
installed 0.8 wheel reconstructed every final master-account metric exactly and
kept execution paused on restart. Lint, formatting and package builds passed.

Core tests cover prior functionality plus market normalization, conservative fills,
order transitions, partials, kill, shared cash/margins, corruption detection,
restart freshness, idempotency, model pinning and matured outcomes. External Alpaca
polling/WebSockets are mocked; licensed futures streaming transport remains unverified.
No streaming credentials, subscriptions or applicable network permissions are configured.
There are **zero eligible validated paper strategies**, and no real-money order capability.

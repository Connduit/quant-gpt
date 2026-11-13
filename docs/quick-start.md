# Quick start: setup to finding strategy candidates

Use this guide for a local Linux/macOS setup. The build and start scripts also
accept `python3` if that is your Python command. The current backend uses Unix
process/file-lock features; on Windows, use WSL rather than native PowerShell.

The app searches bounded combinations of models, features, and trading rules.
Its output is research candidates and rejection reasons, not a ready-to-trade algo.

## 1. Get the project and tools

Install Git, Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and a current Node.js LTS with npm (Node 22.12+ or 24 recommended).

For a first checkout:

```bash
git clone --branch work https://github.com/Connduit/quant-gpt.git
cd quant-gpt
```

If you already have the project, use your existing folder, switch to `work`, and
pull the latest changes. Save any local code changes before switching branches.

## 2. Set up your private .env

Copy the template once; do not overwrite an existing `.env`:

```bash
cp -n .env.example .env
```

Open `.env` in your editor. Keep `QUANTLAB_LOCAL_DEV_AUTH=1` for local development;
leave all three Quantlab role tokens blank. Access is automatic on localhost.

Only for strict role mode (`QUANTLAB_LOCAL_DEV_AUTH=0`), generate three separate
dashboard passwords by running this command three times:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put one different result into each field:

| Setting | What you use it for |
| --- | --- |
| `QUANTLAB_VIEWER_TOKEN` | Read reports and status. |
| `QUANTLAB_OPERATOR_TOKEN` | Add/remove provider keys and control simulated paper accounts. |
| `QUANTLAB_RESEARCHER_TOKEN` | Download data, start training/discovery, cancel jobs. |

These are separate roles. Operator access does not automatically authorize research.
Enter only the password value in the dashboard, not the `NAME=` part.

Either fill in `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` now, or save your
Alpaca pair through the dashboard later. `DATABENTO_API_KEY` is optional.
The comments in `.env` explain every field. Leave broker sandbox credentials
blank for this workflow. Leave `QUANTLAB_CREDENTIALS_MASTER_KEY` blank to use an
automatically generated private local encryption key.

Keep `.env` private; it is excluded from Git. Saved dashboard provider keys override
`.env` provider keys. Removing the saved override restores the `.env` configuration.

## 3. Build and start

From the project root:

```bash
python build.py
python start.py
```

The build command installs locked dependencies and builds the frontend. The start
command loads `.env` and serves the dashboard at **http://127.0.0.1:8000**.
Keep that terminal open. Stop with Ctrl+C. If the port is busy, use
`python start.py --port 8001` and open that port instead.

After pulling updates, stop the app, run `python build.py`, and start it again.
After editing `.env`, restart the app. No rebuild is needed for token changes.

## 4. Connect your data provider

1. Open the dashboard. Local development connects automatically. In strict role mode only, paste your **operator token** into the top bar and click **Connect**.
2. Open **API keys** in the sidebar.
3. Enter your Alpaca key ID and matching secret, then save. Alternatively, enter a Databento key.
4. Local development connects automatically. With `QUANTLAB_LOCAL_DEV_AUTH=0`, switch the top-bar token to your **researcher token** and click **Connect** before downloading.

Saved key fields clear intentionally; the app never displays stored secrets again.
“Configured” means keys are present, not that provider access has been verified.
For Alpaca, use SIP only if your account has the required entitlement; select IEX
explicitly if that is your intended available feed. The app does not switch feeds automatically.


Local development needs no Quantlab tokens. `python start.py` loads `.env`, and
localhost defaults to automatic operator/researcher access. The top bar shows
**Local development · automatic access**, with no token form. Provider API keys
still come from `.env` or **API keys**. Role-token instructions in this guide apply only
if you set `QUANTLAB_LOCAL_DEV_AUTH=0`; do not paste tokens during normal development.
Remote hosting requires token authentication and cannot enable local dev access.

## 5. Download your first snapshots

Open **Data library**. Both download forms default to SPY plus the Mag 7
(`SPY, AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA`). For a full training/test pair,
use **Quick download: training + protected test snapshots** with Alpaca. The
default preset downloads 2020–2024 training data and 2025 through yesterday
(UTC) protected test data in separate requests. A 2016–2018 / 2019 preset and
custom split are also available. Protected snapshots are sealed against routine
training and evaluation; downloading them does not evaluate a strategy. See
[workflow details](dashboard-workflows.md#download-and-create-snapshots).

For a small connectivity check in the single-range form, start with:

| Field | Example |
| --- | --- |
| Provider | Alpaca |
| Symbols | `AAPL, MSFT, SPY` |
| Start date | `2024-01-02` |
| End date | `2024-01-31` |
| Refresh | Off for the first request |

Choose your feed, confirm the request, then click **Download & create snapshots**.
Follow **Equity workflow jobs** and open **View report**. Check each symbol's result;
a partially successful job can still save some snapshots. A month is a connection
check, not enough history for useful ML research.

Downloads accept completed historical dates after 2018; today/future dates are
rejected. Alpaca requests allow up to ten years, Databento up to 31 calendar days.
Databento's default cost cap of zero permits only zero-cost estimates. Changing
it authorizes an estimated download budget; provider billing may differ.

## 6. Check whether your data can be used for discovery

In **Historical snapshot library**, inspect **eligibility** and the blocker text.
Downloading prices alone does not make a dataset research-ready.

Strict research requires unadjusted prices, verified historical universe
membership (which stocks were available at the time), and complete corporate-action
records such as splits/dividends. Alpaca/Databento price downloads alone do not
supply this full bundle, so newly downloaded snapshots can remain ineligible.
There is no dashboard button that certifies or fills in missing evidence.

To train prediction models with downloaded prices, choose **Exploratory ML —
prediction only** in the Machine learning / Research form. This explicit mode
accepts prices without those evidence bundles and reports their limitations.
It generates predictive metrics and saved models, without trading simulations,
strategy qualification, or promotion.
To test trading performance afterwards, open the completed ML report and use
**Evaluate strategy profitability**. This separate Phase 12C action replays saved
predictions with costs and produces net-performance charts and downloadable trade
logs; exploratory results remain unqualified. See [the workflow](phase12c/README.md). Splits and dividends can distort unadjusted
prices; no missing corrections are inferred. Discovery still requires strict inputs.
For strict research or Discovery, an administrator must prepare a verified library
following [the workflow documentation](dashboard-workflows.md#server-setup-and-verification).

Snapshot dates alone no longer block training/discovery. Choose **Research start
date** and **Research end date** in either form. The dashboard automatically extracts
that range, so a 2020–2026 snapshot can supply a 2020–2024 research run without
including 2025–2026 prices in fitting, features or labels. All selected snapshots
must cover the requested range. Data-quality requirements still apply.
Training, validation and evaluation folds stay within the selected range; choosing
a range does not certify that later data is an untouched final holdout.

If you want to try discovery before assembling a qualified library, use the
archived-data demonstration in the next step.

## 7. Run a first algo search

### Option A: try the existing archived-data example

After building, run this single command from the project root:

```bash
uv run --env-file .env --frozen --all-extras python examples/discovery_demo.py --allow-factor-proxy --trials 4 --workers 1 --root data/discovery/first-search
```

This downloads real archived LEAN sample data, builds the inputs, and searches
four configurations. It needs internet access to the archive sources, not your
Alpaca credentials. It does not silently substitute synthetic data.

`--allow-factor-proxy` explicitly accepts approximate corporate-action information
with incomplete event/payment-date evidence. The static stock sample also has
survivorship limitations. This is a learning/research example, not a qualified
strategy or a way to make dashboard data eligible. See [discovery details](discovery.md).

Read `data/discovery/first-search/reports/ranking.md` and `ranking.json` after the
run. The final terminal summary reports eligible and rejected/failed counts.
Use a new `--root` folder for another example run; an existing folder is rejected.
Example results are saved on disk and are not automatically added to the dashboard catalog.

### Option B: search from the dashboard with eligible inputs

With automatic local access (or the **researcher token** in strict mode), open **Discovery**, and select one eligible
snapshot per stock plus **SPY**. Choose research start/end dates covered by every
selected snapshot; the original snapshots may have different wider date ranges.
Start with enough history for training, validation, feature warmup, and evaluation
(several years, not the one-month connection check).

Suggested first settings:

| Field | Starting value |
| --- | --- |
| Run name | `First equity search` |
| Models | Ridge |
| Prediction horizon | 5 sessions |
| Training sessions | 504 |
| Validation sessions | 126 |
| Evaluation sessions per fold | 126 |
| Top holdings | 1 for AAPL/MSFT plus SPY |
| Maximum search trials | 4 |
| Random seed | 42 |

Confirm, click **Start bounded discovery**, and inspect **View report** when it
finishes. If history is insufficient, the job reports why. The dashboard supports
up to eight trials per discovery request. **Machine learning** uses the same data
selection for a training run without the discovery parameter search.

## 8. Decide what is worth investigating

Read the rejection reasons first. For surviving candidates, compare returns after
fees/slippage against SPY and simple baselines, drawdowns, performance across
walk-forward windows, and the doubled-cost checks. Check the data limitations.
A high score from one searched period is not independent proof of an edge.

Keep the configuration, seed, dataset identities, and results. Record every search;
repeating runs until one looks good increases selection bias. Use the project's
[statistical validation](statistical-validation.md) workflow before treating a
candidate as qualified, and keep final holdout evaluation separate from tuning.
No accepted candidate is a valid result. Discovery does not automatically activate
paper or live trading.

## Common fixes

| Symptom | What to check |
| --- | --- |
| `Invalid access token` | Use `python start.py`; copy only the matching value from `.env`; restart after edits. Old exported shell variables take precedence over `.env`. |
| `Role tokens must be distinct` | Give viewer, operator, and researcher three different values. |
| Key fields disabled | Use localhost automatic access, or connect as operator in strict mode. |
| Download/research forbidden | Restart on localhost for automatic access, or connect as researcher in strict mode. |
| Alpaca access/entitlement error | Verify the key pair and the selected SIP/IEX feed with Alpaca. |
| Data downloaded but cannot be selected | Set the research date range, then check actions and historical membership blockers. |
| Missing dashboard build | Run `python build.py`, then `python start.py`. |
| No candidates survive | Inspect reasons and evidence; do not bypass checks to force a winner. |

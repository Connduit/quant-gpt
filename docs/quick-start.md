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

Open `.env` in your editor. Generate three separate dashboard passwords by running
this command three times:

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

1. Open the dashboard. Paste your **operator token** into the top bar and click **Connect**.
2. Open **API keys** in the sidebar.
3. Enter your Alpaca key ID and matching secret, then save. Alternatively, enter a Databento key.
4. Switch the top-bar token to your **researcher token** and click **Connect** before downloading.

Saved key fields clear intentionally; the app never displays stored secrets again.
“Configured” means keys are present, not that provider access has been verified.
For Alpaca, use SIP only if your account has the required entitlement; select IEX
explicitly if that is your intended available feed. The app does not switch feeds automatically.

## 5. Download your first snapshots

Open **Data library**. For a small connectivity check, start with:

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

The current dashboard requires unadjusted prices, verified historical universe
membership (which stocks were available at the time), and complete corporate-action
records such as splits/dividends. Alpaca/Databento price downloads alone do not
supply this full bundle, so newly downloaded snapshots can remain ineligible.
There is no dashboard button that certifies or fills in missing evidence.
An administrator must prepare a verified library following
[the workflow documentation](dashboard-workflows.md#server-setup-and-verification).

The download cutoff was removed, but the **training/discovery holdout gate remains**:
snapshots ending after December 31, 2018 are currently blocked from these workflows.
You can download and inspect their library metadata. For dashboard research, use
eligible snapshots ending by that date, with identical coverage for every symbol.

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

Connect with the **researcher token**, open **Discovery**, and select one eligible
snapshot per stock plus **SPY**. All selected snapshots must have identical dates.
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
| Key fields disabled | Connect as operator and use localhost or HTTPS. |
| Download/research forbidden | Switch to researcher and click Connect. |
| Alpaca access/entitlement error | Verify the key pair and the selected SIP/IEX feed with Alpaca. |
| Data downloaded but cannot be selected | Read eligibility blockers; check holdout dates, actions, and historical membership. |
| Missing dashboard build | Run `python build.py`, then `python start.py`. |
| No candidates survive | Inspect reasons and evidence; do not bypass checks to force a winner. |

import { useState } from "react";
import { request } from "./api";
import { DEFAULT_EQUITY_SYMBOLS } from "./equityDefaults";

function previousDay(value: string) {
  const day = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(day.getTime())) return "";
  day.setUTCDate(day.getUTCDate() - 1);
  return day.toISOString().slice(0, 10);
}
export function QuickDatasetDownload({
  latest,
  queued,
}: {
  latest: string;
  queued: (id: string) => void;
}) {
  const [preset, setPreset] = useState("recent"),
    [symbols, setSymbols] = useState(DEFAULT_EQUITY_SYMBOLS);
  const [feed, setFeed] = useState("sip"),
    [refresh, setRefresh] = useState(false);
  const [customStart, setCustomStart] = useState("2020-01-01"),
    [customSplit, setCustomSplit] = useState("2025-01-01"),
    [customEnd, setCustomEnd] = useState(latest);
  const [pending, setPending] = useState(false),
    [message, setMessage] = useState("");
  const start =
    preset === "legacy"
      ? "2016-01-01"
      : preset === "recent"
        ? "2020-01-01"
        : customStart;
  const split =
    preset === "legacy"
      ? "2019-01-01"
      : preset === "recent"
        ? "2025-01-01"
        : customSplit;
  const end =
    preset === "legacy"
      ? "2019-12-31"
      : preset === "recent"
        ? latest
        : customEnd;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage("");
    try {
      const job = await request<{ id: string }>("/workflows/download-pair", {
        method: "POST",
        body: JSON.stringify({
          provider: "alpaca",
          alpaca_feed: feed,
          symbols: symbols.split(/[\s,]+/).filter(Boolean),
          start,
          split_date: split,
          end,
          refresh,
          confirmed: true,
        }),
      });
      setMessage(
        `Queued ${job.id}: separate training and protected test snapshots.`,
      );
      queued(job.id);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <section
      className="panel equity-workflow"
      aria-label="Quick training and test downloads"
    >
      <h3>Quick download: training + protected test snapshots</h3>
      <p>
        Choose one preset to download both datasets separately. Training
        snapshots go to your research library; protected test snapshots stay
        sealed and cannot be selected for routine ML, discovery or strategy
        evaluation.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <div className="workflow-fields">
          <label>
            Training/test preset
            <select
              aria-label="Training/test preset"
              value={preset}
              onChange={(e) => setPreset(e.target.value)}
            >
              <option value="recent">
                2020–2024 training · 2025 onward protected test
              </option>
              <option value="legacy">
                2016–2018 training · 2019 protected test
              </option>
              <option value="custom">Custom split</option>
            </select>
          </label>
          <label>
            Training/test symbols
            <input
              required
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
            />
          </label>
          <label>
            Split download feed
            <select
              aria-label="Split download feed"
              value={feed}
              onChange={(e) => setFeed(e.target.value)}
            >
              <option value="sip">Alpaca SIP — consolidated</option>
              <option value="iex">Alpaca IEX — single venue</option>
            </select>
          </label>
          {preset === "custom" && (
            <>
              <label>
                Training range start
                <input
                  type="date"
                  required
                  min="1990-01-01"
                  max={previousDay(split)}
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                />
              </label>
              <label>
                First protected test date
                <input
                  type="date"
                  required
                  min={start}
                  max={end}
                  value={customSplit}
                  onChange={(e) => setCustomSplit(e.target.value)}
                />
              </label>
              <label>
                Protected test range end
                <input
                  type="date"
                  required
                  min={split}
                  max={latest}
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                />
              </label>
            </>
          )}
        </div>
        <dl className="result-context">
          <div>
            <dt>Training snapshots</dt>
            <dd>
              {start} – {previousDay(split)}
            </dd>
          </div>
          <div>
            <dt>Protected test snapshots</dt>
            <dd>
              {split} – {end}
            </dd>
          </div>
        </dl>
        <label className="workflow-check">
          <input
            type="checkbox"
            checked={refresh}
            onChange={(e) => setRefresh(e.target.checked)}
          />
          Fetch fresh versions of both datasets
        </label>
        <p className="subtle">
          Researcher access and Alpaca keys are required. Downloading and
          validating test files does not evaluate them. Creating protected
          snapshots cannot make previously viewed data unseen. Strict evidence
          requirements still apply; OHLC-only training snapshots can be used in
          exploratory ML.
        </p>
        <button type="submit" disabled={pending}>
          {pending
            ? "Submitting…"
            : "Download training + protected test snapshots"}
        </button>
        <p role="status" aria-live="polite">
          {message}
        </p>
      </form>
    </section>
  );
}

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QuickDatasetDownload } from "./QuickDatasetDownload";
import { DEFAULT_EQUITY_SYMBOLS } from "./equityDefaults";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function setup() {
  const queued = vi.fn();
  const fetcher = vi.fn(
    async (_url: string, _options?: RequestInit) =>
      new Response(JSON.stringify({ id: "paired-job" }), { status: 202 }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<QuickDatasetDownload latest="2026-11-12" queued={queued} />);
  return { queued, fetcher };
}
describe("quick training/protected snapshot downloads", () => {
  it("defaults both data selection and payload to SPY plus all seven stocks", async () => {
    const { queued, fetcher } = setup();
    expect(screen.getByLabelText("Training/test symbols")).toHaveValue(
      DEFAULT_EQUITY_SYMBOLS,
    );
    expect(screen.getByText("2020-01-01 – 2024-12-31")).toBeInTheDocument();
    expect(screen.getByText("2025-01-01 – 2026-11-12")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Download training + protected test snapshots",
      }),
    );
    await waitFor(() => expect(queued).toHaveBeenCalledWith("paired-job"));
    const body = JSON.parse(String(fetcher.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      start: "2020-01-01",
      split_date: "2025-01-01",
      end: "2026-11-12",
      confirmed: true,
    });
    expect(body.symbols).toEqual([
      "SPY",
      "AAPL",
      "MSFT",
      "AMZN",
      "GOOGL",
      "META",
      "NVDA",
      "TSLA",
    ]);
  });
  it("switches to the legacy split without manually editing dates", async () => {
    const { fetcher } = setup();
    fireEvent.change(screen.getByLabelText("Training/test preset"), {
      target: { value: "legacy" },
    });
    expect(screen.getByText("2016-01-01 – 2018-12-31")).toBeInTheDocument();
    expect(screen.getByText("2019-01-01 – 2019-12-31")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Download training + protected test snapshots",
      }),
    );
    await screen.findByText(/Queued paired-job/);
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toMatchObject({
      start: "2016-01-01",
      split_date: "2019-01-01",
      end: "2019-12-31",
    });
  });
});

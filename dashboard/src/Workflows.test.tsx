import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EquityWorkflows } from "./Workflows";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function mount(page: string) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <EquityWorkflows page={page} />
    </QueryClientProvider>,
  );
}
function api(eligible = false) {
  const post = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit = {}) => {
      let data: unknown = { items: [], approved: [] };
      if (url.includes("/workflows/snapshots"))
        data = {
          items: ["AAA", "SPY"].map((symbol, index) => ({
            id: String(index + 1).repeat(64),
            symbol,
            start: "2014-01-02",
            end: "2018-12-31",
            rows: 1200,
            provider: "test",
            price_basis: eligible
              ? "unadjusted"
              : "vendor_adjustment_unspecified",
            eligible,
            blockers: eligible
              ? []
              : ["Complete corporate-action ledger is missing"],
          })),
          errors: [],
        };
      if (options.method === "POST") {
        post(url, JSON.parse(String(options.body)));
        data = { id: "test-job" };
      }
      return new Response(JSON.stringify(data), {
        status: options.method === "POST" ? 202 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return post;
}
describe("equity dashboard workflows", () => {
  it("submits Databento dataset and explicit cost budget without credentials", async () => {
    const post = api();
    mount("datasets");
    await screen.findByText("AAA");
    fireEvent.change(screen.getByLabelText("Historical data provider"), {
      target: { value: "databento" },
    });
    fireEvent.change(
      screen.getByLabelText("Maximum estimated download cost (USD)"),
      { target: { value: "2.5" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Download & create snapshots" }),
    );
    await screen.findByText(/Queued test-job/);
    expect(post.mock.calls[0][1]).toMatchObject({
      provider: "databento",
      maximum_download_cost: 2.5,
      databento_dataset: "XNAS.ITCH",
      start: "2018-12-03",
    });
    expect(JSON.stringify(post.mock.calls[0][1])).not.toContain("api_key");
  });
  it("submits typed downloads with bounded dates and refresh choice", async () => {
    const post = api();
    mount("datasets");
    await screen.findByText("AAA");
    fireEvent.change(screen.getByLabelText("US equity symbols"), {
      target: { value: "AAPL, SPY" },
    });
    fireEvent.click(screen.getByLabelText(/Fetch a fresh version/));
    fireEvent.click(
      screen.getByRole("button", { name: "Download & create snapshots" }),
    );
    await screen.findByText(/Queued test-job/);
    expect(post).toHaveBeenCalledWith("/api/v1/workflows/download", {
      symbols: ["AAPL", "SPY"],
      provider: "alpaca",
      alpaca_feed: "sip",
      databento_dataset: "XNAS.ITCH",
      maximum_download_cost: 0,
      start: "2016-01-04",
      end: "2018-12-31",
      refresh: true,
      confirmed: true,
    });
  });
  it("keeps unverified Stooq inputs ineligible for trading research", async () => {
    api();
    mount("models");
    await screen.findByText("AAA");
    expect(
      screen.getByRole("button", { name: "Start ML training" }),
    ).toBeDisabled();
    expect(
      screen
        .getAllByRole("checkbox", { name: /^Select / })
        .every((input) => (input as HTMLInputElement).disabled),
    ).toBe(true);
    expect(
      screen.getAllByText("Complete corporate-action ledger is missing"),
    ).toHaveLength(2);
  });
  it("launches training after selecting eligible equity and benchmark snapshots", async () => {
    const post = api(true);
    mount("models");
    const choices = await screen.findAllByRole("checkbox", {
      name: /^Select /,
    });
    choices.forEach((choice) => fireEvent.click(choice));
    fireEvent.click(screen.getByRole("button", { name: "Start ML training" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).toMatchObject({
      workflow: "training",
      models: ["ridge"],
      snapshot_ids: ["1".repeat(64), "2".repeat(64)],
      confirmed: true,
    });
  });
  it("submits discovery trial budget and selected models", async () => {
    const post = api(true);
    mount("discovery");
    (await screen.findAllByRole("checkbox", { name: /^Select / })).forEach(
      (choice) => fireEvent.click(choice),
    );
    fireEvent.change(screen.getByLabelText("Maximum search trials"), {
      target: { value: "2" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Start bounded discovery" }),
    );
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).toMatchObject({
      workflow: "discovery",
      max_trials: 2,
    });
  });
});

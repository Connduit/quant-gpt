import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EquityWorkflows } from "./Workflows";
import { MemoryRouter } from "react-router-dom";

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
      <MemoryRouter>
        <EquityWorkflows page={page} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function api(
  eligible = false,
  coverage = { start: "2014-01-02", end: "2018-12-31" },
) {
  const post = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit = {}) => {
      let data: unknown = { items: [], approved: [] };
      const exploratory = url.includes("research_mode=exploratory");
      if (url.includes("/workflows/snapshots"))
        data = {
          items: ["AAA", "SPY"].map((symbol, index) => ({
            id: String(index + 1).repeat(64),
            symbol,
            ...coverage,
            rows: 1200,
            provider: "test",
            price_basis:
              eligible || exploratory
                ? "unadjusted"
                : "vendor_adjustment_unspecified",
            eligible: eligible || exploratory,
            strict_blockers: eligible
              ? []
              : ["Complete corporate-action ledger is missing"],
            blockers:
              eligible || exploratory
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
  it("shows only Cancel for queued/running jobs and reports after completion", async () => {
    const fetchMock = vi.fn(
      async (url: string) =>
        new Response(
          JSON.stringify(
            url.endsWith("/jobs")
              ? {
                  items: ["QUEUED", "RUNNING", "COMPLETED"].map((status) => ({
                    id: status.toLowerCase(),
                    name: "training-example",
                    status,
                    detail: "",
                    created: "2026-01-01",
                  })),
                  approved: [],
                }
              : { items: [], errors: [] },
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    mount("models");
    for (const status of ["QUEUED", "RUNNING"]) {
      const row = (await screen.findByText(status)).closest("tr")!;
      expect(
        within(row).queryByRole("button", { name: "View report" }),
      ).not.toBeInTheDocument();
      expect(within(row).getByRole("button", { name: "Cancel" })).toBeEnabled();
    }
    const completed = (await screen.findByText("COMPLETED")).closest("tr")!;
    expect(
      within(completed).getByRole("button", { name: "View report" }),
    ).toBeEnabled();
    expect(
      within(completed).queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Cancel" })[0]);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/jobs/queued/cancel",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("lists profitability jobs only in Backtests without training controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (url: string) =>
          new Response(
            JSON.stringify(
              url.endsWith("/jobs")
                ? {
                    items: [
                      {
                        id: "running-backtest",
                        name: "profitability-running",
                        status: "RUNNING",
                        detail: "",
                        created: "2026-01-01",
                      },
                      {
                        id: "training-job",
                        name: "training-example",
                        status: "COMPLETED",
                        detail: "",
                        created: "2026-01-01",
                      },
                    ],
                    approved: [],
                  }
                : { items: [], errors: [] },
            ),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    mount("backtests");
    expect(await screen.findByText("profitability")).toBeInTheDocument();
    expect(screen.queryByText("training-job")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Train equity ML models" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Historical snapshot library" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "View report" }),
    ).not.toBeInTheDocument();
  });

  it("pages and filters the library while retaining selections across pages", async () => {
    const items = Array.from({ length: 18 }, (_, index) => ({
      id: index.toString(16).padStart(64, "0"),
      symbol: index === 0 ? "SPY" : `STK${String(index).padStart(2, "0")}`,
      start: "2020-01-02",
      end: "2024-12-31",
      rows: 1200,
      provider: "alpaca",
      price_basis: "unadjusted",
      retrieved_at: "2026-01-01",
      dataset_role: index === 17 ? "protected_test" : "training",
      eligible: index !== 17,
      blockers: index === 17 ? ["Protected test snapshot"] : [],
    }));
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (url: string) =>
          new Response(
            JSON.stringify(
              url.includes("/workflows/snapshots")
                ? { items, errors: [] }
                : { items: [], approved: [] },
            ),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    mount("models");
    await screen.findByText("SPY");
    expect(screen.getAllByRole("checkbox", { name: /^Select / })).toHaveLength(
      8,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /^Select SPY / }));
    fireEvent.click(screen.getByRole("button", { name: "Next snapshots" }));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /^Select STK08 / }));
    fireEvent.click(screen.getByRole("button", { name: "Previous snapshots" }));
    expect(
      screen.getByRole("checkbox", { name: /^Select SPY / }),
    ).toBeChecked();
    fireEvent.change(screen.getByLabelText("Snapshot eligibility"), {
      target: { value: "selected" },
    });
    expect(screen.getAllByRole("checkbox", { name: /^Select / })).toHaveLength(
      2,
    );
    expect(screen.getByText(/2 selected across all pages/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    fireEvent.change(screen.getByLabelText("Dataset role"), {
      target: { value: "protected_test" },
    });
    expect(
      screen.getByRole("checkbox", { name: /^Select STK17 / }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Search snapshots"), {
      target: { value: "missing" },
    });
    expect(
      screen.getByText(/No snapshots match these filters/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide snapshots" }));
    expect(screen.queryByLabelText("Search snapshots")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Equity workflow jobs" }),
    ).toBeInTheDocument();
  });

  it("defaults the standard download form to SPY and the Magnificent Seven", async () => {
    api();
    mount("datasets");
    expect(screen.getByLabelText("US equity symbols")).toHaveValue(
      "SPY, AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA",
    );
  });

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
      start: (() => {
        const date = new Date();
        date.setUTCDate(date.getUTCDate() - 31);
        return date.toISOString().slice(0, 10);
      })(),
    });
    expect(JSON.stringify(post.mock.calls[0][1])).not.toContain("api_key");
  });
  it("submits downloads after 2018 with refresh choice", async () => {
    const post = api();
    mount("datasets");
    await screen.findByText("AAA");
    fireEvent.change(screen.getByLabelText("US equity symbols"), {
      target: { value: "AAPL, SPY" },
    });
    const yesterday = new Date();
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    const latest = yesterday.toISOString().slice(0, 10);
    expect(screen.getByLabelText("End date")).toHaveValue(latest);
    expect(screen.getByLabelText("End date")).toHaveAttribute("max", latest);
    expect(
      screen.getByText(/Downloads can include dates after 2018/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2024-01-02" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2024-02-01" },
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
      start: "2024-01-02",
      end: "2024-02-01",
      refresh: true,
      confirmed: true,
    });
  });
  it("submits only the chosen research range from larger modern snapshots", async () => {
    const post = api(true, { start: "2020-01-02", end: "2025-12-31" });
    mount("models");
    const choices = await screen.findAllByRole("checkbox", {
      name: /^Select /,
    });
    choices.forEach((choice) => fireEvent.click(choice));
    expect(screen.getByLabelText("Research start date")).toHaveValue(
      "2020-01-02",
    );
    expect(screen.getByLabelText("Research end date")).toHaveValue(
      "2025-12-31",
    );
    fireEvent.change(screen.getByLabelText("Research end date"), {
      target: { value: "2024-12-31" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start ML training" }));
    await screen.findByText(/Queued test-job/);
    expect(post.mock.calls[0][1]).toMatchObject({
      start: "2020-01-02",
      end: "2024-12-31",
    });
    fireEvent.change(screen.getByLabelText("Research end date"), {
      target: { value: "2019-12-31" },
    });
    expect(
      screen.getByRole("button", { name: "Start ML training" }),
    ).toBeDisabled();
  });
  it("enables explicitly selected exploratory ML for downloaded prices", async () => {
    const post = api(false, { start: "2020-01-02", end: "2025-12-31" });
    mount("models");
    await screen.findByText("AAA");
    expect(
      screen.getByRole("button", { name: "Start ML training" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Research mode"), {
      target: { value: "exploratory" },
    });
    await waitFor(() =>
      expect(
        screen.getAllByRole("checkbox", { name: /^Select / })[0],
      ).toBeEnabled(),
    );
    screen
      .getAllByRole("checkbox", { name: /^Select / })
      .forEach((choice) => fireEvent.click(choice));
    expect(screen.queryByLabelText("Top holdings")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Reports contain prediction metrics only/),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Start exploratory ML" }),
    );
    await screen.findByText(/Queued test-job/);
    expect(post.mock.calls[0][1]).toMatchObject({
      workflow: "training",
      research_mode: "exploratory",
      start: "2020-01-02",
      end: "2025-12-31",
    });
  });
  it("fills exploratory training snapshots and dates with one click", async () => {
    const post = api(false, { start: "2020-01-02", end: "2024-12-31" });
    mount("models");
    await screen.findByText("AAA");
    fireEvent.change(screen.getByLabelText("Research mode"), {
      target: { value: "exploratory" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Use training snapshots" }),
      ).toBeEnabled(),
    );
    expect(
      screen.getByText(/Select training snapshots below/),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Use training snapshots" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Start exploratory ML" }),
      ).toBeEnabled(),
    );
    expect(screen.getByLabelText("Research start date")).toHaveValue(
      "2020-01-02",
    );
    expect(screen.getByLabelText("Research end date")).toHaveValue(
      "2024-12-31",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Start exploratory ML" }),
    );
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).toMatchObject({
      research_mode: "exploratory",
      start: "2020-01-02",
      end: "2024-12-31",
    });
  });
  it("does not offer exploratory mode for Discovery", async () => {
    api();
    mount("discovery");
    await screen.findByText("AAA");
    expect(screen.queryByLabelText("Research mode")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start bounded discovery" }),
    ).toBeDisabled();
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

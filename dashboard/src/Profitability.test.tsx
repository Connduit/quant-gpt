import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import fixture from "../e2e/fixtures/profitability-report.json";
import { ProfitabilityReport } from "./ProfitabilityReport";
import { StrategyEvaluation } from "./StrategyEvaluation";
beforeEach(() =>
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  ),
);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const metric = (name: string) =>
  within(
    screen
      .getByText(name, { selector: ".metric > span" })
      .closest(".metric") as HTMLElement,
  );
describe("profitability-first workflow", () => {
  it("shows net performance and changes costs and chart data together", () => {
    render(<ProfitabilityReport data={fixture} identity={"b".repeat(32)} />);
    expect(
      metric("Net simulated return").getByText("35.29%"),
    ).toBeInTheDocument();
    expect(screen.getByText(/No automatic qualification/)).toBeInTheDocument();
    expect(
      screen.getByText(/cash reserve but no single-stock cap/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Net equity curve" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Cost scenario"), {
      target: { value: "high" },
    });
    const value = fixture.report.scenarios.high.strategies.ml.net.total_return;
    expect(
      metric("Net simulated return").getByText(`${(value * 100).toFixed(2)}%`),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Net equity versus benchmarks · high costs"),
    ).toBeInTheDocument();
  });
  it("submits explicit saved-job rules without accepting filesystem paths", async () => {
    const queued = vi.fn(),
      fetcher = vi.fn(
        async (_url: unknown, _options?: RequestInit) =>
          new Response(JSON.stringify({ id: "b".repeat(32) }), { status: 202 }),
      );
    vi.stubGlobal("fetch", fetcher);
    render(
      <StrategyEvaluation
        sourceId={"a".repeat(32)}
        source={{
          research_range: { start: "2016-01-01", end: "2018-12-31" },
          report: {
            research_mode: "exploratory",
            predictive_performance: { ridge: {} },
          },
        }}
        queued={queued}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Evaluate strategy" }));
    await waitFor(() => expect(queued).toHaveBeenCalled());
    const body = JSON.parse(String(fetcher.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      source_job_id: "a".repeat(32),
      research_mode: "exploratory",
      holding_sessions: 20,
      commission_per_share: 0.005,
      confirmed: true,
    });
    expect(body).not.toHaveProperty("path");
    expect(
      screen.getByText(/Saved runs containing protected 2019 data/),
    ).toBeInTheDocument();
  });
  it("explains a protected source run before submission", () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    render(
      <StrategyEvaluation
        sourceId={"a".repeat(32)}
        source={{
          research_range: { start: "2016-01-01", end: "2019-12-31" },
          report: {
            research_mode: "exploratory",
            predictive_performance: { ridge: {} },
          },
        }}
        queued={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "protected 2019 holdout",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Changing only the backtest dates",
    );
    expect(
      screen.getByRole("button", { name: "Evaluate strategy" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Backtest end date"), {
      target: { value: "2018-12-31" },
    });
    expect(
      screen.getByRole("button", { name: "Evaluate strategy" }),
    ).toBeDisabled();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("displays the server's specific validation message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                code: "validation",
                message:
                  "holding sessions: Input should be greater than or equal to 1",
              },
            }),
            { status: 422 },
          ),
      ),
    );
    render(
      <StrategyEvaluation
        sourceId={"a".repeat(32)}
        source={{
          research_range: { start: "2020-01-01", end: "2024-12-31" },
          report: {
            research_mode: "exploratory",
            predictive_performance: { ridge: {} },
          },
        }}
        queued={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Evaluate strategy" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "holding sessions",
    );
  });
});

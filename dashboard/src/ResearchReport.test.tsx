import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import fixture from "../e2e/fixtures/readable-report.json";
import { ResearchReport } from "./ResearchReport";

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const metric = (label: string) =>
  within(
    screen
      .getByText(label, { selector: ".metric > span" })
      .closest(".metric") as HTMLElement,
  );

describe("readable workflow results", () => {
  it("formats actual report units and separates evaluation from the full dataset", () => {
    render(<ResearchReport data={fixture} />);
    expect(metric("Direction accuracy").getByText("53.8%")).toBeInTheDocument();
    expect(
      metric("Average prediction error").getByText("3.71 pp"),
    ).toBeInTheDocument();
    expect(
      metric("Stock ranking correlation").getByText("-0.006"),
    ).toBeInTheDocument();
    expect(metric("Evaluation samples").getByText("1,240")).toBeInTheDocument();
    expect(
      screen.getByText(/3,760 usable dataset samples/),
    ).toBeInTheDocument();
    expect(screen.getByText(/2016-01-01 – 2019-12-31/)).toBeInTheDocument();
    expect(screen.getByText(/2019-10-01 – 2019-12-20/)).toBeInTheDocument();
    expect(
      screen.getByText(/not automatically an improvement/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Zero does not certify/)).toBeInTheDocument();
    expect(screen.getByText(/Raw splits and dividends/)).toBeInTheDocument();
    expect(screen.getByText("0.0512")).toBeInTheDocument();
  });
  it("uses probability units for classifiers rather than percentage-point return errors", () => {
    const data = structuredClone(fixture);
    Object.assign(data.report.predictive_performance, {
      logistic: {
        samples: 1240,
        mean_absolute_error: 0.2,
        directional_accuracy: 0.6,
        rank_information_coefficient: null,
        error_target: "positive_excess_price_change_probability",
      },
    });
    render(<ResearchReport data={data} />);
    fireEvent.change(screen.getByLabelText("Result model"), {
      target: { value: "logistic" },
    });
    expect(metric("Probability error").getByText("0.200")).toBeInTheDocument();
    expect(metric("Direction accuracy").getByText("60.0%")).toBeInTheDocument();
    expect(
      metric("Stock ranking correlation").getByText("Not available"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Model comparison" }),
    ).toBeInTheDocument();
  });
  it("does not display missing metrics as zero", () => {
    render(
      <ResearchReport
        data={{
          report: {
            predictive_performance: {
              ridge: {
                samples: 0,
                directional_accuracy: null,
                mean_absolute_error: null,
                rank_information_coefficient: null,
              },
            },
          },
        }}
      />,
    );
    expect(
      metric("Direction accuracy").getByText("Not available"),
    ).toBeInTheDocument();
    expect(
      metric("Average prediction error").getByText("Not available"),
    ).toBeInTheDocument();
    expect(metric("Evaluation samples").getByText("0")).toBeInTheDocument();
  });
  it("shows blocked reasons and per-symbol download failures without requiring JSON", () => {
    render(
      <ResearchReport
        data={{ status: "BLOCKED_DATA", reason: "Insufficient sessions" }}
      />,
    );
    expect(screen.getByText("Insufficient sessions")).toBeInTheDocument();
    cleanup();
    render(
      <ResearchReport
        data={{
          status: "PARTIAL",
          workflow: "download",
          snapshots: [
            { symbol: "AAPL", status: "CREATED", rows: 1500 },
            {
              symbol: "SPY",
              status: "FAILED",
              reason: "Provider access denied",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("1,500")).toBeInTheDocument();
    expect(screen.getByText("Provider access denied")).toBeInTheDocument();
  });
});

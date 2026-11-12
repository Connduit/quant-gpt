import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { request, setToken } from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  setToken("");
});
function mount(path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const artifact = {
  id: "rejected",
  kind: "research",
  label: "Rejected ES research",
  mode: "ARCHIVAL_RESEARCH",
  status: "REJECTED",
  summary: { candidates: 9 },
  updated_at: "2026-11-12T00:00:00Z",
};
function mockApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const data = input.includes("/health")
        ? {
            status: "LIMITED",
            live_enabled: false,
            streaming_verified: false,
            eligible_strategies: 0,
            paper_accounts: 0,
            warnings: ["Streaming is unverified"],
            catalog_errors: [],
            jobs: [],
          }
        : input.includes("/overview")
          ? { items: [artifact], paper: null }
          : input.includes("/artifacts/rejected")
            ? {
                record: artifact,
                data: {
                  results: [
                    { status: "REJECTED", reason: "insufficient sessions" },
                  ],
                },
                series: [],
              }
            : { items: [artifact], total: 1, offset: 0, limit: 20 };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}
describe("dashboard evidence boundaries", () => {
  it("renders unavailable data and disabled live execution without fabricated returns", async () => {
    mockApi();
    mount();
    expect(await screen.findByText("Rejected ES research")).toBeVisible();
    expect(
      screen.getByText("No strategy is approved for live trading."),
    ).toBeVisible();
    expect(screen.getByText("Unavailable")).toBeVisible();
    expect(screen.getByText("Streaming is unverified")).toBeVisible();
  });
  it("browses rejected experiments and exposes actual rejection details", async () => {
    mockApi();
    mount("/research");
    fireEvent.click(
      await screen.findByRole("button", { name: "Rejected ES research" }),
    );
    expect(
      await screen.findByText(
        "Full artifact · configuration, metrics and limitations",
      ),
    ).toBeVisible();
    expect(screen.getAllByText(/REJECTED/).length).toBeGreaterThan(0);
  });
  it("reports API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { message: "Authentication required" } }),
            { status: 401 },
          ),
      ),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Authentication required",
    );
  });
  it("never puts bearer tokens in URLs", async () => {
    const fetcher = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetcher);
    setToken("test-token");
    await request("/health");
    const [url, options] = fetcher.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).not.toContain("test-token");
    expect((options.headers as Record<string, string>).Authorization).toBe(
      "Bearer test-token",
    );
  });
});

it("escapes spreadsheet formulas in exported CSV", async () => {
  const { csvText } = await import("./api");
  expect(csvText([{ symbol: "=SUM(A1)", quantity: -1 }])).toContain(
    "'=SUM(A1)",
  );
  expect(csvText([{ quantity: -1 }])).toContain('"-1"');
});

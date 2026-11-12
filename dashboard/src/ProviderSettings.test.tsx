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
import { ProviderSettings } from "./ProviderSettings";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function mount(editable = true, saved = false) {
  const mutations = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, options: RequestInit = {}) => {
      if (options.method) {
        mutations(options.method, JSON.parse(String(options.body)));
        saved = options.method !== "DELETE";
        return new Response(JSON.stringify({ status: "SAVED" }), {
          status: 200,
        });
      }
      return new Response(
        JSON.stringify({
          editable,
          items: ["alpaca", "databento"].map((id) => ({
            id,
            configured: saved,
            saved,
            source: saved ? "dashboard" : "none",
            host:
              id === "alpaca" ? "data.alpaca.markets" : "hist.databento.com",
          })),
        }),
        { status: 200 },
      );
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ProviderSettings />
    </QueryClientProvider>,
  );
  return mutations;
}

describe("provider key settings", () => {
  it("saves masked Alpaca fields and clears inputs without returning saved values", async () => {
    const mutations = mount();
    const key = await screen.findByLabelText("Alpaca API key ID");
    await waitFor(() => expect(key).toBeEnabled());
    expect(key).toHaveAttribute("type", "password");
    fireEvent.change(key, { target: { value: "invented-private-key" } });
    fireEvent.change(screen.getByLabelText("Alpaca secret key"), {
      target: { value: "invented-private-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Alpaca keys" }));
    await screen.findByText(/API keys saved/);
    expect(mutations).toHaveBeenCalledWith("PUT", {
      key_id: "invented-private-key",
      secret_key: "invented-private-secret",
      confirmed: true,
    });
    expect(key).toHaveValue("");
    expect(screen.getByLabelText("Alpaca secret key")).toHaveValue("");
    expect(document.body.textContent).not.toContain("invented-private-secret");
  });
  it("saves and removes Databento keys from the same page", async () => {
    const mutations = mount();
    const key = screen.getByLabelText("Databento API key");
    await waitFor(() => expect(key).toBeEnabled());
    fireEvent.change(key, { target: { value: "invented-databento-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Databento key" }));
    await screen.findByText(/API keys saved/);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Remove Databento key" }),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Remove Databento key" }),
    );
    await screen.findByText(/Saved keys removed/);
    expect(mutations).toHaveBeenLastCalledWith("DELETE", { confirmed: true });
    expect(key).toHaveValue("");
  });
  it("shows operator authorization requirement and never prepopulates configured keys", async () => {
    mount(false, true);
    await screen.findByText(/Connect with an operator access token/);
    expect(
      screen.getByRole("button", { name: "Save Alpaca keys" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Save Databento key" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Alpaca API key ID")).toHaveValue("");
    expect(screen.getByLabelText("Databento API key")).toHaveValue("");
    expect(
      screen.getByText(/Saving keys does not change its firewall/),
    ).toBeVisible();
  });
});

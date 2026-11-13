import { test, expect } from "@playwright/test";

test("historical form submits a bounded snapshot request", async ({ page }) => {
  let submitted: unknown;
  await page.route("**/api/v1/workflows/download", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { id: "browser-form-check" } });
  });
  await page.goto("/datasets");
  await page.getByLabel("US equity symbols").fill("AAPL, SPY");
  await page.getByLabel("Start date", { exact: true }).fill("2020-01-02");
  await page.getByLabel("End date", { exact: true }).fill("2024-01-10");
  await page
    .getByRole("button", { name: "Download & create snapshots", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Queued browser-form-check" }),
  ).toBeVisible();
  expect(submitted).toEqual({
    provider: "alpaca",
    alpaca_feed: "sip",
    databento_dataset: "XNAS.ITCH",
    maximum_download_cost: 0,
    symbols: ["AAPL", "SPY"],
    start: "2020-01-02",
    end: "2024-01-10",
    refresh: false,
    confirmed: true,
  });
});

test("eligible selection reaches the training request without a command line", async ({
  page,
}) => {
  await page.route("**/api/v1/workflows/snapshots", (route) =>
    route.fulfill({
      json: {
        items: ["AAA", "SPY"].map((symbol, i) => ({
          id: String(i + 1).repeat(64),
          symbol,
          start: "2014-01-02",
          end: "2018-12-31",
          rows: 1200,
          eligible: true,
          price_basis: "unadjusted",
          provider: "browser-fixture",
          blockers: [],
        })),
        errors: [],
      },
    }),
  );
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/v1/workflows/research", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      json: { id: "browser-training-check" },
    });
  });
  await page.goto("/models");
  await expect(
    page.getByRole("button", { name: "Start ML training", exact: true }),
  ).toBeDisabled();
  await page.getByRole("checkbox", { name: /^Select AAA/ }).check();
  await page.getByRole("checkbox", { name: /^Select SPY/ }).check();
  await page
    .getByRole("button", { name: "Start ML training", exact: true })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Queued browser-training-check" }),
  ).toBeVisible();
  expect(submitted?.workflow).toBe("training");
  expect(submitted?.snapshot_ids).toEqual(["1".repeat(64), "2".repeat(64)]);
});

test("discovery remains usable at a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/discovery");
  await expect(page.getByLabel("Maximum search trials")).toHaveValue("4");
  await expect(
    page.getByRole("button", { name: "Start bounded discovery", exact: true }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Databento provider selection sends a bounded explicit cost authorization", async ({
  page,
}) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/v1/workflows/download", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { id: "databento-form-check" } });
  });
  await page.goto("/datasets");
  await page.getByLabel("End date", { exact: true }).fill("2024-01-31");
  await page.getByLabel("Historical data provider").selectOption("databento");
  await expect(page.getByLabel("Start date", { exact: true })).toHaveValue(
    "2024-01-01",
  );
  await page.getByLabel("Maximum estimated download cost (USD)").fill("1.25");
  await page
    .getByRole("button", { name: "Download & create snapshots", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Queued databento-form-check" }),
  ).toBeVisible();
  expect(submitted?.provider).toBe("databento");
  expect(submitted?.maximum_download_cost).toBe(1.25);
  expect(submitted?.databento_dataset).toBe("XNAS.ITCH");
});

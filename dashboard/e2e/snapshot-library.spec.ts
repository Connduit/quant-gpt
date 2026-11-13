import { test, expect } from "@playwright/test";

test("large snapshot library stays compact, searchable and collapsible on desktop and mobile", async ({
  page,
}) => {
  const items = Array.from({ length: 50 }, (_, index) => ({
    id: index.toString(16).padStart(64, "0"),
    symbol: `STK${String(index).padStart(2, "0")}`,
    start: "2020-01-02",
    end: "2024-12-31",
    rows: 1200,
    provider: "alpaca",
    price_basis: "unadjusted",
    retrieved_at: "2026-01-01",
    dataset_role: index % 2 ? "protected_test" : "training",
    eligible: index % 2 === 0,
    blockers: index % 2 ? ["Protected test snapshot"] : [],
  }));
  await page.route("**/api/v1/workflows/snapshots**", (route) =>
    route.fulfill({ json: { items, errors: [] } }),
  );
  await page.goto("/datasets");
  const library = page.getByRole("region", {
    name: "Historical snapshots",
    exact: true,
  });
  await expect(library.getByRole("row")).toHaveCount(9);
  expect((await library.boundingBox())!.height).toBeLessThanOrEqual(440);
  await page
    .getByRole("button", { name: "Next snapshots", exact: true })
    .click();
  await expect(page.getByText("Page 2 of 7", { exact: true })).toBeVisible();
  await page.getByLabel("Search snapshots", { exact: true }).fill("STK49");
  await expect(library.getByRole("row")).toHaveCount(2);
  await expect(library.getByText("STK49", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Clear filters", exact: true })
    .click();
  await page
    .getByLabel("Dataset role", { exact: true })
    .selectOption("training");
  await expect(page.getByText(/of 25 · 50 total/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Hide snapshots", exact: true })
    .click();
  await expect(library).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Equity workflow jobs", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Show snapshots", exact: true })
    .click();
  await expect(library.getByRole("row")).toHaveCount(9);
});

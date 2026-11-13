import { test, expect } from "@playwright/test";
import fixture from "./fixtures/profitability-report.json" with { type: "json" };

test("saved ML report launches strategy evaluation and presents net profitability", async ({
  page,
}) => {
  const source = "c".repeat(32),
    evaluated = "d".repeat(32);
  let submitted: Record<string, unknown> | undefined;
  const sourceReport = {
    status: "COMPLETED",
    workflow: "training",
    research_status: "EXPLORATORY_ML",
    research_range: { start: "2016-01-01", end: "2018-12-31" },
    report: {
      name: "Browser source fixture",
      research_mode: "exploratory",
      predictive_performance: { ridge: { directional_accuracy: 0.53 } },
    },
  };
  await page.route("**/api/v1/jobs", (route) =>
    route.fulfill({
      json: {
        items: [
          ...(submitted
            ? [
                {
                  id: evaluated,
                  name: "profitability-evaluated",
                  status: "COMPLETED",
                  detail: "Completed",
                  created: "2026-11-13",
                },
              ]
            : []),
          {
            id: source,
            name: "training-saved",
            status: "COMPLETED",
            detail: "Completed",
            created: "2026-11-12",
          },
        ],
        approved: [],
      },
    }),
  );
  await page.route(`**/api/v1/workflows/jobs/${source}`, (route) =>
    route.fulfill({ json: { result: sourceReport } }),
  );
  await page.route(`**/api/v1/workflows/jobs/${evaluated}`, (route) =>
    route.fulfill({ json: { result: fixture } }),
  );
  await page.route("**/api/v1/workflows/profitability", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { id: evaluated } });
  });
  await page.goto("/models");
  await page.getByRole("button", { name: "View report", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Evaluate strategy profitability" }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Backtest evidence mode", { exact: true }),
  ).toHaveValue("exploratory");
  await page
    .getByRole("button", { name: "Evaluate strategy", exact: true })
    .click();
  await expect(
    page.getByRole("row").filter({ hasText: "profitability" }),
  ).toBeVisible();
  expect(submitted?.source_job_id).toBe(source);
  expect(submitted?.research_mode).toBe("exploratory");
  expect(submitted?.start).toBe("2016-01-01");
  expect(submitted?.commission_per_share).toBe(0.005);
  await page
    .getByRole("row")
    .filter({ hasText: "profitability" })
    .getByRole("button", { name: "View report" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Strategy profitability evaluation" }),
  ).toBeVisible();
  const metrics = page.locator(".result-metrics");
  await expect(metrics.getByText("35.29%", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Trading benchmark comparison" }),
  ).toBeVisible();
  await page.getByLabel("Cost scenario", { exact: true }).selectOption("high");
  await expect(metrics.getByText("32.08%", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Net equity versus benchmarks · high costs",
    }),
  ).toBeVisible();
  await expect(page.getByText(/No automatic qualification/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download trade logs and reports" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page
    .locator(".workflow-report")
    .screenshot({ path: "/workspace/work/phase12c-profitability-mobile.png" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .locator(".workflow-report")
    .screenshot({ path: "/workspace/work/phase12c-profitability-desktop.png" });
});

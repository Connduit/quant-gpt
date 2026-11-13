import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import fixture from "./fixtures/readable-report.json" with { type: "json" };

test("workflow report presents readable metrics, a chart, and the original JSON", async ({
  page,
}) => {
  await page.route("**/api/v1/jobs", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "readable",
            name: "training-readable",
            status: "COMPLETED",
            detail: "Completed",
            created: "2026-11-12T12:00:00Z",
          },
        ],
        approved: [],
      },
    }),
  );
  await page.route("**/api/v1/workflows/jobs/readable", (route) =>
    route.fulfill({ json: { result: fixture } }),
  );
  await page.goto("/models");
  await page.getByRole("button", { name: "View report", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Equity research", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".result-metrics").getByText("53.8%", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".result-metrics").getByText("3.71 pp", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Results by time period" }),
  ).toBeVisible();
  await expect(page.locator(".result-chart .recharts-line-curve")).toHaveCount(
    2,
  );
  await page
    .getByRole("region", { name: "Results by time period" })
    .getByLabel("Chart metric", { exact: true })
    .selectOption("rank_information_coefficient");
  await expect(
    page.getByRole("img", {
      name: /Ridge validation and evaluation ranking correlation/,
    }),
  ).toBeVisible();
  const raw = page
    .locator("details")
    .filter({ has: page.locator("summary", { hasText: "Raw report JSON" }) });
  await expect(raw).not.toHaveAttribute("open");
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download report JSON" }).click();
  const download = await waiting;
  expect(download.suggestedFilename()).toBe("equity-readable.json");
  expect(JSON.parse(await readFile((await download.path())!, "utf8"))).toEqual(
    fixture,
  );
  await raw.locator("summary").click();
  await expect(raw.locator("pre")).toContainText(
    '"research_mode": "exploratory"',
  );
  await raw.locator("summary").click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.locator(".result-metrics").getByText("53.8%", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.locator(".workflow-report").screenshot({
    path: "/workspace/work/readable-report-mobile.png",
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator(".workflow-report").screenshot({
    path: "/workspace/work/readable-report-desktop.png",
  });
});

import { test, expect } from "@playwright/test";

test("preset downloads a training/test pair with SPY and all seven stocks", async ({
  page,
}) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/v1/workflows/download-pair", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { id: "paired-browser-job" } });
  });
  await page.route("**/api/v1/workflows/snapshots*", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "a".repeat(64),
            symbol: "AAPL",
            start: "2020-01-01",
            end: "2024-12-31",
            rows: 1258,
            provider: "browser-test",
            price_basis: "unadjusted",
            dataset_role: "training",
            eligible: false,
            blockers: ["Complete corporate-action ledger is missing"],
          },
          {
            id: "b".repeat(64),
            symbol: "AAPL",
            start: "2025-01-01",
            end: "2026-11-12",
            rows: 470,
            provider: "browser-test",
            price_basis: "unadjusted",
            dataset_role: "protected_test",
            eligible: false,
            blockers: [
              "Protected test snapshot: sealed; unavailable for routine training or evaluation",
            ],
          },
        ],
        errors: [],
      },
    }),
  );
  await page.goto("/datasets");
  const quick = page.getByRole("region", {
    name: "Quick training and test downloads",
  });
  await expect(quick.getByLabel("Training/test symbols")).toHaveValue(
    "SPY, AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA",
  );
  await expect(page.getByLabel("US equity symbols")).toHaveValue(
    "SPY, AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA",
  );
  await quick
    .getByLabel("Training/test preset", { exact: true })
    .selectOption("legacy");
  await expect(
    quick.getByText("2016-01-01 – 2018-12-31", { exact: true }),
  ).toBeVisible();
  await expect(
    quick.getByText("2019-01-01 – 2019-12-31", { exact: true }),
  ).toBeVisible();
  await quick
    .getByRole("button", {
      name: "Download training + protected test snapshots",
      exact: true,
    })
    .click();
  await expect(quick.getByRole("status")).toContainText(
    "Queued paired-browser-job",
  );
  expect(submitted?.start).toBe("2016-01-01");
  expect(submitted?.split_date).toBe("2019-01-01");
  expect(submitted?.end).toBe("2019-12-31");
  expect(submitted?.symbols).toEqual([
    "SPY",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "NVDA",
    "TSLA",
  ]);
  await expect(
    page.getByText("Protected test · sealed", { exact: true }),
  ).toBeVisible();
  await page.goto("/models");
  await page
    .getByLabel("Research mode", { exact: false })
    .selectOption("exploratory");
  await expect(
    page.getByRole("checkbox", { name: /^Select AAPL bbbbb/ }),
  ).toBeDisabled();
  await page.goto("/datasets");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
});

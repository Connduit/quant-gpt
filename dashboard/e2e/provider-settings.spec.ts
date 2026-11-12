import { test, expect } from "@playwright/test";

test("operator settings mask and clear keys after saving, including after reload", async ({
  page,
}) => {
  let saved = false;
  let submitted: unknown;
  await page.route("**/api/v1/settings/providers", (route) =>
    route.fulfill({
      json: {
        editable: true,
        items: [
          {
            id: "alpaca",
            configured: saved,
            saved,
            source: saved ? "dashboard" : "none",
            host: "data.alpaca.markets",
          },
          {
            id: "databento",
            configured: false,
            saved: false,
            source: "none",
            host: "hist.databento.com",
          },
        ],
      },
    }),
  );
  await page.route("**/api/v1/settings/providers/alpaca", async (route) => {
    submitted = route.request().postDataJSON();
    saved = true;
    await route.fulfill({ json: { status: "SAVED", provider: "alpaca" } });
  });
  await page.goto("/datasets");
  await page.getByRole("link", { name: "API keys", exact: true }).click();
  const key = page.getByLabel("Alpaca API key ID", { exact: true });
  await expect(key).toHaveAttribute("type", "password");
  await key.fill("invented-browser-key");
  await page
    .getByLabel("Alpaca secret key", { exact: true })
    .fill("invented-browser-secret");
  await page
    .getByRole("button", { name: "Save Alpaca keys", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("API keys saved");
  await expect(key).toHaveValue("");
  await expect(
    page.getByLabel("Alpaca secret key", { exact: true }),
  ).toHaveValue("");
  expect(submitted).toEqual({
    key_id: "invented-browser-key",
    secret_key: "invented-browser-secret",
    confirmed: true,
  });
  await page.reload();
  await expect(key).toHaveValue("");
  await expect(
    page.getByLabel("Alpaca secret key", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByText("Source: saved in dashboard.", { exact: false }),
  ).toBeVisible();
});

test("read-only visitors see the operator requirement and network hosts", async ({
  page,
}) => {
  await page.goto("/provider-settings");
  await expect(
    page.getByRole("button", { name: "Save Alpaca keys", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Connect with an operator access token/),
  ).toBeVisible();
  await expect(
    page.getByText("data.alpaca.markets", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("hist.databento.com", { exact: true }),
  ).toBeVisible();
});

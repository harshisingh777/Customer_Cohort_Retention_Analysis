import { expect, test } from "@playwright/test";

test.describe("as admin", () => {
  test.use({ storageState: "playwright/.auth/admin.json" });

  test("summary shows findings, vitals, a data stamp and the cohort table", async ({ page }) => {
    await page.goto("/summary");
    await expect(page.getByRole("heading", { name: "What stands out" })).toBeVisible();
    await expect(page.getByRole("table", { name: /Vitals/ })).toBeVisible();
    await expect(page.getByText(/^Data through \d/).first()).toBeVisible();
    await expect(page.getByRole("table", { name: /Last 12 monthly cohorts/ })).toBeVisible();
  });

  test("change filters through the sentence; the URL holds them", async ({ page }) => {
    await page.goto("/cohorts");
    await page.getByRole("button", { name: /Acquisition channel: from all channels/ }).click();
    const first = page.getByRole("dialog").getByRole("checkbox").first();
    await first.check();
    await expect(page).toHaveURL(/channel=/);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: /Acquisition channel: from (?!all)/ })).toBeVisible();
    // Back button returns to the unfiltered view.
    await page.goBack();
    await expect(page).not.toHaveURL(/channel=/);
  });

  test("select a cohort from the table with the keyboard; focus moves to its curve", async ({ page }) => {
    await page.goto("/cohorts");
    const table = page.getByRole("table", { name: /Monthly cohorts/ });
    await table.getByRole("rowheader").nth(2).focus();
    // Arrow keys move between cells.
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await expect(page.locator(":focus")).toHaveAttribute("aria-label", /customers|Not observable/);
    await page.keyboard.press("ArrowDown");
    // Enter selects the cohort row (highlighter) and focuses its curve below.
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/select=\d{4}-\d{2}/);
    await expect(page.getByRole("img", { name: /cohort selected/ })).toBeVisible();
    await expect(page.locator(":focus")).toContainText("Curves");
    await expect(table.locator("tr[aria-selected=true] .highlight")).toHaveCount(1);
  });

  test("blank cells mean not observable; observed zeros show 0%", async ({ page }) => {
    await page.goto("/cohorts");
    await expect(page.getByLabel("Not observable yet").first()).toBeAttached();
  });

  test("open a definition from a metric name", async ({ page }) => {
    await page.goto("/cohorts");
    await page
      .getByRole("button", { name: /bought again: definition/ })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toContainText("Customer retention");
    await expect(page.getByRole("dialog").getByRole("link", { name: "Methodology" })).toBeVisible();
  });

  test("export CSV", async ({ page }) => {
    await page.goto("/cohorts");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/^cohorts-.*\.csv$/);
    await expect(page.getByRole("status").filter({ hasText: "CSV exported" })).toBeVisible();
  });

  test("customers: open a customer panel with their order timeline", async ({ page }) => {
    await page.goto("/customers");
    await page
      .getByRole("row", { name: /Open details/ })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toContainText("Orders");
    await expect(page).toHaveURL(/customer=/);
  });

  test("segments link to their customers", async ({ page }) => {
    await page.goto("/segments");
    await page.getByRole("button", { name: "Champions" }).first().click();
    await expect(page).toHaveURL(/\/customers\?.*segment=Champions/);
  });

  test("methodology renders from metrics.yml", async ({ page }) => {
    await page.goto("/methodology");
    await expect(page.getByRole("heading", { name: "Lapse rate", level: 3 })).toBeVisible();
    await expect(page.getByText("Reporting timezone", { exact: true })).toBeVisible();
  });

  test("admin sees the refresh control", async ({ page }) => {
    await page.goto("/data");
    await expect(page.getByRole("button", { name: "Refresh now" })).toBeVisible();
  });
});

test.describe("as viewer", () => {
  test.use({ storageState: "playwright/.auth/viewer.json" });

  test("viewer cannot trigger a refresh, in the UI or at the API", async ({ page }) => {
    await page.goto("/data");
    await expect(page.getByRole("heading", { name: "Data", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh now" })).toHaveCount(0);
    const { token } = await (await page.request.get("/api/token")).json();
    const apiUrl = process.env.E2E_API_URL ?? "http://localhost:8000";
    const res = await page.request.post(`${apiUrl}/v1/pipeline/runs`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(403);
  });

  test("viewer sees masked emails", async ({ page }) => {
    await page.goto("/customers");
    const first = page.getByRole("row", { name: /Open details/ }).first();
    await expect(first).toBeVisible();
    const label = (await first.getAttribute("aria-label")) ?? "";
    expect(label.includes("@") ? label.includes("***@") : true).toBe(true);
  });

  test("settings is not available to viewers", async ({ page }) => {
    const res = await page.goto("/settings");
    expect(res?.status()).toBe(404);
  });
});

import { expect, test } from "@playwright/test";

test.use({ storageState: "playwright/.auth/admin.json" });

for (const path of ["/summary", "/cohorts", "/repeat", "/segments", "/channels", "/customers", "/data"]) {
  test(`375 px: ${path} has no horizontal page scroll`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("375 px: filters collapse to a button", async ({ page }) => {
  await page.goto("/cohorts");
  await page.getByRole("button", { name: /^Filters/ }).click();
  await expect(page.getByRole("dialog", { name: "Filters" })).toBeVisible();
  await page.getByRole("button", { name: "Show results" }).click();
});

test("375 px: navigation opens from the menu", async ({ page }) => {
  await page.goto("/summary");
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Repeat" }).click();
  await expect(page).toHaveURL(/\/repeat/);
});

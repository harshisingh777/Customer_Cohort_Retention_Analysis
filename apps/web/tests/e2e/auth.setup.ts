import { expect, test as setup } from "@playwright/test";

export const ADMIN = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
export const VIEWER = process.env.E2E_VIEWER_EMAIL ?? "viewer@example.com";

for (const [name, email] of [
  ["admin", ADMIN],
  ["viewer", VIEWER],
] as const) {
  setup(`sign in as ${name}`, async ({ page }) => {
    await page.goto("/sign-in");
    await page.getByLabel("Development sign-in (local and CI only)").fill(email);
    await page.getByRole("button", { name: "Sign in without a link" }).click();
    await expect(page).toHaveURL(/\/summary/);
    await expect(page.getByRole("heading", { name: "Summary", level: 1 })).toBeVisible();
    await page.context().storageState({ path: `playwright/.auth/${name}.json` });
  });
}

setup("an uninvited email is refused", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Development sign-in (local and CI only)").fill("stranger@example.com");
  await page.getByRole("button", { name: "Sign in without a link" }).click();
  await expect(page.getByText("This email isn't invited")).toBeVisible();
});

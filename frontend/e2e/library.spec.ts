import { expect, test } from "@playwright/test";
import { register } from "./helpers";

test("library lists domains and opens a system graph", async ({ page }) => {
  await register(page);
  await page.goto("/library");
  await page.getByRole("tab", { name: "Domains" }).click();
  await expect(page.getByRole("button", { name: "Browse systems" }).first()).toBeVisible();
  await page.getByRole("tab", { name: "Systems" }).click();
  await page.getByRole("button", { name: "View graph" }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("settings shows provider status without key values", async ({ page }) => {
  await register(page);
  await page.goto("/settings");
  await expect(page.getByText("local", { exact: true })).toBeVisible();
  await expect(page.getByText(/sk-/)).toHaveCount(0);
});

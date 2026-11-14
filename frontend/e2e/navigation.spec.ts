import { expect, test } from "@playwright/test";
import { register } from "./helpers";

const SECTIONS: Array<[string, string]> = [
  ["Overview", "/"], ["New Discovery", "/new"], ["My Investigations", "/investigations"], ["Structural DNA", "/dna"],
  ["Discovery Universe", "/universe"], ["Transformation Studio", "/transformation"], ["Hypothesis Arena", "/hypotheses"],
  ["Validation Lab", "/validation"], ["Discovery Archive", "/archive"], ["Knowledge Library", "/library"], ["Settings", "/settings"],
];

test("unauthenticated users are sent to login", async ({ page }) => {
  await page.goto("/investigations");
  await expect(page).toHaveURL(/\/login/);
});

test("all eleven sections are reachable from the sidebar", async ({ page }) => {
  await register(page);
  for (const [label, path] of SECTIONS) {
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: label }).click();
    await expect(page).toHaveURL(new RegExp(`${path === "/" ? "/$" : path}`));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  }
});

test("command palette navigates with the keyboard", async ({ page }) => {
  await register(page);
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: "Search pages" }).fill("library");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/library/);
});

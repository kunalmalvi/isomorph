import { expect, test } from "@playwright/test";
import { register } from "./helpers";

const STATEMENT =
  "Strip made of copper or silver must be reduced in thickness by passing it between two rollers. The roller force must not exceed 90 kN. " +
  "The strip thickness deviates when the load varies, and the mill stand stretches under force.";

test("flagship flow: describe a problem, watch stages, inspect results", async ({ page }) => {
  await register(page);
  await page.goto("/new");
  await page.getByLabel("Title").fill("Reduce strip thickness");
  await page.getByLabel("Problem statement").fill(STATEMENT);
  await page.getByRole("button", { name: "Save problem" }).click();
  await page.getByRole("button", { name: "Start discovery" }).click();

  await expect(page).toHaveURL(/\/investigations\//);
  await expect(page.getByRole("list", { name: "Pipeline stages" })).toBeVisible();
  await expect(page.getByText(/9 of 9 stages complete/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "Ranked matches" })).toBeVisible();

  await page.goto("/dna");
  await expect(page.getByRole("heading", { name: "Structural DNA" })).toBeVisible();
  await expect(page.getByText(/Structural fingerprint/)).toBeVisible();

  await page.goto("/universe");
  await expect(page.getByRole("img", { name: /Scatter chart/ })).toBeVisible();

  await page.goto("/hypotheses");
  await expect(page.getByText(/stored in this browser only/)).toBeVisible();
  await page.goto("/validation");
  await expect(page.getByText(/not real world evidence/i)).toBeVisible();
});

test("an invalid stage edit is shown as an error", async ({ page }) => {
  await register(page);
  await page.goto("/new");
  await page.getByLabel("Title").fill("Edit test");
  await page.getByLabel("Problem statement").fill(STATEMENT);
  await page.getByRole("button", { name: "Save problem" }).click();
  await page.getByRole("button", { name: "Start discovery" }).click();
  await expect(page.getByText(/9 of 9 stages complete/)).toBeVisible({ timeout: 45_000 });
  await page.getByRole("tab", { name: "Edit and rerun" }).click();
  await page.getByLabel("Stage output JSON").fill("[1, 2");
  await page.getByRole("button", { name: "Save edit" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
});

test("weights that do not total 100 block the start button", async ({ page }) => {
  await register(page);
  await page.goto("/new");
  await page.getByRole("tab", { name: "Advanced" }).click();
  await page.getByLabel("Functional").fill("40");
  await expect(page.getByText(/must be 100/)).toBeVisible();
});

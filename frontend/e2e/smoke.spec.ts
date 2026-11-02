import { expect, test } from "@playwright/test";

test("login, ask, citation click, quiz start", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));

  // login
  await page.goto("/login");
  await page.fill("#username", "student1");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ask$/);
  await expect(page.getByText("What would you like to know?")).toBeVisible();

  // a reload keeps the session
  await page.reload();
  await expect(page.getByText("What would you like to know?")).toBeVisible();

  // ask
  await page.getByRole("button", { name: "What are the boundaries and contents of the femoral triangle?" }).click();
  await expect(page.getByText("The femoral triangle is a region in the upper anterior thigh.")).toBeVisible({ timeout: 15_000 });

  // citation click opens the source panel at that source
  await page.getByRole("button", { name: "Source 1" }).first().click();
  await expect(page.getByText("Source 1 of 2")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lecture notes" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("Source 1 of 2")).toBeHidden();

  // quiz start
  await page.getByRole("link", { name: "Quiz" }).click();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.getByRole("button", { name: "Build quiz" }).click();
  await expect(page.getByText("Preparing your quiz")).toBeVisible();
  await expect(page.getByText("Question 1 of 5")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("radio").nth(1).click();
  await expect(page.getByRole("radio").nth(1)).toHaveAttribute("aria-checked", "true");

  expect(errors).toEqual([]);
});

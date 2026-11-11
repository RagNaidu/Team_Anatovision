/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";

/** The app shell is fixed-height: the window never scrolls, the sidebar (or the mobile top bar) never moves, only <main> scrolls. */
const SHOTS = process.env.SHELL_SHOTS_DIR ?? "../reports/ui_screenshots/react";
const TAG = process.env.SHELL_TAG ?? "after";

async function login(page: Page, user = "student1") {
  await page.goto("/login");
  await page.fill("#username", user);
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/(ask|admin)/);
}

/** The window must be exactly the viewport tall, and the fixed bar (sidebar on desktop, top bar on a phone) must sit at the top. */
async function assertShellStill(page: Page, mobile: boolean) {
  const m = await page.evaluate((mobile) => {
    const bar = mobile ? document.querySelector("header") : document.querySelector("[data-testid=app-sidebar]");
    const r = bar!.getBoundingClientRect();
    return { docH: document.documentElement.scrollHeight, vh: window.innerHeight, winY: window.scrollY, barTop: r.top, barH: r.height };
  }, mobile);
  expect.soft(m.docH, "document.scrollHeight must equal the viewport height").toBe(m.vh);
  expect.soft(m.winY).toBe(0);
  expect.soft(m.barTop, mobile ? "mobile top bar" : "sidebar").toBe(0);
  if (!mobile) expect.soft(m.barH).toBe(m.vh);
}

async function scrollMain(page: Page) {
  const main = page.locator("#main");
  const before = await main.evaluate((e) => ({ top: e.scrollTop, over: e.scrollHeight - e.clientHeight }));
  await page.mouse.move(mobileSafe(page), 400);
  await page.mouse.wheel(0, 3000);
  await page.waitForTimeout(250);
  const after = await main.evaluate((e) => e.scrollTop);
  return { before, after };
}
const mobileSafe = (page: Page) => Math.min(700, (page.viewportSize()?.width ?? 1000) - 40);

async function buildAndReach(page: Page) {
  await page.goto("/quiz");
  await page.getByRole("button", { name: /^Lectures/ }).click();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Build quiz" }).click();
  await expect(page.getByText("Question 1 of 5")).toBeVisible({ timeout: 20_000 });
  for (let i = 0; i < 4; i++) { await page.getByRole("radio").nth(0).click(); await page.getByRole("button", { name: "Next" }).click(); }
  await page.getByRole("radio").nth(0).click();
  await page.getByRole("button", { name: "Review answers" }).click();
  await expect(page).toHaveURL(/\/review$/);
  await page.getByRole("button", { name: "Submit quiz" }).click();
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(page).toHaveURL(/\/results$/, { timeout: 20_000 });
  await page.waitForTimeout(600);
}

for (const [w, h, name] of [[1440, 900, "1440"], [390, 844, "390"]] as const) {
  test(`Quiz page at ${w}x${h}: the sidebar stays put and only the main area scrolls`, async ({ page }) => {
    fs.mkdirSync(SHOTS, { recursive: true });
    await page.setViewportSize({ width: w, height: h });
    await login(page);
    await buildAndReach(page);
    const mobile = w < 1024;
    await assertShellStill(page, mobile);
    await page.screenshot({ path: `${SHOTS}/scroll-${TAG}-quiz-${name}-top.png` });
    const { before, after } = await scrollMain(page);
    expect.soft(before.over, "the results page must be taller than the window for this test to mean anything").toBeGreaterThan(0);
    expect.soft(after, "main scrollTop changes").toBeGreaterThan(before.top);
    await assertShellStill(page, mobile);
    await page.screenshot({ path: `${SHOTS}/scroll-${TAG}-quiz-${name}-scrolled.png` });
    // it ends where the quiz ends: scroll all the way down, then nothing is left below and the last element sits within the page padding of the bottom edge
    for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 1500); await page.waitForTimeout(150); }
    const end = await page.locator("#main").evaluate((e) => {
      const mb = e.getBoundingClientRect().bottom;
      let last = 0;
      e.querySelectorAll<HTMLElement>("*").forEach((n) => { const cs = getComputedStyle(n); if (cs.position !== "absolute" && cs.position !== "fixed" && n.offsetHeight > 0) last = Math.max(last, n.getBoundingClientRect().bottom); });
      return { left: e.scrollHeight - e.clientHeight - e.scrollTop, gap: mb - last };
    });
    expect.soft(end.left).toBeLessThanOrEqual(1);
    expect.soft(end.gap, "blank space below the last element").toBeLessThanOrEqual(48);
    await page.screenshot({ path: `${SHOTS}/scroll-${TAG}-quiz-${name}-end.png` });
    // scroll the WINDOW itself too (what a keyboard Space / PageDown or a scroll that chains out of the content does): it must not move anything
    await page.evaluate(() => window.scrollTo(0, 99999)); await page.waitForTimeout(150);
    await page.screenshot({ path: `${SHOTS}/scroll-${TAG}-quiz-${name}-window-scrolled.png` });
    // scrolling past the end does not drag the page or the sidebar along
    await page.mouse.wheel(0, 3000); await page.waitForTimeout(200);
    await assertShellStill(page, mobile);
  });
}

// Every other page uses the same shell: the window must never be taller than the viewport and the sidebar must not move.
const STUDENT = ["/ask", "/guide", "/quiz"];
const INSTRUCTOR = ["/admin", "/admin/notes", "/admin/bank", "/admin/review", "/admin/questions", "/admin/access"];
for (const [w, h] of [[1440, 900], [1440, 520], [390, 844]] as const) {
  test(`all pages keep a fixed shell at ${w}x${h}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    const mobile = w < 1024;
    await login(page, "student1");
    for (const path of STUDENT) {
      await page.goto(path); await page.waitForTimeout(400);
      await scrollMain(page);
      await assertShellStill(page, mobile);
    }
    await page.evaluate(() => { localStorage.clear(); });
    await page.context().clearCookies();
    await login(page, "inglis");
    for (const path of INSTRUCTOR) {
      await page.goto(path); await page.waitForTimeout(500);
      await scrollMain(page);
      await assertShellStill(page, mobile);
    }
  });
}

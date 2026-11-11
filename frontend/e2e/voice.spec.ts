/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";

/**
 * Voice input. Playwright cannot speak, so a FAKE SpeechRecognition is injected and the test says what the "person" said.
 * Nothing here proves the real microphone or the real speech service works.
 */
const SHOTS = process.env.SHELL_SHOTS_DIR ?? "../reports/ui_screenshots/react";

type Mode = "ok" | "denied" | "none";
async function fakeSpeech(page: Page, mode: Mode = "ok") {
  await page.addInitScript((mode) => {
    const w = window as unknown as Record<string, unknown>;
    if (mode === "none") { Object.defineProperty(window, "SpeechRecognition", { value: undefined, configurable: true }); Object.defineProperty(window, "webkitSpeechRecognition", { value: undefined, configurable: true }); return; }
    class FakeSR {
      lang = ""; continuous = false; interimResults = false;
      onresult: ((e: unknown) => void) | null = null; onerror: ((e: { error: string }) => void) | null = null; onend: (() => void) | null = null;
      constructor() { (w.__sr as unknown[]).push(this); }
      start() { (w.__srStarts as number[])[0]++; if (mode === "denied") setTimeout(() => { this.onerror?.({ error: "not-allowed" }); this.onend?.(); }, 0); }
      stop() { (w.__srStops as number[])[0]++; setTimeout(() => this.onend?.(), 0); }
      abort() { /* nothing */ }
    }
    w.__sr = []; w.__srStarts = [0]; w.__srStops = [0];
    // the engine's results are cumulative within a session: say([[text, isFinal], ...])
    w.__say = (items: Array<[string, boolean]>) => {
      const list = w.__sr as FakeSR[]; const cur = list[list.length - 1];
      const results = items.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f }));
      cur.onresult?.({ resultIndex: 0, results: Object.assign(results, { length: results.length }) });
    };
    w.SpeechRecognition = FakeSR; w.webkitSpeechRecognition = FakeSR;
  }, mode);
}
const say = (page: Page, items: Array<[string, boolean]>) => page.evaluate((i) => (window as unknown as { __say: (x: unknown) => void }).__say(i), items);
const started = (page: Page) => page.evaluate(() => (window as unknown as { __srStarts: number[] }).__srStarts[0]);

async function login(page: Page) {
  await page.goto("/login");
  await page.fill("#username", "student1");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ask$/);
}

test("Chat: dictation fills the box live, appends, stops after silence and is never sent until Enter", async ({ page }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  await fakeSpeech(page);
  await login(page);
  const box = page.locator("#composer");
  const mic = page.getByRole("button", { name: /^Start voice input for your question/ });
  await expect(mic).toBeVisible();
  const bb = await mic.boundingBox();
  expect(bb!.width).toBeLessThanOrEqual(32); expect(bb!.height).toBeLessThanOrEqual(32);   // a small icon...
  await expect(mic).toHaveCSS("border-top-width", "0px");                                  // ...with no bubble
  await expect(mic).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(mic.locator("svg")).toHaveAttribute("width", "16");
  await expect(page.getByTestId("handsfree-toggle")).toHaveCount(0);                       // and no Hands-free switch
  await expect(page.getByTestId("voice-privacy")).toHaveText("Voice is processed by your browser's speech service.");

  await box.fill("About the");                                      // text already in the box is kept
  await mic.click();
  await expect(page.getByTestId("voice-status")).toContainText("Listening…");
  await expect(page.getByRole("button", { name: /^Stop voice input/ })).toHaveAttribute("aria-pressed", "true");
  await say(page, [["femoral", false]]);
  await expect(box).toHaveValue("About the femoral");              // interim words appear live
  await say(page, [["femoral triangle", true]]);
  await expect(box).toHaveValue("About the femoral triangle");     // the final phrase replaces them
  await page.screenshot({ path: `${SHOTS}/voice-chat-listening-1440.png` });
  await say(page, [["femoral triangle", true], ["borders", false]]);
  await expect(box).toHaveValue("About the femoral triangle borders");

  // nothing was sent: no question in the conversation, the text is still in the box
  await expect(page.getByTestId("chat-scroll")).not.toContainText("femoral triangle borders");
  await expect(page.getByText("What would you like to know?")).toBeVisible();

  // about 3 seconds of silence stops listening by itself (and still sends nothing)
  await expect(page.getByTestId("voice-status")).toHaveText("", { timeout: 6000 });
  await expect(page.getByRole("button", { name: /^Start voice input/ })).toHaveAttribute("aria-pressed", "false");
  await expect(box).toHaveValue("About the femoral triangle borders");
  await expect(page.getByText("What would you like to know?")).toBeVisible();

  await box.press("Enter");                                         // the person reviews, then sends
  await expect(page.getByTestId("chat-scroll")).toContainText("About the femoral triangle borders");
  await expect(box).toHaveValue("");
});

test("Chat: tap the mic again to stop; typing while listening ends listening and keeps your edit", async ({ page }) => {
  await fakeSpeech(page);
  await login(page);
  const box = page.locator("#composer");
  await page.getByRole("button", { name: /^Start voice input/ }).click();
  await say(page, [["hello there", true]]);
  await expect(box).toHaveValue("hello there");
  await page.getByRole("button", { name: /^Stop voice input/ }).click();
  await expect(page.getByTestId("voice-status")).toHaveText("");
  await page.getByRole("button", { name: /^Start voice input/ }).click();
  await say(page, [["more", false]]);
  await expect(box).toHaveValue("hello there more");
  await box.press("End"); await box.pressSequentially("!");           // the person edits by hand while listening
  await expect(page.getByTestId("voice-status")).toHaveText("");
  await say(page, [["more words", true]]);                          // late words do not overwrite the edit
  await expect(box).toHaveValue("hello there more!");
});

test('Chat: the word "send" is just text, and nothing is sent by voice', async ({ page }) => {
  await fakeSpeech(page);
  await login(page);
  const box = page.locator("#composer");
  await page.getByRole("button", { name: /^Start voice input/ }).click();
  await say(page, [["what is the femoral triangle send it", true]]);
  await expect(box).toHaveValue("what is the femoral triangle send it");
  await page.getByRole("button", { name: /^Stop voice input/ }).click();
  await expect(page.getByText("What would you like to know?")).toBeVisible();     // still nothing sent
  await expect(page.getByTestId("handsfree-toggle")).toHaveCount(0);
});

test("Chat: microphone blocked shows a clear message; Firefox-style browsers get no mic, just the one-line reason", async ({ browser }) => {
  const denied = await browser.newPage();
  await fakeSpeech(denied, "denied");
  await login(denied);
  await denied.getByRole("button", { name: /^Start voice input/ }).click();
  await expect(denied.getByTestId("voice-error")).toContainText("The microphone is blocked");
  await expect(denied.getByRole("button", { name: /^Start voice input/ })).toBeVisible();
  await denied.getByRole("button", { name: "Dismiss" }).click();
  await expect(denied.getByTestId("voice-error")).toBeHidden();
  await denied.close();

  const none = await browser.newPage();
  await fakeSpeech(none, "none");
  await login(none);
  await expect(none.getByTestId("mic-button")).toHaveCount(0);
  const info = none.getByTestId("voice-unsupported");
  await info.focus();
  await expect(none.getByRole("tooltip")).toHaveText("Voice input works in Chrome, Edge and Safari");
    await none.close();
});

test("Guide: the describe box takes dictation and only Check sends it", async ({ page }) => {
  await fakeSpeech(page);
  await login(page);
  await page.goto("/guide/class-17/0");
  const box = page.locator("#describe");
  await expect(box).toBeVisible();
  const mic = page.getByRole("button", { name: /^Start voice input for your description/ });
  await expect(mic).toBeVisible();
  await mic.click();
  await say(page, [["I found the great saphenous vein", false]]);
  await expect(box).toHaveValue("I found the great saphenous vein");
  await say(page, [["I found the great saphenous vein", true]]);
  await page.getByRole("button", { name: /^Stop voice input/ }).click();
  await expect(page.getByText(/Correct|Partly|Not matching/).first()).toBeHidden();   // no verdict: nothing was checked
  await page.getByRole("button", { name: "Check", exact: true }).click();
  await expect(page.getByText(/^(Correct|Partly|Not matching)$/).first()).toBeVisible({ timeout: 15_000 });
});

test("Quiz: the topic field takes dictation; answers are picked by voice and always show what was heard", async ({ page }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  await fakeSpeech(page);
  await login(page);
  await page.getByRole("link", { name: "Quiz" }).click();
  await page.getByRole("radio", { name: "A topic" }).click();
  const topic = page.locator("#topic");
  const tmic = page.getByRole("button", { name: /^Start voice input for the topic/ });
  await expect(tmic).toBeVisible();
  const tb = await tmic.boundingBox(); expect(tb!.width).toBeLessThanOrEqual(32);
  await tmic.click();
  await say(page, [["rotator cuff muscles", true]]);
  await expect(topic).toHaveValue("rotator cuff muscles");
  await page.getByRole("button", { name: /^Stop voice input/ }).click();
  await expect(page.getByRole("button", { name: "Build quiz" })).toBeVisible();      // dictating never starts the quiz
  await expect(page).toHaveURL(/\/quiz$/);

  // a quiz from the notes, then answer by voice
  await page.getByRole("radio", { name: "My lectures and guides" }).click();
  await page.getByRole("button", { name: /^Lectures/ }).click();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Build quiz" }).click();
  await expect(page.getByText("Question 1 of 5")).toBeVisible({ timeout: 20_000 });
  const radios = page.getByRole("radio");
  const mic = page.getByRole("button", { name: /^Start voice answers for question 1/ });
  await expect(mic).toBeVisible();

  await expect(page.getByTestId("handsfree-toggle")).toHaveCount(0);
  await mic.click();
  await say(page, [["option b", true]]);
  await expect(page.getByTestId("quiz-heard")).toContainText("“option b”");
  await expect(radios.nth(1)).toHaveAttribute("data-pending", "true");           // marked, not saved
  await expect(radios.nth(1)).toHaveAttribute("aria-checked", "false");
  await page.screenshot({ path: `${SHOTS}/voice-quiz-heard-1440.png` });
  await say(page, [["option b", true], ["next", true]]);                          // "next" is refused while a letter is unconfirmed
  await expect(page.getByText("Question 1 of 5")).toBeVisible();
  await expect(page.getByTestId("quiz-heard")).toContainText("Say “submit” to save B first");
  await radios.nth(3).click();                                                    // a misheard letter is fixed by tapping
  await expect(radios.nth(3)).toHaveAttribute("aria-checked", "true");
  await expect(radios.nth(1)).not.toHaveAttribute("data-pending", "true");
  await say(page, [["option b", true], ["next", true], ["c", true]]);
  await expect(radios.nth(2)).toHaveAttribute("data-pending", "true");
  await say(page, [["option b", true], ["next", true], ["c", true], ["submit", true]]);
  await expect(radios.nth(2)).toHaveAttribute("aria-checked", "true");            // "submit" saves it
  await say(page, [["option b", true], ["next", true], ["c", true], ["submit", true], ["the femoral nerve", true]]);
  await expect(page.getByTestId("quiz-heard")).toContainText("That wasn't an answer command");   // other talk changes nothing
  await expect(radios.nth(2)).toHaveAttribute("aria-checked", "true");
  await say(page, [["option b", true], ["next", true], ["c", true], ["submit", true], ["the femoral nerve", true], ["next", true]]);
  await expect(page.getByText("Question 2 of 5")).toBeVisible();
});

test("Voice controls fit at phone width and in dark mode", async ({ page }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  await fakeSpeech(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.locator("#composer").fill("what is the");
  await page.getByRole("button", { name: /^Start voice input/ }).click();
  await say(page, [["femoral triangle", false]]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: `${SHOTS}/voice-chat-listening-390.png` });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  await page.screenshot({ path: `${SHOTS}/voice-chat-listening-390-dark.png` });
});

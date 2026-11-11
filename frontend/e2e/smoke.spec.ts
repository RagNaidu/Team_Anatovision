import { expect, test } from "@playwright/test";

test("login, ask, citation click, quiz start", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));

  // login
  await page.goto("/login");
  await page.fill("#username", "student1");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Show password" }).click();                       // eye toggle
  await expect(page.locator("#password")).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide password" }).click();
  await expect(page.locator("#password")).toHaveAttribute("type", "password");
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
  await page.getByRole("button", { name: /^Lectures/ }).click();                            // dropdown with search, checkboxes and "Select all"
  await expect(page.getByLabel("Search lectures")).toBeVisible();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: /^Lectures/ })).toContainText("4 lectures");
  await expect(page.getByText("Past quizzes", { exact: true })).toBeVisible();              // the history is in the sidebar
  await page.getByRole("button", { name: "Build quiz" }).click();
  await expect(page.getByText("Preparing your quiz")).toBeVisible();
  await expect(page.getByText("Question 1 of 5")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("radio").nth(1).click();
  await expect(page.getByRole("radio").nth(1)).toHaveAttribute("aria-checked", "true");

  expect(errors).toEqual([]);
});

test("revised-notes effects for a student: source updated pill, guide place notice", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/login");
  await page.fill("#username", "student1");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ask$/);
  // an old answer whose source was changed by the revised notes
  await page.getByRole("link", { name: /Dissecting the gluteal region/ }).first().click();
  await page.getByRole("button", { name: "Source 1" }).first().click();
  await expect(page.getByText("Source updated", { exact: false }).filter({ hasText: "this answer was written before" })).toBeVisible();
  await page.keyboard.press("Escape");
  // a guide whose place was moved
  await page.getByRole("link", { name: "Guide" }).first().click();
  await page.getByRole("link", { name: /Gluteal Region/ }).first().click();
  await expect(page.getByText("This guide was updated. Your place was moved")).toBeVisible();
  expect(errors).toEqual([]);
});

test("instructor: changed review status and the Notes manager", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/login");
  await page.fill("#username", "inglis");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/admin$/);

  // review queue: "Changed in revised notes"
  await page.getByRole("link", { name: "Review queue" }).click();
  await page.getByLabel("Status").selectOption("changed");
  await expect(page.getByText("Changed in revised notes").nth(1)).toBeVisible();

  // Notes manager: list, upload, steps, ready, publish, edit
  await expect(page.getByRole("link", { name: "Student questions" })).toBeVisible();
  await page.getByRole("link", { name: "Notes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Notes" })).toBeVisible();
  await expect(page.getByText("Lecture 08 - The Femoral Triangle")).toBeVisible();
  await expect(page.getByText("Earlier version, not in revised notes")).toBeVisible();
  await page.getByLabel("Status").selectOption("archived");
  await expect(page.getByText("First version, replaced by the revised notes")).toBeVisible();
  await page.getByLabel("Status").selectOption("");
  await page.getByRole("button", { name: "Upload" }).first().click();
  await page.locator('input[type="file"]').setInputFiles({ name: "Lecture 40 - Zebra Anatomy.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("PK\u0003\u0004zebra") });
  await page.getByRole("button", { name: "Upload and prepare" }).click();
  await expect(page.getByText("Preparing the document")).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/This looks like Lecture 08/)).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await page.getByLabel("All students").check();
  await page.getByRole("dialog").getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText(/Published version 1/)).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /^Edit Overview/ }).first().click();
  await page.getByLabel("Section text").fill("Edited text.");
  await page.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByText(/Saved as version 2/)).toBeVisible({ timeout: 10_000 });
  await page.getByRole("tab", { name: "Versions" }).click();
  await expect(page.getByText("Version 2")).toBeVisible();
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Archive" }).click();
  await expect(page.getByText(/Archived on|Archived\./).first()).toBeVisible({ timeout: 10_000 });
  expect(errors).toEqual([]);
});

test("instructor: Question bank list, import preview, editor", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/login");
  await page.fill("#username", "inglis");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Question bank").first()).toBeVisible();
  await page.getByRole("link", { name: "Question bank" }).click();
  await expect(page.getByRole("heading", { name: "Question bank" })).toBeVisible();
  await expect(page.getByText("15 in the bank")).toBeVisible();
  await expect(page.getByText("Which nerve passes through the carpal tunnel?")).toBeVisible();

  // filters and search
  await page.getByLabel("Use", { exact: true }).selectOption("exam_secure");
  await expect(page.getByText("Which structure lies medial to the femoral vein?")).toBeVisible();
  await expect(page.getByText("Which nerve passes through the carpal tunnel?")).toBeHidden();
  await page.getByLabel("Use", { exact: true }).selectOption("");
  await page.getByLabel("Search questions").fill("hyoid");
  await expect(page.getByText("Which muscle elevates the hyoid bone?")).toBeVisible();
  await page.getByLabel("Search questions").fill("");

  // bulk: select two, tag them
  await page.getByLabel("Select Which nerve passes through the carpal tunnel?").check();
  await page.getByLabel("Select Which muscle abducts the thumb?").check();
  await page.getByLabel("Tag to add or remove").fill("hand-lab");
  await page.getByRole("button", { name: "Add tag" }).click();
  await expect(page.getByText("Tag added: 2 questions changed.")).toBeVisible();

  // import: an odd layout is mapped in the preview
  await page.getByRole("button", { name: "Import" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "my exam.csv", mimeType: "text/csv", buffer: Buffer.from("a,b\n1,2") });
  await expect(page.getByText("Match your columns")).toBeVisible();
  await expect(page.getByText("0 ready to import")).toBeVisible();
  await page.getByLabel("Column for Question (lead-in)").selectOption("What is asked");
  await page.getByLabel("Column for Correct answer").selectOption("Right one");
  await expect(page.getByText("3 ready to import")).toBeVisible();
  await expect(page.getByText("Which nerve is injured in a fractured surgical neck")).toBeVisible();
  await expect(page.getByText(/Looks like q-sample/)).toBeVisible();
  await page.getByRole("button", { name: "Import 3 questions" }).click();
  await expect(page.getByText(/Imported .* question/)).toBeVisible();
  await page.getByLabel("Source").selectOption("imported");
  const list = page.getByRole("list", { name: "Questions" });
  await expect(list.getByText("Exam-secure").first()).toBeVisible();
  await expect(list.getByText("draft").first()).toBeVisible();

  // editor: edit, version history, restore, flags
  await page.getByLabel("Source").selectOption("");
  await page.getByText("Which nerve supplies the quadriceps femoris?").click();
  await expect(page.getByRole("heading", { name: "Edit question" })).toBeVisible();
  await page.getByLabel("Question (lead-in)").fill("Which nerve does NOT supply the quadriceps femoris?");
  await page.getByRole("button", { name: "Save as new version" }).click();
  await expect(page.getByText(/Saved as a new version/)).toBeVisible();
  await expect(page.getByText("Negative lead-in")).toBeVisible();
  await expect(page.getByText("Version 2 (current)")).toBeVisible();
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("Version 3 (current)")).toBeVisible();
  await page.getByRole("tab", { name: "Comments" }).click();
  await page.getByLabel("New comment").fill("check this");
  await page.getByRole("button", { name: "Add comment" }).click();
  await expect(page.getByText("check this")).toBeVisible();
  await page.getByRole("tab", { name: "Statistics" }).click();
  await expect(page.getByText(/Based on \d+ attempts/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("student quiz never shows exam-secure, draft or retired bank questions", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#username", "student1");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Quiz" }).click();
  await page.getByRole("button", { name: /^Lectures/ }).click();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("A different style from the instructor's examples")).toBeVisible();
  await page.getByRole("button", { name: "Build quiz" }).click();
  await expect(page.getByText("Question 1 of 5")).toBeVisible({ timeout: 20_000 });
  const secure = ["Which structure lies medial to the femoral vein?", "Which arch lies more distally in the palm?", "Which muscle elevates the hyoid bone?"];
  const draft = ["Which artery is the main blood supply of the thigh?", "Where does the great saphenous vein drain?"];
  for (let i = 0; i < 5; i++) {
    const text = await page.locator("main").innerText();
    for (const s of [...secure, ...draft]) expect(text).not.toContain(s);
    if (i < 4) await page.getByRole("button", { name: "Next" }).click();
  }
});

test("student guide: slide image, step-by-step marks, lightbox keyboard, image-only station, chat image cards", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/login");
  await page.fill("#username", "student1");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ask$/);

  await page.goto("/guide/class-17/0");
  const fig = page.getByRole("figure", { name: "Slide image" });
  await expect(fig).toBeVisible();
  await expect(fig.getByText("Slide 3 · Dr. Inglis's dissection guide")).toBeVisible();
  await expect(fig.getByText("Your cadaver may look different.")).toBeVisible();
  const marks = () => fig.locator("svg[data-marks]").first().getAttribute("data-marks");
  expect(await marks()).toBe("2");                                              // step 1: its label pin and arrow (the draft pin is never sent)
  await page.getByRole("button", { name: /^Step 2:/ }).click();
  await expect.poll(marks).toBe("1");                                          // step 2: the cut line only
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.getByRole("button", { name: /^Step 3:/ })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(marks).toBe("1");                                          // step 3: the circle
  await page.getByRole("button", { name: "Back a step" }).click();
  await expect(page.getByRole("button", { name: /^Step 2:/ })).toHaveAttribute("aria-pressed", "true");

  // lightbox: open, keep the marks, arrows move between the station's slides, Esc closes
  await page.getByRole("button", { name: /^Enlarge/ }).click();
  const box = page.locator("[data-lightbox]");
  await expect(box.getByText("Slide 3 · Dr. Inglis's dissection guide")).toBeVisible();
  await expect(box.getByText(/Your cadaver may look different\. · 1 of 2/)).toBeVisible();
  expect(await box.locator("svg[data-marks]").getAttribute("data-marks")).toBe("1");
  await page.keyboard.press("ArrowRight");
  await expect(box.getByText("Slide 4 · Dr. Inglis's dissection guide")).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await expect(box.getByText("Slide 3 · Dr. Inglis's dissection guide")).toBeVisible();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(box.locator("img").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(box).toBeHidden();

  // the picture panel is the larger column (about 60%), a student has no way to see the whole slide, and "Explain simply" is labelled as AI
  const panel = await page.locator("[data-image-panel]").boundingBox();
  const content = await page.getByRole("heading", { level: 1 }).first().boundingBox();
  expect(panel!.width / (panel!.width + content!.width * 0.0 + 1)).toBeGreaterThan(0.5);
  await expect(page.getByLabel("View original slide")).toHaveCount(0);
  await page.getByRole("button", { name: "Explain simply" }).click();
  await expect(page.getByLabel("AI explanation")).toContainText("AI explanation, check your guide");
  await expect(page.getByLabel("AI explanation")).toContainText("From: Dissection guide");

  // an image-only station shows its slide, not "See slide N"
  await page.goto("/guide/class-17/3");
  await expect(page.getByRole("figure", { name: "Slide image" })).toBeVisible();
  await expect(page.getByText("See slide 14 in your lab guide")).toBeHidden();

  // chat: one card per step of a procedural answer, tap opens the lightbox
  await page.goto("/ask");
  await page.getByPlaceholder("Ask about a structure, region or dissection step").fill("How do I expose the femoral triangle?");
  await page.getByRole("button", { name: "Send question" }).click();
  const cards = page.getByRole("region", { name: "Slide images from the dissection guide" });
  await expect(cards).toBeVisible({ timeout: 20_000 });
  await expect(cards.getByRole("listitem")).toHaveCount(2);
  await expect(cards.getByText("Step 1 · Slide 3")).toBeVisible();
  await cards.getByRole("button", { name: /^Enlarge/ }).first().click();
  const lb = page.locator("[data-lightbox]");
  await expect(lb.getByText("Slide 3 · Dr. Inglis's dissection guide")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(lb.getByText("Slide 5 · Dr. Inglis's dissection guide")).toBeVisible();
  await page.keyboard.press("Escape");
  expect(errors).toEqual([]);
});

test("instructor: image marks editor draws a draft, approves the station and previews the student view", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/login");
  await page.fill("#username", "inglis");
  await page.fill("#password", "anything");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.goto("/admin/notes/G-class-17");
  await page.getByRole("tab", { name: "Image marks" }).click();
  await expect(page.getByText("Marks on slide 3")).toBeVisible();
  await expect(page.getByText("Draft", { exact: true }).first()).toBeVisible();
  const rows = page.getByRole("region", { name: "Marks on this slide" }).locator("> ul > li");
  const before = await rows.count();
  // draw an arrow
  await page.getByRole("button", { name: "Arrow", exact: true }).click();
  const area = page.getByRole("application", { name: /Drawing area for slide 3/ });
  await page.getByRole("toolbar", { name: "Drawing tools" }).scrollIntoViewIfNeeded();
  await page.locator("[data-canvas]").scrollIntoViewIfNeeded();
  const bb = (await area.boundingBox())!;
  await page.mouse.move(bb.x + bb.width * 0.2, bb.y + bb.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(bb.x + bb.width * 0.4, bb.y + bb.height * 0.5, { steps: 5 });
  await page.mouse.up();
  await expect(page.getByText("Added as a draft.")).toBeVisible();
  await expect(rows).toHaveCount(before + 1);
  // a label pin needs its text
  await page.getByRole("button", { name: "Label pin", exact: true }).click();
  await page.locator("[data-canvas]").scrollIntoViewIfNeeded();
  const bb2 = (await area.boundingBox())!;
  await page.mouse.click(bb2.x + bb2.width * 0.5, bb2.y + bb2.height * 0.7);
  await page.getByLabel("Text for the pin").fill("Femoral artery");
  await page.getByRole("button", { name: "Add pin" }).click();
  await expect(rows).toHaveCount(before + 2);
  // move a mark by dragging it, resize with a handle, nudge with the arrow keys, undo and redo
  await page.getByRole("button", { name: "Select", exact: true }).click();
  await page.locator("[data-canvas]").scrollIntoViewIfNeeded();
  const hit = page.locator("[data-hit]").first();
  const hb = (await hit.boundingBox())!;
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
  await page.mouse.down();
  await page.mouse.move(hb.x + hb.width / 2 + 40, hb.y + hb.height / 2 + 25, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByRole("button", { name: "Undo" })).toBeEnabled();
  const arrowHit = page.locator("[data-hit]").nth(1);
  const ab = (await arrowHit.boundingBox())!;
  await page.mouse.move(ab.x + ab.width / 2, ab.y + ab.height / 2);
  await page.mouse.down();
  await page.mouse.up();                                                        // a click selects the arrow: its two end handles appear
  await expect(page.locator("[data-handle]").first()).toBeVisible();
  const handle = page.locator("[data-handle]").first();
  const hh = (await handle.boundingBox())!;
  await page.mouse.move(hh.x + hh.width / 2, hh.y + hh.height / 2);
  await page.mouse.down();
  await page.mouse.move(hh.x + hh.width / 2 + 30, hh.y + hh.height / 2 + 10, { steps: 5 });
  await page.mouse.up();
  await page.locator("[data-canvas]").focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Shift+ArrowDown");
  await expect.poll(async () => (await page.getByRole("region", { name: "Marks on this slide" }).innerText()).match(/v(\d+)/g)?.length ?? 0).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "Redo" })).toBeEnabled();
  await page.getByRole("button", { name: "Redo" }).click();
  // the whole original slide is for instructors only
  await page.getByLabel("View original slide").check();
  await expect(page.getByAltText(/^Original slide 3/)).toBeVisible();
  await page.getByLabel("View original slide").uncheck();
  // approve the station, then preview what a student sees
  await page.getByRole("button", { name: "Approve drafts…" }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg.getByLabel("Approval preview")).toBeVisible();
  await expect(dlg.getByText(/draft marks? will be approved/)).toBeVisible();
  await dlg.getByRole("button", { name: /^Approve \d+$/ }).click();
  await expect(page.getByText(/Approved the marks of/)).toBeVisible();
  await page.getByLabel("Preview as a student sees it").check();
  await expect(page.getByLabel("Student preview")).toBeVisible();
  expect(errors).toEqual([]);
});

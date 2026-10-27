# UI audit fix report (Parts 1 to 4)

Status key: **done**, **partly**, **not done**. Quiz mode was out of scope. IDs P68, P71, P91 and P94 were not itemised in the briefs, so they are not listed.
Checked in Chrome at 1440, 961, 768 and 390 px; screenshots are in `reports/ui_screenshots/part2`, `part3`, `part4`.

## Privacy and answer logic (Part 1)
| ID | Status | Note |
|---|---|---|
| P01 | done | Students get only `src/student_view.py` data; a test scans everything a student session sees for instructor-only strings. |
| P02 | done | One neutral sentence for a line under review. |
| P03 | done | No red chip inside quoted notes. |
| P04 | done | "That page is for instructors" with a Back button; every professor view re-checks the role. |
| P05 | done | Demo notice only in demo mode and never after sign-in. |
| P06 | done | 10 characters, confirm field, clear errors. No self-service password change exists (professor sets passwords). |
| P07 | done | Usage split by kind; previews excluded from student totals. |
| P08, P09 | done | Numbers per distinct passage; one supporting line per sentence (styling in Part 3). |
| P12 | done | No scores, tokens or "hybrid" for students. |
| P18 | done | Doubtful marker in the data (UI in Part 3). |
| P19 | done | Follow-ups use the last turns. |
| P20, P21 | done | Three "not covered" cases; access message names the lecture. |
| P24 | done | List questions retrieve 12 and say the list may be incomplete. |
| P25 | done | Cost and model for the professor only. |
| P30 | done | 600 characters, counter from 480. |
| P69 | partly | Reload still signs out (a safe fix needs tokens and stored chats); warning + README note instead. |

## Design system and shell (Part 2)
| ID | Status | Note |
|---|---|---|
| P49, P90, P92, P93, P95, P96 | done | One button family, tokens, components. |
| P70 | done | Mode switcher = real links with a selected state; Quiz disabled with a badge. |
| P65, P66, P67, P72, P73, P74 | done | Sidebar toggle (44px) was hidden by the old CSS; layout shell fixed. |
| P14, P15, P27, P35, P40, P44, P60 | done | Buttons size to their text; no clipping at any width (browser audit). |
| P46 | done | Sidebar shows only what applies. |
| P82, P83, P84 | done | One alert component, friendly login error, loading skeleton, calmer "not covered". |
| P85 to P90 | partly | Contrast measured and enforced; focus rings, names and labels checked by script. No real screen-reader testing. |
| P98, P99 | done | Logo, favicon, 150 ms transitions, empty-state icons. |

## Student chat and Guide (Part 3)
| ID | Status | Note |
|---|---|---|
| P10, P11, P13, P14, P16, P17, P22, P23, P26, P27, P28, P29, P30, P31, P97 | done | See the Part 3 report; the trust-line date is now the index load date. |
| P32, P33, P34, P35, P36, P37, P39, P40, P41, P42, P43, P44, P45, P46 | done | Guide describes first, notes after; real station names; one-click Check. |
| P38 | partly | Exact repeats and fully contained lines are removed; short "Identify" names stay. |

## Professor dashboard (Part 4)
| ID | Status | Note |
|---|---|---|
| P47, P48 | done | One card per item; details behind "Show details"; "Shown in student answers" chip emphasised. |
| P50 | done | Ctrl/Cmd+Enter hits a hidden no-op first (checked in the browser: nothing recorded, text kept); Confirm error needs a correction and says what it does. |
| P51 | done | Toasts (about 5 s, no layout shift); cards fade in. |
| P52 | done | Before/after ledger; Undo is a normal button with a confirmation. |
| P53 | done | Plain form wording. |
| P54, P55 | done | "Student reports" tab (lists reports, "Mark as handled"); one line under each tab; bulk action for typos only, with a count confirmation. No bulk confirm-error. |
| P56 | done | "Page 1 of N", Previous/Next, page size. |
| P57 | done | Plain filter labels. |
| P58 | partly | Each tab has its own heading ("Review queue"), but the dashboard page heading stays "Dashboard" because the six tabs share one page. |
| P59 | done | File names only; server paths removed from all professor text. |
| P60, P61 | done | Grant all / Revoke all confirm with a count; duplicate titles get a short suffix (none exist today). |
| P62 | done | Stacked by type, axis titles, dollar units, tooltip and a table. |
| P63 | done | Headings and helper text. |
| P64 | done | Coloured preview bar with Exit preview; never shown in a student's own session. |

## Phone and tablet (Part 4)
| ID | Status | Note |
|---|---|---|
| P75 | done | Drawer has a 44px close button and closes after choosing a page. |
| P76 | done | A chip opens a fixed bottom sheet (also at 768 px, clear of the sidebar) with a Close button. |
| P77 | done | No tap target under 44px at 390 and 768 (script check). |
| P78 | done | Fixed input bar; last line clears it (measured). |
| P79 | done | No pane tab bar before an answer. |
| P80 | done | One column, no horizontal scroll, Decide reachable. |
| P81 | done | At 768 px the pane stacks or opens as a sheet; no clipped controls. |

## Also fixed in Part 4
Withheld lines show only the neutral sentence (the model had still paraphrased the claim); report form opens in place; Guide progress track visible; passage text uses a real line layout; the path under chips is short and said once; "the sources list" wording: 0 hits in 5 real answers.

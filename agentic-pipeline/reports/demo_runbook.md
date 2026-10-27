# AnatoVision demo runbook

Run time: about 10 minutes. Every output below is **real**: it was captured on 2026-10-06 by running the steps
end to end once (a live Q&A session kept open while the fix was resolved from another process).
The AI's wording changes a little from run to run; the structure, citations and tags should not.
Rehearsal cost: **$0.054** (4 model answers plus one guide judge call; guide station cards were already cached;
18,312 input / 1,746 output tokens; the whole rehearsal took 24 seconds).

## UI demo (about 5 minutes). The CLI flow below is the backup.

Screenshots of every step are in `reports/ui_screenshots/` (numbers in brackets). Cost of the whole flow: about $0.05 (three answers and one guide check).

**Set up (1 minute, before the audience arrives).**
```
cd /Users/anirudhramesh_11/Desktop/anatovision
DEMO_PROFESSOR_PASSWORD='choose-one' DEMO_STUDENT_PASSWORD='choose-another' .venv/bin/streamlit run app/main.py
```
Wait for the browser (about 10 s). Sign in once as `inglis`, open Dashboard > Access, expand Student One and tick Lecture 09 and Lecture 16b (Middle Ear); Save. Check `wc -c data/verified_fixes.jsonl` says 0. Sign out. (If you did not set the env vars, the passwords were printed once in the terminal.)

1. **Student: body type first, then a question [02, 03, 04].** Sign in as `student1`. Say: "It asks the cadaver first, as the lab does." Click Continue, then the chip "What are the walls of the middle ear?". Point at the numbered chips under each line and the amber "Flagged for review" tag.
2. **Live citation [05].** Click chip 1. The right pane shows the exact passage, breadcrumb, "Course notes" badge, the retrieval score and the highlighted lines the sentence came from. Say: "A citation that is not one of the retrieved passages would show in red as 'not found'."
3. **Not a black box [06].** Click "How this answer was built". Say: "These are the steps the program really ran, recorded as it ran: search, relevance check, fact-check lookup, one model call, citation check. It is a fixed pipeline, not an agent."
4. **Not covered [07].** Ask "Explain how quantum entanglement works in photons." The card says "Not covered in the course notes", no unrelated sources, no model call.
5. **Guide [08, 09, 10].** Click Guide, Lecture 09, Start. Say: "Sample mode: the notes are descriptive, so this walks the lecture's own order." Click station 1, type "thumb, opposable, carpal bones", Check my description (verdict in plain words). Then station 3: it first asks "have you identified these?" and refuses to skip ahead.
6. **Professor decides [11 to 15].** Sign out, sign in as `inglis`. Review queue: Start here (14), Likely factual, Second look, Typos; filters. Open Decide on "Continuation of femoral nerve past the adductor hiatus", correction "The popliteal artery continues the femoral artery, not a nerve.", Confirm error. Say: "AI suggestion, not a verdict; he decides. The notes file is never edited." Show it in Verified fixes (with Undo).
7. **Student sees the green chip [23, 24].** Sign in as `student1` again, ask about the popliteal artery (Lecture 16 must be granted to student1 for this: tick Lecture 16 Posterior Thigh in Access during set-up) or use any line you decided. The answer now carries the green "Verified by Dr. Inglis, <date>" chip; its pane shows the verified fix.
8. **Access control [18, 22].** As the professor tick only Lecture 09 for `student2`; as `student2` ask about the middle ear: "That isn't in the notes you have access to. Ask your instructor." Say: "This is enforced in the search; the other lectures never reach the model."
9. **View as student [21]** (professor sidebar), Usage [19] (questions the notes could not answer = gaps in the notes), Notes library [16, 17] (upload, versions, fact-check cost shown first), Settings [20] (spending cap).

**Restore after the demo:** Dashboard > Verified fixes > Undo each fix you made (`wc -c data/verified_fixes.jsonl` must say 0); `rm -f data/question_log.jsonl` if you want the usage page empty; the 11 original flags stay (`.venv/bin/python -m src.verified list | head -1` says "11 open" plus any you triggered, which is intended). Stop the app with Ctrl+C.

**If it misbehaves:** the model call failed (credit/API) shows "Could not answer", nothing else breaks. If the page looks stale after code changes, restart the server (Streamlit does not reload `src/`). Say the limits out loud: demo-grade login, Quiz not built, AI fact-check items are suggestions.

---

# CLI demo (backup, about 10 minutes)

## Before you start (2 minutes)

Use **two terminals**, both in the project folder:
```
cd /Users/anirudhramesh_11/Desktop/anatovision
```
- **Terminal 1** runs the Q&A session and stays open for steps b, c, d, e and g.
- **Terminal 2** is for the short commands (steps a, d, e, f).

Pre-flight (Terminal 2). Expected: the fixes file is empty and the flags are all open.
```
wc -c data/verified_fixes.jsonl
.venv/bin/python -m src.verified list | head -1
```
Real output when I started:
```
       0 data/verified_fixes.jsonl
11 open of 11 flags in data/flags.jsonl
```

If the fixes file is not 0 bytes, restore it first (step e). Do not open `.env` on screen.
The first start of any mode takes about 10 seconds (it loads the search model); start Terminal 1 once, early, and let it sit.

## a. Show the "Start here" list

```
sed -n '/^## Start here/,/^## Summary by lecture/p' reports/factcheck_all.md
```
(or open `reports/factcheck_all.md` in the editor and scroll to the top).

**Say:**
- "I checked all 562 sections of Dr. Inglis's notes with an AI, against the open textbook and general anatomy knowledge."
- "It produced 733 items for review. Every one is an AI suggestion, not a verdict. Nothing in his notes was changed."
- "These 14 are the highest-priority ones: a second AI check confirmed them and rated them high. Dr. Inglis decides which are real."
- Pick one or two to read aloud, for example the "femoral nerve" line (it appears in two lectures) or "5 lumbar (C1 - C8)".

Real output (the top of the report, then the Start here section, verbatim):
```
Items for review: **90 factual items** (confirmed by a second check), **474 worth a second look** (wording, or factual but doubtful), **169 typos**. 13 factual items were dropped because the second check judged the notes correct.
```

## Start here: high-priority items for review

Factual items confirmed by a second check and rated high: statements that could mislead a student's dissection or exam answer. Each shows the exact words from the notes. Please judge each one yourself: the AI can be wrong. Showing the 14 highest-confidence of 25; the rest are in section 1.

1. **Lecture 16 - Posterior Thigh and Popliteal Fossa** > Popliteal Fossa > Contents > Popliteal Artery
   - Notes say: "Continuation of femoral nerve past the adductor hiatus"
   - Why: The popliteal artery is the continuation of the femoral artery (an artery, not a nerve) as it passes through the adductor hiatus.
   - Basis: OpenStax §20.5 | confidence 0.96 | second check: confirmed

2. **Lecture 08 - Anterior and Medial Thigh** > Anterior and Medial Thigh > The Femoral Triangle > Femoral Artery
   - Notes say: "where it becomes the tibial artery"
   - Why: In the popliteal fossa the femoral artery becomes the popliteal artery, not a 'tibial artery'. The popliteal artery then divides into the anterior and posterior tibial arteries.
   - Basis: OpenStax §20.5 | confidence 0.95 | second check: confirmed

3. **Lecture 12 - Posterior Leg and Plantar Surface of Foot** > Popliteal Fossa > Contents > Popliteal Artery
   - Notes say: "Continuation of femoral nerve past the adductor hiatus"
   - Why: The popliteal artery is the continuation of the femoral artery (not a nerve) as it passes through the adductor hiatus. Calling it a nerve is a wrong structure type.
   - Basis: OpenStax §20.5 | confidence 0.95 | second check: confirmed

4. **Lecture 03 - Nerves Spinal Cord and Meninges** > Spinal Nerves
   - Notes say: "5 lumbar (C1 – C8)"
   - Why: The lumbar nerves are labelled L1–L5, not C1–C8. C1–C8 is the cervical designation, so this label is wrong and contradicts the 5 lumbar nerves stated in the same line.
   - Basis: OpenStax §13.4 | confidence 0.93 | second check: confirmed

5. **Lecture 08 - Anterior and Medial Thigh** > Anterior and Medial Thigh > Muscles of the Medial Compartment
   - Notes say: "All muscles innervated by obturator nerve"
   - Why: Not all medial compartment muscles are supplied solely by the obturator nerve. Pectineus is typically supplied by the femoral nerve (sometimes with an accessory obturator branch). The ischial (hamstring) part of adductor magnus is supplied by the tibial division of the sciatic nerve. 'All' is therefore misleading.
   - Basis: general anatomy knowledge | confidence 0.9 | second check: confirmed

6. **Lecture 08 - Anterior and Medial Thigh** > Anterior and Medial Thigh > The Femoral Triangle
   - Notes say: "Superior – inguinal canal"
   - Why: The superior border of the femoral triangle is the inguinal ligament, not the inguinal canal. The inguinal canal is a separate passage in the anterior abdominal wall above the ligament.
   - Basis: general anatomy knowledge | confidence 0.9 | second check: confirmed

7. **Lecture 12 - Posterior Leg and Plantar Surface of Foot** > The Foot > Muscles > 4th Plantar Layer > Plantar interossei
   - Notes say: "originating off the medial shaft of 3rd through 5th metacarpals"
   - Why: The plantar interossei are in the foot and arise from the metatarsals, not the metacarpals (hand bones). The 3rd to 5th metatarsals is correct.
   - Basis: general anatomy knowledge | confidence 0.9 | second check: confirmed

8. **Lecture 13 - The Hip and Knee Joints** > The Knee Joint > Joint Stability
   - Notes say: "Primarily due greater rolling of smaller medial femoral condyle"
   - Why: The medial femoral condyle is the larger one, and the lateral condyle is the smaller one. The lateral condyle finishes its rolling first, and the medial condyle continues to roll, which produces the rotation. The notes reverse which condyle is smaller.
   - Basis: OpenStax §9.6 | confidence 0.88 | second check: confirmed

9. **Lecture 16 - Anterolateral Thoracoabdominal Wall** > Slide 08
   - Notes say: "It’s nourished by the testicular artery, off the internal iliac, and has a rich sympathetic nerve supply"
   - Why: The ductus deferens is supplied by the artery to the ductus deferens, usually a branch of the inferior (or superior) vesical artery from the internal iliac. The testicular artery arises from the abdominal aorta, as the notes say earlier, so it cannot be 'off the internal iliac'. The statement is internally inconsistent and wrong.
   - Basis: general anatomy knowledge | confidence 0.88 | second check: confirmed

10. **ANA407 Class 28 - The Posterior Abdominal Wall** > Accessory Digestive Organs > Liver > part 2 of 2
   - Notes say: "augmenting hypoglycemia"
   - Why: In the fasted state, glucagon-driven release of stored glucose raises plasma glucose and counteracts or prevents hypoglycemia. 'Augmenting hypoglycemia' says the opposite and would mislead students.
   - Basis: general anatomy knowledge | confidence 0.85 | second check: confirmed

11. **Lecture 07 - The Antebrachium** > Bones of the Antebrachium > Ulna
   - Notes say: "Shaft terminates in ulnar head for articulation at the wrist joint"
   - Why: The ulnar head articulates with the ulnar notch of the radius (distal radioulnar joint). It does not articulate with the carpal bones, so it does not take part in the radiocarpal (wrist) joint. An articular disc separates it from the carpus.
   - Basis: OpenStax §8.2 | confidence 0.85 | second check: confirmed

12. **Lecture 07 - The Antebrachium** > Nerves of the Antebrachium > Radial Nerve > Deep Branch
   - Notes say: "Supplies branches to muscles of the posterior compartment of the arm"
   - Why: The deep branch of the radial nerve supplies muscles of the posterior compartment of the forearm (antebrachium), not the arm. Triceps (posterior arm) is supplied by radial nerve branches proximal to this point.
   - Basis: general anatomy knowledge | confidence 0.85 | second check: confirmed

13. **Lecture 08 - Anterior and Medial Thigh** > Anterior and Medial Thigh > Obturator Canal
   - Notes say: "Typically found at the medial margins of the membrane"
   - Why: The obturator canal lies at the superolateral margin of the obturator foramen, where the membrane is deficient beneath the obturator groove of the superior pubic ramus. It is not at the medial margin, so a student could misplace the canal.
   - Basis: general anatomy knowledge | confidence 0.85 | second check: confirmed

14. **Lecture 09 - The Hand** > Muscles of the Hand > Hypothenar Eminence > Opponens DigitiMinimi
   - Notes say: "Deep portion of the thenar eminence"
   - Why: Opponens digiti minimi is a hypothenar muscle (deep to the other hypothenar muscles), not part of the thenar eminence. The thenar eminence is the thumb's muscle group. The note sits under the Hypothenar Eminence heading, so 'thenar' appears to be an error.
   - Basis: OpenStax §11.5 | confidence 0.85 | second check: confirmed

## b. Q&A: the walls of the middle ear (citations and the "flagged" tag)

Terminal 1:
```
.venv/bin/python -m src.modes.qa
```
It asks for the cadaver body type first. Type `more fat, less muscle`, then ask the question.

**Say:**
- "It asks the cadaver's body type first. It will only mention it where the notes actually discuss variation."
- "Every claim carries a citation in brackets: lecture and section."
- "This line, 'vascular structures (jugular vein and internal carotid artery)', has a tag: the fact-check found it doubtful. The tool still uses it, but marks it, and logs it for Dr. Inglis."

Real output:
```
Loading the search index...
Before we start: which cadaver are you working on?
Tell me its body type, e.g. 'more fat, less muscle, small build'
(fat: more / average / less; muscle: more / average / less; build: large / average / small).
Press Enter to skip.
Body type> more fat, less muscle
Body type noted: more fat, less muscle. Fact-check: 90 lines under review, 32 doubtful. Verified fixes on file: 0.

Ask a question about the lab or the lecture notes (type 'quit' to leave).

Question> What are the walls of the middle ear?
```
```
====================================================================================================
Q: What are the walls of the middle ear?
====================================================================================================
The middle ear has lateral, posterior, inferior, medial and anterior walls. [Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear]
Lateral wall: tympanic membrane, chorda tympani nerve and malleus; posterior wall: aditus to the mastoid antrum, a canaliculus for the chorda tympani, and the stapedius muscle. [Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear]
Inferior wall: tympanic canaliculus for the tympanic nerve of CN IX, plus vascular structures (jugular vein and internal carotid artery). (flagged for review, see fact-check) [Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear]
Medial wall: oval window closed by the stapes footplate, and round window closed by a membrane; anterior wall: auditory tube opening and tensor tympani opening. [Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear]
Ask for more detail if you need it.

--- retrieved (hybrid search; score = boosted RRF) ---
  0.0410 cos 0.73  NOTES   Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear
  0.0397 cos 0.73  NOTES   Lecture 16b - Middle Ear > I. Basic Subdivisions of the Ear
  0.0388 cos 0.73  NOTES   Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 1. Located in the petrous portion
  0.0388 cos 0.75  NOTES   Lecture 16b - Middle Ear > II. External Ear > 7. Tympanic Membrane (ear drum)
  0.0385 cos 0.83  NOTES   Lecture 16b - Middle Ear > II. External Ear > 2. Ear Lobe
[flag: doubtful, used with a note] Vascular structures (Jugular vein and internal carotid artery). -> already in data/flags.jsonl
[tokens] in 4,408 / out 506 | $0.0139
```

## c. Q&A: femoral triangle borders ("under review" and the general-knowledge statement)

Same Terminal 1 session:
```
What are the borders of the femoral triangle?
```

**Say:**
- "The notes line for the superior border was confirmed as an error by the fact-check, so the tool does not repeat it."
- "It says the line is under review, and gives the standard statement, labelled 'general anatomy knowledge, pending Dr. Inglis'."
- "That statement is the AI's, not the notes'. It is clearly labelled until Dr. Inglis decides."

Real output:
```
====================================================================================================
Q: What are the borders of the femoral triangle?
====================================================================================================
The medial border is adductor longus and the lateral border is sartorius. [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle]
The superior border line in the course notes is currently under review. [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle]
General anatomy knowledge, pending Dr. Inglis: the superior border is the inguinal ligament, not the inguinal canal, which is a separate passage in the abdominal wall above it.
The apex lies inferiorly where sartorius crosses adductor longus, and the floor is formed by pectineus and iliopsoas. [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle]
Ask for more detail if you need it.

--- retrieved (hybrid search; score = boosted RRF) ---
  0.0403 cos 0.78  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle
  0.0394 cos 0.80  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Femo
  0.0388 cos 0.77  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Femo
  0.0386 cos 0.76  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Cont
  0.0382 cos 0.76  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Deep
[flag: under review] Superior – inguinal canal -> already in data/flags.jsonl
[tokens] in 4,254 / out 368 | $0.0122
```

## d. Resolve one flag live as "Dr. Inglis (DEMO)", then re-ask

Terminal 2 (the Q&A session in Terminal 1 stays open). First list the open flags and find the femoral triangle one:
```
.venv/bin/python -m src.verified list
```
Real output (8 is the flag number for "Superior – inguinal canal"; numbers are stable, but always read it off the list):
```
11 open of 11 flags in data/flags.jsonl

#1   [CONFIRMED-ERROR?] Lecture 16b - Middle Ear > II. External Ear > 7. Tympanic Membrane (ear drum)
      notes say: "Perforation of the tympanic membrane causes deafness in the affected ear"
      standard : A perforated tympanic membrane typically causes partial conductive hearing loss, not complete deafness. Overstated clinical claim.
#2   [CONFIRMED-ERROR?] Lecture 09 - The Hand > Nerves of the Hand > Median Nerve
      notes say: "Injury to any part of the median nerve results in loss of function of thenar eminence, progressing to ape-hand deformity without recovery"
      standard : Injury to 'any part' of the median nerve does not cause thenar loss. Only injury at or proximal to the recurrent branch (e.g., wrist/carpal tunnel or higher) does; a lesion distal to the recurrent bra
#3   [CONFIRMED-ERROR?] Lecture 09 - The Hand > Nerves of the Hand > Median Nerve
      notes say: "When asked to make fist, loss of function results in incomplete flexion of digits 2 and 3 (the “Hand of Benediction” sign)"
      standard : The 'Hand of Benediction' (benediction sign) with a median nerve lesion at the forearm/elbow is due to loss of FDS/FDP to digits 2 and 3 when making a fist. It is not caused by loss of lumbricals, whi
#4   [CONFIRMED-ERROR?] Lecture 09 - The Hand > Nerves of the Hand > Ulnar Nerve
      notes say: "Gives off motor branches to 3rd and 4th lumbricals"
      standard : Placed under the superficial branch. The motor branches to the 3rd and 4th (medial) lumbricals arise from the deep branch of the ulnar nerve, not the superficial branch, which is mainly sensory plus p
#5   [CONFIRMED-ERROR?] Lecture 16 - Posterior Thigh and Popliteal Fossa > Popliteal Fossa > Contents > Popliteal Artery
      notes say: "Continuation of femoral nerve past the adductor hiatus"
      standard : The popliteal artery is the continuation of the femoral artery (an artery, not a nerve) as it passes through the adductor hiatus.
#6   [CONFIRMED-ERROR?] Lecture 12 - Posterior Leg and Plantar Surface of Foot > Popliteal Fossa > Contents > Popliteal Artery
      notes say: "Continuation of femoral nerve past the adductor hiatus"
      standard : The popliteal artery is the continuation of the femoral artery (not a nerve) as it passes through the adductor hiatus. Calling it a nerve is a wrong structure type.
#7   [CONFIRMED-ERROR?] Lecture 12 - Posterior Leg and Plantar Surface of Foot > The Foot > Muscles > 4th Plantar Layer > Plantar inte
      notes say: "originating off the medial shaft of 3rd through 5th metacarpals"
      standard : The plantar interossei are in the foot and arise from the metatarsals, not the metacarpals (hand bones). The 3rd to 5th metatarsals is correct.
#8   [CONFIRMED-ERROR?] Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle
      notes say: "Superior – inguinal canal"
      standard : The superior border of the femoral triangle is the inguinal ligament, not the inguinal canal. The inguinal canal is a separate passage in the anterior abdominal wall above the ligament.
#9   [doubtful] Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear
      notes say: "Vascular structures (Jugular vein and internal carotid artery)."
      standard : The inferior wall (floor) is related to the jugular bulb (internal jugular vein). The internal carotid artery is related to the anterior wall (carotid wall), not the floor. Listing it as part of the i
#10  [CONFIRMED-ERROR?] Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle
      notes say: "permits communication between anterior compartment of leg and pelvis"
      standard : The subinguinal space (retro-inguinal passage) connects the anterior compartment of the thigh, not the leg, with the abdomen/pelvis. The femoral vessels and nerve pass through it into the thigh.
#11  [CONFIRMED-ERROR?] Lecture 09 - The Hand > Bones of the hand > Carpal bones
      notes say: "Articulate with radius, ulna through wrist joint proximally"
      standard : The ulna does not directly articulate with the carpal bones. The wrist (radiocarpal) joint is formed by the distal radius and an articular disc (fibrocartilaginous pad), which separates the ulna from 
```

Then resolve it:
```
.venv/bin/python -m src.verified resolve 8 --decision confirm_error --correction "Superior border: inguinal ligament" --by "Dr. Inglis (DEMO)"
```
Real output:
```
Resolved flag #8 as confirm_error. Verified fix(es) written:
  vf-0001  Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle
```

The record it wrote (`cat data/verified_fixes.jsonl`):
```
{"id": "vf-0001", "lecture": "Lecture 08 - Anterior and Medial Thigh", "breadcrumb": "Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle", "notes_quote": "Superior – inguinal canal", "correction": "Superior border: inguinal ligament", "decision": "confirm_error", "by": "Dr. Inglis (DEMO)", "date": "2026-10-06"}
```

Now go back to **Terminal 1** and ask the same question again (no restart needed: the session reloads fixes on every question):
```
What are the borders of the femoral triangle?
```

**Say:**
- "Dr. Inglis's reply is stored as a verified fix. It becomes the top-priority source."
- "The answer now uses his correction and cites who verified it and when: the square bracket shows the name that was recorded."
- "The original wrong line is never repeated. His notes file is still untouched."
- (A different line in the same section, about the subinguinal canal, is still under review. That is expected.)

Real output:
```
====================================================================================================
Q: What are the borders of the femoral triangle?
====================================================================================================
The femoral triangle is bordered superiorly by the inguinal ligament [Verified by Dr. Inglis (DEMO), 2026-10-06].
The medial border is adductor longus [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle].
The lateral border is sartorius, and the apex lies inferiorly where sartorius crosses adductor longus [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle].
The line on the subinguinal canal in the course notes is currently under review [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle]; general anatomy knowledge, pending Dr. Inglis: this space connects the abdomen/pelvis with the anterior thigh, and the femoral vessels and nerve pass through it.
Ask for more detail if you need it.

--- retrieved (hybrid search; score = boosted RRF) ---
  0.0403 cos 0.78  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle
  0.0394 cos 0.80  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Femo
  0.0388 cos 0.77  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Femo
  0.0386 cos 0.76  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Cont
  0.0382 cos 0.76  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Deep
[verified fix used] vf-0001 (confirm_error, Verified by Dr. Inglis (DEMO), 2026-10-06): "Superior – inguinal canal" -> "Superior border: inguinal ligament"
[flag: under review] permits communication between anterior compartment of leg and pelvis -> already in data/flags.jsonl
[tokens] in 4,214 / out 404 | $0.0125
```

## e. Restore the original state

Terminal 2:
```
.venv/bin/python -m src.verified unresolve vf-0001
wc -c data/verified_fixes.jsonl
.venv/bin/python -m src.verified list | head -1
```
Real output:
```
Removed vf-0001; reopened 1 flag(s).
       0 data/verified_fixes.jsonl
11 open of 11 flags in data/flags.jsonl
```

Confirm the flag is open again (optional): `{'status': 'open', 'notes_quote': 'Superior – inguinal canal'}`.
Optional: ask the femoral triangle question once more in Terminal 1; it goes back to "under review" (real output):
```
====================================================================================================
Q: What are the borders of the femoral triangle?
====================================================================================================
The medial border is adductor longus and the lateral border is sartorius [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle].
The superior border line in the course notes is currently under review [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle].
General anatomy knowledge, pending Dr. Inglis: the superior border is the inguinal ligament, not the inguinal canal, which is a separate passage in the anterior abdominal wall above the ligament.
The apex lies inferiorly, where sartorius crosses adductor longus [Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle].
Ask for more detail if you need it.

--- retrieved (hybrid search; score = boosted RRF) ---
  0.0403 cos 0.78  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle
  0.0394 cos 0.80  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Femo
  0.0388 cos 0.77  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Femo
  0.0386 cos 0.76  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Cont
  0.0382 cos 0.76  NOTES   Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle > Deep
[flag: under review] Superior – inguinal canal -> already in data/flags.jsonl
[tokens] in 4,254 / out 352 | $0.0120
```

**Say:** "That was a demo fix; the file is back to empty and the flag is open again."

## f. Guide mode, Lecture 09

Terminal 2 (interactive; type the lines after each `>`):
```
.venv/bin/python -m src.modes.guide --lecture "Lecture 09" --body-type "more fat, less muscle"
```
Type, in order: `I'm at station 4` / `not sure` / `skip to the last station` / `rechecked` / `next` / `I see six carpal bones in three rows, and the pisiform is in the distal row.` / `quit`
(To replay it without typing: `.venv/bin/python -m src.modes.guide --lecture "Lecture 09" --body-type "more fat, less muscle" --script tests/scripts/guide_demo.txt`.)

**Say:**
- "This is SAMPLE MODE: the notes are descriptive, not a dissection procedure, so it walks the lecture in its own order. It does not invent steps."
- "I claim I'm at station 4. It checks stations 1-3 and sends me back when I'm not sure. It never lets me skip ahead."
- "I describe station 2 wrongly. It corrects me from the notes. It only shows a consequence when the notes state one that relates to my specific mistake; otherwise it says so and sends me to the instructor."

Real output (the cards were cached, so there is no wait):
```
SAMPLE MODE: built from the lecture's own order, not a dissection procedure.
Preparing Lecture 09 - The Hand (station cards are extracted once and cached)...
22 stations ready. New card extractions: 0 (cached: 22)

Body type: more fat, less muscle
Stations (* = done): 1 Overview  |  2 Bones of the hand: Carpal bones  |  3 Bones of the hand:
Metacarpal Bones  |  4 Bones of the hand: Phalanges  |  5 Fascia and Compartments  |  6 Fascia and
Compartments: Palmar Fascia  |  7 Fascia and Compartments: Dorsal Fascia, Central Compartment  |  8
Fascia and Compartments: Thenar Compartment  |  9 Fascia and Compartments: Hypothenar Compartment,
Interosseus Compartment, Adductor Compartment  |  10 Muscles of the Hand: Thenar Muscles  |  11
Muscles of the Hand: Hypothenar Eminence  |  12 Muscles of the Hand: Adductor Pollicis  |  13
Muscles of the Hand: Lumbricals  |  14 Muscles of the Hand: Interossei Muscles  |  15 Long Tendons
of the Hand: Flexor Digitorum Tendons  |  16 Long Tendons of the Hand: Flexor Pollicis Longus Tendon
|  17 Long Tendons of the Hand: Extensor Digitorum Tendons  |  18 Vasculature of the Hand  |  19
Vasculature of the Hand: Superficial Palmar Arch  |  20 Vasculature of the Hand: Deep Palmer Arch  |
21 Nerves of the Hand: Median Nerve  |  22 Nerves of the Hand: Ulnar Nerve, Radial Nerve
22 stations. Which station are you at? (number or name)
> I'm at station 4
Before station 4 you should have identified:
S1 Overview: Distal-most region of the upper appendage; Opposable digit; 1st digit; Palmar region; Dorsal region
S2 Bones of the hand: Carpal bones: Carpal bones; Scaphoid; Lunate; Triquetrium; Pisiform (+5 more)
S3 Bones of the hand: Metacarpal Bones: Metacarpal bones; Base of metacarpal; Head of metacarpal; Carpal bones; Phalanges (+2 more)
Have you?
> not sure
Go back to station 1 (Overview) first. You can't skip ahead.
Station 1/22: Overview
Identify: Distal-most region of the upper appendage; Opposable digit; 1st digit; Palmar region; Dorsal region
You should see: Distal-most region of the upper appendage; Palmar region found anteriorly (+2 more)
Landmarks: Palmar region found anteriorly, dorsal region found posteriorly (+1 more)
Describe what you see.
> skip to the last station
You can't skip ahead: station 1 (Overview) isn't done yet.
Finish station 1 first: describe what you see, or say 'rechecked'.
> rechecked
Noted: you re-checked it. Type next to continue.
> next
Station 2/22: Bones of the hand: Carpal bones
Identify: Carpal bones; Scaphoid; Lunate; Triquetrium; Pisiform; Trapezium; Trapezoid (+3 more)
You should see: 8 bones arranged in 2 rows of 4; Row one: scaphoid, lunate, triquetrium, pisiform (+2 more)
Landmarks: Carpal bones are the bones of the wrist (+1 more)
One line here is under review. General anatomy knowledge, pending Dr. Inglis: The ulna does not directly articulate with the carpal bones. The wrist (radiocarpal) joint is formed by the distal radius and an articular disc (fibrocartilaginous pad), which separates the ulna from…
Describe what you see.
> I see six carpal bones in three rows, and the pisiform is in the distal row.
Not yet. The notes say there are 8 carpal bones in 2 rows of 4, not six bones in three rows. The pisiform is in the proximal row (scaphoid, lunate, triquetrium, pisiform), while the distal row is trapezium, trapezoid, capitate, hamate.
The notes say you should see: 8 bones arranged in 2 rows of 4; Row one: scaphoid, lunate, triquetrium, pisiform (+2 more)
The notes don't state a consequence for this. Ask your instructor.
Re-check and describe it again, or say 'rechecked'.
> quit
Goodbye. Progress this session: 1/22 stations done.

[judge tokens] in 1,182 / out 116 | $0.0035
```

## g. Q&A: amoxicillin dosing (the "not covered" decline)

Terminal 1:
```
What is the normal dose of amoxicillin?
```

**Say:** "Clinical advice is outside the notes and the textbook. It declines and does not answer from memory. Questions like treatment of a disease or diagnosing a heart attack are declined the same way."

Real output:
```
====================================================================================================
Q: What is the normal dose of amoxicillin?
====================================================================================================
Not covered: I could not find anything relevant in Dr. Inglis's course notes or the OpenStax reference text, so I won't answer from memory. (There is no web search yet.)

--- retrieved (hybrid search; score = boosted RRF) ---
  0.0261 cos 0.60  OpenStax OpenStax A&P 2e > Fluid, Electrolyte, and Acid-Base Balance > Disorders of Acid-Base Balance > C
  0.0253 cos 0.56  OpenStax OpenStax A&P 2e > Fluid, Electrolyte, and Acid-Base Balance > Water Balance > Regulation of Wate
  0.0164 cos 0.59  OpenStax OpenStax A&P 2e > The Cardiovascular System: The Heart > Cardiac Physiology > Heart Rates
  0.0164 cos 0.54  OpenStax OpenStax A&P 2e > The Reproductive System > Anatomy and Physiology of the Ovarian Reproductive S
  0.0161 cos 0.44  OpenStax OpenStax A&P 2e > Fluid, Electrolyte, and Acid-Base Balance > Electrolyte Balance > Roles of Ele
  -> treated as NOT FOUND (best cosine 0.60 < 0.68)
[note] no model call made (best cosine 0.60 < 0.68)
```

Then type `quit` in Terminal 1.

## If something goes wrong

- **"Your credit balance is too low" / an API error:** the Q&A prints "Sorry, I could not answer that (...)" and the guide judge says "I couldn't check that just now". Top up the Anthropic balance and retry. Steps a, e and the pre-flight need no API.
- **The Q&A answer reads slightly differently from this runbook:** normal. Check that the citations, the "flagged for review" tag, the "under review" wording and (in d) the `[Verified by ...]` citation are present.
- **Step d: the answer does not show `[Verified by ...]`:** run `.venv/bin/python -m src.verified list`; if the flag is not listed as open, it was already resolved: `cat data/verified_fixes.jsonl`, then `unresolve` the id shown and retry.
- **Restore everything after a demo:** `.venv/bin/python -m src.verified unresolve vf-0001` (use the id in `data/verified_fixes.jsonl`); `wc -c data/verified_fixes.jsonl` must say 0.
- **`data/flags.jsonl` grows** when you ask new questions that touch flagged lines. That is intended (duplicates are skipped), and it only adds to the review queue.
- **Cost:** a Q&A answer is about $0.012-0.015; the guide's first run on a new lecture costs about $0.17 for its station cards (cached afterwards).

## Say these limits out loud if asked

- Everything in the fact-check is AI-generated and unreviewed. About 83% of the items are wording or typo suggestions (only 90 are confirmed factual), and 617 of 733 rest on general anatomy knowledge, not on the textbook.
- The OpenStax text is a placeholder under CC BY-NC-SA 4.0 (non-commercial); the tool quotes at most one short sentence of it.
- Guide mode is a sample built from the lecture's own order. It was only tried live on Lecture 09, and it is not a dissection procedure.
- No web search yet; no QUIZ mode yet.

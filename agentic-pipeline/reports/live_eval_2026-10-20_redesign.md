# Live evaluation after the answer redesign (2026-10-20)

Same 31 questions, same pipeline (BullsAI gemma-4-31B-it, reranker on, web on), no-logging sandbox, judge `openai/gpt-oss-120b` (given the answer and the passages it cites). Previous run: {'yes': 23, 'partly': 2, 'no': 1}. This run: **{'yes': 24, 'partly': 2, 'no': 0}**.

| # | group | question | sec | tier | cites ok | judge |
|---|---|---|---|---|---|---|
| 1 | keyword | apex | 5.8 | term | 6/6 | **yes**: All statements are directly supported by the provided citations. |
| 2 | keyword | thenar | 4.0 | term | 5/5 | **yes**: All statements are directly supported by the cited lecture passages. |
| 3 | keyword | hypothenar | 4.6 | term | 6/6 | **yes**: All claims are supported by the cited passages. |
| 4 | keyword | trochanter | 3.5 | term | 5/5 | **yes**: All statements are directly supported by the cited passages. |
| 5 | keyword | nerve supply | 10.6 | term | 6/6 | **yes**: All answer statements are directly supported by the cited passages. |
| 6 | keyword | what is a foramen? | 4.4 | openstax | 2/2 | **yes**: All statements are directly supported by the cited OpenStax passages. |
| 7 | normal | What are the walls of the middle ear? | 10.4 | course | 1/1 | **yes**: All claims in the answer are directly supported by the cited passage. |
| 8 | normal | What are the boundaries and contents of the femoral triangle? | 11.8 | course | 3/3 | **partly**: One statement about Dr. Inglis reviewing the line is not supported by the cited passages |
| 9 | normal | What does the sartorius do? | 3.2 | course | 1/1 | **yes**: The answer's claim that the sartorius covers the adductor (subsartorial) canal is directly supported by the cited passage. |
| 10 | normal | Which muscles make up the rotator cuff? | 2.8 | course | 3/3 | **yes**: All statements are directly supported by the cited passages. |
| 11 | normal | What nerve supplies the muscles of the hypothenar eminence? | 2.8 | course | 1/1 | **yes**: The citation states the ulnar nerve provides branches to the hypothenar eminence, supporting the answer's claim. |
| 12 | normal | What are the contents of the carpal tunnel? | 3.7 | course | 3/3 | **yes**: All statements in the answer are directly supported by the cited passages. |
| 13 | procedural | How do I reflect the skin over the thigh? | 3.1 | course | 3/3 | **yes**: All three steps are directly supported by the cited dissection guide passages. |
| 14 | procedural | What are the steps to expose the femoral triangle? | 4.2 | course | 3/3 | **yes**: All steps mentioned in the answer are directly supported by the cited passages. |
| 15 | procedural | How do I remove the gluteus maximus? | 2.8 | course | 1/1 | **yes**: All claims in the answer are directly supported by the cited passage. |
| 16 | procedural | How do I identify the piriformis and the sciatic nerve? | 3.8 | course | 3/3 | **yes**: All statements in the answer are directly supported by the provided citations. |
| 17 | procedural | How do I open the adductor canal? | 2.1 | course | 1/1 | **yes**: All steps are directly stated in the cited passage |
| 18 | procedural | How do I open the carpal tunnel? | 2.8 | course | 1/1 | **yes**: All steps in the answer are directly stated in the cited dissection guide passage. |
| 19 | procedural | How do I remove the brain? | 5.3 | course | 7/7 | **yes**: All steps described in the answer are directly supported by the cited passage excerpts. |
| 20 | procedural | How do I open the pericardium? | 2.6 | course | 1/1 | **yes**: All steps in the answer are directly supported by the cited passage. |
| 21 | web | What is Broca's area? | 3.3 | web | 1/1 | **yes**: The answer's statement about Broca's area being in the frontal lobe of the dominant (typically left) hemisphere and supporting speech production is directly supported by the cited passage. |
| 22 | web | What is the thyroglossal duct? | 4.4 | web | 1/1 | **yes**: All statements are directly supported by the cited passage |
| 23 | web | What is the glomus tympanicum? | 3.1 | web | 1/1 | **yes**: All statements in the answer are directly supported by the cited passage. |
| 24 | refusal | amoxicillin | 0.7 | refused (not_anatomy) | 0/0 | n/a |
| 25 | refusal | Who won the 2022 World Cup? | 0.3 | refused (not_anatomy) | 0/0 | n/a |
| 26 | follow-up | What is the roof made of? | 2.4 | refused (nothing_relevant) | 0/0 | n/a |
| 27 | follow-up | And which nerve is the most lateral? | 3.5 | course | 2/2 | **yes**: All stated claims are directly supported by the cited passages |
| 28 | follow-up | Where does it insert? | 5.5 | course | 2/2 | **yes**: All claims in the answer are directly stated in the cited passages. |
| 29 | follow-up | What do I identify after that? | 2.6 | course | 1/1 | **partly**: The answer adds a step about reflecting the gluteus maximus that is not mentioned in the cited passage |
| 30 | outside-access | What are the walls of the middle ear? | 3.1 | refused (outside_access) | 0/0 | n/a |
| 31 | outside-access | How do I remove the gluteus maximus? | 0.4 | refused (outside_access) | 0/0 | n/a |

Mean 4.0 s (previous 3.2 s). Leaks in the student view: 0. Unmatched citations: 0.
The two 'partly' verdicts: #8 counts the program's own neutral sentence 'Dr. Inglis is reviewing this line' as unsupported (it is not a claim); #29 counts the framing sentence 'After reflecting the gluteus maximus, the guide indicates...' (the two listed steps are from slide 9). No 'no' verdicts.
Coverage check (OpenStax-only answers): ran for 1 of 31 questions here (#30, walls of the middle ear for a student without Lecture 16b: check 0.8 s, Wikipedia 0.4 s, nothing relevant found, so the answer was 'not in your lectures'). In four extra runs of OpenStax-only questions it added 1.0 to 1.9 s (check about 1 s, Wikipedia about 0.8 s); average extra about 1.8 s. It does not run for notes, guides, steps or term lookups.
OpenStax links: all 197 section URLs of the ingested book were requested (`scripts/verify_openstax_urls.py`) and all returned the real section page; none needed the contents-page fallback.

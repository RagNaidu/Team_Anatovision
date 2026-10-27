# Wikipedia web tier: live check (2026-10-19)

One run each through the real pipeline (BullsAI gemma-4-31B-it, reranker on, web fallback on, Wikipedia first then MeSH/MedlinePlus), no-logging sandbox. Judge: `openai/gpt-oss-120b`, given the answer and the fetched text. Topics 4 to 6 are my picks: none is in the notes or OpenStax.

| question | sec | page(s) used | answer correct | label shown | attribution in Sources tab | web searched | judge |
|---|---|---|---|---|---|---|---|
| What is Broca's area? | 4.9 | Broca's area; Prefrontal cortex; Brain asymmetry | yes: speech production in the left inferior frontal gyrus (pars triangularis) matches the page | From Wikipedia, ... | title, link, retrieved date, "Wikipedia, CC BY-SA 4.0" | yes | **yes**: All answer statements are supported by the provided Wikipedia excerpts. |
| What is the thyroglossal duct? | 6.4 | Persistent thyroglossal duct; MeSH: Thyroglossal Cyst | yes: embryonic midline duct from thyroid to tongue base; relations to strap muscles match | From Wikipedia, ... | title, link, retrieved date, "Wikipedia, CC BY-SA 4.0" | yes | **yes**: All statements in the answer are directly supported by the fetched text. |
| What is the glomus tympanicum? | 4.9 | MeSH: Glomus Tympanicum Tumor; MeSH: Glomus Tympanicum | yes (no Wikipedia page exists for it, so MeSH answered): chemoreceptive body beside the tympanic cavity | From the web, ... (MeSH only) | title, link, date (MeSH) | yes | **yes**: All statements are directly supported by the fetched text |
| What is Waldeyer's ring? | 2.7 | Tonsil | yes: ring of lingual, palatine, tubal and adenoid tonsils (the page is 'Tonsil') | From Wikipedia, ... | title, link, retrieved date, "Wikipedia, CC BY-SA 4.0" | yes | **yes**: All statements in the answer are directly supported by the fetched text. |
| What is Calot's triangle? | 4.7 | Cystohepatic triangle; Cystic node | yes: cystic duct, common hepatic duct, liver edge; cystic artery inside (page 'Cystohepatic triangle') | From Wikipedia, ... | title, link, retrieved date, "Wikipedia, CC BY-SA 4.0" | yes | **yes**: All statements in the answer are directly supported by the fetched text. |
| What is the sphincter of Oddi? | 5.4 | Sphincter of Oddi; Biliary endoscopic sphincterotomy; MeSH: Sphincter of Oddi | yes: muscular valve at the major duodenal papilla controlling bile and pancreatic juice | From Wikipedia, ... | title, link, retrieved date, "Wikipedia, CC BY-SA 4.0" | yes | **yes**: All claims are directly supported by the fetched text |
| amoxicillin dose | 0.5 | none | refused as clinical advice, no search | n/a (refused) | n/a | no | n/a |
| who won the world cup | 0.4 | none | refused as not anatomy, no search | n/a (refused) | n/a | no | n/a |

Judge totals: yes 6, partly 0, no 0

Notes: Wikimedia answers HTTP 429 to bursts from a generic User-Agent (no contact address is allowed in requests), so the fetcher spaces its Wikipedia calls (0.7 s), reads only the best page in full, and retries once after Retry-After. When Wikipedia still refuses, the tier silently uses MeSH/MedlinePlus (this happened in two earlier runs of the same check, before the spacing was added). The web tier added about 2 to 6 s.

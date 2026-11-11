"""The right-hand pane.

Student side (renders ONLY the student-safe data from src/student_view.py): Sources (the passage behind a citation, the
line that supports the sentence) and a plain "How this answer was built". No scores, no fact-check text, no cost.
Instructor side (a professor previewing as a student): `instructor_detail` shows the full result: real pipeline events,
scores, tokens, cost, model, fact-check detail.
"""
import streamlit as st

from app import theme
from app.data import openstax_credit
from src import citations as cit
from src import llm
from src import trust
from src import student_view as sv

PANES = ["Sources", "How this answer was built"]


def select(msg, kind, **kw):
    st.session_state.sel = {"msg": msg, "kind": kind, **kw}
    if kind == "cite":
        st.session_state["pane"] = "Sources"                       # a source marker opens the Sources tab (and that source)


def clear_selection():
    st.session_state.sel = None


def badge(kind):
    return theme.badge_html(kind)


def credit_html(src):
    c = openstax_credit()
    link = f'<a href="{theme.esc(src["source_url"])}" target="_blank">this section</a> · ' if src.get("source_url") else ""
    return (f'<div class="credit">{link}<a href="{theme.esc(c["book_url"])}" target="_blank">{theme.esc(c["text"])}</a> '
            f'(<a href="{theme.esc(c["licence_url"])}" target="_blank">licence</a>). Reference text, not course notes.</div>')


# ----------------------------------------------------------------------------
# student side
# ----------------------------------------------------------------------------

def source_head(src):
    """Title ("Lecture 16b · Middle Ear") with the muted heading path under it."""
    crumb = f'<div class="crumb">{theme.esc(src["crumb"])}</div>' if src.get("crumb") else ""
    return f'<div class="pane-title">{theme.esc(src["title"])}</div>{crumb}'


def passage_block(src, spans=(), sentence=""):
    """One passage for a student: badge, title + path, the text (indentation kept) with ONLY the supporting line highlighted,
    then any neutral notes (outside the quoted text)."""
    spans = sorted({tuple(sp) for sp in spans})
    parts = [badge(src["source_type"])]
    if src.get("uploaded"):
        parts.append(" " + theme.badge_html("uploaded", f'Uploaded {src["uploaded"]}'))
    parts.append(source_head(src))
    if src.get("section_number"):
        parts.append(f'<div class="kv">section {theme.esc(src["section_number"])}</div>')
    if sentence:
        parts.append(f'<div class="supports"><b>Supports:</b> “{theme.esc(sentence)}”'
                     + ("" if spans else "<br>That sentence could not be matched to one line of this passage.") + "</div>")
    parts.append(f'<div class="passage">{cit.passage_html(src["text"], spans)}</div>')
    for n in src.get("notes", []):
        parts.append(f'<div class="kv">{theme.esc(n)}</div>')
    if src["source_type"] == "open_text":
        parts.append(credit_html(src))
    if src["source_type"] == "web":
        parts.append(web_credit_html(src))
    return "".join(parts)


def web_credit_html(src):
    """Where a web passage came from: site, link, the date it was fetched. Always labelled as not course material."""
    link = (f'<a href="{theme.esc(src["source_url"])}" target="_blank" rel="noopener">{theme.esc(src["source_url"])}</a>'
            if src.get("source_url") else "")
    who = src.get("license") or src.get("site", "")            # "Wikipedia, CC BY-SA 4.0" for Wikipedia pages
    return (f'<div class="credit"><b>{theme.esc(who)}</b> · retrieved {theme.esc(src.get("retrieved", ""))}<br>{link}<br>'
            "From the web, not course notes. Check with your instructor.</div>")


def correction_block(fix):
    return (f'{theme.badge_html("verified", "Corrected")}<div class="pane-title">{theme.esc(fix["breadcrumb"])}</div>'
            f'<div class="kv">{theme.esc(fix["label"])}</div>'
            f'<div class="passage">{theme.esc(fix["correction"] or "Dr. Inglis confirmed the line as written.")}</div>')


def status_block(what, view):
    """Chip pane for a status chip: one neutral sentence per affected section. Nothing else."""
    if what == "corrected":
        return "".join(correction_block(f) for f in view["fixes"]) or ""
    mark, sentence = ("reviewing", sv.NEUTRAL_REVIEW) if what == "reviewing" else ("check", sv.CHECK_SENTENCE)
    names = [s for s in view["sources"] if mark in s["marks"]]
    head = source_head(names[0]) if names else ""
    return f'{head}<div class="passage">{theme.esc(sentence)}</div>'


def source_card(msg_index, k, src, tag="", num=None):
    """The whole card is the button (a transparent button covers it), so there is no tiny Open target. `num` is the source's number
    in the answer, the same as its marker [n] and its line in the Sources list."""
    with st.container(key=f"srccard_{msg_index}_{tag}{k}"):
        n = f'<span class="srcnum">{num}</span>' if num else ""
        st.markdown(f'<div>{n}{badge(src["source_type"])}{source_head(src)}</div>', unsafe_allow_html=True)
        st.button(f'Open passage: {src["title"]}, {src["crumb"]}', key=f"srcopen_{msg_index}_{tag}{k}", on_click=select,
                  args=(msg_index, "chunk"), kwargs={"chunk": k})


def trust_html(view):
    """'Notes: Dr. Inglis, updated <date>' and the textbook credit, only for what this answer used."""
    t, bits = view.get("trust", {}), []
    if t.get("notes"):
        when = trust.pretty(t.get("updated", ""))
        bits.append("Notes: Dr. Inglis" + (f", loaded {theme.esc(when)}" if when else ""))
    if t.get("guides"):
        bits.append("Dissection guide: Dr. Inglis")
    if t.get("textbook"):
        bits.append("OpenStax A&amp;P 2e (CC BY-NC-SA)")
    if t.get("web"):
        bits.append("Public web pages, not course notes")
    return f'<div class="trust">{" · ".join(bits)}</div>' if bits else ""


def select_clear_note():
    pass


def render_sources(msg_index, view, header="Sources for the answer above", report=None):
    sel = st.session_state.sel
    theme.label(header)
    if view["status"] in ("not_found", "out_of_scope", "capped", "error") or not view["sources"]:
        theme.meta("No sources for this answer. Nothing relevant was found, so no passages are shown.")
        return
    st.markdown(trust_html(view), unsafe_allow_html=True)
    if report:
        report()
    if not sel or sel["msg"] != msg_index:
        used = view.get("used", [])
        theme.meta("Select a numbered marker in the answer, or a card below, to read the passage.")
        theme.label("Used in this answer")
        numbers = {c["chunk"]: c["n"] for c in view["citations"] if c["chunk"] is not None}
        for k in used:
            source_card(msg_index, k, view["sources"][k], "u", numbers.get(k))
        if not used:
            theme.meta("No passage was cited in this answer.")
        others = [k for k in range(len(view["sources"])) if k not in used]
        if others:
            with st.expander(f"Also looked at ({len(others)})"):
                for k in others:
                    source_card(msg_index, k, view["sources"][k], "o")
        return
    st.button("Back to all sources", key=f"back_{msg_index}", on_click=clear_selection, icon=":material/arrow_back:")
    if sel["kind"] == "cite":
        c = next(c for c in view["citations"] if c["n"] == sel["n"])
        if not c["matched"]:
            theme.alert("error", "Citation not found in retrieved sources",
                        f'The answer cites “{c["cite"]}”, but that is not one of the passages found for this question. '
                        "Treat the sentence as unsupported.")
        elif c["kind"] == "verified":
            st.markdown(correction_block(view["fixes"][c["fix"]]), unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="srcnum-head">Source {c["n"]}</div>', unsafe_allow_html=True)
            unit = view["units"][sel["unit"]] if sel.get("unit") is not None else None
            spans = (unit or {}).get("support", {}).get(c["n"], c["support"][0]["spans"] if c["support"] else [])
            sentence = (unit or {}).get("text") or (c["support"][0]["sentence"] if c["support"] else "")
            st.markdown(passage_block(view["sources"][c["chunk"]], spans, sentence), unsafe_allow_html=True)
    elif sel["kind"] == "chunk":
        st.markdown(passage_block(view["sources"][sel["chunk"]]), unsafe_allow_html=True)
    elif sel["kind"] == "status":
        st.markdown(status_block(sel["what"], view), unsafe_allow_html=True)


def render_built(view):
    """'How this answer was built', student version: which notes and textbook passages, and whether Dr. Inglis corrected a line."""
    theme.label("How this answer was built")
    groups, corrections = sv.built_lines(view["built"])
    show_built(groups, corrections)


def show_built(groups, corrections):
    for title, items in groups:
        rows = "".join(f"<li>{theme.esc(i)}</li>" for i in items)
        st.markdown(f'<div class="label">{theme.esc(title)}</div>' + (f'<ul class="items">{rows}</ul>' if rows else
                    '<div class="small">None.</div>'), unsafe_allow_html=True)
    for sentence in corrections:
        st.markdown(f'<div class="small">{theme.esc(sentence)}</div>', unsafe_allow_html=True)


def render_pane(msg_index, msg, instructor=False, latest=True, question="", report=None):
    """msg = {"result": student view, "instructor": full result or None}. `instructor` adds the Instructor detail tab.
    Choosing a chip or a card never changes the tab: only the person clicking a tab does."""
    view = msg["result"] if msg else None
    chosen = bool(st.session_state.sel and msg and st.session_state.sel["msg"] == msg_index)
    st.markdown(f'<span class="pane-marker{" sheet-open" if chosen else ""}"></span>', unsafe_allow_html=True)
    if chosen:                                    # on a phone or tablet the pane is a bottom sheet: it needs a way out
        with st.container(key="sheet_bar"):
            st.button("Close", key="sheet_close_btn", on_click=clear_selection, icon=":material/close:")
    options = PANES + (["Instructor detail"] if instructor else [])
    pane = st.segmented_control("Pane", options, key="pane", label_visibility="collapsed", default=PANES[0])
    if view is None:
        theme.meta("Sources for each answer appear here.")
    elif pane == "How this answer was built":
        render_built(view)
        if st.session_state.sel and st.session_state.sel["msg"] == msg_index:
            theme.meta("You selected a passage. Switch to the Sources tab to read it.")
    elif pane == "Instructor detail" and instructor:
        instructor_detail(msg.get("instructor"))
    else:
        head = "Sources for the answer above" if latest else "Sources for an earlier answer" + (f': “{question[:60]}”' if question else "")
        render_sources(msg_index, view, head, report)


# ----------------------------------------------------------------------------
# instructor side (full detail; never rendered in a real student session)
# ----------------------------------------------------------------------------

def chunk_block(chunk, sentences=(), fixes=()):
    """HTML for one retrieved passage: badge, breadcrumb, scores, the full text with the used sentence highlighted."""
    spans = []
    for s in sentences:
        spans += cit.best_spans(chunk["text"], s)
    spans = sorted(set(spans))
    by_marker = {f["marker"]: f for f in fixes if f.get("marker")}
    parts = [badge(chunk["source_type"])]
    if chunk.get("uploaded"):
        parts.append(" " + theme.badge_html("uploaded", f'Uploaded {chunk["uploaded"]}'))
    parts.append(f'<div class="pane-title">{theme.esc(chunk["breadcrumb"])}</div>')
    parts.append(f'<div class="kv">retrieval score {chunk["score"]:.4f} · similarity {chunk["cosine"]:.2f}'
                 + (f' · section {theme.esc(chunk["section_number"])}' if chunk.get("section_number") else "") + "</div>")
    if sentences:
        note = "highlighted: the passage the answer sentence was built from" if spans else \
            "the answer sentence could not be matched to one line of this passage"
        parts.append(f'<div class="kv">{note}</div>')
    parts.append(f'<div class="passage">{cit.passage_html(chunk["text"], spans, by_marker)}</div>')
    if chunk["source_type"] == "web":
        parts.append(web_credit_html(chunk))
    if chunk["source_type"] == "open_text":
        c = openstax_credit()
        link = f'<a href="{theme.esc(chunk["source_url"])}" target="_blank">this section</a> · ' if chunk.get("source_url") else ""
        parts.append(f'<div class="credit">{link}<a href="{theme.esc(c["book_url"])}" target="_blank">{theme.esc(c["text"])}</a> '
                     f'(<a href="{theme.esc(c["licence_url"])}" target="_blank">licence</a>). Reference text, not course notes.</div>')
    return "".join(parts)


def fix_block(fix):
    return (f'{badge("verified")}<div class="pane-title">{theme.esc(fix["breadcrumb"])}</div>'
            f'<div class="kv">{theme.esc(fix["decision"].replace("_", " "))} · verified by {theme.esc(fix["by"])}, '
            f'{theme.esc(fix["date"])} · record {theme.esc(fix["id"])}</div>'
            f'<div class="passage">{theme.esc(fix["correction"] or "Dr. Inglis confirmed the line as written.")}</div>'
            '<div class="credit">A verified fix is the highest-priority source. The original wording is not repeated.</div>')


def flag_block(flag, professor):
    names = {"under_review": ("Under review", "chip chip-review"), "doubtful": ("Flagged for review", "chip chip-flag")}
    text, cls = names.get(flag["kind"], (flag["kind"], "chip"))
    body = [f'<span class="{cls}">{text}</span><div class="pane-title">{theme.esc(flag["breadcrumb"])}</div>']
    if flag["kind"] == "under_review":
        body.append('<div class="passage">A fact-check flagged one line here as probably wrong, so this answer does not '
                    'repeat it. General anatomy knowledge, pending Dr. Inglis: '
                    f'{theme.esc(flag["statement"])}</div>')
    else:
        body.append('<div class="passage">A fact-check thinks one line here may be imprecise. The line was used, '
                    f'with a note. What it suggests: {theme.esc(flag["statement"])}</div>')
    if professor:
        body.append(f'<div class="kv">Notes quote: “{theme.esc(flag.get("quote", ""))}”</div>'
                    f'<div class="kv">AI reason: {theme.esc(flag.get("reason", ""))}</div>'
                    f'<div class="kv">severity {theme.esc(flag.get("severity", ""))} · confidence {flag.get("confidence")}</div>')
    body.append('<div class="credit">AI-generated suggestion, not a verdict. Dr. Inglis decides.</div>')
    return "".join(body)


def event_detail(ev):
    d, k = ev["detail"], ev["kind"]
    if k == "search":
        top = "; ".join(f'{"notes" if h["source_type"] == "notes" else "OpenStax"} {h["score"]:.3f} (cos {h["cosine"]:.2f})'
                        for h in d["hits"][:5])
        return f'{d["n_hits"]} passages ranked. Top scores: {top or "none"}.'
    if k == "threshold":
        return (f'Best cosine similarity {d["best_cosine"]:.2f} against a minimum of {d["min_cosine"]}: '
                + ("relevant enough, so the model was called." if d["found"] else f'not relevant enough ({d["reason"]}); no model call.'))
    if k == "access":
        return f'{d["n_lectures"]} lecture(s) allowed; notes from all other lectures were removed before ranking.'
    if k == "access_check":
        return ("Relevant notes exist outside your lectures; none were used." if d["outside_notes_found"]
                else "No relevant notes outside your lectures.")
    if k == "factcheck":
        return (f'{len(d["withheld"])} line(s) withheld as under review; {len(d["flagged_doubtful"])} line(s) tagged as doubtful.')
    if k == "verified_check":
        return f'{d["fixes_on_file"]} verified fix(es) on file; {len(d["found"])} apply to the retrieved passages.'
    if k == "model_call":
        return f'{d["input_tokens"]:,} tokens in, {d["output_tokens"]:,} out, {d["seconds"]} s.'
    if k == "guard_check":
        bits = ["OpenStax quoting limit " + ("ok" if d["copyright_ok"] else "exceeded")]
        bits.append("brief format ok" if not d["format_problems"] else "format problems: " + "; ".join(d["format_problems"]))
        return ", ".join(bits) + "."
    if k == "citation_check":
        s = f'{d["n_matched"]} of {d["n_citations"]} citations matched a retrieved passage.'
        return s + (f' Not found: {"; ".join(d["not_found"])}.' if d["not_found"] else "")
    if k == "flags":
        return f'{len(d["flags"])} flag(s) logged for review.'
    if k == "cap":
        return f'Session cost ${d["session_cost"]:.2f} reached the cap of ${d["cap"]:.2f}.'
    if k == "error":
        return d.get("error", "")
    return " ".join(f"{a}: {b}" for a, b in d.items())


def render_timeline(result):
    st.markdown('<div class="label">How this answer was built</div>'
                '<div class="small">The steps the program actually ran for this answer, in order, as recorded while it ran. '
                'It is a fixed pipeline (search, checks, one model call, checks), not an autonomous agent.</div>',
                unsafe_allow_html=True)
    rows = "".join(f'<div class="tl-item"><span class="tl-t">{e["t"]:.1f} s</span><div class="tl-label">{theme.esc(e["label"])}</div>'
                   f'<div class="tl-detail">{theme.esc(event_detail(e))}</div></div>' for e in result["events"])
    st.markdown(f'<div class="tl">{rows}</div>', unsafe_allow_html=True)
    t = result["tokens"]
    st.markdown(f'<div class="kv">Tokens {t["input"]:,} in / {t["output"]:,} out · cost {theme.dollars(result["cost"]) if llm.cost_tracked(result.get("model", "")) else llm.NOT_TRACKED} · model {theme.esc(result.get("model", ""))}</div>',
                unsafe_allow_html=True)


def instructor_detail(raw):
    """Everything the program knew about this answer: events, scores, tokens, cost, model, fact-check detail."""
    if raw is None:
        st.markdown('<div class="small">No detail was kept for this turn.</div>', unsafe_allow_html=True)
        return
    st.markdown('<div class="small">Only you see this tab. A student sees none of it.</div>', unsafe_allow_html=True)
    render_timeline(raw)
    if raw.get("flags_hit"):
        st.markdown('<div class="label">Fact-check flags used in this answer</div>', unsafe_allow_html=True)
        for f in raw["flags_hit"]:
            st.markdown(flag_block(f, True), unsafe_allow_html=True)
    if raw.get("verified_fix_used"):
        st.markdown('<div class="label">Verified fixes used</div>', unsafe_allow_html=True)
        for f in raw["verified_fix_used"]:
            st.markdown(fix_block(f), unsafe_allow_html=True)
    if raw.get("retrieved_chunks"):
        st.markdown('<div class="label">Retrieved passages</div>', unsafe_allow_html=True)
        for ch in raw["retrieved_chunks"]:
            st.markdown(chunk_block(ch, (), raw.get("verified_marks", [])), unsafe_allow_html=True)

"""Look and feel: "Vellum & Petrol". Calm warm paper, ink text, ONE teal accent. Everything visual lives in this file.

  TOKENS / STATUS / BADGES      the colours, defined once and written out as CSS variables on :root
  icon(), alert(), chip_html(), badge_html(), card_html(), page_title(), section(), label(), meta(), stat(),
  empty_state(), loading_html(), wordmark(), button_row()      shared components; views never write colours, fonts or
                                                              pixel sizes of their own
  inject()                      the stylesheet (+ a very small script that names Streamlit's own icon-only buttons)

Rules the stylesheet follows: spacing only from 4/8/12/16/24/32 px; radius 8px (cards, inputs) and 999px (chips); body
16px, secondary text 14px, nothing under 13px; one sans for the interface, a serif ONLY for the wordmark and page titles;
every interactive element has a 2px teal focus ring; status is always icon + text, never colour alone.
"""
import html
import json
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"
FAVICON = str(ASSETS / "favicon.png")

TOKENS = {
    "bg": "#FAF7F2", "surface": "#FFFFFF", "sidebar": "#F0EBE0", "text": "#1F2528", "muted": "#5A6166",
    "border": "#DDD6C8", "input-border": "#8A8374", "primary": "#0F5E6C", "primary-hover": "#0B4A56",
    "primary-pressed": "#083A44", "tint": "#DDEEF0", "link": "#0B5563",
    # the specified #7A7466 is 3.9:1 on the sidebar; this is the same hue, darkened until it reaches 4.5:1 everywhere
    "disabled-text": "#6B6659", "progress-track": "#E6E0D2", "locked-border": "#CFC8B8",
    "highlight": "#F6E3A6", "highlight-bar": "#C9A227",
}
STATUS = {   # kind: (text, fill, border, icon)
    "review": ("#8A1F2D", "#F8E3E5", "#D9A3AA", "eye-off"),
    "doubtful": ("#6F4300", "#FCEFD0", "#E3BE6A", "warning"),
    "verified": ("#1F5E3A", "#DFF1E4", "#8FC4A0", "check"),
}
BADGES = {   # kind: (text colour, fill, label)
    "notes": ("#0B4F5C", "#DDEEF0", "Course notes"),
    "open_text": ("#42464C", "#E9E8E4", "OpenStax A&P 2e"),
    "dissection_guide": ("#0B4F5C", "#DDEEF0", "Dissection guide"),
    "web": ("#6F4300", "#FCEFD0", "From the web"),
    "verified": (STATUS["verified"][0], STATUS["verified"][1], "Verified fix"),
    "uploaded": ("#42464C", "#E9E8E4", "Uploaded"),
}
ALERTS = {   # kind: (icon, status colours or None for the neutral/teal ones, ARIA role)
    "info": ("info", None, "status"), "success": ("check-circle", "verified", "status"),
    "warning": ("alert-triangle", "doubtful", "alert"), "error": ("x-circle", "review", "alert"),
}

# ---- icons: simple 24px line drawings, used as CSS masks so they take the text colour ------------------------------
ICONS = {
    "info": "<circle cx='12' cy='12' r='9'/><path d='M12 11v5M12 8h.01'/>",
    "check-circle": "<circle cx='12' cy='12' r='9'/><path d='M8 12.5l2.7 2.7L16 9.5'/>",
    "alert-triangle": "<path d='M12 4l9 16H3z'/><path d='M12 10v4M12 17h.01'/>",
    "warning": "<path d='M12 4l9 16H3z'/><path d='M12 10v4M12 17h.01'/>",
    "x-circle": "<circle cx='12' cy='12' r='9'/><path d='M9 9l6 6M15 9l-6 6'/>",
    "eye-off": "<path d='M3 3l18 18'/><path d='M10.6 6.1A9.7 9.7 0 0 1 12 6c5 0 8.5 4 9.5 6a14 14 0 0 1-2.6 3.4M6.6 7.7A14 14 0 0 0 2.5 12c1 2 4.5 6 9.5 6 1.5 0 2.8-.4 4-.9'/><path d='M9.9 10a3 3 0 0 0 4.1 4.1'/>",
    "check": "<path d='M5 12.5l4.5 4.5L19 7.5'/>",
    "lock": "<rect x='5' y='11' width='14' height='9' rx='2'/><path d='M8 11V8a4 4 0 0 1 8 0v3'/>",
    "book-open": "<path d='M3 5.5C5 4.5 8 4.5 12 6.5c4-2 7-2 9-1v13c-2-1-5-1-9 1-4-2-7-2-9-1z'/><path d='M12 6.5v13'/>",
    "search": "<circle cx='11' cy='11' r='6.5'/><path d='M16 16l4.5 4.5'/>",
    "shield": "<path d='M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z'/>",
    "dot": "<circle cx='12' cy='12' r='3'/>",
}
LOGO = ("<svg class='logo' viewBox='0 0 24 24' width='{s}' height='{s}' role='img' aria-label='AnatoVision'>"
        "<path d='M8 16L16 8' stroke='{c}' stroke-width='3.4' stroke-linecap='round' fill='none'/>"
        "<g fill='{c}'><circle cx='6.2' cy='14.2' r='2.5'/><circle cx='9.8' cy='17.8' r='2.5'/>"
        "<circle cx='14.2' cy='6.2' r='2.5'/><circle cx='17.8' cy='9.8' r='2.5'/></g></svg>")


def _uri(inner):
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' "
           f"stroke-linecap='round' stroke-linejoin='round'>{inner}</svg>")
    return 'url("data:image/svg+xml,' + svg.replace("<", "%3C").replace(">", "%3E").replace("#", "%23") + '")'


def logo_svg(size=32, colour=None):
    return LOGO.format(s=size, c=colour or TOKENS["primary"])


def root_css():
    v = [f"--{k}:{val};" for k, val in TOKENS.items()]
    for kind, (t, f, b, _) in STATUS.items():
        v += [f"--{kind}-text:{t};", f"--{kind}-fill:{f};", f"--{kind}-border:{b};"]
    for kind, (t, f, _) in BADGES.items():
        v += [f"--badge-{kind.replace('_', '-')}-text:{t};", f"--badge-{kind.replace('_', '-')}-fill:{f};"]
    v += [f"--ic-{name}:{_uri(inner)};" for name, inner in ICONS.items()]
    v += ["--sp-1:4px;--sp-2:8px;--sp-3:12px;--sp-4:16px;--sp-6:24px;--sp-8:32px;--radius:8px;--pill:999px;",
          "--ring:2px solid var(--primary);",
          "--font-sans:'Source Sans','Source Sans 3','Source Sans Pro',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;",
          "--font-serif:Georgia,'Iowan Old Style','Times New Roman',serif;"]
    return ":root{" + "".join(v) + "}"


CSS = """
/* ============ base ============ */
html, body, .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
  background: var(--bg); color: var(--text); font-family: var(--font-sans); font-size: 16px; line-height: 1.5; }
.stApp * { letter-spacing: normal; }
p, li, label, .stMarkdown { font-size: 16px; line-height: 1.5; }
h1, h2, h3, h4, h5 { font-family: var(--font-sans); color: var(--text); font-weight: 600; line-height: 1.25; margin: 0; padding: 0; }
h1, [data-testid="stMarkdownContainer"] h1, .stMarkdown h1 { font-family: var(--font-serif) !important; font-weight: 600 !important; font-size: 32px !important; line-height: 1.2 !important; letter-spacing: -0.01em !important; padding: 0 !important; }
h2, [data-testid="stMarkdownContainer"] h2 { font-family: var(--font-sans) !important; font-size: 24px !important; font-weight: 600 !important; padding: 0 !important; }
h3, [data-testid="stMarkdownContainer"] h3 { font-family: var(--font-sans) !important; font-size: 20px !important; font-weight: 600 !important; padding: 0 !important; }
h4, [data-testid="stMarkdownContainer"] h4 { font-family: var(--font-sans) !important; font-size: 18px !important; font-weight: 600 !important; padding: 0 !important; }
[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[data-testid="stMarkdownContainer"] p { margin: 0 0 var(--sp-3) 0; }
[data-testid="stMarkdownContainer"] p:last-child { margin-bottom: 0; }
a { color: var(--link); text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px; cursor: pointer; }
a:hover { color: var(--primary-hover); text-decoration-thickness: 2px; }
hr { border: 0; border-top: 1px solid var(--border); margin: var(--sp-6) 0; }
#MainMenu, footer, [data-testid="stMainMenu"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stSidebarNav"] { display: none !important; }
/* the toolbar itself must stay: Streamlit puts the "open sidebar" button inside it */
[data-testid="stToolbar"] { display: flex !important; visibility: visible !important; }
* { transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }

/* ============ focus: a 2px teal ring on everything interactive, never removed ============ */
a:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, summary:focus-visible,
[role="tab"]:focus-visible, [role="button"]:focus-visible, [role="radio"]:focus-visible, [tabindex]:focus-visible {
  outline: var(--ring) !important; outline-offset: 2px !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="base-input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"]:focus-within > div, [data-testid="stChatInput"]:focus-within {
  outline: var(--ring) !important; outline-offset: 2px !important; border-color: var(--primary) !important; }
input:focus-visible { outline: none !important; }   /* the wrapper above draws the ring */
textarea:focus-visible { outline: var(--ring) !important; outline-offset: 2px !important; }
[data-testid="stChatInput"] textarea:focus-visible { outline: none !important; }          /* the chat box draws one ring, on its frame */
[data-testid="stDataFrame"]:focus-within, [data-testid="stDataFrame"] :focus-visible { outline: var(--ring); outline-offset: 2px; }

/* ============ layout shell ============ */
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1100px; margin: 0 auto; padding: var(--sp-6) var(--sp-8) calc(var(--sp-8) * 4) var(--sp-8); }
[data-testid="stHeader"] { background: transparent; height: 0; min-height: 0; pointer-events: none; }
[data-testid="stHeader"] > * { pointer-events: auto; }
[data-testid="stBottomBlockContainer"] { max-width: 1100px; margin: 0 auto; padding: var(--sp-2) var(--sp-8) var(--sp-6) var(--sp-8); }
[data-testid="stBottom"] > div, [data-testid="stBottom"] { background: var(--bg); }

/* sidebar */
[data-testid="stSidebar"] { background: var(--sidebar); border-right: 1px solid var(--border); }
[data-testid="stSidebarContent"] { padding: var(--sp-4) var(--sp-4) var(--sp-6) var(--sp-4); }
[data-testid="stSidebarHeader"] { padding: var(--sp-2) var(--sp-4) 0 var(--sp-4); min-height: 0; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: var(--sp-2); }
/* the sidebar open/close toggles: a real 44px target, always visible (Streamlit hides the close button until hover) */
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] button { opacity: 1 !important; visibility: visible !important; }
[data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] button,
button[data-testid="stBaseButton-headerNoPadding"] {
  min-width: 44px !important; min-height: 44px !important; width: 44px; height: 44px; border-radius: var(--radius);
  background: var(--surface) !important; border: 1.5px solid var(--input-border) !important; color: var(--text) !important; cursor: pointer; }
[data-testid="stSidebarCollapseButton"] button:hover, [data-testid="stExpandSidebarButton"]:hover, button[data-testid="stBaseButton-headerNoPadding"]:hover {
  background: var(--tint) !important; border-color: var(--primary) !important; }
[data-testid="stExpandSidebarButton"] { position: fixed; top: var(--sp-2); left: var(--sp-2); z-index: 1000; pointer-events: auto; }
.stApp:has([data-testid="stExpandSidebarButton"]) .block-container { padding-top: calc(var(--sp-8) * 2); }
[data-testid="stSidebar"][aria-expanded="false"] { visibility: hidden; }          /* a collapsed sidebar must not stay in the tab order */
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] { visibility: visible !important; opacity: 1 !important; }
[data-testid="stTabs"] button[aria-label^="Scroll tabs"] { min-width: 44px; min-height: 44px; }
.footer { margin-top: var(--sp-6); padding-top: var(--sp-3); border-top: 1px solid var(--border); color: var(--muted); font-size: 14px; }

/* ============ type roles ============ */
.wordmark { display: flex; align-items: center; gap: var(--sp-2); font-family: var(--font-serif); font-size: 24px; font-weight: 600; color: var(--primary); line-height: 1.1; }
.wordmark svg { flex: 0 0 auto; }
.wordmark-sub { color: var(--muted); font-size: 14px; margin-top: var(--sp-1); }
.page-title { margin: 0 0 var(--sp-1) 0; }
.page-sub { color: var(--muted); font-size: 16px; margin: 0 0 var(--sp-6) 0; max-width: 640px; }
.section-title { font-size: 20px; font-weight: 600; margin: var(--sp-6) 0 var(--sp-2) 0; }
.label { font-size: 13px; letter-spacing: 0.06em !important; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: var(--sp-4) 0 var(--sp-1) 0; }
.small, .meta { color: var(--muted); font-size: 14px; line-height: 1.5; }
.meta-error { color: var(--review-text); }
.mt-4 { margin-top: var(--sp-4); } .mt-6 { margin-top: var(--sp-6); } .mt-8 { margin-top: var(--sp-8); }
.station-title { font-size: 24px; margin: 0 0 var(--sp-3) 0; }
[class*="st-key-guide_top"] > [data-testid="stElementContainer"]:first-child, [class*="st-key-srcrow_"] > [data-testid="stElementContainer"]:first-child,
[class*="st-key-fixrow_"] > [data-testid="stElementContainer"]:first-child { flex: 1 1 200px; }
[data-testid="stColumn"]:has(.pane-marker) ul.items { columns: 1; }
.stat-label { font-size: 13px; letter-spacing: 0.06em !important; text-transform: uppercase; color: var(--muted); font-weight: 600; }
.stat-value { font-size: 28px; font-weight: 600; line-height: 1.2; }
.stat-value.stat-sm { font-size: 20px; }

/* ============ buttons: primary (teal), secondary (outlined), danger, ghost ============ */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button, [data-testid^="stBaseButton"] {
  min-height: 40px; padding: var(--sp-2) var(--sp-4); border-radius: var(--radius); font-size: 16px; font-weight: 600; line-height: 1.25;
  white-space: nowrap; width: auto; cursor: pointer; box-shadow: none; }
.stButton > button p, .stFormSubmitButton > button p { font-size: inherit; font-weight: inherit; color: inherit; white-space: nowrap; margin: 0; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {
  background: var(--surface); color: var(--primary); border: 1.5px solid var(--primary); }
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover { background: var(--tint); color: var(--primary-hover); border-color: var(--primary-hover); }
[data-testid="stBaseButton-secondary"]:active, [data-testid="stBaseButton-secondaryFormSubmit"]:active { background: #C8E1E5; transform: translateY(1px); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] { background: var(--primary); color: #fff; border: 1.5px solid var(--primary); }
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover { background: var(--primary-hover); border-color: var(--primary-hover); color: #fff; }
[data-testid="stBaseButton-primary"]:active, [data-testid="stBaseButton-primaryFormSubmit"]:active { background: var(--primary-pressed); border-color: var(--primary-pressed); transform: translateY(1px); }
[data-testid="stBaseButton-tertiary"], [data-testid="stBaseButton-tertiaryFormSubmit"] { background: transparent; color: var(--link); border: 1.5px solid transparent; text-decoration: underline; text-underline-offset: 3px; }
[data-testid="stBaseButton-tertiary"]:hover { background: var(--tint); color: var(--primary-hover); }
[data-testid="stBaseButton-tertiary"]:active { background: #C8E1E5; transform: translateY(1px); }
[class*="st-key-danger_"] button { background: var(--surface) !important; color: var(--review-text) !important; border: 1.5px solid var(--review-text) !important; }
[class*="st-key-danger_"] button:hover { background: var(--review-fill) !important; }
[class*="st-key-danger_"] button:active { background: var(--review-border) !important; transform: translateY(1px); }
.stButton > button:disabled, .stFormSubmitButton > button:disabled, [data-testid^="stBaseButton"]:disabled {
  background: transparent !important; color: var(--disabled-text) !important; border: 1.5px dashed var(--locked-border) !important; cursor: not-allowed; text-decoration: none; transform: none; }
/* a row of buttons: they size to their text and wrap, they never shrink or clip */
[data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] > [data-testid="stButton"]:only-child) { min-width: max-content; }
[data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: var(--sp-2); }
[data-testid="stElementContainer"]:has(> [data-testid="stButton"]), [data-testid="stButton"] { width: auto !important; max-width: 100%; }

/* ============ mode switcher (sidebar nav) ============ */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"], [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
  display: flex; align-items: center; gap: var(--sp-2); min-height: 44px; padding: var(--sp-2) var(--sp-3); border-radius: var(--radius);
  border-left: 4px solid transparent; color: var(--text); text-decoration: none; font-weight: 600; font-size: 16px; cursor: pointer; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: var(--tint); color: var(--primary-hover); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] { background: var(--tint); border-left-color: var(--primary); color: var(--primary-hover); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][disabled], [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-disabled="true"] {
  color: var(--disabled-text); cursor: not-allowed; background: transparent; font-weight: 400; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-disabled="true"]::after, [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][disabled]::after {
  content: "Coming soon"; margin-left: auto; font-size: 13px; font-weight: 600; color: var(--badge-open-text-text); background: var(--badge-open-text-fill);
  border-radius: var(--pill); padding: var(--sp-1) var(--sp-2); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-size: 16px; margin: 0; }

/* ============ icons, chips, badges ============ */
.ic { display: inline-block; width: 16px; height: 16px; flex: 0 0 auto; background: currentColor; vertical-align: -3px;
  -webkit-mask: var(--ic) center / contain no-repeat; mask: var(--ic) center / contain no-repeat; }
.ic-info { --ic: var(--ic-info); } .ic-check-circle { --ic: var(--ic-check-circle); } .ic-alert-triangle { --ic: var(--ic-alert-triangle); }
.ic-warning { --ic: var(--ic-warning); } .ic-x-circle { --ic: var(--ic-x-circle); } .ic-eye-off { --ic: var(--ic-eye-off); }
.ic-check { --ic: var(--ic-check); } .ic-lock { --ic: var(--ic-lock); } .ic-book-open { --ic: var(--ic-book-open); }
.ic-search { --ic: var(--ic-search); } .ic-shield { --ic: var(--ic-shield); } .ic-dot { --ic: var(--ic-dot); }
.chip { display: inline-flex; align-items: center; gap: var(--sp-1); font-size: 14px; font-weight: 600; line-height: 1.25; padding: var(--sp-1) var(--sp-3);
  border: 1px solid; border-radius: var(--pill); white-space: nowrap; vertical-align: baseline; margin: 0 var(--sp-1); }
.chip-review { color: var(--review-text); background: var(--review-fill); border-color: var(--review-border); }
.chip-flag, .chip-doubtful { color: var(--doubtful-text); background: var(--doubtful-fill); border-color: var(--doubtful-border); }
.chip-verified { color: var(--verified-text); background: var(--verified-fill); border-color: var(--verified-border); }
.chip::before { content: ""; width: 16px; height: 16px; flex: 0 0 auto; background: currentColor; -webkit-mask: var(--ic) center / contain no-repeat; mask: var(--ic) center / contain no-repeat; }
.chip-review::before { --ic: var(--ic-eye-off); } .chip-flag::before, .chip-doubtful::before { --ic: var(--ic-warning); } .chip-verified::before { --ic: var(--ic-check); }
.badge { display: inline-flex; align-items: center; gap: var(--sp-1); font-size: 13px; font-weight: 600; letter-spacing: 0.02em; padding: var(--sp-1) var(--sp-2); border-radius: var(--pill); white-space: nowrap; }
.badge-notes { color: var(--badge-notes-text); background: var(--badge-notes-fill); }
.badge-web { color: #6F4300; background: #FCEFD0; }
.badge-open-text { color: var(--badge-open-text-text); background: var(--badge-open-text-fill); }
.badge-open { color: var(--badge-open-text-text); background: var(--badge-open-text-fill); }
.badge-ok { color: var(--verified-text); background: var(--verified-fill); }
.badge-uploaded { color: var(--badge-uploaded-text); background: var(--badge-uploaded-fill); }

/* citation and status chips in an answer (they are buttons) */
/* ============ chat history (sidebar) ============ */
[class*="st-key-chatnew"] button { width: 100%; justify-content: center; }
[class*="st-key-chatrow_"] { gap: var(--sp-1); flex-wrap: nowrap !important; align-items: center; }
[class*="st-key-chatrow_"] > [data-testid="stElementContainer"]:first-child { flex: 1 1 auto; min-width: 0; }
[class*="st-key-chatrow_"] > [data-testid="stElementContainer"]:last-child { flex: 0 0 auto; }
[class*="st-key-chatopen_"] button, [class*="st-key-chatcur_"] button { width: 100%; justify-content: flex-start; text-align: left; min-height: 40px; height: auto; padding-top: var(--sp-2); padding-bottom: var(--sp-2);
  background: transparent; color: var(--text); border: 1px solid transparent; border-left: 3px solid transparent; font-weight: 500; }
[class*="st-key-chatopen_"] button p, [class*="st-key-chatcur_"] button p { white-space: normal; text-align: left; margin: 0; line-height: 1.3; }
[class*="st-key-chatopen_"] button:hover { background: var(--tint); border-color: var(--border); }
[class*="st-key-chatcur_"] button { background: var(--tint); border-left-color: var(--primary); font-weight: 700; }
[class*="st-key-chatmenu_"] button { min-height: 36px; min-width: 36px; padding: 0 var(--sp-2); background: transparent; border: 1px solid transparent; color: var(--muted); }
[class*="st-key-chatmenu_"] button:hover { background: var(--tint); color: var(--text); }
[class*="st-key-chatmenu_"] [data-testid="stIconMaterial"], [class*="st-key-chatmenu_"] button svg { display: none; }
[class*="st-key-chatopen_"] button > div, [class*="st-key-chatcur_"] button > div, [class*="st-key-chatopen_"] button span, [class*="st-key-chatcur_"] button span { width: 100%; justify-content: flex-start; text-align: left; }
[class*="st-key-chatopen_"] button p, [class*="st-key-chatcur_"] button p { width: 100%; }
[data-testid="stDialog"] h2 { padding: 0 var(--sp-6) !important; }
[class*="st-key-chip_"] button, [class*="st-key-chipx_"] button { min-width: 32px; min-height: 32px; padding: 0 var(--sp-2); border-radius: var(--pill); font-size: 14px; font-weight: 700;
  background: var(--tint); color: var(--link); border: 1.5px solid var(--primary); }
[class*="st-key-chip_"] button:hover { background: var(--primary); color: #fff; }
[class*="st-key-chipx_"] button { background: var(--review-fill); color: var(--review-text); border-color: var(--review-text); }
[class*="st-key-sreview_"] button, [class*="st-key-sflag_"] button, [class*="st-key-sverif_"] button { min-height: 32px; padding: var(--sp-1) var(--sp-3); border-radius: var(--pill); font-size: 14px; font-weight: 600; }
[class*="st-key-sreview_"] button { background: var(--review-fill); color: var(--review-text); border: 1px solid var(--review-border); }
[class*="st-key-sflag_"] button { background: var(--doubtful-fill); color: var(--doubtful-text); border: 1px solid var(--doubtful-border); }
[class*="st-key-sverif_"] button { background: var(--verified-fill); color: var(--verified-text); border: 1px solid var(--verified-border); }
[class*="st-key-sreview_"] button:hover, [class*="st-key-sflag_"] button:hover, [class*="st-key-sverif_"] button:hover { filter: brightness(0.96); border-width: 2px; }
[class*="st-key-sreview_"] button::before, [class*="st-key-sflag_"] button::before, [class*="st-key-sverif_"] button::before {
  content: ""; width: 16px; height: 16px; margin-right: var(--sp-1); background: currentColor; flex: 0 0 auto;
  -webkit-mask: var(--ic) center / contain no-repeat; mask: var(--ic) center / contain no-repeat; }
[class*="st-key-sreview_"] button::before { --ic: var(--ic-eye-off); }
[class*="st-key-sflag_"] button::before { --ic: var(--ic-warning); }
[class*="st-key-sverif_"] button::before { --ic: var(--ic-check); }
[class*="st-key-cites_"] { display: none !important; }
a.cite, a.cite:visited { font-size: 13px; font-weight: 700; color: var(--primary); text-decoration: none; padding: 0 var(--sp-1); border-radius: var(--sp-1); cursor: pointer; white-space: nowrap; }
a.cite:hover { background: var(--tint); text-decoration: underline; }
a.cite:focus-visible, a.cite-open:focus-visible { outline: var(--ring); outline-offset: 2px; }
.muted-note { color: var(--muted); font-size: 14px; }
.src-block { margin: var(--sp-4) 0 var(--sp-1) 0; padding-top: var(--sp-3); border-top: 1px solid var(--border); }
.src-title { font-size: 13px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); margin-bottom: var(--sp-1); }
.src-list { margin: 0; padding-left: 1.4em; font-size: 15px; line-height: 1.5; color: var(--text); }
.src-list li { margin: var(--sp-1) 0; }
.src-list a { color: var(--link); text-decoration: underline; text-underline-offset: 2px; }
.src-foot { color: var(--muted); font-size: 14px; margin: var(--sp-1) 0; }
.srcnum { display: inline-block; min-width: 22px; margin-right: var(--sp-2); text-align: center; font-weight: 700; font-size: 13px; color: var(--primary); background: var(--tint); border-radius: var(--pill); padding: 0 var(--sp-2); }
.srcnum-head { font-size: 13px; font-weight: 700; color: var(--primary); margin: var(--sp-2) 0; }
[class*="st-key-ans_"] ul, [class*="st-key-ans_"] ol { margin: var(--sp-1) 0 var(--sp-2) 0; padding-left: var(--sp-6); }
[class*="st-key-ans_"] li { margin: var(--sp-1) 0; }
[class*="st-key-ans_"] { gap: var(--sp-1); }
[class*="st-key-row_"] { gap: var(--sp-2); margin: 0 0 var(--sp-4) 0; align-items: center; flex-wrap: wrap; }
[class*="st-key-ans_"] p { margin: 0 !important; }
.cite-missing { color: var(--review-text); font-size: 14px; font-weight: 600; }

/* example prompts on the landing page */
[class*="st-key-ex_"] button { background: var(--surface); color: var(--text); border: 1.5px solid var(--input-border); border-radius: var(--pill);
  font-weight: 400; padding: var(--sp-2) var(--sp-4); white-space: normal; text-align: left; }
[class*="st-key-ex_"] button p { white-space: normal; }
[class*="st-key-ex_"] button:hover { background: var(--tint); border-color: var(--primary); color: var(--primary-hover); }

/* ============ cards, alerts, states ============ */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-4) var(--sp-6); margin: var(--sp-2) 0 var(--sp-4) 0; }
.card h4 { margin: 0 0 var(--sp-1) 0; font-size: 18px; } .card p { margin: var(--sp-1) 0; }
.card-accent { border-left: 4px solid var(--primary); }
.alert { display: flex; gap: var(--sp-3); align-items: flex-start; border: 1px solid var(--border); border-left-width: 4px; border-radius: var(--radius);
  padding: var(--sp-3) var(--sp-4); margin: var(--sp-2) 0 var(--sp-4) 0; background: var(--surface); }
.alert .ic { width: 20px; height: 20px; margin-top: var(--sp-1); }
.alert-title { font-weight: 600; font-size: 16px; line-height: 1.5; } .alert-text { font-size: 16px; line-height: 1.5; margin: 0; }
.alert-info { border-left-color: var(--primary); background: var(--tint); color: var(--text); } .alert-info .ic { color: var(--primary); }
.alert-success { border-color: var(--verified-border); border-left-color: var(--verified-text); background: var(--verified-fill); } .alert-success .ic { color: var(--verified-text); }
.alert-warning { border-color: var(--doubtful-border); border-left-color: var(--doubtful-text); background: var(--doubtful-fill); } .alert-warning .ic { color: var(--doubtful-text); }
.alert-error { border-color: var(--review-border); border-left-color: var(--review-text); background: var(--review-fill); } .alert-error .ic { color: var(--review-text); }
.empty { text-align: left; padding: var(--sp-6) 0 var(--sp-2) 0; }
.empty h1 { margin: 0 0 var(--sp-2) 0 !important; } .empty p.lead { color: var(--muted); font-size: 18px; max-width: 560px; margin: 0 0 var(--sp-4) 0; }
.empty .ic { width: 48px; height: 48px; color: var(--primary); opacity: 0.85; display: block; margin-bottom: var(--sp-3); }
.landing { padding-top: var(--sp-8); } .landing p.lead { color: var(--muted); font-size: 18px; max-width: 560px; margin: var(--sp-2) 0 var(--sp-4) 0; }
.loading { display: flex; gap: var(--sp-3); align-items: center; padding: var(--sp-3) 0; min-height: 72px; }
.loading .bars { flex: 1 1 auto; display: grid; gap: var(--sp-2); max-width: 520px; }
.loading .bar { height: 12px; border-radius: var(--pill); background: linear-gradient(90deg, var(--progress-track) 25%, var(--tint) 50%, var(--progress-track) 75%); background-size: 200% 100%; animation: shimmer 1.4s linear infinite; }
.loading .bar:nth-child(2) { width: 80%; } .loading .bar:nth-child(3) { width: 55%; }
.loading-text { color: var(--muted); font-size: 14px; min-width: 190px; }
.loading-slow { display: block; visibility: hidden; animation: reveal 0s linear 8s forwards; }
@keyframes shimmer { to { background-position: -200% 0; } } @keyframes reveal { to { visibility: visible; } }
.msg-label { font-size: 13px; letter-spacing: 0.06em !important; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: var(--sp-6) 0 var(--sp-1) 0; }
.msg-user { font-size: 20px; font-weight: 600; line-height: 1.35; margin: 0 0 var(--sp-1) 0; }
.msg-meta { color: var(--muted); font-size: 14px; margin-top: var(--sp-1); }
.turn-rule { border-top: 1px solid var(--border); margin: var(--sp-6) 0 0 0; }
.notice-line { color: var(--muted); font-size: 14px; }
[data-testid="stMarkdownContainer"] ul.items, ul.items { list-style: none; padding: 0 !important; margin: 0 0 var(--sp-2) 0 !important; columns: 2; column-gap: var(--sp-8); }
[data-testid="stMarkdownContainer"] ul.items li, ul.items li { list-style: none; margin: 0 !important; padding: var(--sp-2) 0 !important; border-bottom: 1px solid var(--border); font-size: 16px; break-inside: avoid; }
table.lib { width: 100%; border-collapse: collapse; font-size: 15px; margin: var(--sp-3) 0; }
table.lib th { text-align: left; font-size: 13px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); font-weight: 600; border-bottom: 2px solid var(--text); padding: var(--sp-2) var(--sp-2) var(--sp-2) 0; }
table.lib td { border-bottom: 1px solid var(--border); padding: var(--sp-2) var(--sp-2) var(--sp-2) 0; vertical-align: top; }
table.lib .num { text-align: right; padding-right: var(--sp-6); }
.quote { font-size: 16px; line-height: 1.5; margin: var(--sp-1) 0 var(--sp-2) 0; padding-left: var(--sp-3); border-left: 3px solid var(--border); font-style: italic; }

/* ============ sources pane ============ */
[data-testid="stColumn"]:has(.pane-marker) { position: sticky; top: var(--sp-4); align-self: flex-start; border-left: 1px solid var(--border); padding-left: var(--sp-6); }
[data-testid="stHorizontalBlock"]:has(.pane-marker) { flex-wrap: wrap; gap: var(--sp-6); }
[data-testid="stHorizontalBlock"]:has(.pane-marker) > [data-testid="stColumn"] { flex: 1 1 360px !important; min-width: min(100%, 360px) !important; width: auto !important; }
[data-testid="stHorizontalBlock"]:has(.pane-marker) > [data-testid="stColumn"]:first-child { flex: 3 1 420px !important; min-width: min(100%, 420px) !important; }
.passage { font-size: 16px; line-height: 1.5; border-top: 1px solid var(--border); padding-top: var(--sp-3); margin-top: var(--sp-3); overflow-wrap: anywhere; }
.pl { position: relative; padding: var(--sp-1) 0 var(--sp-1) 0; line-height: 1.5; }
.pl-b { padding-left: var(--sp-4); } .pl-b::before { content: "•"; position: absolute; left: 0; color: var(--muted); }
.pl-1 { margin-left: var(--sp-4); } .pl-2 { margin-left: var(--sp-8); } .pl-3 { margin-left: calc(var(--sp-8) + var(--sp-4)); } .pl-4 { margin-left: calc(var(--sp-8) * 2); }
.passage mark { background: var(--highlight); color: var(--text); padding: var(--sp-1) var(--sp-1); border-left: 3px solid var(--highlight-bar); }
.supports { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-2) var(--sp-3); margin: var(--sp-2) 0; font-size: 14px; color: var(--muted); }
.supports b { color: var(--text); }
.crumb { color: var(--muted); font-size: 14px; margin: 0 0 var(--sp-1) 0; }
.trust { color: var(--muted); font-size: 14px; margin: var(--sp-1) 0 var(--sp-3) 0; }
hr.thin { border: 0; border-top: 1px solid var(--doubtful-border); margin: var(--sp-3) 0 var(--sp-2) 0; }
.cite-path { color: var(--muted); font-size: 14px; margin: 0 0 var(--sp-3) 0; }
.cite-path span { display: block; }
.chat-end { height: calc(var(--sp-8) * 3); }
.pane-title { font-size: 18px; font-weight: 600; margin: var(--sp-2) 0 var(--sp-1) 0; line-height: 1.3; }
.pane-title.sm { font-size: 16px; }
.kv { color: var(--muted); font-size: 14px; margin: var(--sp-1) 0; }
.credit { color: var(--muted); font-size: 14px; border-top: 1px solid var(--border); margin-top: var(--sp-4); padding-top: var(--sp-2); }
.src-row { padding: var(--sp-2) 0; }
.tl { border-left: 2px solid var(--border); margin: var(--sp-3) 0 var(--sp-3) var(--sp-2); padding-left: var(--sp-4); }
.tl-item { position: relative; padding: 0 0 var(--sp-4) 0; }
.tl-item:before { content: ''; position: absolute; left: -22px; top: 8px; width: 10px; height: 10px; border-radius: 50%; background: var(--surface); border: 2px solid var(--primary); }
.tl-label { font-size: 16px; font-weight: 600; } .tl-detail { color: var(--muted); font-size: 14px; line-height: 1.5; } .tl-t { color: var(--muted); font-size: 13px; float: right; }
@media (max-width: 1130px) { [data-testid="stColumn"]:has(.pane-marker) { position: static; border-left: 0; padding-left: 0; } }

/* a source card: the whole card is clickable (a transparent button covers it); hover and keyboard focus are drawn on the card */
[class*="st-key-srccard_"] { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-3) var(--sp-4); margin: 0 0 var(--sp-2) 0; cursor: pointer; }
[class*="st-key-srccard_"]:hover { border-color: var(--primary); background: var(--tint); }
[class*="st-key-srccard_"]:has(button:focus-visible) { outline: var(--ring); outline-offset: 2px; }
[class*="st-key-srccard_"] > [data-testid="stElementContainer"]:has([data-testid="stButton"]) { position: absolute; inset: 0; z-index: 2; margin: 0; width: 100% !important; height: 100%; }
[class*="st-key-srccard_"] [data-testid="stButton"], [class*="st-key-srccard_"] [data-testid="stButton"] button { width: 100% !important; height: 100% !important; opacity: 0; cursor: pointer; }
[class*="st-key-srccard_"] .pane-title { margin-top: var(--sp-2); }
[class*="st-key-mark_"] { gap: var(--sp-2); margin: var(--sp-1) 0 var(--sp-1) 0; }
[class*="st-key-examples"] { align-items: center; gap: var(--sp-2); }
[class*="st-key-examples"] > * { max-width: 100%; }
.empty-center { text-align: center; } .empty-center .ic { margin: 0 auto var(--sp-3) auto; } .empty-center p.lead { margin-left: auto; margin-right: auto; }
/* the send arrow stays visible (greyed) while the box is empty */
[data-testid="stChatInput"] button:disabled, [data-testid="stChatInputSubmitButton"]:disabled { background: var(--progress-track) !important; color: var(--disabled-text) !important; opacity: 1 !important; border: 0 !important; }
#av-count { position: fixed; bottom: var(--sp-1); right: var(--sp-8); font-size: 14px; color: var(--muted); background: var(--bg); padding: 0 var(--sp-2); z-index: 5; display: none; }
#av-count.warn { color: var(--review-text); font-weight: 600; }
/* guide */
.station-title .station-count { color: var(--muted); font-weight: 400; }
.checklist { list-style: none; padding: 0 !important; margin: var(--sp-2) 0 var(--sp-3) 0 !important; }
.checklist li { display: flex; gap: var(--sp-3); align-items: flex-start; padding: var(--sp-2) 0 !important; border-bottom: 1px solid var(--border); margin: 0 !important; }
.checklist li::before { content: ""; flex: 0 0 auto; width: 20px; height: 20px; margin-top: var(--sp-1); border: 2px solid var(--input-border); border-radius: var(--sp-1); background: var(--surface); }
.prompt-card { background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--primary); border-radius: var(--radius); padding: var(--sp-4) var(--sp-6); margin: var(--sp-2) 0 var(--sp-4) 0; }
.prompt-card h3 { margin: 0 0 var(--sp-1) 0 !important; }
[class*="st-key-stlist_"] button { width: 100%; justify-content: flex-start; text-align: left; min-height: 44px; }
[class*="st-key-stlist_"] button p { white-space: normal; text-align: left; }
@media (max-width: 640px) { [class*="st-key-stepper"], .legend { display: none; } }

/* ============ professor dashboard ============ */
[class*="st-key-noop_"] { display: none !important; }
[class*="st-key-rqcard_"], [class*="st-key-fixcard_"], [class*="st-key-report_"] { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: var(--sp-4) var(--sp-6); margin: 0 0 var(--sp-4) 0; animation: fadein 200ms ease-out; }
@keyframes fadein { from { opacity: 0; transform: translateY(var(--sp-1)); } to { opacity: 1; transform: none; } }
.why { font-size: 16px; margin: var(--sp-1) 0; }
.metarow { display: flex; flex-wrap: wrap; gap: var(--sp-2); align-items: center; margin: var(--sp-3) 0 var(--sp-2) 0; }
.metarow .chip { margin: 0; }
.beforeafter { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-6); margin: var(--sp-2) 0; }
.pager-text { font-weight: 600; white-space: nowrap; padding: 0 var(--sp-2); }
[class*="st-key-pager_"] { margin: var(--sp-2) 0 var(--sp-4) 0; }
[class*="st-key-pager_"] [data-testid="stSelectbox"] { flex: 0 0 140px; width: 140px; min-width: 140px; }
@media (max-width: 640px) { .beforeafter { grid-template-columns: 1fr; } [class*="st-key-rqcard_"], [class*="st-key-fixcard_"], [class*="st-key-report_"] { padding: var(--sp-3) var(--sp-4); } }

/* ============ preview mode: unmistakable, with an exit that is always in view ============ */
[class*="st-key-preview_bar"] { position: sticky; top: 0; z-index: 90; background: var(--primary-pressed); color: #fff; border-radius: var(--radius);
  padding: var(--sp-3) var(--sp-4); margin: 0 0 var(--sp-4) 0; display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-3); }
[class*="st-key-preview_bar"] p, [class*="st-key-preview_bar"] .preview-text { color: #fff; margin: 0; font-size: 16px; flex: 1 1 280px; }
[class*="st-key-preview_bar"] a[data-testid="stPageLink-NavLink"] { background: #fff; color: var(--primary-pressed); border-radius: var(--radius); border-left: 0; font-weight: 600; width: auto; }
[class*="st-key-preview_bar"] a[data-testid="stPageLink-NavLink"] p { color: var(--primary-pressed); }

/* ============ tablet and phone: the Sources pane becomes a bottom sheet when a passage is chosen ============ */
[class*="st-key-sheet_bar"] { display: none; }
@media (max-width: 1130px) {
  [data-testid="stColumn"]:has(.sheet-open) { position: fixed !important; left: 0; right: 0; bottom: 0; top: auto; max-height: 78vh; overflow-y: auto; z-index: 120;
    background: var(--surface); border-top: 2px solid var(--primary); border-radius: var(--radius) var(--radius) 0 0; box-shadow: 0 calc(var(--sp-1) * -1) var(--sp-6) rgba(31, 37, 40, 0.18);
    padding: var(--sp-4) var(--sp-4) var(--sp-8) var(--sp-4) !important; width: 100% !important; min-width: 0 !important; flex: none !important; }
  @media (min-width: 768px) { .stApp:has([data-testid="stSidebar"][aria-expanded="true"]) [data-testid="stColumn"]:has(.sheet-open) { left: 300px; width: auto !important; } }
  [data-testid="stColumn"]:has(.sheet-open) [class*="st-key-sheet_bar"] { display: block; position: sticky; top: 0; background: var(--surface); padding-bottom: var(--sp-2); z-index: 2; }
}

/* ============ inputs, tabs, expanders, selects ============ */
input, textarea { color: var(--text) !important; font-size: 16px !important; background: transparent !important; }
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stTextAreaRootElement"], [data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div, [data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="textarea"] {
  border: 1.5px solid var(--input-border) !important; border-radius: var(--radius) !important; background: var(--surface) !important; color: var(--text) !important; font-size: 16px !important; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within, [data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stMultiSelect"] > div > div:focus-within { outline: var(--ring) !important; outline-offset: 2px !important; border-color: var(--primary) !important; }
[data-baseweb="base-input"] { border: 0 !important; background: transparent !important; }
[data-baseweb="input"], [data-baseweb="input"] > div, [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="select"] input { background: var(--surface) !important; }
[data-testid="InputInstructions"] { display: none; }
[data-testid="stNumberInput"] { max-width: 200px; }
[data-testid="stCheckbox"] label p, [data-testid="stCheckbox"] label span { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
[data-testid="stTextInput"] button, [data-testid="stNumberInput"] button { background: var(--surface) !important; color: var(--text) !important; border: 0 !important; min-width: 40px; min-height: 40px; }
[data-testid="stWidgetLabel"] p, label p { font-size: 16px; font-weight: 600; color: var(--text); }
[data-testid="stChatInput"] { background: var(--surface) !important; border: 1.5px solid var(--input-border); border-radius: var(--radius); }
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] [data-baseweb] { background: var(--surface) !important; border-radius: var(--radius); }
[data-testid="stChatInput"] textarea { font-family: var(--font-sans); font-size: 16px; background: var(--surface) !important; }
[data-testid="stChatInput"] button { background: var(--primary) !important; color: #fff !important; border-radius: var(--radius); min-width: 40px; min-height: 40px; }
[data-testid="stChatInput"] button:hover { background: var(--primary-hover) !important; }
@media (min-width: 1131px) { [data-testid="stChatInput"] { max-width: 60%; } }
[data-testid="stTabs"] [role="tab"] { font-size: 16px; font-weight: 600; color: var(--muted); padding: var(--sp-3) var(--sp-4); min-height: 44px; cursor: pointer; }
[data-testid="stTabs"] [role="tab"]:hover { color: var(--primary-hover); background: var(--tint); }
[data-testid="stTabs"] [aria-selected="true"] { color: var(--primary); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: var(--primary); height: 3px; }
[data-testid="stTabs"] [data-baseweb="tab-border"] { background: var(--border); }
[data-testid="stExpander"] { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
[data-testid="stExpander"] summary { min-height: 44px; cursor: pointer; font-weight: 600; }
[data-testid="stExpander"] summary:hover { background: var(--tint); }
[data-testid="stAlert"] { border-radius: var(--radius); }
[data-testid="stProgressBarTrack"] { background: var(--progress-track) !important; border: 1px solid var(--input-border); border-radius: var(--pill); box-sizing: content-box; }
[data-testid="stProgressBarTrack"] > div { background: var(--primary) !important; border-radius: var(--pill); }
[data-testid="stFileUploader"] section { background: var(--surface) !important; border: 1.5px dashed var(--input-border); border-radius: var(--radius); }

/* segmented control (the Sources / How this answer was built switcher): sized to its text, wraps instead of clipping */
[data-testid="stButtonGroup"] { flex-wrap: wrap; gap: var(--sp-2); }
[data-testid="stSegmentedControl"] button, [data-testid="stSegmentedControl"] [role="button"], [data-testid="stSegmentedControl"] [role="radio"] {
  flex: 0 0 auto; width: auto; min-height: 40px; white-space: nowrap; padding: var(--sp-2) var(--sp-4); border-radius: var(--radius) !important;
  background: var(--surface) !important; color: var(--primary) !important; border: 1.5px solid var(--input-border) !important; font-size: 16px; font-weight: 600; cursor: pointer; }
[data-testid="stSegmentedControl"] button:hover { background: var(--tint) !important; border-color: var(--primary) !important; }
[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"], [data-testid="stSegmentedControl"] button[aria-checked="true"], [data-testid="stSegmentedControl"] button[aria-pressed="true"] {
  background: var(--tint) !important; color: var(--primary-hover) !important; border-color: var(--primary) !important; box-shadow: inset 0 -3px 0 var(--primary); }
[data-testid="stSegmentedControl"] button p { color: inherit !important; white-space: nowrap; font-size: 16px; }

/* guide stepper: icon + number, never colour alone */
[class*="st-key-stepper"] { gap: var(--sp-2); flex-wrap: wrap; }
[class*="st-key-step_"] button { min-width: 48px; min-height: 44px; padding: 0 var(--sp-2); border-radius: var(--radius); font-size: 16px; font-weight: 600; }
[class*="st-key-step_"] button::before, [class*="st-key-stlist_"] button::before { content: ""; width: 16px; height: 16px; margin-right: var(--sp-1); background: currentColor; flex: 0 0 auto;
  -webkit-mask: var(--ic) center / contain no-repeat; mask: var(--ic) center / contain no-repeat; }
[class*="st-key-step_done_"] button { background: var(--primary); color: #fff; border: 1.5px solid var(--primary); } [class*="st-key-step_done_"] button::before { --ic: var(--ic-check); }
[class*="st-key-step_done_"] button:hover { background: var(--primary-hover); color: #fff; }
[class*="st-key-step_current_"] button, [class*="st-key-stlist_current_"] button { background: var(--primary); color: #fff; border: 1.5px solid var(--primary); } [class*="st-key-step_current_"] button::before, [class*="st-key-stlist_current_"] button::before { --ic: var(--ic-dot); }
[class*="st-key-step_locked_"] button, [class*="st-key-stlist_locked_"] button { background: transparent; color: var(--disabled-text); border: 1.5px dashed var(--locked-border); }
[class*="st-key-stlist_done_"] button { background: var(--surface); color: var(--primary); border: 1.5px solid var(--primary); } [class*="st-key-stlist_done_"] button::before { --ic: var(--ic-check); }
[class*="st-key-stlist_open_"] button { background: var(--surface); color: var(--primary); border: 1.5px solid var(--primary); }
[class*="st-key-step_open_"] button { background: var(--surface); color: var(--primary); border: 1.5px solid var(--primary); } [class*="st-key-step_open_"] button::before { display: none; }
[class*="st-key-step_locked_"] button::before, [class*="st-key-stlist_locked_"] button::before { --ic: var(--ic-lock); }
.legend { color: var(--muted); font-size: 14px; margin: var(--sp-1) 0 var(--sp-2) 0; }

/* ============ login ============ */
[class*="st-key-login_card"] { max-width: 420px; margin: 8vh auto 0 auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-8); }
[class*="st-key-login_msg"] { min-height: 112px; }
[class*="st-key-login_card"] [data-testid="stVerticalBlock"] { gap: var(--sp-3); }
@media (max-width: 640px) { [class*="st-key-login_msg"] { min-height: 144px; }
  .block-container, [data-testid="stMainBlockContainer"] { padding-left: var(--sp-4); padding-right: var(--sp-4); }
  [class*="st-key-login_card"] { padding: var(--sp-6) var(--sp-4); margin-top: var(--sp-4); } [data-testid="stMarkdownContainer"] ul.items, ul.items { columns: 1 !important; }
  [data-testid="stBottomBlockContainer"] { padding-left: var(--sp-4); padding-right: var(--sp-4); } .landing { padding-top: var(--sp-4); } h1 { font-size: 28px; } }
@media (max-width: 960px) { [data-testid^="stBaseButton"], .stButton > button { min-height: 44px; } }
@media (max-width: 960px) {
  [class*="st-key-chip_"] button, [class*="st-key-chipx_"] button { min-height: 44px; min-width: 44px; }
  [class*="st-key-sreview_"] button, [class*="st-key-sflag_"] button, [class*="st-key-sverif_"] button { min-height: 44px; }
  [data-testid="stSegmentedControl"] button { min-height: 44px; }
  [class*="st-key-step_"] button { min-height: 44px; min-width: 44px; }
  [data-testid="stCheckbox"] label, [data-testid="stSelectbox"] [data-baseweb="select"] { min-height: 44px; }
  [data-testid="stExpander"] summary { min-height: 44px; }
  .stFormSubmitButton > button, .stButton > button, [data-testid="stChatInput"] button, [data-testid="stChatInputSubmitButton"] { min-height: 44px; min-width: 44px; }
  [data-testid="stButtonGroup"] button { min-height: 44px; }
"""

# Names Streamlit's own icon-only controls (it gives them no accessible name), focuses the field after a login error, and
# opens the sidebar once after sign-in on wide screens. Only touches attributes and focus; no data leaves the page.
A11Y_JS = r"""
(function () {
  if (window.__avA11y) return; window.__avA11y = true;
  const name = (el, label) => { if (el && el.getAttribute('aria-label') !== label) el.setAttribute('aria-label', label); };
  const pass = () => {
    document.querySelectorAll('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarCollapseButton"][role="button"]').forEach(b => name(b, 'Close sidebar'));
    document.querySelectorAll('[data-testid="stExpandSidebarButton"]').forEach(b => name(b, 'Open sidebar'));
    document.querySelectorAll('[data-testid="stChatInputSubmitButton"]').forEach(b => name(b, 'Send question'));
    document.querySelectorAll('[data-testid="stChatInputTextArea"]').forEach(t => name(t, t.getAttribute('placeholder') || 'Ask a question'));
    document.querySelectorAll('[data-testid="stTextInput"]').forEach(w => {
      const input = w.querySelector('input'); const btn = w.querySelector('button');
      if (btn && input) name(btn, input.type === 'password' ? 'Show password' : 'Hide password');
    });
    document.querySelectorAll('[data-testid="stNumberInput"] button').forEach(b => {
      const t = b.getAttribute('data-testid') || ''; name(b, /up|incr|plus/i.test(t) || b.matches('button:last-of-type') ? 'Increase' : 'Decrease'); });
    document.querySelectorAll('a[data-testid="stPageLink-NavLink"]').forEach(a => {
      if (a.hasAttribute('disabled')) { a.setAttribute('aria-disabled', 'true'); a.removeAttribute('aria-current'); a.setAttribute('tabindex', '-1'); return; }
      const norm = p => p.replace(/\/+$/, '') || '/';
      const href = a.getAttribute('href'); const same = norm(href ? new URL(href, location.href).pathname : '/') === norm(location.pathname);
      if (same) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    const err = document.querySelector('.alert-error[data-focus], .alert-warning[data-focus]');
    if (err && err.dataset.done !== '1') { err.dataset.done = '1';
      const f = document.querySelector('input[aria-label="' + err.dataset.focus + '"]'); if (f) f.focus(); }
  };
  // Never leave someone on a collapsed sidebar on a wide screen: open it after sign-in, and when the window is widened.
  const WIDE = 768; let wasWide = window.innerWidth >= WIDE; let sawLogin = false;
  const expand = () => { const b = document.querySelector('[data-testid="stExpandSidebarButton"]'); if (b && window.innerWidth >= WIDE) b.click(); };
  window.addEventListener('resize', () => { const wide = window.innerWidth >= WIDE; if (wide && !wasWide) setTimeout(expand, 150); wasWide = wide; });
  // on a phone the sidebar is an overlay: close it once a mode or a chat has been chosen, so the page is not left covered
  document.addEventListener('click', e => {
    if (window.innerWidth >= WIDE || !e.target.closest('a[data-testid="stPageLink-NavLink"], [class*="st-key-chatopen_"] button, [class*="st-key-chatcur_"] button, [class*="st-key-chatnew"] button')) return;
    setTimeout(() => { const c = document.querySelector('[data-testid="stSidebarCollapseButton"] button'); if (c) c.click(); }, 250);
  });
  // a source marker [n] in an answer, or a notes/guide line of the Sources list: press that source's hidden button, which opens it in the side panel
  const openCite = el => { const b = document.querySelector('.st-key-chip_' + el.getAttribute('data-cite') + ' button'); if (b) b.click(); };
  document.addEventListener('click', e => { const el = e.target.closest('[data-cite]'); if (!el) return; e.preventDefault(); openCite(el); });
  document.addEventListener('keydown', e => { if (e.key !== 'Enter' && e.key !== ' ') return; const el = e.target.closest && e.target.closest('[data-cite]');
    if (el) { e.preventDefault(); openCite(el); } });
  // opening a "Report an error" form: bring it fully into view
  document.addEventListener('click', e => {
    const sum = e.target.closest('[class*="st-key-rp_"] summary'); if (!sum) return;
    setTimeout(() => { const box = sum.closest('[class*="st-key-rp_"]'); if (box) box.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 250);
  });
  // after sending: bring the new question (and the start of its answer) into view once the answer has arrived
  let askCount = document.querySelectorAll('.msg-user').length, scrollDue = false, timer = null;
  const settleScroll = () => {
    const users = document.querySelectorAll('.msg-user'); const n = users.length;
    if (n > askCount) scrollDue = true; askCount = n;
    if (scrollDue && !document.querySelector('.loading')) {
      clearTimeout(timer); timer = setTimeout(() => { if (document.querySelector('.loading')) return;
        scrollDue = false; const last = [...document.querySelectorAll('.msg-user')].pop();
        if (last) last.scrollIntoView({ block: 'start', behavior: 'smooth' }); }, 350);
    }
  };
  // a character counter next to the 600 limit (shown from 480 characters)
  const counter = () => {
    const ta = document.querySelector('[data-testid="stChatInputTextArea"]'); let c = document.getElementById('av-count');
    if (!ta) { if (c) c.style.display = 'none'; return; }
    if (!c) { c = document.createElement('div'); c.id = 'av-count'; c.setAttribute('aria-live', 'polite'); document.body.appendChild(c); }
    if (!ta.dataset.avCount) { ta.dataset.avCount = '1'; ta.addEventListener('input', () => { const n = ta.value.length;
      c.textContent = n + ' / 600 characters'; c.className = n >= 580 ? 'warn' : ''; c.style.display = n >= 480 ? 'block' : 'none'; }); }
  };
  const watch = () => {
    settleScroll(); counter();
    if (document.querySelector('[class*="st-key-login_card"]')) sawLogin = true;
    else if (sawLogin && document.querySelector('[data-testid="stSidebar"]')) { sawLogin = false; setTimeout(expand, 250); }
    pass();
  };
  new MutationObserver(watch).observe(document.body, { childList: true, subtree: true });
  watch();
})();
"""


GUIDE_CSS = """
/* ============ Guide conversation ============ */
.ghead { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--sp-1) var(--sp-3); margin: 0 0 var(--sp-1) 0; }
.ghead .gname { font-size: 20px; font-weight: 600; line-height: 1.25; }
.ghead .gpos { color: var(--muted); font-size: 14px; }
.gmsg-u { font-size: 17px !important; font-weight: 500 !important; margin: var(--sp-4) 0 var(--sp-1) 0 !important; padding: var(--sp-2) var(--sp-3);
  background: var(--tint); border-radius: var(--radius); max-width: 90%; margin-left: auto !important; overflow-wrap: anywhere; }
.gmsg-a { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-3) var(--sp-4);
  margin: var(--sp-2) 0 var(--sp-1) 0; max-width: 100%; overflow-wrap: anywhere; }
[class*="st-key-gma_"] { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-3) var(--sp-4); margin: var(--sp-2) 0 var(--sp-1) 0; }
[class*="st-key-gma_"] p { margin: 0 0 var(--sp-2) 0; } [class*="st-key-gma_"] p:last-child, [class*="st-key-gma_"] ul:last-child { margin-bottom: 0; }
[class*="st-key-gma_"] ul { margin: 0 0 var(--sp-2) var(--sp-4); padding: 0; }
.gmsg-a p { margin: 0 0 var(--sp-2) 0; } .gmsg-a p:last-child, .gmsg-a ul:last-child { margin-bottom: 0; }
.gmsg-a ul { margin: 0 0 var(--sp-2) var(--sp-4); padding: 0; }
.gmsg-note { color: var(--muted); font-size: 14px; margin-top: var(--sp-1); }
.gsrcs { display: flex; flex-wrap: wrap; gap: var(--sp-1) var(--sp-2); margin: 0 0 var(--sp-3) 0; }
.gsrcs details { font-size: 14px; max-width: 100%; }
.gsrcs summary { cursor: pointer; color: var(--link); font-weight: 600; padding: var(--sp-1) var(--sp-2); border: 1px solid var(--border); border-radius: var(--pill);
  background: var(--surface); list-style: none; min-height: 28px; display: inline-flex; align-items: center; }
.gsrcs summary::-webkit-details-marker { display: none; }
.gsrcs summary:focus-visible { outline: var(--ring); outline-offset: 2px; }
.gsrcs details[open] { flex: 1 1 100%; }
.gsrcs details[open] summary { background: var(--tint); }
.gsrcs .gpass { margin: var(--sp-1) 0 0 0; padding: var(--sp-2) var(--sp-3); border-left: 3px solid var(--primary); background: var(--bg); white-space: pre-wrap; overflow-wrap: anywhere; }
.gsrcs .gpass-cite { color: var(--muted); font-size: 13px; display: block; margin-top: var(--sp-1); }
.gwelcome { background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--primary); border-radius: var(--radius); padding: var(--sp-3) var(--sp-4); margin: var(--sp-2) 0; }
.gwelcome p { margin: 0 0 var(--sp-1) 0; } .gwelcome .small { margin: 0; }
.goutline { list-style: none; margin: 0; padding: 0; }
.goutline li { display: flex; gap: var(--sp-2); padding: var(--sp-1) 0; border-bottom: 1px solid var(--border); font-size: 15px; align-items: baseline; }
.goutline .gmark { flex: 0 0 auto; min-width: 5.5em; font-weight: 600; color: var(--muted); font-size: 13px; }
.goutline li.cur { font-weight: 600; } .goutline li.cur .gmark { color: var(--primary); }
.goutline li.miss .gmark { color: var(--review-text); }
.gerr { margin: var(--sp-2) 0; }
.gquick { margin: var(--sp-2) 0 var(--sp-1) 0; }
[class*="st-key-gquick"] button { min-height: 40px; }
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-ghead_wrap"]) { position: sticky; top: 0; z-index: 20; background: var(--bg); }   /* the wrapper, not the container, must stick */
[class*="st-key-ghead_wrap"] { padding: var(--sp-1) 0 var(--sp-2) 0; border-bottom: 1px solid var(--border); }
[class*="st-key-ghead_row"] { align-items: center; }
[class*="st-key-ghead_row"] > [data-testid="stElementContainer"]:first-child { flex: 1 1 240px; }
@media (max-width: 640px) {
  .ghead { padding-left: 52px; }                                  /* clear of the sidebar toggle */
  .ghead .gname { font-size: 18px; }
  .gmsg-u { max-width: 100%; }
  [data-testid="stColumn"]:has(.gside) { display: none; }           /* the source markers carry the passage on a phone */
  [class*="st-key-gquick"] { gap: var(--sp-2); }
  [class*="st-key-gquick"] button { padding: var(--sp-1) var(--sp-3); }
}
"""


QUIZ_CSS = """
/* ============ Quiz ============ */
.qz-stem { font-size: 17px; line-height: 1.5; margin: var(--sp-3) 0 var(--sp-2) 0; padding: var(--sp-3) var(--sp-4); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow-wrap: anywhere; }
.qz-lead { font-size: 18px; font-weight: 600; margin: var(--sp-2) 0; overflow-wrap: anywhere; }
[data-testid="stRadio"] label p { font-size: 17px; line-height: 1.4; overflow-wrap: anywhere; }
[data-testid="stRadio"] [role="radiogroup"] label { padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); margin-bottom: var(--sp-2); min-height: 44px; }
.qz-row { padding: var(--sp-2) 0 var(--sp-1) 0; border-top: 1px solid var(--border); overflow-wrap: anywhere; } .qz-a { color: var(--muted); }
.qz-res-h { margin: var(--sp-6) 0 var(--sp-1) 0; font-size: 15px; border-top: 1px solid var(--border); padding-top: var(--sp-3); }
.qz-ok { color: #1F5E3A; font-weight: 700; } .qz-no { color: #8A1F2D; font-weight: 700; }
.qz-opts { list-style: none; margin: var(--sp-1) 0 var(--sp-3) 0; padding: 0; } .qz-opts li { padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: var(--sp-1); overflow-wrap: anywhere; }
.qz-opts li.qz-opt-right { border-left: 4px solid #1F5E3A; background: #F3FAF5; } .qz-tag { font-size: 13px; font-weight: 700; color: var(--primary); margin-left: var(--sp-2); }
.qz-why { margin: 0 0 var(--sp-2) var(--sp-4); padding: 0; } .qz-src { margin: 0 0 var(--sp-3) 0; } .qz-pass { margin: var(--sp-1) 0; padding: var(--sp-2) var(--sp-3); border-left: 3px solid var(--primary); background: var(--bg); white-space: pre-wrap; overflow-wrap: anywhere; }
mark.qz-span { background: var(--highlight); border-bottom: 2px solid var(--highlight-bar); color: inherit; }
.qz-item { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sp-3) var(--sp-4); margin: var(--sp-2) 0; background: var(--surface); }
@media (max-width: 640px) { .qz-stem { font-size: 16px; } .qz-lead { font-size: 17px; } }
"""


def set_title(page_title):
    """The browser tab title: "<page> · AnatoVision". (Streamlit does not do this for pages added with position="hidden".)"""
    st.html(f"<script>document.title = {json.dumps(page_title + ' · AnatoVision')};</script>", unsafe_allow_javascript=True)


def inject():
    # CSS ends inside an @media block that was never closed (browsers close it silently); close it so later blocks are not swallowed
    st.html(f"<style>{root_css()}{CSS}\n}}\n{GUIDE_CSS}{QUIZ_CSS}</style>")
    st.html(f"<script>{A11Y_JS}</script>", unsafe_allow_javascript=True)


# ----------------------------------------------------------------------------
# small components (every view uses these, none writes colours or sizes)
# ----------------------------------------------------------------------------

def esc(text):
    return html.escape(str(text))


def icon(name, extra=""):
    return f'<span class="ic ic-{name} {extra}" aria-hidden="true"></span>'


def dollars(x):
    return f"${x:,.4f}" if x < 0.1 else f"${x:,.2f}"


def alert_html(kind, title, text="", focus=None):
    """info | success | warning | error: icon + title + one line. warning/error are announced at once (role=alert)."""
    ic, _, role = ALERTS[kind]
    body = f'<p class="alert-text">{esc(text)}</p>' if text else ""
    attr = f' data-focus="{esc(focus)}"' if focus else ""
    return (f'<div class="alert alert-{kind}" role="{role}"{attr}>{icon(ic)}'
            f'<div><div class="alert-title">{esc(title)}</div>{body}</div></div>')


def alert(kind, title, text="", focus=None):
    st.markdown(alert_html(kind, title, text, focus), unsafe_allow_html=True)


def notice(text, problem=False):
    """Kept for older call sites: an error alert (problem) or an info alert."""
    alert("error" if problem else "info", "Please check this" if problem else "Note", text)


def chip_html(kind, text):
    """A status chip: the icon comes from the stylesheet (.chip-* ::before), the text is always there. kind = review | doubtful | verified."""
    return f'<span class="chip chip-{"flag" if kind == "doubtful" else kind}">{esc(text)}</span>'


def badge_html(kind, text=None):
    fill = {"notes": "badge-notes", "dissection_guide": "badge-notes", "open_text": "badge-open-text", "web": "badge-web",
            "verified": "badge-ok", "uploaded": "badge-uploaded"}[kind]
    label = text or BADGES[kind][2]
    return f'<span class="badge {fill}">{icon("check") if kind == "verified" else ""}{esc(label)}</span>'


def card_html(title, text, kind="info"):
    """A calm content card (the 'not covered' style)."""
    return f'<div class="card card-accent"><h4>{esc(title)}</h4><p>{esc(text)}</p></div>'


def page_title(title, sub=""):
    st.markdown(f'<h1 class="page-title">{esc(title)}</h1>' + (f'<p class="page-sub">{esc(sub)}</p>' if sub else ""), unsafe_allow_html=True)


def section(text):
    st.markdown(f'<div class="section-title">{esc(text)}</div>', unsafe_allow_html=True)


def label(text):
    st.markdown(f'<div class="label">{esc(text)}</div>', unsafe_allow_html=True)


def meta(text, tone=""):
    st.markdown(f'<div class="meta {"meta-error" if tone == "error" else ""}">{esc(text)}</div>', unsafe_allow_html=True)


def stat(label_text, value, small=False):
    return (f'<div class="stat-label">{esc(label_text)}</div><div class="stat-value{" stat-sm" if small else ""}">{esc(value)}</div>')


def empty_state_html(icon_name, title, text):
    return f'<div class="empty">{icon(icon_name)}<h1>{esc(title)}</h1><p class="lead">{esc(text)}</p></div>'


def loading_html(text="Searching the notes…", slow="This is taking longer than usual. Still working."):
    """A skeleton row. The 'taking longer' line is always laid out (hidden), then shown after 8 s, so nothing shifts."""
    return (f'<div class="loading" role="status" aria-live="polite"><div class="bars"><div class="bar"></div><div class="bar"></div>'
            f'<div class="bar"></div></div><div class="loading-text">{esc(text)}<span class="loading-slow">{esc(slow)}</span></div></div>')


def wordmark(sub=True):
    st.markdown(f'<div class="wordmark">{logo_svg(32)}<span>AnatoVision</span></div>'
                + ('<div class="wordmark-sub">Anatomy lab assistant · Dr. Inglis</div>' if sub else ""), unsafe_allow_html=True)


def button_row(key):
    """Buttons placed in this container size to their text and wrap onto the next line instead of shrinking or clipping."""
    return st.container(horizontal=True, gap="small", key=key)


def cost_chart(cost_by_day_kind):
    """Cost per day, stacked by type (student chat, student Guide, professor preview, fact-check), with axis titles, dollar units
    and a tooltip. Fonts are 14px (nothing under 13px). The same numbers are always shown as a table under it."""
    import altair as alt
    import pandas as pd
    rows = [{"Day (UTC)": d, "Type": k, "Cost (US dollars)": v} for d, kinds in cost_by_day_kind.items() for k, v in kinds.items()]
    df = pd.DataFrame(rows)
    order = ["Student chat", "Student Guide", "Professor preview", "Fact-check"]
    colours = [TOKENS["primary"], TOKENS["highlight-bar"], TOKENS["input-border"], STATUS["review"][0]]
    chart = (alt.Chart(df).mark_bar()
             .encode(x=alt.X("Day (UTC):N", axis=alt.Axis(labelAngle=0, title="Day (UTC)")),
                     y=alt.Y("Cost (US dollars):Q", axis=alt.Axis(format="$.2f", title="Cost (US dollars)")),
                     color=alt.Color("Type:N", scale=alt.Scale(domain=order, range=colours), legend=alt.Legend(orient="bottom", title=None)),
                     tooltip=["Day (UTC)", "Type", alt.Tooltip("Cost (US dollars):Q", format="$.4f")])
             .properties(height=240)
             .configure_axis(labelFontSize=14, titleFontSize=14, labelColor=TOKENS["text"], titleColor=TOKENS["muted"],
                             gridColor=TOKENS["progress-track"], domainColor=TOKENS["input-border"])
             .configure_legend(labelFontSize=14, labelColor=TOKENS["text"])
             .configure_view(strokeWidth=0))
    st.altair_chart(chart, use_container_width=True)

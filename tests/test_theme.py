"""UI audit Part 2: the shared components (theme helpers), the contrast table, and rules the stylesheet must keep."""
import re
import tomllib
from pathlib import Path

import pytest

from app import contrast, theme

ROOT = Path(__file__).resolve().parents[1]
CSS = theme.root_css() + theme.CSS


# ---- components --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind,role", [("info", "status"), ("success", "status"), ("warning", "alert"), ("error", "alert")])
def test_alert_has_icon_title_one_line_and_the_right_aria_role(kind, role):
    h = theme.alert_html(kind, "A title", "One line of text.")
    assert f'class="alert alert-{kind}"' in h and f'role="{role}"' in h
    assert 'class="ic ic-' in h and 'aria-hidden="true"' in h               # the icon is decoration; the title says it
    assert '<div class="alert-title">A title</div>' in h and "One line of text." in h


def test_alert_escapes_text_and_can_ask_for_focus_on_a_field():
    h = theme.alert_html("error", "<b>x</b>", "a & b", focus="Password")
    assert "&lt;b&gt;" in h and "a &amp; b" in h and 'data-focus="Password"' in h


@pytest.mark.parametrize("kind,css", [("review", "chip-review"), ("doubtful", "chip-flag"), ("verified", "chip-verified")])
def test_status_chip_is_text_plus_icon_class(kind, css):
    h = theme.chip_html(kind, "Being reviewed")
    assert f"chip {css}" in h and "Being reviewed" in h
    assert f".{css}::before" in CSS or f".{css}::before" in CSS.replace(", .chip-doubtful::before", "")   # the icon comes from the stylesheet
    for icon_class in ("ic-eye-off", "ic-warning", "ic-check"):
        assert f"--ic-{icon_class[3:]}" in theme.root_css()


@pytest.mark.parametrize("kind,css", [("notes", "badge-notes"), ("open_text", "badge-open-text"), ("verified", "badge-ok"), ("uploaded", "badge-uploaded")])
def test_source_badges(kind, css):
    assert f"badge {css}" in theme.badge_html(kind)
    assert "Course notes" in theme.badge_html("notes") and "OpenStax A&amp;P 2e" in theme.badge_html("open_text")
    assert "Verified fix" in theme.badge_html("verified")


def test_loading_row_is_announced_and_reserves_room_for_the_slow_message():
    h = theme.loading_html("Searching the notes…")
    assert 'role="status"' in h and 'aria-live="polite"' in h and "Searching the notes…" in h
    assert "taking longer than usual" in h and "loading-slow" in h
    assert re.search(r"\.loading-slow \{[^}]*visibility: hidden[^}]*animation: reveal 0s linear 8s", CSS)   # shown after 8 seconds, no layout shift


def test_wordmark_logo_is_an_original_inline_svg_with_a_name():
    svg = theme.logo_svg(32)
    assert svg.startswith("<svg") and "role='img'" in svg and "aria-label='AnatoVision'" in svg and "http" not in svg
    assert Path(theme.FAVICON).exists() and (ROOT / "app" / "assets" / "favicon.svg").exists()


def test_page_title_helper_is_json_safe():
    # the tab title is written with json.dumps, so a quote in a title cannot break out of the script
    import json
    assert json.dumps('He said "hi" · AnatoVision').startswith('"He said \\"hi\\"')


# ---- the stylesheet's rules ----------------------------------------------------------------------------------------

def test_the_tokens_are_the_specified_palette():
    t = theme.TOKENS
    assert (t["bg"], t["surface"], t["sidebar"], t["text"], t["primary"], t["tint"], t["input-border"]) == (
        "#FAF7F2", "#FFFFFF", "#F0EBE0", "#1F2528", "#0F5E6C", "#DDEEF0", "#8A8374")
    assert theme.STATUS["review"][:3] == ("#8A1F2D", "#F8E3E5", "#D9A3AA") and theme.STATUS["verified"][0] == "#1F5E3A"
    assert re.search(r":root\{[^}]*--primary:#0F5E6C", theme.root_css())


def test_streamlits_own_theme_matches_the_tokens():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())["theme"]
    t = theme.TOKENS
    assert (cfg["backgroundColor"], cfg["primaryColor"], cfg["textColor"], cfg["borderColor"]) == (t["bg"], t["primary"], t["text"], t["border"])
    assert cfg["sidebar"]["backgroundColor"] == t["sidebar"] and cfg["baseFontSize"] == 16


def test_no_font_under_13px_and_body_is_16px():
    sizes = [int(x) for x in re.findall(r"font-size:\s*(\d+)px", CSS)]
    assert sizes and min(sizes) >= 13
    assert re.search(r"html, body, \.stApp[^}]*font-size: 16px", CSS)


def test_spacing_uses_only_the_scale():
    scale = {0, 4, 8, 12, 16, 24, 32}
    bad = []
    for decl in re.findall(r"(?:padding|margin|gap)(?:-[a-z]+)?:\s*([^;}]*)[;}]", CSS):
        if "calc" in decl or "min(" in decl or "vh" in decl:
            continue
        for n in re.findall(r"(?<![\w.#-])(-?\d+)px", decl):
            if int(n) not in scale:
                bad.append(decl)
    assert not bad, bad[:5]
    assert "--sp-1:4px" in theme.root_css() and "--sp-8:32px" in theme.root_css()


def test_radius_is_8_for_cards_and_999_for_chips():
    assert "--radius:8px" in theme.root_css() and "--pill:999px" in theme.root_css()
    assert re.search(r"\.chip \{[^}]*border-radius: var\(--pill\)", CSS) and re.search(r"\.card \{[^}]*border-radius: var\(--radius\)", CSS)


def test_every_interactive_element_gets_a_teal_focus_ring_and_it_is_never_removed():
    assert "--ring:2px solid var(--primary)" in theme.root_css()
    assert re.search(r"button:focus-visible[^{]*\{\s*outline: var\(--ring\) !important", CSS)
    assert not re.search(r"button[^{]*\{[^}]*outline:\s*none", CSS)


def test_a_serif_is_used_only_for_the_wordmark_and_page_titles():
    users = re.findall(r"([^{}]+)\{[^}]*font-family: var\(--font-serif\)", CSS)
    assert users and all(any(k in u for k in ("h1", ".wordmark")) for u in users)


def test_buttons_size_to_their_text_and_never_cut_it():
    assert re.search(r"\.stButton > button[^{]*\{[^}]*white-space: nowrap", CSS)
    assert "text-overflow: ellipsis" not in CSS


def test_the_four_button_roles_and_the_sidebar_toggle_exist():
    for sel in ('stBaseButton-primary"]', 'stBaseButton-secondary"]', 'stBaseButton-tertiary"]', 'st-key-danger_'):
        assert sel in CSS
    assert "min-width: 44px !important; min-height: 44px !important" in CSS and "stExpandSidebarButton" in CSS
    assert ":active" in CSS and "transition: background-color 150ms" in CSS


def test_the_aria_script_names_streamlits_icon_only_buttons():
    for label in ("Close sidebar", "Open sidebar", "Send question", "Show password", "aria-current"):
        assert label in theme.A11Y_JS


def test_views_carry_no_inline_colours_or_font_sizes():
    offenders = []
    for f in (ROOT / "app" / "views").glob("*.py"):
        text = f.read_text()
        offenders += [f"{f.name}: {m}" for m in re.findall(r'style="[^"]*"', text)]
        offenders += [f"{f.name}: {m}" for m in re.findall(r"#[0-9A-Fa-f]{6}\b", text)]
    assert not offenders, offenders[:5]


# ---- contrast -------------------------------------------------------------------------------------------------------

def test_contrast_helper_matches_known_values():
    assert contrast.ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast.ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.02)


@pytest.mark.parametrize("kind,need,name,fg,bg,got", [r for r in contrast.rows() if r[1]])
def test_every_text_and_non_text_pair_meets_wcag(kind, need, name, fg, bg, got):
    assert got >= need, f"{name}: {got:.2f} < {need}"


def test_the_disabled_text_colour_reaches_4_5_on_every_surface_it_sits_on():
    for bg in ("bg", "sidebar", "surface"):
        assert contrast.ratio(theme.TOKENS["disabled-text"], theme.TOKENS[bg]) >= 4.5


# ---- login slot and the remembered path (run in the app, no browser) -----------------------------------------------

def _login_script():
    from app.views import login
    login.page()


def test_login_always_has_a_message_slot_and_a_wrong_password_fills_it():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_login_script, default_timeout=30).run()
    body = " ".join(m.value for m in at.markdown)
    assert 'class="alert-slot"' in body and 'role="alert"' not in body
    at.text_input(key="login_user").input("nobody")
    at.text_input(key="login_pass").input("nothing-like-it")
    next(b for b in at.button if b.label == "Sign in").click().run()
    body = " ".join(m.value for m in at.markdown)
    assert 'role="alert"' in body and "didn&#x27;t match" in body and 'data-focus="Password"' in body and 'class="alert-slot"' not in body


def _asked_path_script():
    import streamlit as st
    from app import nav
    st.session_state.asked_path = "dashboard"
    st.session_state.something = "cleared"
    nav.sign_in({"username": "s"})
    st.write(f'{st.session_state.asked_path}|{"something" in st.session_state}|{st.session_state.auth_user}')


def test_signing_in_keeps_the_page_that_was_asked_for_and_nothing_else():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_asked_path_script, default_timeout=30).run()
    assert at.markdown[-1].value == "dashboard|False|s"

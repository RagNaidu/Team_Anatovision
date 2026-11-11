"""WCAG contrast ratios for every colour pair the theme uses. `python -m app.contrast` prints the table; tests enforce it.

TEXT pairs must reach 4.5:1 (WCAG 1.4.3). NON-TEXT pairs (control borders, icons, the focus ring, the filled part of a
progress bar) must reach 3:1 (1.4.11). INFO pairs are reported but not enforced: hairlines and fills that only decorate,
because the same information is always also given by text or an icon.
"""
from app.theme import BADGES, STATUS, TOKENS

T = TOKENS
WHITE = "#FFFFFF"


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT = [
    ("body text on page", T["text"], T["bg"]), ("body text on card", T["text"], T["surface"]),
    ("body text on sidebar", T["text"], T["sidebar"]), ("body text on tint", T["text"], T["tint"]),
    ("muted text on page", T["muted"], T["bg"]), ("muted text on card", T["muted"], T["surface"]),
    ("muted text on sidebar", T["muted"], T["sidebar"]), ("muted text on tint", T["muted"], T["tint"]),
    ("link on page", T["link"], T["bg"]), ("link on card", T["link"], T["surface"]), ("link on tint", T["link"], T["tint"]),
    ("teal text on card (secondary button)", T["primary"], T["surface"]), ("teal text on page", T["primary"], T["bg"]),
    ("teal text on sidebar", T["primary"], T["sidebar"]), ("teal text on tint (selected tab/segment)", T["primary"], T["tint"]),
    ("hover teal text on tint (selected nav item)", T["primary-hover"], T["tint"]),
    ("white on primary button", WHITE, T["primary"]), ("white on primary hover", WHITE, T["primary-hover"]),
    ("white on primary pressed", WHITE, T["primary-pressed"]),
    ("disabled text on page", T["disabled-text"], T["bg"]), ("disabled text on sidebar", T["disabled-text"], T["sidebar"]),
    ("disabled text on card", T["disabled-text"], T["surface"]),
    ("text on highlight", T["text"], T["highlight"]),
] + [(f"{k} chip text on its fill", t, f) for k, (t, f, _, _) in STATUS.items()] \
  + [(f"{k} badge text on its fill", t, f) for k, (t, f, _) in BADGES.items()] \
  + [("danger button text on card", STATUS["review"][0], T["surface"])]

NON_TEXT = [
    ("input border on page", T["input-border"], T["bg"]), ("input border on card", T["input-border"], T["surface"]),
    ("button border / icon (teal) on card", T["primary"], T["surface"]), ("button border (teal) on page", T["primary"], T["bg"]),
    ("focus ring (teal) on page", T["primary"], T["bg"]), ("focus ring (teal) on sidebar", T["primary"], T["sidebar"]),
    ("focus ring (teal) on card", T["primary"], T["surface"]), ("progress fill on its track", T["primary"], T["progress-track"]),
    ("selected-nav bar (teal) on sidebar", T["primary"], T["sidebar"]),
] + [(f"{k} chip icon on its fill", t, f) for k, (t, f, _, _) in STATUS.items()]

INFO = [
    ("hairline border on page (decorative)", T["border"], T["bg"]),
    ("locked-step dashed border on page (a padlock icon and a disabled state also say it)", T["locked-border"], T["bg"]),
    ("progress track on page (the filled part is checked above)", T["progress-track"], T["bg"]),
    ("highlighted-line bar on card (the line is also announced by the visible note and <mark>)", T["highlight-bar"], T["surface"]),
] + [(f"{k} chip border on its fill (icon + text carry the meaning)", b, f) for k, (t, f, b, _) in STATUS.items()]


def rows():
    return ([("text", 4.5, n, a, b, ratio(a, b)) for n, a, b in TEXT] + [("non-text", 3.0, n, a, b, ratio(a, b)) for n, a, b in NON_TEXT]
            + [("info", 0, n, a, b, ratio(a, b)) for n, a, b in INFO])


def report():
    lines = [f'{"kind":9}{"need":>5} {"got":>6}  {"pair":58} fg / bg']
    for kind, need, name, a, b, got in rows():
        mark = "" if need == 0 else ("ok" if got >= need else "FAIL")
        lines.append(f"{kind:9}{need:>5} {got:>6.2f}  {name:58} {a} / {b} {mark}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())

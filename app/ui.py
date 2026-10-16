"""Small HTML building blocks for the dashboard: numbers on graphics, explanations in ⓘ tooltips.

Colours (checked with the dataviz validator on white; order keeps sage and orange apart for
colour-blind readers): sage = completed / engaged, blue = flow and transfers, orange = left by
choice / relapse, violet = discharged by the house, greys = unknown or not reached.

Every class is prefixed "ax-" so it can't collide with Streamlit's or Vega's own class names
(Vega draws each chart inside an SVG with class "marks").
"""

from __future__ import annotations

from html import escape

SAGE, BLUE, ORANGE, VIOLET = "#578550", "#2a78d6", "#eb6834", "#4a3aa7"
GREY_1, GREY_2, GREY_3, LIGHT = "#54586b", "#7e7d91", "#a9a7b8", "#d7d5e0"
TINT = {SAGE: "#edf3ef", BLUE: "#eef4fc", ORANGE: "#fdf0ea", VIOLET: "#efedfb"}
DARK = {SAGE: "#35522f", BLUE: "#1c5cab", ORANGE: "#b4501f", VIOLET: "#3c2f8a"}

ICONS = {  # simple line icons, 24x24
    "bed": '<path d="M3 18V7M3 14h18v4M21 14v-1.5A2.5 2.5 0 0 0 18.5 10H11v4"/><circle cx="7" cy="11.5" r="1.6"/>',
    "inbox": '<path d="M4 13h4l1.2 3h5.6l1.2-3h4"/><path d="M4 13 6.2 6h11.6L20 13v5H4z"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>',
    "file": '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/>'
            '<path d="M12 11v3M12 17h.01"/>',
}

CSS = """
<style>
.block-container { max-width: 1180px; padding-top: 2.4rem; padding-bottom: 3rem; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
.ax-name { font-size: 1.3rem; font-weight: 600; color: #030302; margin: 0; }
.ax-meta { color: #7e7d91; font-size: .85rem; margin: .1rem 0 0; }
.ax-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .6rem; margin: .4rem 0 .8rem; }
.ax-s { position: relative; display: flex; gap: .7rem; align-items: center; background: #fff; border: 1px solid #eceaf2; border-radius: 12px; padding: .6rem 1.9rem .6rem .8rem; min-width: 0; }
@media (max-width: 960px) { .ax-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.ax-ic { flex: none; width: 36px; height: 36px; border-radius: 9px; display: flex; align-items: center; justify-content: center; }
.ax-ic svg { width: 20px; height: 20px; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.ax-sv { font-size: 1.25rem; font-weight: 600; color: #030302; line-height: 1.15; font-variant-numeric: tabular-nums; }
.ax-sl { font-size: .78rem; color: #54586b; line-height: 1.3; }
.ax-sl2 { color: #7e7d91; }
.ax-s > .ax-info { position: absolute; top: .55rem; right: .55rem; }
.ax-card { background: #fff; border: 1px solid #eceaf2; border-radius: 12px; padding: .9rem 1rem 1rem; margin-bottom: .8rem; }
.ax-ct { display: flex; justify-content: space-between; align-items: center; font-size: .72rem; letter-spacing: .07em;
         text-transform: uppercase; color: #7e7d91; margin-bottom: .7rem; }
.ax-info { position: relative; flex: none; display: inline-flex; width: 18px; height: 18px; border-radius: 50%;
           border: 1px solid #a9a7b8; color: #7e7d91; font-size: .68rem; align-items: center; justify-content: center;
           cursor: help; text-transform: none; letter-spacing: 0; outline: none; }
.ax-info:hover, .ax-info:focus { border-color: #578550; color: #446a3f; }
.ax-tip { display: none; position: absolute; top: 24px; right: -6px; z-index: 1000; width: 300px; max-width: 70vw;
          background: #21273f; color: #fff; border-radius: 8px; padding: .6rem .75rem; font-size: .8rem; line-height: 1.45;
          text-align: left; font-weight: 400; box-shadow: 0 6px 20px rgba(33, 39, 63, .18); white-space: normal; }
.ax-info:hover .ax-tip, .ax-info:focus .ax-tip, .ax-info:focus-within .ax-tip { display: block; }
.ax-big { font-size: 2rem; font-weight: 600; color: #030302; line-height: 1.1; font-variant-numeric: tabular-nums; }
.ax-unit { font-size: .9rem; color: #54586b; font-weight: 400; }
.ax-sub { font-size: .8rem; color: #7e7d91; margin-top: .25rem; }
.ax-fun { display: grid; grid-template-columns: 90px 1fr; gap: .35rem .8rem; align-items: center; }
.ax-fl { font-size: .82rem; color: #54586b; text-align: right; }
.ax-fb { height: 34px; border-radius: 7px; color: #fff; font-size: .9rem; font-weight: 600; display: flex; align-items: center;
         padding-left: .7rem; white-space: nowrap; min-width: 7rem; }
.ax-chip { display: inline-block; font-size: .76rem; border-radius: 999px; padding: .12rem .6rem; }
.ax-bar { display: flex; height: 34px; border-radius: 7px; overflow: hidden; gap: 2px; }
.ax-seg { display: flex; align-items: center; justify-content: center; color: #fff; font-size: .82rem; font-weight: 600; min-width: 0; }
.ax-leg { display: flex; flex-wrap: wrap; gap: .3rem 1rem; margin-top: .6rem; font-size: .8rem; color: #54586b; }
.ax-dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: .35rem; vertical-align: -1px; }
.ax-range { position: relative; height: 34px; margin-top: 4px; }
.ax-bracket { position: absolute; top: 0; height: 8px; border: 2px solid #21273f; border-top: none; border-radius: 0 0 3px 3px; }
.ax-rl { position: absolute; top: 12px; transform: translateX(-50%); white-space: nowrap; font-size: .8rem; color: #21273f; }
.ax-hb { display: grid; grid-template-columns: minmax(100px, 170px) minmax(90px, 1fr) max-content; gap: .45rem .7rem; align-items: center; font-size: .82rem; color: #21273f; }
.ax-hb .ax-track { height: 14px; background: #f5f3f9; border-radius: 7px; position: relative; overflow: hidden; }
.ax-hb .ax-fill { height: 100%; border-radius: 7px; }
.ax-hb .ax-n { text-align: right; font-variant-numeric: tabular-nums; color: #54586b; }
.ax-tiles { display: grid; gap: .6rem; margin-bottom: .8rem; }
.ax-tile { background: #fff; border: 1px solid #eceaf2; border-radius: 12px; padding: .8rem 1rem; }
[data-testid="stVerticalBlockBorderWrapper"] { background: #fff; border-radius: 12px !important; border-color: #eceaf2 !important; margin-bottom: .8rem; }
.ax-lab { font-size: .72rem; letter-spacing: .07em; text-transform: uppercase; color: #7e7d91; }
</style>
"""


def info(text: str) -> str:
    """ⓘ that shows its explanation on hover, or on tap/focus (keyboard and touch)."""
    return (f'<span class="ax-info" tabindex="0" role="button" aria-label="{escape(text, quote=True)}">i'
            f'<span class="ax-tip" role="tooltip">{escape(text)}</span></span>')


def title_row(title: str, tip: str | None = None) -> str:
    return f'<div class="ax-ct"><span>{title}</span>{info(tip) if tip else ""}</div>'


def card(title: str, body: str, tip: str | None = None) -> str:
    return f'<div class="ax-card">{title_row(title, tip)}{body}</div>'


def sub(text: str, top: str = ".6rem") -> str:
    return f'<div class="ax-sub" style="margin-top:{top}">{text}</div>'


def strip(items: list[tuple[str, str, str, str, str | None]]) -> str:
    """(icon, colour, value, label, tip). A label's second line, after a newline, is drawn lighter."""
    def text(label: str) -> str:
        first, _, second = label.partition("\n")
        return escape(first) + (f'<br><span class="ax-sl2">{escape(second)}</span>' if second else "")

    cells = "".join(
        f'<div class="ax-s"><div class="ax-ic" style="background:{TINT[c]}"><svg viewBox="0 0 24 24" style="stroke:{DARK[c]}">'
        f'{ICONS[icon]}</svg></div><div style="min-width:0"><div class="ax-sv">{escape(v)}</div>'
        f'<div class="ax-sl">{text(l)}</div></div>{info(tip) if tip else ""}</div>'
        for icon, c, v, l, tip in items)
    return f'<div class="ax-strip">{cells}</div>'


def tiles(items: list[tuple[str, str, str, str]], cols: int = 3) -> str:
    """(label, value, unit, sub)"""
    cells = "".join(f'<div class="ax-tile"><div class="ax-lab">{l}</div><div class="ax-big">{v}<span class="ax-unit">{u}</span></div>'
                    f'<div class="ax-sub">{s}</div></div>' for l, v, u, s in items)
    return f'<div class="ax-tiles" style="grid-template-columns:repeat({cols},minmax(0,1fr))">{cells}</div>'


def funnel(stages: list[tuple[str, int, str]], gaps: list[str], color: str = BLUE) -> str:
    """stages: (label, n, text on bar); gaps: chip text between consecutive stages."""
    top = max(n for _, n, _ in stages) or 1
    rows = []
    for i, (label, n, text) in enumerate(stages):
        rows.append(f'<div class="ax-fl">{label}</div><div class="ax-fb" style="width:{max(8, 100 * n / top):.0f}%;background:{color}">'
                    f'{text}</div>')
        if i < len(gaps):
            rows.append(f'<div></div><div><span class="ax-chip" style="background:{TINT[color]};color:{DARK[color]}">'
                        f'↓ {gaps[i]}</span></div>')
    return f'<div class="ax-fun">{"".join(rows)}</div>'


def seg_bar(parts: list[tuple[str, int, str]], span: tuple[float, float, str] | None = None) -> str:
    """parts: (label, count, colour). Counts sit on the bar; the legend names each colour.

    span: (from %, to %, label) draws a bracket under that stretch of the bar, e.g. the range
    between the worst and the best case."""
    total = sum(n for _, n, _ in parts) or 1
    segs = "".join(
        f'<div class="ax-seg" style="width:{100 * n / total:.2f}%;background:{c};color:{"#21273f" if c in (LIGHT, GREY_3) else "#fff"}" '
        f'title="{escape(l, quote=True)}: {n} ({n / total:.0%})">{n if n / total >= 0.035 else ""}</div>'
        for l, n, c in parts if n)
    legend = "".join(f'<span><i class="ax-dot" style="background:{c}"></i>{escape(l)}</span>' for l, n, c in parts if n)
    rng = ""
    if span:
        lo, hi, text = span
        mid = min(max((lo + hi) / 2, 22), 78)
        rng = (f'<div class="ax-range"><div class="ax-bracket" style="left:{lo:.1f}%;width:{max(hi - lo, 0.5):.1f}%"></div>'
               f'<div class="ax-rl" style="left:{mid:.1f}%">{text}</div></div>')
    return f'<div class="ax-bar">{segs}</div>{rng}<div class="ax-leg">{legend}</div>'


def hbars(rows: list[tuple[str, float, str, str]], scale: float | None = None) -> str:
    """rows: (label, value, colour, text at right)."""
    top = scale or max((v for _, v, _, _ in rows), default=1) or 1
    cells = "".join(
        f'<div>{escape(l)}</div><div class="ax-track"><div class="ax-fill" style="width:{100 * v / top:.1f}%;background:{c}"></div></div>'
        f'<div class="ax-n">{t}</div>' for l, v, c, t in rows)
    return f'<div class="ax-hb">{cells}</div>'

"""Small HTML building blocks for the dashboard: numbers on graphics, explanations in ⓘ tooltips.

Colours (checked with the dataviz validator on white; order keeps sage and orange apart for
colour-blind readers): sage = completed / engaged, blue = flow and transfers, orange = left by
choice / relapse, violet = discharged by the house, greys = unknown or not reached.
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
.hdr-name { font-size: 1.3rem; font-weight: 600; color: #030302; margin: 0; }
.hdr-meta { color: #7e7d91; font-size: .85rem; margin: .1rem 0 0; }
.strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .6rem; margin: .4rem 0 .8rem; }
.s { display: flex; gap: .7rem; align-items: center; background: #fff; border: 1px solid #eceaf2; border-radius: 12px; padding: .6rem .8rem; min-width: 0; }
.ic { flex: none; width: 36px; height: 36px; border-radius: 9px; display: flex; align-items: center; justify-content: center; }
.ic svg { width: 20px; height: 20px; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.sv { font-size: 1.25rem; font-weight: 600; color: #030302; line-height: 1.15; font-variant-numeric: tabular-nums; }
.sl { font-size: .78rem; color: #54586b; line-height: 1.3; }
.card { background: #fff; border: 1px solid #eceaf2; border-radius: 12px; padding: .9rem 1rem 1rem; margin-bottom: .8rem; }
.ct { display: flex; justify-content: space-between; align-items: center; font-size: .72rem; letter-spacing: .07em;
      text-transform: uppercase; color: #7e7d91; margin-bottom: .7rem; }
.info { display: inline-flex; width: 17px; height: 17px; border-radius: 50%; border: 1px solid #a9a7b8; color: #7e7d91;
        font-size: .68rem; align-items: center; justify-content: center; cursor: help; text-transform: none; letter-spacing: 0; }
.big { font-size: 2rem; font-weight: 600; color: #030302; line-height: 1.1; font-variant-numeric: tabular-nums; }
.unit { font-size: .9rem; color: #54586b; font-weight: 400; }
.sub { font-size: .8rem; color: #7e7d91; margin-top: .25rem; }
.fun { display: grid; grid-template-columns: 90px 1fr; gap: .35rem .8rem; align-items: center; }
.fl { font-size: .82rem; color: #54586b; text-align: right; }
.fb { height: 34px; border-radius: 7px; color: #fff; font-size: .9rem; font-weight: 600; display: flex; align-items: center;
      padding-left: .7rem; white-space: nowrap; min-width: 7rem; }
.chip { display: inline-block; font-size: .76rem; border-radius: 999px; padding: .12rem .6rem; }
.bar { display: flex; height: 34px; border-radius: 7px; overflow: hidden; gap: 2px; }
.seg { display: flex; align-items: center; justify-content: center; color: #fff; font-size: .82rem; font-weight: 600; min-width: 0; }
.leg { display: flex; flex-wrap: wrap; gap: .3rem 1rem; margin-top: .6rem; font-size: .8rem; color: #54586b; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: .35rem; vertical-align: -1px; }
.marks { position: relative; height: 18px; margin-top: .3rem; font-size: .75rem; color: #54586b; }
.hb { display: grid; grid-template-columns: minmax(100px, 170px) minmax(90px, 1fr) max-content; gap: .45rem .7rem; align-items: center; font-size: .82rem; color: #21273f; }
.hb .track { height: 14px; background: #f5f3f9; border-radius: 7px; position: relative; overflow: hidden; }
.hb .fill { height: 100%; border-radius: 7px; }
.hb .n { text-align: right; font-variant-numeric: tabular-nums; color: #54586b; }
.tile-row { display: grid; gap: .6rem; margin-bottom: .8rem; }
.tile { background: #fff; border: 1px solid #eceaf2; border-radius: 12px; padding: .8rem 1rem; }
[data-testid="stVerticalBlockBorderWrapper"] { background: #fff; border-radius: 12px !important; border-color: #eceaf2 !important; margin-bottom: .8rem; }
.lab { font-size: .72rem; letter-spacing: .07em; text-transform: uppercase; color: #7e7d91; }
</style>
"""


def info(text: str) -> str:
    return f'<span class="info" title="{escape(text, quote=True)}">i</span>'


def card(title: str, body: str, tip: str | None = None) -> str:
    return f'<div class="card"><div class="ct"><span>{title}</span>{info(tip) if tip else ""}</div>{body}</div>'


def strip(items: list[tuple[str, str, str, str]]) -> str:
    """(icon, colour, value, label)"""
    cells = "".join(
        f'<div class="s"><div class="ic" style="background:{TINT[c]}"><svg viewBox="0 0 24 24" style="stroke:{DARK[c]}">'
        f'{ICONS[icon]}</svg></div><div style="min-width:0"><div class="sv">{escape(v)}</div>'
        f'<div class="sl" title="{escape(l, quote=True)}">{escape(l)}</div></div></div>'
        for icon, c, v, l in items)
    return f'<div class="strip">{cells}</div>'


def tiles(items: list[tuple[str, str, str, str]], cols: int = 3) -> str:
    """(label, value, unit, sub)"""
    cells = "".join(f'<div class="tile"><div class="lab">{l}</div><div class="big">{v}<span class="unit">{u}</span></div>'
                    f'<div class="sub">{s}</div></div>' for l, v, u, s in items)
    return f'<div class="tile-row" style="grid-template-columns:repeat({cols},minmax(0,1fr))">{cells}</div>'


def funnel(stages: list[tuple[str, int, str]], gaps: list[str], color: str = BLUE) -> str:
    """stages: (label, n, text on bar); gaps: chip text between consecutive stages."""
    top = max(n for _, n, _ in stages) or 1
    rows = []
    for i, (label, n, text) in enumerate(stages):
        rows.append(f'<div class="fl">{label}</div><div class="fb" style="width:{max(8, 100 * n / top):.0f}%;background:{color}">'
                    f'{text}</div>')
        if i < len(gaps):
            rows.append(f'<div></div><div><span class="chip" style="background:{TINT[color]};color:{DARK[color]}">'
                        f'↓ {gaps[i]}</span></div>')
    return f'<div class="fun">{"".join(rows)}</div>'


def seg_bar(parts: list[tuple[str, int, str]], marks: list[tuple[float, str]] | None = None) -> str:
    """parts: (label, count, colour). Counts sit on the bar; the legend names each colour."""
    total = sum(n for _, n, _ in parts) or 1
    segs = "".join(
        f'<div class="seg" style="width:{100 * n / total:.2f}%;background:{c};color:{"#21273f" if c in (LIGHT, GREY_3) else "#fff"}" '
        f'title="{escape(l, quote=True)}: {n} ({n / total:.0%})">{n if n / total >= 0.035 else ""}</div>'
        for l, n, c in parts if n)
    legend = "".join(f'<span><i class="dot" style="background:{c}"></i>{escape(l)}</span>' for l, n, c in parts if n)
    mk = ""
    if marks:
        mk = '<div class="marks">' + "".join(
            f'<span style="position:absolute;left:{min(max(x, 0), 82):.1f}%">{t}</span>' for x, t in marks) + "</div>"
    return f'<div class="bar">{segs}</div>{mk}<div class="leg">{legend}</div>'


def hbars(rows: list[tuple[str, float, str, str]], scale: float | None = None) -> str:
    """rows: (label, value, colour, text at right)."""
    top = scale or max((v for _, v, _, _ in rows), default=1) or 1
    cells = "".join(
        f'<div>{escape(l)}</div><div class="track"><div class="fill" style="width:{100 * v / top:.1f}%;background:{c}"></div></div>'
        f'<div class="n">{t}</div>' for l, v, c, t in rows)
    return f'<div class="hb">{cells}</div>'

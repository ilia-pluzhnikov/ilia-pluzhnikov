"""Build the profile's images: an animated header, three project covers and the badges.

The star and release badges carry live numbers from the GitHub API, so a
scheduled workflow (.github/workflows/refresh.yml) reruns this script daily.

GitHub puts README images inside <img>. An SVG shown that way still runs its
CSS animations, but it loads no fonts, scripts or outside files. So every
line of text here is turned into glyph outlines, and each SVG carries
everything it needs inside itself.

    python tools/build_assets.py

Needs fontTools, uharfbuzz and Pillow. Fonts: Space Grotesk and JetBrains
Mono, both under the SIL Open Font License (see tools/fonts/).
"""
from __future__ import annotations

import base64
import json
import math
import os
import random
import re
import urllib.error
import urllib.request
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / "fonts"
ASSETS = ROOT / "assets"

# Page colours.
BG = "#0f0b18"
PANEL = "#1a1323"
CARD = "#231a2e"
RULE = "#3a2d47"
TICK = "#5a4b6a"
TEXT = "#f6f2ff"
SOFT = "#b9b0d6"
MUTE = "#8a80a3"
# The statusline's own colours, sampled from a screenshot of my terminal.
DIM = "#6f6479"      # ANSI dim
FG = "#9a93a6"       # default foreground
PINK = "#ff7dda"
YELLOW = "#ffe600"
GREEN = "#41ffa6"
CYAN = "#00ffff"
TEAL = "#007f7f"     # ANSI dim cyan
CLAUDE = "#d77757"   # Claude Code's spinner
# Star colours from the Stargaze sky.
STAR_COLOURS = ["#f5a524", "#b07cff", "#5b8cff", "#6fdc8c", "#ffffff"]


def num(v: float) -> str:
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return "0" if s == "-0" else s


class Face:
    """One weight of a variable font: shapes text with HarfBuzz, emits SVG path data."""

    def __init__(self, filename: str, weight: int):
        path = FONTS / filename
        self.hb_font = hb.Font(hb.Face(path.read_bytes()))
        self.hb_font.set_variations({"wght": weight})
        tt = instantiateVariableFont(TTFont(path), {"wght": weight})
        self.glyphs = tt.getGlyphSet()
        self.names = tt.getGlyphOrder()
        self.upem = tt["head"].unitsPerEm
        self.cap_height = tt["OS/2"].sCapHeight / self.upem

    def _shape(self, text: str):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        # No ligatures: JetBrains Mono would otherwise merge "->" and friends.
        hb.shape(self.hb_font, buf, {"liga": False, "calt": False})
        return buf.glyph_infos, buf.glyph_positions

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        _, positions = self._shape(text)
        advance = sum(p.x_advance for p in positions) * size / self.upem
        return advance + tracking * max(len(positions) - 1, 0)

    def path(self, text, x, y, size, tracking=0.0, anchor="start") -> str:
        if anchor == "middle":
            x -= self.width(text, size, tracking) / 2
        elif anchor == "end":
            x -= self.width(text, size, tracking)
        scale = size / self.upem
        pen = SVGPathPen(self.glyphs, ntos=num)
        infos, positions = self._shape(text)
        for info, p in zip(infos, positions):
            transform = (scale, 0, 0, -scale, x + p.x_offset * scale, y - p.y_offset * scale)
            self.glyphs[self.names[info.codepoint]].draw(TransformPen(pen, transform))
            x += p.x_advance * scale + tracking
        return pen.getCommands()

    def text(self, text, x, y, size, fill, tracking=0.0, anchor="start", attrs="") -> str:
        d = self.path(text, x, y, size, tracking, anchor)
        return f'<path fill="{fill}"{attrs} d="{d}"/>' if d else ""


SANS = SANS_MED = SANS_BOLD = MONO = MONO_BOLD = None  # loaded in main()


# --- shared pieces ---------------------------------------------------------

def svg_doc(w, h, label, defs, css, body) -> str:
    style = f"<style>{css}</style>" if css else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{label}">'
        f"<title>{label}</title><defs>{defs}</defs>{style}{body}</svg>"
    )


def backdrop(w, h, glows):
    """A dark base plus soft radial glows: (cx, cy, r, colour, opacity)."""
    defs, layers = [], [f'<rect width="{w}" height="{h}" fill="{BG}"/>']
    for i, (cx, cy, r, colour, opacity) in enumerate(glows):
        defs.append(
            f'<radialGradient id="glow{i}" cx="{cx}" cy="{cy}" r="{r}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{colour}" stop-opacity="{opacity}"/>'
            f'<stop offset="1" stop-color="{colour}" stop-opacity="0"/></radialGradient>'
        )
        layers.append(f'<rect width="{w}" height="{h}" fill="url(#glow{i})"/>')
    return "".join(defs), "".join(layers)


def starfield(rng, w, h, count, keep_out=(), twinkle_every=None):
    stars = []
    for i in range(count):
        x, y = rng.uniform(8, w - 8), rng.uniform(8, h - 8)
        r = rng.choice([0.6, 0.7, 0.8, 1.0, 1.0, 1.3, 1.6])
        opacity = rng.uniform(0.25, 0.75)
        if any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in keep_out):
            continue
        attrs = ""
        if twinkle_every and i % twinkle_every == 0:
            attrs = (
                f' class="tw" style="animation-duration:{rng.uniform(2.8, 5.5):.1f}s;'
                f'animation-delay:-{rng.uniform(0, 5):.1f}s"'
            )
        stars.append(
            f'<circle cx="{num(x)}" cy="{num(y)}" r="{r}" fill="#dcd6ff" '
            f'opacity="{opacity:.2f}"{attrs}/>'
        )
    return "".join(stars)


def mono_runs(runs, x, y, size):
    """Lay coloured runs on a monospace grid. A run is (text, colour[, "bold"])."""
    advance = MONO.width(" ", size)
    parts = []
    for run in runs:
        text, colour = run[0], run[1]
        face = MONO_BOLD if len(run) > 2 else MONO
        if colour and text.strip():
            parts.append(face.text(text, x, y, size, colour))
        x += advance * len(text)
    return "".join(parts), x


def render_line(line, x, y, size):
    """Render a statusline made of segments.

    A segment is a list of runs, or a dict of states {"A": runs, "B": runs}
    that swap in place. Returns (static svg, {state: svg}, [(x0, x1) per segment]).
    """
    static, states, bounds = [], {}, []
    for segment in line:
        start = x
        if isinstance(segment, dict):
            lengths = {sum(len(r[0]) for r in runs) for runs in segment.values()}
            assert len(lengths) == 1, f"states differ in width: {segment}"
            for key, runs in segment.items():
                svg, end = mono_runs(runs, start, y, size)
                states.setdefault(key, []).append(svg)
            x = end
        else:
            svg, x = mono_runs(segment, x, y, size)
            static.append(svg)
        bounds.append((start, x))
    return "".join(static), {k: "".join(v) for k, v in states.items()}, bounds


SEP = [(" │ ", FG)]


# --- header ----------------------------------------------------------------

NAME = "Ilia Pluzhnikov"
TAGLINE = "I build tools for Claude Code and teach teams to work with AI."
PROMPT = "make my GitHub profile"

# The header's statusline before (A) and after (B) the prompt is sent. Past
# 250k tokens the context bar turns yellow even in a 1M window: that is the
# statusline's own rule.
HEADER_LINE = [
    [("Op5.5:hg (1m)", DIM)],
    SEP,
    [("ilia-pluzhnikov", DIM), (" ", None), ("(main)", CYAN)],
    SEP,
    {"A": [("█░░░░ 211k/1M", PINK)], "B": [("█▌░░░ 312k/1M", YELLOW)]},
    SEP,
    [("cache", DIM), (" ", None)],
    {
        "A": [("97%", GREEN, "bold"), (" ", None), ("↓204k", GREEN, "bold"), (" ", None),
              ("+4.6k", YELLOW), (" ", None), ("1h", TEAL), (":58m", DIM)],
        "B": [("98%", GREEN, "bold"), (" ", None), ("↓307k", GREEN, "bold"), (" ", None),
              ("+3.9k", YELLOW), (" ", None), ("1h", TEAL), (":60m", DIM)],
    },
    SEP,
    [("5h:", FG)],
    {"A": [("12%", PINK), ("(3h41m)", DIM)], "B": [("14%", PINK), ("(3h40m)", DIM)]},
    SEP,
    [("7d:", FG), ("9%", PINK), ("(5d)", DIM)],
]

# The Big Dipper: handle first, then the bowl.
DIPPER = [(902, 70), (950, 92), (1000, 102), (1050, 124), (1068, 176), (1148, 184), (1162, 128)]
DIPPER_EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 3)]

CYCLE = 12          # seconds of one prompt loop
TYPE_FROM, TYPE_TO = 6, 36   # % of the cycle spent typing
SUBMIT = 60         # % when the prompt is sent
UPDATE = 68         # % when the statusline catches up


def header() -> str:
    w, h = 1280, 320
    rng = random.Random(11)
    defs, layers = backdrop(w, h, [
        (250, 110, 560, "#2b1748", 0.95),
        (1060, 130, 380, "#182a55", 0.75),
    ])
    defs += (
        '<linearGradient id="name" x1="64" y1="0" x2="700" y2="0" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{TEXT}"/><stop offset="1" stop-color="#ffc8ef"/></linearGradient>'
        '<filter id="blur" x="-2" y="-2" width="5" height="5"><feGaussianBlur stdDeviation="3"/></filter>'
    )

    css = [
        ".tw{animation:tw 4s ease-in-out infinite}",
        "@keyframes tw{0%,100%{opacity:.15}50%{opacity:1}}",
        ".ln{fill:none;stroke:#9d93d9;stroke-opacity:.5;stroke-width:1.2;stroke-dasharray:1;"
        "animation:draw 14s ease-in-out infinite backwards}",
        "@keyframes draw{0%{stroke-dashoffset:1;opacity:1}8%,86%{stroke-dashoffset:0;opacity:1}"
        "94%,100%{stroke-dashoffset:0;opacity:0}}",
        ".halo{opacity:.35;animation:halo 4s ease-in-out infinite}",
        "@keyframes halo{0%,100%{opacity:.25}50%{opacity:.6}}",
        f".cur{{animation:cur {CYCLE}s infinite}}",
        f"@keyframes cur{{0%,{TYPE_FROM}%{{transform:translateX(0);"
        f"animation-timing-function:steps({len(PROMPT)},end)}}"
        f"{TYPE_TO}%,{SUBMIT}%{{transform:translateX({12 * len(PROMPT)}px)}}"
        f"{SUBMIT + 0.01}%,100%{{transform:translateX(0)}}}}",
        ".blink{animation:blink 1.1s infinite}",
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}",
        f".think{{opacity:0;animation:think {CYCLE}s infinite}}",
        f"@keyframes think{{0%,{SUBMIT}%{{opacity:0}}{SUBMIT + 0.01}%,{UPDATE}%{{opacity:1}}"
        f"{UPDATE + 0.01}%,100%{{opacity:0}}}}",
        ".spin{animation:spin 1s linear infinite}",
        "@keyframes spin{to{transform:rotate(360deg)}}",
        f".sA{{animation:sA {CYCLE}s infinite}}",
        f"@keyframes sA{{0%,{UPDATE}%{{opacity:1}}{UPDATE + 0.01}%,100%{{opacity:0}}}}",
        f".sB{{opacity:0;animation:sB {CYCLE}s infinite}}",
        f"@keyframes sB{{0%,{UPDATE}%{{opacity:0}}{UPDATE + 0.01}%,100%{{opacity:1}}}}",
    ]

    body = [layers]
    body.append(starfield(rng, w, h, 130, keep_out=[(40, 40, 760, 186), (0, 196, w, h)],
                          twinkle_every=3))

    # Constellation: lines draw themselves one after another, stars pulse.
    for i, (a, b) in enumerate(DIPPER_EDGES):
        (x1, y1), (x2, y2) = DIPPER[a], DIPPER[b]
        body.append(f'<path class="ln" style="animation-delay:{0.25 * i:.2f}s" '
                    f'pathLength="1" d="M{x1} {y1}L{x2} {y2}"/>')
    for i, (x, y) in enumerate(DIPPER):
        colour = STAR_COLOURS[i % len(STAR_COLOURS)]
        body.append(f'<circle class="halo" style="animation-delay:-{0.6 * i:.1f}s" cx="{x}" '
                    f'cy="{y}" r="7" fill="{colour}" filter="url(#blur)"/>')
        body.append(f'<circle cx="{x}" cy="{y}" r="2.6" fill="{colour}"/>')

    body.append(SANS_BOLD.text(NAME, 64, 122, 76, "url(#name)", tracking=-1))
    body.append(SANS.text(TAGLINE, 66, 168, 25, SOFT))
    room = min(x for x, _ in DIPPER) - 40 - 66
    assert SANS.width(TAGLINE, 25) <= room, "tagline runs into the constellation"

    # Claude Code's input box: rule, prompt, rule, statusline.
    body.append(f'<path d="M64 224H1216M64 274H1216" stroke="{RULE}" stroke-width="1"/>')
    body.append(MONO.text("❯", 64, 255, 20, PINK))
    advance = MONO.width(" ", 20)
    x0 = 64 + 2 * advance
    step = (TYPE_TO - TYPE_FROM) / len(PROMPT)
    for i, ch in enumerate(PROMPT):
        if ch == " ":
            continue
        at = TYPE_FROM + (i + 1) * step
        css.append(f".k{i}{{opacity:0;animation:k{i} {CYCLE}s infinite}}")
        css.append(f"@keyframes k{i}{{0%,{at:.2f}%{{opacity:0}}{at + 0.01:.2f}%,{SUBMIT}%"
                   f"{{opacity:1}}{SUBMIT + 0.01}%,100%{{opacity:0}}}}")
        body.append(MONO.text(ch, x0 + i * advance, 255, 20, TEXT, attrs=f' class="k{i}"'))
    body.append(f'<g class="cur"><rect class="blink" x="{num(x0)}" y="238" width="11" '
                f'height="22" fill="{PINK}"/></g>')

    # "Thinking…" with a spinning asterisk, between sending and the update.
    spokes = "M0 -6V6M-5.2 -3L5.2 3M-5.2 3L5.2 -3"
    body.append(f'<g class="think"><g transform="translate(71 199)"><path class="spin" '
                f'd="{spokes}" stroke="{CLAUDE}" stroke-width="2" stroke-linecap="round"/></g>'
                + MONO.text("Thinking…", 86, 204, 15, CLAUDE) + "</g>")

    static, states, _ = render_line(HEADER_LINE, 64, 303, 16)
    body.append(static)
    body.append(f'<g class="sA">{states["A"]}</g><g class="sB">{states["B"]}</g>')

    css.append("@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    label = f"{NAME}. {TAGLINE}"
    return svg_doc(w, h, label, defs, "".join(css), "".join(body))


# --- covers ----------------------------------------------------------------

COVER_LINE = [
    [("Op5.5:hg (1m)", DIM)],
    SEP,
    [("ilia-pluzhnikov", DIM), (" ", None), ("(main)", CYAN)],
    SEP,
    [("↑1 push", YELLOW)],
    SEP,
    [("█▌░░░ 312k/1M", YELLOW)],
    SEP,
    [("cache", DIM), (" ", None), ("98%", GREEN, "bold"), (" ", None), ("↓307k", GREEN, "bold"),
     (" ", None), ("+3.9k", YELLOW), (" ", None), ("1h", TEAL), (":60m", DIM)],
    SEP,
    [("5h:", FG), ("14%", PINK), ("(3h40m)", DIM)],
    SEP,
    [("7d:", FG), ("9%", PINK), ("(5d)", DIM)],
]

# segment index -> (underline colour, title, detail lines); the folder label
# also covers the git segment next to it.
COVER_LABELS = {
    0: (DIM, "Model", ["version, effort,", "context size"]),
    2: (CYAN, "Folder & git", ["branch, changes,", "ahead or behind"]),
    6: (YELLOW, "Context used", ["yellow past 250k,", "even with 1M"]),
    8: (GREEN, "Prompt cache", ["hit rate, read, written,", "time until it expires"]),
    10: (PINK, "5-hour limit", ["used, resets in"]),
    12: (PINK, "7-day limit", ["used, resets in"]),
}


def statusline_cover() -> str:
    w, h = 1280, 400
    rng = random.Random(5)
    defs, layers = backdrop(w, h, [(300, 120, 640, "#2b1748", 0.8), (1100, 360, 420, "#182a55", 0.6)])
    body = [layers, starfield(rng, w, h, 90, keep_out=[(20, 24, 1260, 380)])]

    body.append(f'<rect x="32" y="36" width="1216" height="150" rx="16" fill="{PANEL}" '
                f'stroke="{RULE}"/>')
    body.append(f'<path d="M56 70H1224M56 118H1224" stroke="{RULE}"/>')
    body.append(MONO.text("❯", 56, 101, 18, PINK))
    body.append(f'<rect x="{num(56 + 2 * MONO.width(" ", 18))}" y="86" width="10" height="20" '
                f'fill="{PINK}"/>')
    static, _, bounds = render_line(COVER_LINE, 56, 152, 15)
    body.append(static)

    starts = sorted(COVER_LABELS)
    for n, index in enumerate(starts):
        colour, title, details = COVER_LABELS[index]
        x0, x1 = bounds[index]
        if index == 2:  # underline the git segment too
            x1 = bounds[4][1]
        body.append(f'<path d="M{num(x0)} 163H{num(x1)}" stroke="{colour}" stroke-width="2" '
                    f'stroke-opacity=".8"/>')
        body.append(f'<path d="M{num(x0)} 163V226" stroke="{TICK}"/>')
        body.append(SANS_MED.text(title, x0, 250, 17, TEXT))
        for k, line in enumerate(details):
            body.append(SANS.text(line, x0, 274 + 20 * k, 14, MUTE))
        # Warn when a label would run into the next one.
        widest = max([SANS_MED.width(title, 17)] + [SANS.width(d, 14) for d in details])
        limit = bounds[starts[n + 1]][0] if n + 1 < len(starts) else w - 32
        if x0 + widest > limit - 10:
            print(f"warning: label {title!r} is {x0 + widest - limit + 10:.0f}px too wide")

    body.append(MONO.text("statusline.js · one file · Node built-ins only · no network",
                          56, 356, 14, MUTE))
    label = "Claude Code statusline: model, folder and git, context used, prompt cache, 5-hour and 7-day limits"
    return svg_doc(w, h, label, defs, "", "".join(body))


def arrow(x1, x2, y) -> str:
    return (f'<path d="M{x1} {y}H{x2 - 2}" stroke="{PINK}" stroke-width="2"/>'
            f'<path d="M{x2 - 9} {y - 6}L{x2} {y}L{x2 - 9} {y + 6}" fill="none" stroke="{PINK}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')


def book_distill_cover() -> str:
    w, h = 1280, 400
    rng = random.Random(9)
    defs, layers = backdrop(w, h, [(640, 60, 700, "#2b1748", 0.8), (180, 380, 420, "#182a55", 0.5)])
    body = [layers, starfield(rng, w, h, 80, keep_out=[(28, 36, 1252, 364)])]

    cols = [(40, 236), (336, 268), (664, 268), (992, 248)]
    kickers = ["SOURCE", "STAGE 1", "STAGE 1.5", "STAGES 2–5"]
    titles = ["One book", "5 extractors", "3 checks", "3–7 skills"]
    for (x, cw), kicker, title in zip(cols, kickers, titles):
        body.append(f'<rect x="{x}" y="48" width="{cw}" height="304" rx="16" fill="{PANEL}" '
                    f'stroke="{RULE}"/>')
        body.append(MONO.text(kicker, x + 24, 88, 13, PINK, tracking=1.5))
        body.append(SANS_BOLD.text(title, x + 24, 126, 27, TEXT))
    for (x, cw), (nx, _) in zip(cols, cols[1:]):
        body.append(arrow(x + cw + 10, nx - 10, 200))

    # 1. An open book.
    bx, by = 40 + 118, 168
    pages = (f"M{bx} {by + 8}Q{bx - 34} {by - 6} {bx - 70} {by + 6}V{by + 98}"
             f"Q{bx - 34} {by + 86} {bx} {by + 100}Z"
             f"M{bx} {by + 8}Q{bx + 34} {by - 6} {bx + 70} {by + 6}V{by + 98}"
             f"Q{bx + 34} {by + 86} {bx} {by + 100}Z")
    body.append(f'<path d="{pages}" fill="{CARD}" stroke="{SOFT}" stroke-width="1.6" '
                f'stroke-linejoin="round"/>')
    lines = "".join(f"M{bx - 58} {by + 26 + 14 * k}H{bx - 12}M{bx + 12} {by + 26 + 14 * k}H{bx + 58}"
                    for k in range(5))
    body.append(f'<path d="{lines}" stroke="{MUTE}" stroke-width="1.4" stroke-linecap="round"/>')
    body.append(SANS.text("or a course, podcast,", 64, 304, 15, SOFT))
    body.append(SANS.text("transcript, longread", 64, 326, 15, SOFT))

    # 2. The five extractors.
    x = 336 + 24
    for k, item in enumerate(["methods", "principles", "cases", "pitfalls", "terms"]):
        y = 172 + 34 * k
        body.append(f'<rect x="{x}" y="{y - 13}" width="7" height="7" rx="1.5" fill="{PINK}"/>')
        body.append(MONO.text(item, x + 20, y, 17, SOFT))

    # 3. The three checks, and where failures go.
    x = 664 + 24
    checks = [("V1", "found twice in the source"), ("V2", "answers a new question"),
              ("V3", "not obvious without it")]
    for k, (code, text) in enumerate(checks):
        y = 174 + 36 * k
        body.append(MONO_BOLD.text(code, x, y, 16, PINK))
        body.append(SANS.text(text, x + 36, y, 15, SOFT))
    body.append(f'<path d="M{x} 286H{x + 220}" stroke="{RULE}" stroke-dasharray="4 4"/>')
    body.append(MONO.text("× rejected/", x, 318, 15, DIM))
    body.append(SANS.text("with the reason", x + 112, 318, 15, DIM))

    # 4. A stack of skills.
    x = 992 + 24
    for k in range(3):
        cx, cy = x + 20 - 10 * k, 150 + 12 * k
        body.append(f'<rect x="{cx}" y="{cy}" width="168" height="96" rx="10" fill="{CARD}" '
                    f'stroke="{RULE if k < 2 else SOFT}"/>')
    body.append(MONO.text("SKILL.md", x + 18, 198, 16, TEXT))
    body.append(SANS.text("steps · example · limits", x + 18, 224, 12, MUTE))
    body.append(SANS.text("one method each,", x, 304, 15, SOFT))
    body.append(SANS.text("tested on live routing", x, 326, 15, SOFT))

    label = ("book-distill: a book goes through five extractors and three checks "
             "and comes out as three to seven Claude Code skills")
    return svg_doc(w, h, label, defs, "", "".join(body))


def stargaze_cover() -> str:
    """My own Stargaze sky, framed like the other covers.

    tools/stargaze-sky.jpg is the "Небо" tab of my live instance, captured at
    1.5x with the top bar (sparks, hero level) hidden. It is embedded as is,
    at more pixels than the frame, so it stays sharp on high-density screens.
    """
    source = ROOT / "tools" / "stargaze-sky.jpg"
    iw, ih = Image.open(source).size
    fx, fy, fw = 32, 24, 1216
    fh = round(fw * ih / iw)
    w, h = 1280, fh + 2 * fy
    data = base64.b64encode(source.read_bytes()).decode("ascii")

    rng = random.Random(3)
    defs, layers = backdrop(w, h, [(200, 80, 600, "#2b1748", 0.8), (1100, 420, 420, "#182a55", 0.6)])
    defs += f'<clipPath id="frame"><rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="16"/></clipPath>'
    body = [
        layers,
        starfield(rng, w, h, 60, keep_out=[(fx - 8, fy - 8, fx + fw + 8, fy + fh + 8)]),
        f'<image x="{fx}" y="{fy}" width="{fw}" height="{fh}" clip-path="url(#frame)" '
        f'href="data:image/jpeg;base64,{data}"/>',
        f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="16" fill="none" stroke="{RULE}"/>',
    ]
    label = "Stargaze: skills drawn as constellations in a night sky, with quests, XP and sparks"
    return svg_doc(w, h, label, defs, "", "".join(body))


# --- badges ----------------------------------------------------------------
# Brand icons come from Simple Icons (CC0 1.0), tools/icons/; the globe, star
# and tag are drawn here. All icons live in a 24x24 box.

CHIP = "#3a2d47"
INK = "#1a1323"      # dark text on the pink chip


def brand_icon(name):
    svg = (ROOT / "tools" / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    d = re.search(r' d="([^"]+)"', svg).group(1)
    return lambda colour: f'<path fill="{colour}" d="{d}"/>'


def globe_icon(colour):
    return (f'<g fill="none" stroke="{colour}" stroke-width="2"><circle cx="12" cy="12" r="10"/>'
            '<path d="M2 12H22M12 2A15 15 0 0 1 12 22M12 2A15 15 0 0 0 12 22"/></g>')


def star_icon(colour):
    points = []
    for k in range(10):
        r = 11 if k % 2 == 0 else 4.6
        a = math.pi / 2 + k * math.pi / 5
        points.append(f"{num(12 + r * math.cos(a))},{num(13 - r * math.sin(a))}")
    return f'<polygon fill="{colour}" points="{" ".join(points)}"/>'


def tag_icon(colour):
    return (f'<path d="M3 3H11.6L21 12.4L12.4 21L3 11.6Z" fill="none" stroke="{colour}" '
            f'stroke-width="2" stroke-linejoin="round"/><circle cx="7.6" cy="7.6" r="1.7" fill="{colour}"/>')


def badge(text, icon, icon_colour, bg=CHIP, fg=TEXT) -> str:
    """A chip with an icon and a short label, with generous padding around both."""
    h, size, pad, icon_size, gap = 32, 12.5, 14, 14, 8
    w = round(pad + icon_size + gap + SANS_MED.width(text, size) + pad)
    scale = icon_size / 24
    body = (
        f'<rect width="{w}" height="{h}" rx="6" fill="{bg}"/>'
        f'<g transform="translate({pad} {num((h - icon_size) / 2)}) scale({scale:.4f})">'
        f"{icon(icon_colour)}</g>"
        + SANS_MED.text(text, pad + icon_size + gap, h / 2 + size * SANS_MED.cap_height / 2, size, fg)
    )
    return svg_doc(w, h, text, "", "", body)


def github_numbers(repo):
    """Stars and the latest release tag (None without releases) of one of my repositories."""
    headers = {"User-Agent": "ilia-pluzhnikov-profile", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

    def get(path):
        url = f"https://api.github.com/repos/ilia-pluzhnikov/{repo}{path}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return json.load(r)

    stars = get("")["stargazers_count"]
    try:
        release = get("/releases/latest")["tag_name"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        release = None
    return stars, release


def badges():
    out = {
        "site.svg": badge("Personal site", globe_icon, PINK),
        "youtube.svg": badge("YouTube channel", brand_icon("youtube"), "#ff0033"),
        "telegram.svg": badge("Telegram channel", brand_icon("telegram"), "#26a5e4"),
        "repository.svg": badge("Repository", brand_icon("github"), INK, bg=PINK, fg=INK),
    }
    for repo, show_stars, show_release in [("claude-code-statusline", True, True),
                                           ("stargaze", False, True),
                                           ("book-distill", True, False)]:
        stars, release = github_numbers(repo)
        if show_stars:
            out[f"{repo}-stars.svg"] = badge(f"{stars} stars", star_icon, "#f5c451")
        if show_release and release:
            out[f"{repo}-release.svg"] = badge(f"Release {release}", tag_icon, SOFT)
    return out


def main() -> None:
    global SANS, SANS_MED, SANS_BOLD, MONO, MONO_BOLD
    SANS = Face("SpaceGrotesk[wght].ttf", 400)
    SANS_MED = Face("SpaceGrotesk[wght].ttf", 500)
    SANS_BOLD = Face("SpaceGrotesk[wght].ttf", 700)
    MONO = Face("JetBrainsMono[wght].ttf", 400)
    MONO_BOLD = Face("JetBrainsMono[wght].ttf", 700)

    ASSETS.mkdir(exist_ok=True)
    for name, build in [("header.svg", header), ("statusline.svg", statusline_cover),
                        ("stargaze.svg", stargaze_cover), ("book-distill.svg", book_distill_cover)]:
        (ASSETS / name).write_text(build(), encoding="utf-8")
    (ASSETS / "badges").mkdir(exist_ok=True)
    for name, svg in badges().items():
        (ASSETS / "badges" / name).write_text(svg, encoding="utf-8")
    for f in sorted(p for p in ASSETS.rglob("*") if p.is_file()):
        print(f"{f.name:20} {f.stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main()

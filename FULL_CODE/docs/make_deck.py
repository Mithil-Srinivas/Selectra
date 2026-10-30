"""Build the Selectra presentation: a 5-minute deck (editable .pptx, native shapes, speaker notes).

    uv run --no-project --with python-pptx python docs/make_deck.py      (from FULL_CODE/)

Screenshots are read from docs/deck_assets/ (taken from the running app). Numbers match docs/project_brief.html.
"""
from __future__ import annotations

from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).parent
ASSETS = HERE / "deck_assets"
OUT = HERE / "selectra.pptx"

NAVY, ACCENT, INK = RGBColor(0x0B, 0x1F, 0x3A), RGBColor(0x1D, 0x4E, 0xD8), RGBColor(0x0E, 0x1B, 0x2C)
MUTED, RULE, WASH = RGBColor(0x56, 0x67, 0x7F), RGBColor(0xD8, 0xE0, 0xEB), RGBColor(0xF2, 0xF5, 0xFA)
ACCENT_SOFT, WHITE, OK = RGBColor(0xE6, 0xED, 0xFC), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0x04, 0x78, 0x57)
OK_SOFT, BAR_RAW, BAR_LLM = RGBColor(0xE6, 0xF5, 0xEE), RGBColor(0xA9, 0xB6, 0xC8), RGBColor(0x93, 0xB4, 0xF5)
HERO_SUB = RGBColor(0xA9, 0xBC, 0xD8)
SANS, SANS_SEMI, MONO = "Segoe UI", "Segoe UI Semibold", "Consolas"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


# ------------------------------------------------------------------ helpers
def text(slide, x, y, w, h, content, size=14, color=INK, font=SANS, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.1):
    """content: a string, or a list of paragraphs; each paragraph a string or list of (text, overrides) runs."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        runs = para if isinstance(para, list) else [(para, {})]
        for run_text, o in runs:
            r = p.add_run()
            r.text = run_text
            r.font.size = Pt(o.get("size", size))
            r.font.name = o.get("font", font)
            r.font.bold = o.get("bold", bold)
            r.font.color.rgb = o.get("color", color)
    return tb


def box(slide, x, y, w, h, fill=WASH, line=RULE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, width=1.0):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(width)
    s.shadow.inherit = False
    s.text_frame.margin_left = s.text_frame.margin_right = Inches(0.1)
    return s


def shape_text(s, paras, size=11, color=INK, bold=False, align=PP_ALIGN.CENTER, font=SANS):
    tf = s.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = para if isinstance(para, list) else [(para, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.name = o.get("font", font)
            r.font.color.rgb = o.get("color", color)


def arrow(slide, x1, y1, x2, y2, color=MUTED, dashed=False, head=True, width=1.25):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    if dashed:
        c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    if head:
        ln = c.line._get_or_add_ln()
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")
    return c


def rule(slide, x1, y1, x2, y2, color=RULE):
    slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
                               ).line.color.rgb = color


def header(slide, kicker, title, n):
    text(slide, 0.6, 0.42, 9, 0.3, kicker.upper(), size=11, color=ACCENT, font=MONO)
    text(slide, 0.6, 0.72, 12.1, 0.8, title, size=28, color=NAVY, font=SANS_SEMI)
    rule(slide, 0.6, 7.05, 12.73, 7.05)
    text(slide, 0.6, 7.12, 6, 0.25, "Selectra · R3 grounded shopping assistant", size=9, color=MUTED)
    text(slide, 11.73, 7.12, 1.0, 0.25, str(n), size=9, color=MUTED, align=PP_ALIGN.RIGHT)


def notes(slide, body):
    slide.notes_slide.notes_text_frame.text = body


def new(kicker, title, n):
    s = prs.slides.add_slide(BLANK)
    header(s, kicker, title, n)
    return s


def bullets(slide, x, y, w, h, items, size=16, gap=10):
    paras = []
    for it in items:
        runs = it if isinstance(it, list) else [(it, {})]
        paras.append([("■  ", {"color": ACCENT, "size": size - 6})] + runs)
    tb = text(slide, x, y, w, h, paras, size=size, spacing=1.15)
    for p in tb.text_frame.paragraphs:
        p.space_after = Pt(gap)
    return tb


def picture(slide, name, x, y, w):
    pic = slide.shapes.add_picture(str(ASSETS / f"{name}.png"), Inches(x), Inches(y), width=Inches(w))
    pic.line.color.rgb = RULE
    pic.line.width = Pt(0.75)
    return pic


# ------------------------------------------------------------------ 1 title (~15 s)
s = prs.slides.add_slide(BLANK)
box(s, 0, 0, 13.333, 7.5, fill=NAVY, line=None, shape=MSO_SHAPE.RECTANGLE)
logo = box(s, 0.9, 0.9, 0.62, 0.62, fill=ACCENT, line=None, radius=0.22)
shape_text(logo, [[("S", {"bold": True, "size": 24, "color": WHITE})]])
text(s, 0.9, 2.35, 11, 0.4, "R3 · TALENTAP MEGA HACKATHON 2026", size=13, color=HERO_SUB, font=MONO)
text(s, 0.9, 2.8, 11, 1.2, "Selectra", size=60, color=WHITE, font=SANS_SEMI)
text(s, 0.9, 4.05, 10.5, 1.0, "A shopping assistant that doesn't lie: every price, stock status and spec "
                             "is read from the catalogue.", size=22, color=HERO_SUB)
text(s, 0.9, 5.55, 11, 0.4, "Team dino  ·  Team ID 1086", size=16, color=WHITE, font=SANS_SEMI)
text(s, 0.9, 6.35, 11, 0.4, "AI understands  ·  code verifies  ·  catalogue decides", size=14, color=WHITE, font=MONO)
notes(s, "One line: shopping chatbots invent prices; Selectra cannot state a price or fact that isn't in the catalogue.")

# ------------------------------------------------------------------ 2 problem overview (~40 s)
s = new("Problem overview", "Shopping chatbots invent prices, products and policies", 2)
bullets(s, 0.6, 1.7, 6.3, 4.6, [
    "A made-up price is a legal and trust problem for a retailer.",
    "We get a fixed catalogue of 5,000 products and a 30-section store policy.",
    [("Shoppers type short, misspelt Hinglish: ", {}), ("“herbiqe ultraflex trimer kitne ka h”", {"font": MONO, "size": 14})],
    "Every question needs one action: answer, clarify (which product?) or refuse.",
], size=17)
box(s, 7.3, 1.7, 5.43, 4.6, fill=WASH, line=RULE, radius=0.04)
text(s, 7.6, 1.95, 5, 0.3, "HOW THE COMPETITION SCORES EACH QUESTION", size=11, color=MUTED, font=MONO)
text(s, 7.6, 2.35, 4.9, 0.9, ["action × (0.4 + 0.3·grounded + 0.3·helpful)", "− 3 × hallucinated_prices"],
     size=14, color=NAVY, font=MONO, spacing=1.3)
for i, (big, small) in enumerate([("−3", "per price not copied from the catalogue"), ("0.73", "organisers' baseline on dev"),
                                  ("1.0", "perfect question score")]):
    text(s, 7.6 + i * 1.65, 3.45, 1.6, 0.5, big, size=26, color=NAVY, font=SANS_SEMI)
    text(s, 7.6 + i * 1.65, 4.0, 1.5, 0.6, small, size=10.5, color=MUTED)
text(s, 7.6, 4.85, 5, 0.3, "TEST QUESTION MIX (150)", size=11, color=MUTED, font=MONO)
mix = [("Answerable", 45, ACCENT), ("Clarify", 20, BAR_LLM), ("Not sold", 15, NAVY), ("Unanswerable", 8, BAR_RAW),
       ("Policy", 12, MUTED)]
x = 7.6
for label, pct, col in mix:  # widths to scale: 4.85 in = 100%
    w = 4.85 * pct / 100
    seg = box(s, x, 5.2, w, 0.38, fill=col, line=WHITE, shape=MSO_SHAPE.RECTANGLE, width=1.5)
    if pct >= 12:
        shape_text(seg, [[(f"{pct}%", {"size": 10, "bold": True, "color": WHITE if col != BAR_LLM else NAVY})]])
    x += w
text(s, 7.6, 5.7, 4.9, 0.6, "  ·  ".join(f"{label} {pct}%" for label, pct, _ in mix), size=10, color=MUTED)
notes(s, "One wrong price costs 3 points on that question, more than three perfect answers earn. So the design goal is: "
         "never let a model write a fact.")

# ------------------------------------------------------------------ 3 architecture (~50 s)
s = new("Architecture", "How a question flows through the system", 3)
stages = [
    ("Shopper message", "“herbiqe astraair facewash kitne ka”", "English, Hinglish, typos", "input"),
    ("Name spell-check", "51 brands, 963 product lines", "Hints only; text never rewritten", "code"),
    ("LLM interpretation", "Hinglish → JSON search plan", "Only real sub-categories and fields allowed", "AI"),
    ("Code checks", "numbers · colours · values", "Drops numbers the shopper never typed", "code"),
    ("Similarity search ×2", "raw text + LLM phrase", "A bad rewrite can't hide a product", "AI"),
    ("Rank fusion", "Σ 1 / (60 + rank)", "Combines both rankings by position", "code"),
    ("Category grounding", "named product line wins", "LLM guess dropped if searches disagree", "code"),
    ("Evidence ledger", "verified · contradicted · unknown", "Missing ≠ false; exact colour match", "code"),
    ("Decision", "answer · clarify · refuse", "Rules, not the model, pick the action", "code"),
    ("Web app + Debug", "cards, details, full trace", "Every value read from the record", "output"),
]
BW, BH, GAP, X0 = 2.2, 1.75, 0.33, 0.6
rows_y = [1.75, 4.45]
for i, (title, detail, guard, tag) in enumerate(stages):
    row, col = divmod(i, 5)
    x, y = X0 + col * (BW + GAP), rows_y[row]
    ai = tag == "AI"
    box(s, x, y, BW, BH, fill=ACCENT_SOFT if ai else (WHITE if tag == "output" else WASH),
        line=ACCENT if ai else (NAVY if tag == "output" else RULE), width=1.6 if ai else 1.0, radius=0.06)
    text(s, x + 0.14, y + 0.12, BW - 0.28, 0.25, tag.upper(), size=8.5, color=ACCENT if ai else MUTED, font=MONO,
         align=PP_ALIGN.RIGHT)
    text(s, x + 0.14, y + 0.3, BW - 0.28, 0.35, title, size=13, color=NAVY, font=SANS_SEMI)
    text(s, x + 0.14, y + 0.66, BW - 0.28, 0.45, detail, size=9.5, color=MUTED, font=MONO if "Σ" in detail else SANS)
    rule(s, x + 0.14, y + 1.1, x + BW - 0.14, y + 1.1)
    text(s, x + 0.14, y + 1.17, BW - 0.28, 0.55, guard, size=9.5, color=INK)
    if col < 4:
        arrow(s, x + BW + 0.03, y + BH / 2, x + BW + GAP - 0.03, y + BH / 2)
x5, x6 = X0 + 4 * (BW + GAP) + BW / 2, X0 + BW / 2
arrow(s, x5, rows_y[0] + BH, x5, 3.9, head=False)
arrow(s, x5, 3.9, x6, 3.9, head=False)
arrow(s, x6, 3.9, x6, rows_y[1] - 0.03)
text(s, 5.0, 3.68, 3.5, 0.2, "2 × 5,000 similarity scores", size=9, color=MUTED, font=MONO, align=PP_ALIGN.CENTER)
text(s, 0.6, 6.4, 12.1, 0.45, "Blue boxes are AI. Everything else is plain code, so every fact on screen can be traced "
                              "to a field in a product record.", size=11.5, color=MUTED)
notes(s, "Walk left to right. Only the blue boxes involve models. The LLM is called once per question.")

# ------------------------------------------------------------------ 4 tech stack (~30 s)
s = new("Tech stack", "Small, local and open-licence", 4)
layers = [
    ("Interface", ["NiceGUI web app", "Search tab", "Debug tab", "Terminal search tool"], WHITE, NAVY),
    ("Pipeline · Python 3.13", ["Pydantic schema checks", "RapidFuzz name matching", "NumPy search + rank fusion",
                                "Evidence ledger"], WASH, RULE),
    ("AI models · Ollama, local GPU", ["Qwen3.5-9B Instruct (LLM)", "qwen3-embedding 0.6B (1,024-d)"], ACCENT_SOFT, ACCENT),
    ("Data", ["catalogue.jsonl · 5,000 products", "policy.md · 30 sections", "cached vectors · 20 MB"], WASH, RULE),
]
LX, LW, LH, LG = 0.6, 8.0, 1.0, 0.33
for i, (name, chips, fill, line) in enumerate(layers):
    y = 1.7 + i * (LH + LG)
    box(s, LX, y, LW, LH, fill=fill, line=line, radius=0.06, width=1.4 if line in (NAVY, ACCENT) else 1.0)
    text(s, LX + 0.25, y + 0.33, 2.3, 0.4, name, size=12.5, color=ACCENT if line == ACCENT else NAVY, font=SANS_SEMI)
    cx = LX + 2.75
    cw = (LW - 2.95 - 0.12 * (len(chips) - 1)) / len(chips)
    for c in chips:
        chip = box(s, cx, y + 0.25, cw, 0.5, fill=WHITE, line=RULE, radius=0.2)
        shape_text(chip, [c], size=10.5, color=INK)
        cx += cw + 0.12
    if i < 3:
        arrow(s, LX + LW / 2, y + LH + 0.02, LX + LW / 2, y + LH + LG - 0.02)
for i, lbl in enumerate(["question / results", "plan, vectors", "records, vectors"]):
    text(s, LX + LW / 2 + 0.15, 1.7 + i * (LH + LG) + LH + 0.06, 3, 0.25, lbl, size=9, color=MUTED, font=MONO)
cost = [("1", "LLM call per question"), ("≈ 3,000 / 120", "tokens in / out per question"),
        ("1.5 – 2.5 s", "per question on a healthy server"), ("≈ 1 ms", "search over 5,000 products"),
        ("0", "paid APIs or fact-checking LLM calls")]
for i, (big, small) in enumerate(cost):
    y = 1.7 + i * 1.03
    text(s, 9.2, y, 3.5, 0.45, big, size=22, color=NAVY, font=SANS_SEMI)
    text(s, 9.2, y + 0.45, 3.5, 0.45, small, size=11, color=MUTED)
notes(s, "No vector database and no reranker: 5,000 products fit in 20 MB and search takes a millisecond. "
         "All models are open-licence and run locally.")

# ------------------------------------------------------------------ 5 role of AI (~45 s)
s = new("Role of AI", "AI understands the question. It never states a fact.", 5)
text(s, 0.6, 1.65, 3, 0.3, "AI", size=11, color=ACCENT, font=MONO)
text(s, 0.6, 3.7, 3, 0.3, "CODE", size=11, color=MUTED, font=MONO)
ai_boxes = [("Understand", "LLM turns Hinglish and typos into a search plan: product type, brand, budget, "
                           "fields asked about"),
            ("Find", "Embedding model finds similar products for both the raw text and the LLM's phrase")]
code_boxes = [("Check the plan", "Drops invented numbers and values the catalogue never uses"),
              ("Verify", "Each condition vs the product record: verified, contradicted, unknown"),
              ("Decide", "Rules pick answer, clarify or refuse"),
              ("State facts", "Prices and specs copied from the record, with product ID")]
for i, (t, d) in enumerate(ai_boxes):
    x = 0.6 + i * 6.15
    box(s, x, 1.95, 5.95, 1.15, fill=ACCENT_SOFT, line=ACCENT, width=1.5, radius=0.08)
    text(s, x + 0.25, 2.07, 5.5, 0.35, t, size=15, color=ACCENT, font=SANS_SEMI)
    text(s, x + 0.25, 2.45, 5.5, 0.6, d, size=11.5, color=INK)
CW = (12.13 - 3 * 0.2) / 4
for i, (t, d) in enumerate(code_boxes):
    x = 0.6 + i * (CW + 0.2)
    box(s, x, 4.0, CW, 1.25, fill=WASH, line=RULE, radius=0.08)
    text(s, x + 0.2, 4.12, CW - 0.4, 0.35, t, size=14, color=NAVY, font=SANS_SEMI)
    text(s, x + 0.2, 4.5, CW - 0.4, 0.7, d, size=11, color=INK)
    if i < 3:
        arrow(s, x + CW + 0.02, 4.62, x + CW + 0.18, 4.62)
arrow(s, 3.57, 3.12, 1.95, 3.98)
arrow(s, 9.72, 3.12, 4.95, 3.98)
text(s, 2.05, 3.38, 2.0, 0.3, "plan", size=9.5, color=MUTED, font=MONO)
text(s, 7.6, 3.38, 2.4, 0.3, "candidates", size=9.5, color=MUTED, font=MONO)
ex = box(s, 0.6, 5.6, 12.13, 1.05, fill=WHITE, line=NAVY, radius=0.06)
text(s, 0.9, 5.72, 11.6, 0.3, "REAL EXAMPLE FROM TESTING", size=10, color=MUTED, font=MONO)
text(s, 0.9, 6.05, 11.6, 0.5, [[("“cheapest nike shoes”", {"font": MONO, "size": 12.5}),
                                ("   →  LLM wrote a budget of ₹0 that nobody typed   →  code dropped it   →  ", {"size": 12.5}),
                                ("“We don't carry Nike” + cheapest shoes we do sell", {"size": 12.5, "bold": True, "color": NAVY})]])
notes(s, "AI is used where language is messy: understanding and finding. Everything that could become a false claim "
         "is code reading the catalogue. The Nike example is a real bug the code check caught.")

# ------------------------------------------------------------------ 6 decision flow (~30 s)
s = new("How it decides", "Rules choose answer, clarify or refuse", 6)
steps = [("Policy question?", "yes", "Policy answer with § citation", "answer · next phase"),
         ("No store sub-category and no catalogue brand?", "yes", "“We don't sell this”", "refuse"),
         ("Brand named that we don't carry?", "yes", "Notice “We don't carry Nike”, then search other brands", "continue"),
         ("Any product with no contradicted condition?", "no", "No match: closest shown, mismatches marked", "refuse"),
         ("Lookup with ≥ 2 matches that differ in what was asked?", "yes", "Ask “Which one do you mean?”", "clarify")]
DW, DH, DG, DX0, DY = 1.8, 1.55, 0.26, 0.6, 1.9
for i, (q, branch, outcome, action) in enumerate(steps):
    x = DX0 + i * (DW + DG)
    d = box(s, x, DY, DW, DH, fill=WHITE, line=NAVY, shape=MSO_SHAPE.DIAMOND, width=1.25)
    d.text_frame.margin_left = d.text_frame.margin_right = Inches(0.02)
    shape_text(d, [q], size=9.5, color=INK)
    if i < 4:
        nxt = "yes" if branch == "no" else "no"
        arrow(s, x + DW + 0.02, DY + DH / 2, x + DW + DG - 0.02, DY + DH / 2)
        text(s, x + DW - 0.05, DY + DH / 2 - 0.3, DG + 0.1, 0.25, nxt, size=9, color=MUTED, font=MONO,
             align=PP_ALIGN.CENTER)
    arrow(s, x + DW / 2, DY + DH + 0.02, x + DW / 2, 4.08)
    text(s, x + DW / 2 + 0.06, DY + DH + 0.12, 0.6, 0.25, branch, size=9, color=MUTED, font=MONO)
    box(s, x, 4.1, DW, 1.45, fill=WASH, line=RULE, radius=0.06)
    text(s, x + 0.12, 4.22, DW - 0.24, 0.95, outcome, size=11, color=NAVY, font=SANS_SEMI, spacing=1.1)
    text(s, x + 0.12, 5.18, DW - 0.24, 0.3, action, size=9.5, color=ACCENT, font=MONO)
xa = DX0 + 5 * (DW + DG)
arrow(s, xa - DG + 0.02, DY + DH / 2, xa - 0.02, DY + DH / 2)
text(s, xa - DG - 0.05, DY + DH / 2 - 0.3, DG + 0.1, 0.25, "no", size=9, color=MUTED, font=MONO, align=PP_ALIGN.CENTER)
ans = box(s, xa, DY + 0.2, DW, DH - 0.4, fill=NAVY, line=None, radius=0.08)
shape_text(ans, [[("Top products with evidence", {"bold": True, "color": WHITE, "size": 11.5})],
                 [("answer", {"font": MONO, "color": HERO_SUB, "size": 9.5})]])
text(s, 0.6, 5.95, 12.1, 0.8, "Checked left to right. Before the fourth question, every condition is checked on every "
                              "candidate. Blue labels are the competition action each branch maps to.",
     size=11.5, color=MUTED)
notes(s, "The model never picks the action. That makes refusals and clarifications predictable and explainable.")

# ------------------------------------------------------------------ 7 solution completeness (~40 s)
s = new("Solution completeness", "Complete pipeline, scored with the official evaluator", 7)
items = [("Hinglish and typo understanding", True), ("Hybrid search with category grounding", True),
         ("Evidence ledger: verified / contradicted / unknown", True), ("Refuses things we don't sell or carry", True),
         ("Asks which one when variants differ", True), ("Policy answers citing § sections", True),
         ("Multi-turn memory (budget, colour carry over)", True), ("Submission file for all 150 test questions", True),
         ("Web app with full Debug trace", True), ("Code backstop for material words", False)]
for i, (label, done) in enumerate(items):
    y = 1.7 + i * 0.47
    pill = box(s, 0.6, y + 0.04, 0.85, 0.32, fill=OK_SOFT if done else ACCENT_SOFT, line=None, radius=0.5)
    shape_text(pill, [[("DONE" if done else "NEXT", {"font": MONO, "size": 9, "bold": True,
                                                     "color": OK if done else ACCENT})]])
    text(s, 1.65, y + 0.05, 6.0, 0.35, label, size=13.5, color=INK if done else MUTED)
box(s, 7.95, 1.7, 4.78, 4.75, fill=WASH, line=RULE, radius=0.04)
text(s, 8.25, 1.92, 4.3, 0.3, "OFFICIAL EVALUATE.PY, 40 DEV QUESTIONS", size=10.5, color=MUTED, font=MONO)
results = [("1.000", "dev score (organisers' baseline: 0.73)"),
           ("0", "hallucinated prices"),
           ("100%", "correct action: answer, clarify or refuse"),
           ("0.51 → 0.89", "first result correct on descriptive Hinglish (probe set)")]
for i, (big, small) in enumerate(results):
    y = 2.35 + i * 1.0
    text(s, 8.25, y, 4.3, 0.45, big, size=24, color=NAVY, font=SANS_SEMI)
    text(s, 8.25, y + 0.47, 4.3, 0.45, small, size=11, color=MUTED)
notes(s, "The full pipeline runs end to end and writes the submission file. Dev score 1.000 with the official scorer. "
         "Be honest: we fixed two rules after looking at dev failures and dev has only 40 questions, so expect the "
         "hidden test score to be lower.")

# ------------------------------------------------------------------ 8-10 demo screenshots (~60 s)
s = new("Demo", "Search: understood, filtered and verified", 8)
picture(s, "football", 0.6, 1.65, 8.1)
bullets(s, 9.05, 1.75, 3.7, 5.0, [
    "“Understood as” shows the plan in plain words.",
    "Budget applied by code: 21 footballs, all ≤ ₹600, each with a ✓.",
    "Real price, MRP, discount and stock from the record.",
    "No images in the catalogue, so none are invented.",
], size=13, gap=9)
notes(s, "Query: 'mere bete ke liye football chahiye 600 ke andar'.")

s = new("Demo", "It asks, or says no, instead of guessing", 9)
picture(s, "herbique", 0.6, 1.65, 5.95)
picture(s, "nike", 6.78, 1.65, 5.95)
text(s, 0.6, 5.75, 5.95, 0.9, [[("Clarify. ", {"bold": True, "color": NAVY}),
                                ("Two AstraAir face washes match and their prices differ, so it asks which one.", {})]],
     size=12.5)
text(s, 6.78, 5.75, 5.95, 0.9, [[("Refuse the brand. ", {"bold": True, "color": NAVY}),
                                 ("Nike isn't in the catalogue. It says so, then shows shoes we do sell.", {})]],
     size=12.5)
notes(s, "If there is time, also type 'silver payal dikhao' live: it returns 'We don't sell this'.")

s = new("Demo", "Debug: every step is visible", 10)
picture(s, "debug", 0.6, 1.65, 8.1)
bullets(s, 9.05, 1.75, 3.7, 5.0, [
    "Latency per stage and LLM tokens per question.",
    "The LLM's plan exactly as returned.",
    "What code dropped, added or restricted, and why.",
    "Evidence per product: field, value, source, status.",
], size=13, gap=9)
notes(s, "This is how a judge can check any answer: open Debug and trace each fact to its catalogue field.")

# ------------------------------------------------------------------ 11 close (~10 s)
s = prs.slides.add_slide(BLANK)
box(s, 0, 0, 13.333, 7.5, fill=NAVY, line=None, shape=MSO_SHAPE.RECTANGLE)
text(s, 0.9, 2.3, 11.5, 2.4, ["AI understands.", "Code verifies.", "The catalogue decides."], size=40,
     color=WHITE, font=SANS_SEMI, spacing=1.05)
text(s, 0.9, 5.2, 11, 0.5, "Selectra · Team dino (1086) · Thank you. Questions?", size=20, color=HERO_SUB)
notes(s, "Offer to run any question the judges type, live.")

prs.save(OUT)
print(f"saved {OUT} ({len(prs.slides)} slides)")

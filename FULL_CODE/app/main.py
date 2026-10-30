"""Selectra: demo web UI for the grounded product search.

    cd FULL_CODE
    uv run python -m app.main          -> http://localhost:8080

Search tab: shopper view (understood-as summary, top products as cards, product details).
Debug tab: every pipeline stage for the last query (LLM plan, grounding, fusion ranks, evidence ledger, latency).
"""
from __future__ import annotations

import logging

from nicegui import run, ui

from app import formatting as fmt
from app import theme
from app.debug_view import render_debug
from app.product_view import product_card, product_dialog
from src.search_service import SearchOutcome, SearchService
from src.verification.evidence import field_value

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

SERVICE = SearchService()  # loads catalogue + cached embedding index once, shared by all browser sessions

DEMO_QUERIES = [
    "baal sukhane wali machine",
    "mere bete ke liye football chahiye 600 ke andar",
    "herbiqe astraair facewash kitne ka",
    "pani ki bottle jo der tak thanda rakhe",
    "sabse sasta 1.5 litre electric kettle",
    "boltek halo flex beige speaker paani me chalega?",
    "cheapest nike shoes",
    "silver payal dikhao",
]
INTENT = {"lookup": "Specific product", "browse": "Browsing options", "cheapest": "Cheapest first",
          "most_expensive": "Most expensive first", "compare": "Comparison"}
PAGE = 5


def _notice(text: str, tone: str = "info") -> None:
    with ui.element("div").classes(f"ss-notice {tone} w-full"):
        ui.icon("info" if tone == "info" else "warning").style("font-size:18px")
        ui.label(text)


def _empty(icon: str, title: str, body: str) -> None:
    with ui.element("div").classes("ss-panel ss-empty w-full"):
        ui.icon(icon)
        ui.label(title).style("font-size:19px;font-weight:700;margin:10px 0 4px;color:#0F172A")
        ui.label(body).style("color:#64748B;font-size:14px")


def _understood(out: SearchOutcome) -> None:
    p = out.result.interpretation.plan
    with ui.element("div").classes("ss-panel w-full"):
        with ui.element("div").classes("ss-understood"):
            ui.label("Understood as").classes("ss-kicker").style("margin-right:6px")
            if p.operation in INTENT:
                ui.label(INTENT[p.operation]).classes("ss-tag")
            if p.product_type:
                ui.label(p.product_type).classes("ss-tag")
            for s in sorted(out.result.allowed_sub_categories or []):
                ui.label(f"in {s}").classes("ss-tag dim")
            for c in out.conditions:
                ui.label(fmt.condition(c)).classes("ss-tag")
            asked = [f for f in p.asked_fields if f not in ("price_inr", "stock_status")]
            if asked and p.operation in ("lookup", "compare"):
                ui.label("Asking: " + ", ".join(fmt.label(f).lower() for f in asked)).classes("ss-tag dim")
            for u in p.unmapped_asks:
                ui.label(f"Asking: {u} (not in catalogue)").classes("ss-tag dim")


def _variant_notice(out: SearchOutcome) -> str | None:
    """A lookup that matches several variants which differ in what was asked: say so instead of guessing."""
    p = out.result.interpretation.plan
    matches = [h for h in out.hits if h.ledger.group == 0]
    if p.operation != "lookup" or len(matches) < 2:
        return None
    fields = p.asked_fields or ["price_inr"]
    differ = [f for f in fields if len({str(field_value(h.record, f)[1]) for h in matches}) > 1]
    if differ:
        return (f"{len(matches)} products match and they differ in {', '.join(fmt.label(f).lower() for f in differ)}. "
                "Which one do you mean?")
    return None


@ui.page("/")
def index() -> None:
    ui.add_head_html(theme.HEAD_HTML)
    ui.colors(primary=theme.BLUE)
    state: dict = {"out": None, "shown": PAGE}

    with ui.header().classes("ss-header items-center px-6 py-1"):
        with ui.row().classes("items-center gap-3"):
            ui.label("S").classes("ss-logo")
            with ui.column().classes("gap-0"):
                ui.label("Selectra").classes("ss-wordmark")
                ui.label("Every price, stock and spec read from the catalogue").classes("ss-tagline")
        ui.space()
        with ui.tabs().classes("ss-tabs").props("dense indicator-color=blue-4 no-caps") as tabs:
            t_search = ui.tab("search", label="Search", icon="search")
            t_debug = ui.tab("debug", label="Debug", icon="insights")

    with ui.tab_panels(tabs, value=t_search, animated=False).classes("w-full"):
        with ui.tab_panel(t_search):
            with ui.element("div").classes("ss-hero w-full"):
                with ui.column().classes("gap-4 mx-auto").style("max-width:1240px;width:100%"):
                    with ui.column().classes("gap-0"):
                        ui.html("<h1>What are you looking for?</h1>", sanitize=False)
                        ui.html("<p>Ask in English or Hinglish: misspellings, descriptions and budgets are fine.</p>",
                                sanitize=False)
                    with ui.row().classes("ss-searchbox items-center no-wrap gap-2"):
                        ui.icon("search").style("font-size:24px;color:#94A3B8")
                        box = ui.input(placeholder="e.g. baal sukhane wali machine 1500 ke andar").props(
                            "borderless").classes("flex-grow")
                        ui.button("Search", on_click=lambda: do_search(box.value)).classes("ss-search-btn")
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Try").classes("ss-try-label")
                        for q in DEMO_QUERIES:
                            ui.button(q, on_click=lambda q=q: do_search(q)).props("flat dense").classes("ss-try")
            body = ui.column().classes("ss-body gap-4")
        with ui.tab_panel(t_debug):
            debug_body = ui.column().classes("w-full gap-4").style("max-width:1240px;margin:0 auto;padding:24px")
    box.on("keydown.enter", lambda: do_search(box.value))
    render_debug(debug_body, None)
    with body:
        _empty("travel_explore", "Search 5,000 products across 10 categories",
               "Apparel, footwear, kitchen, beauty, electronics accessories, sports, bags, appliances, toys and stationery.")

    def render_results() -> None:
        out: SearchOutcome = state["out"]
        body.clear()
        with body:
            p = out.result.interpretation.plan
            if out.state == "not_sold":
                _understood(out)
                _empty("remove_shopping_cart", "We don't sell this",
                       f"Nothing in our catalogue matches “{out.query}”. We carry apparel, footwear, home & kitchen, "
                       "beauty, electronics accessories, sports, bags, small appliances, toys and stationery.")
                return
            if out.state == "policy":
                _empty("policy", "That's a store-policy question",
                       f"Topic: {p.policy_topic}. Policy answers with section citations come in the assistant chat.")
                return
            if out.state == "other":
                _empty("chat", "I can help you find products",
                       "Describe what you want, a brand, a budget or a feature.")
                return
            _understood(out)
            for n in out.notices:
                _notice(n, "warn")
            if v := _variant_notice(out):
                _notice(v)
            c = out.counts
            with ui.row().classes("w-full items-baseline justify-between"):
                if out.state == "no_match":
                    ui.label("Closest products (none matches every condition)").classes("ss-count")
                elif out.conditions:
                    extra = f" · {c['unknown']} more might (details not listed)" if c["unknown"] else ""
                    verb = "product matches" if c["match"] == 1 else "products match"
                    ui.html(f"<b>{c['match']}</b> {verb} all your conditions{extra}", sanitize=True).classes(
                        "ss-count")
                else:
                    noun = "product" if len(out.hits) == 1 else "products"
                    ui.html(f"<b>{len(out.hits)}</b> {noun} found", sanitize=True).classes("ss-count")
                ui.label(f"{out.timings_ms['total'] / 1000:.1f} s").classes("ss-count")
            show_asked = p.operation in ("lookup", "compare")
            with ui.element("div").classes("ss-grid"):
                for i, h in enumerate(out.hits[: state["shown"]], 1):
                    product_card(h, i, out.conditions, show_asked, lambda hit: product_dialog(hit, out.conditions))
            if len(out.hits) > state["shown"]:
                ui.button(f"Show {min(PAGE, len(out.hits) - state['shown'])} more", on_click=show_more).props(
                    "outline no-caps").classes("self-center")
            ui.label("Prices and stock as of the catalogue snapshot (1 Oct 2026). Product images are not part of the "
                     "catalogue.").classes("ss-footer w-full")

    def show_more() -> None:
        state["shown"] += PAGE
        render_results()

    async def do_search(text: str | None) -> None:
        text = (text or "").strip()
        if not text:
            return
        box.value = text
        body.clear()
        with body, ui.element("div").classes("ss-panel w-full ss-empty"):
            ui.spinner("dots", size="xl", color="primary")
            ui.label("Understanding your query and checking the catalogue…").style("color:#64748B;margin-top:8px")
        try:
            out = await run.io_bound(SERVICE.search, text)
        except Exception as e:  # LLM server down, CUDA error, timeout ...
            log.exception("search failed")
            body.clear()
            with body:
                _empty("cloud_off", "Search is temporarily unavailable", f"The model server returned an error: {e}")
            return
        state.update(out=out, shown=PAGE)
        render_results()
        render_debug(debug_body, out, SERVICE.searcher.interpreter.system)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Selectra", port=8080, reload=False, show=False, favicon="🔎")

"""Debug tab: how a result was produced, stage by stage, straight from the SearchOutcome."""
from __future__ import annotations

import json

from nicegui import ui

from app import formatting as fmt
from src.search_service import SearchOutcome
from src.verification.evidence import Status

STAGE_COLOURS = {"interpret": "#1D4ED8", "embed": "#0EA5E9", "search": "#14B8A6", "verify": "#0B1F3A"}
STAGE_NAMES = {"interpret": "LLM interpretation", "embed": "Query embedding", "search": "Similarity + fusion",
               "verify": "Evidence check"}
GROUP_NAMES = {0: "match", 1: "unknown", 2: "contradicted"}


def _metric(value: str, label: str) -> None:
    with ui.element("div").classes("ss-metric"):
        ui.label(value).classes("v")
        ui.label(label).classes("l")


def _step(title: str, note: str = "") -> None:
    with ui.row().classes("items-baseline gap-0"):
        ui.label(title).classes("ss-step")
        if note:
            ui.label(note).classes("ss-step").style("font-size:12.5px;color:#64748B;font-weight:500;margin-left:8px")


def render_debug(container, out: SearchOutcome | None, system_prompt: str = "") -> None:
    container.clear()
    with container:
        if out is None:
            with ui.element("div").classes("ss-panel ss-empty w-full"):
                ui.icon("insights")
                ui.html("<h3>Run a search to see how it was answered</h3>", sanitize=False)
                ui.label("Every stage of the pipeline is shown here: interpretation, retrieval, fusion and evidence.")
            return

        interp = out.result.interpretation
        t = out.timings_ms
        # ---- headline metrics
        with ui.row().classes("w-full gap-3"):
            _metric(f"{t['total']:,.0f} ms", "total latency")
            _metric(f"{interp.usage.tokens_in:,}", "LLM tokens in")
            _metric(f"{interp.usage.tokens_out:,}", "LLM tokens out")
            _metric(out.state.replace("_", " "), "outcome")
            _metric(f"{out.counts['match']}/{out.counts['unknown']}/{out.counts['contradicted']}",
                    "match / unknown / contra.")
        # ---- stage timeline
        with ui.element("div").classes("ss-panel w-full"):
            _step("Latency by stage", f"query: “{out.query}”")
            stages = [s for s in STAGE_NAMES if s in t]
            total = sum(t[s] for s in stages) or 1
            with ui.element("div").classes("ss-stagebar mt-2"):
                for s in stages:
                    pct = max(100 * t[s] / total, 1.5)
                    ui.label(f"{STAGE_NAMES[s]} · {t[s]:,.0f} ms" if pct > 14 else "").style(
                        f"width:{pct}%;background:{STAGE_COLOURS[s]}").tooltip(f"{STAGE_NAMES[s]}: {t[s]:,.1f} ms")
            with ui.element("div").classes("ss-legend"):
                for s in stages:
                    ui.html(f'<span class="dot" style="background:{STAGE_COLOURS[s]}"></span>'
                            f"{STAGE_NAMES[s]} <b>{t[s]:,.1f} ms</b>", sanitize=False)

        with ui.element("div").classes("ss-debug-grid"):
            # ---- 1. spell hints
            with ui.element("div").classes("ss-panel"):
                _step("1 · Name spell-check", "fuzzy match against 51 brands + 963 line names")
                if interp.hints:
                    ui.table(columns=[{"name": "t", "label": "Shopper typed", "field": "t", "align": "left"},
                                      {"name": "c", "label": "Catalogue name", "field": "c", "align": "left"},
                                      {"name": "k", "label": "Kind", "field": "k", "align": "left"},
                                      {"name": "s", "label": "Similarity", "field": "s"}],
                             rows=[{"t": h.text, "c": h.canonical, "k": h.kind, "s": f"{h.score:.0f}"}
                                   for h in interp.hints]).props("dense flat").classes("w-full mt-2")
                else:
                    ui.label("No brand or product-line names detected.").classes("ss-count mt-2")
                ui.label("Hints are passed to the LLM as suggestions; they never rewrite the query.").classes(
                    "ss-count mt-2").style("font-size:12px")

            # ---- 2. LLM plan
            with ui.element("div").classes("ss-panel"):
                _step("2 · LLM interpretation", f"{interp.usage.tokens_in:,} tokens in · {interp.usage.tokens_out} out · "
                                                f"{interp.usage.latency_ms:,.0f} ms · {interp.usage.attempts} attempt(s)")
                ui.code(json.dumps(interp.raw_plan, indent=2, ensure_ascii=False), language="json").classes(
                    "w-full mt-2")
                ui.label("Exactly as returned by the LLM; changes made by code are listed in step 3.").classes(
                    "ss-count").style("font-size:12px")
                if system_prompt:
                    with ui.expansion("System prompt sent to the LLM").classes("w-full"):
                        ui.code(system_prompt, language="text").classes("w-full")

        # ---- 3. grounding + code checks
        with ui.element("div").classes("ss-panel w-full"):
                _step("3 · Code checks on the plan", "deterministic: no LLM involved from here on")
                rows = [("Sub-category restriction",
                         ", ".join(sorted(out.result.allowed_sub_categories)) if out.result.allowed_sub_categories
                         else "none (unrestricted)"),
                        ("Why", out.result.grounding)]
                rows += [("Dropped (number not typed)", f"{c.field} {c.op} {c.value}")
                         for c in interp.dropped_constraints]
                rows += [("Added (colour typed)", f"{c.field} = {c.value}") for c in interp.added_constraints]
                rows += [("Notice", n) for n in out.notices]
                rows += [("Condition checked", fmt.condition(c) + ("" if c.hard else " (preference)"))
                         for c in out.conditions]
                with ui.element("div").classes("ss-spec w-full mt-2").style("grid-template-columns:200px 1fr"):
                    for k, v in rows:
                        ui.label(k).classes("k")
                        ui.label(v)

        # ---- 4. ranking
        if out.pool:
            with ui.element("div").classes("ss-panel w-full"):
                _step("4 · Retrieval, fusion and evidence",
                      "RRF score = 1/(60 + raw-text rank) + 1/(60 + LLM-query rank); ranks are out of 5,000 products")
                rows = []
                for i, h in enumerate(out.pool[:40], 1):
                    r, c = h.record, h.candidate
                    rows.append({"pos": i, "sku": r["product_id"], "title": r["title"][:64],
                                 "sub": r["sub_category"], "price": fmt.rupees(r["price_inr"]),
                                 "raw": c.raw_rank, "llm": c.llm_rank, "rrf": f"{c.fused_score:.5f}",
                                 "group": GROUP_NAMES[h.ledger.group],
                                 "checks": " ".join(f"{e.field}:{e.status.value[:3]}" for e in h.ledger.conditions)})
                cols = [("pos", "#"), ("sku", "SKU"), ("title", "Title"), ("sub", "Sub-category"), ("price", "Price"),
                        ("raw", "Raw rank"), ("llm", "LLM rank"), ("rrf", "RRF"), ("group", "Evidence"),
                        ("checks", "Condition checks")]
                ui.table(columns=[{"name": k, "label": l, "field": k, "align": "left", "sortable": k in
                                   ("raw", "llm", "pos")} for k, l in cols], rows=rows, row_key="pos",
                         pagination=10).props("dense flat").classes("w-full mt-2")
                ui.label(f"Showing the first 40 of {len(out.pool)} verified candidates, in display order "
                         "(matches first; contradicted candidates are hidden from shoppers when matches exist).").classes(
                    "ss-count").style("font-size:12px")

        # ---- 5. evidence ledger
        if out.hits:
            with ui.element("div").classes("ss-panel w-full"):
                _step("5 · Evidence ledger", "top 5 shown to the shopper; every value read from the catalogue record")
                for h in out.hits[:5]:
                    ev = h.ledger.conditions + h.ledger.asked
                    with ui.expansion(f"{h.record['product_id']} · {h.record['title']}",
                                      value=h is out.hits[0]).classes("w-full"):
                        if not ev:
                            ui.label("No conditions or asked fields to check for this query.").classes("ss-count")
                            continue
                        ui.table(columns=[{"name": k, "label": l, "field": k, "align": "left"} for k, l in
                                          [("field", "Field"), ("condition", "Condition"), ("actual", "Catalogue value"),
                                           ("source", "Source"), ("status", "Status")]],
                                 rows=[{"field": e.field, "condition": e.condition or "(asked)",
                                        "actual": fmt.value(e.field, e.actual) if e.status is not Status.UNKNOWN
                                        else "—", "source": e.source, "status": e.status.value.upper()}
                                       for e in ev]).props("dense flat").classes("w-full")

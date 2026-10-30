"""Shopper-facing product cards and the product detail dialog.

Every value shown is read from the catalogue record. The catalogue has no product images, so the card shows a
category placeholder labelled as such instead of inventing one.
"""
from __future__ import annotations

from nicegui import ui

from app import formatting as fmt
from src.conversation.query_interpreter import Constraint
from src.search_service import ProductHit
from src.verification.evidence import Evidence, Status

STATUS_ICON = {Status.VERIFIED: "check_circle", Status.CONTRADICTED: "cancel", Status.UNKNOWN: "help"}


def _stock_pill(stock: str) -> None:
    text, tone, icon = fmt.STOCK.get(stock, (stock, "warn", "info"))
    with ui.element("div").classes(f"ss-pill {tone}"):
        ui.icon(icon)
        ui.label(text)


def _price_block(r: dict, big: bool = False) -> None:
    with ui.row().classes("items-baseline gap-2"):
        ui.label(fmt.rupees(r["price_inr"])).classes("ss-price").style("font-size:26px" if big else "")
        if r["mrp_inr"] > r["price_inr"]:
            ui.label(fmt.rupees(r["mrp_inr"])).classes("ss-mrp")
            ui.label(f"{round(100 * (r['mrp_inr'] - r['price_inr']) / r['mrp_inr'])}% off").classes("ss-off")


def _rating(r: dict) -> None:
    rating = r.get("rating")
    if rating is None or rating != rating:
        ui.label("No reviews yet").classes("ss-rating")
    else:
        with ui.row().classes("items-center gap-1 ss-rating"):
            ui.label("★").classes("star")
            ui.label(f"{rating:.1f} · {r['review_count']:,} reviews")


def _evidence_rows(conditions: list[Constraint], evidence: list[Evidence]) -> None:
    for c, e in zip(conditions, evidence):
        tip = {Status.VERIFIED: f"Catalogue {e.source} = {fmt.value(e.field, e.actual)}",
               Status.CONTRADICTED: f"Catalogue {e.source} = {fmt.value(e.field, e.actual)}",
               Status.UNKNOWN: "Not listed in the catalogue record"}[e.status]
        with ui.element("div").classes(f"ss-ev {e.status.value}").tooltip(tip):
            ui.icon(STATUS_ICON[e.status])
            text = fmt.condition(c)
            if e.status is Status.CONTRADICTED:
                text += f" (is {fmt.value(e.field, e.actual)})"
            elif e.status is Status.UNKNOWN:
                text += " (not listed)"
            ui.label(text + ("" if c.hard else " · preference"))


def _asked_rows(asked: list[Evidence]) -> None:
    for e in asked:
        with ui.row().classes("ss-ask items-baseline gap-1 w-full"):
            ui.label(f"{fmt.label(e.field)}:").style("color:#64748B")
            if e.status is Status.VERIFIED:
                ui.label(fmt.value(e.field, e.actual)).classes("font-bold").style("color:#0B1F3A")
                if e.source.startswith("policy"):
                    ui.label("(none listed, policy §3.1)").style("color:#64748B")
            else:
                ui.label("Not listed in catalogue").classes("font-semibold").style("color:#B45309")


def product_card(hit: ProductHit, rank: int, conditions: list[Constraint], show_asked: bool, on_open) -> None:
    r = hit.record
    asked = [e for e in hit.ledger.asked if e.field not in ("price_inr", "stock_status")] if show_asked else []
    card = ui.element("div").classes("ss-card" + (" dim" if hit.ledger.group == 2 else ""))
    card.on("click", lambda: on_open(hit))
    with card:
        with ui.element("div").classes("ss-thumb"):
            ui.label(f"#{rank}").classes("ss-rank")
            ui.icon(fmt.CATEGORY_ICON.get(r["category"], "inventory_2"))
            ui.label(f"{r['sub_category']} · no image in catalogue").classes("ss-thumb-cap")
        with ui.element("div").classes("ss-card-body"):
            ui.label(r["brand"]).classes("ss-brand")
            ui.label(r["title"]).classes("ss-title").tooltip(r["title"])
            _rating(r)
            _price_block(r)
            _stock_pill(r["stock_status"])
            if chips := fmt.key_attributes(r["attributes"]):
                with ui.element("div").classes("ss-chips"):
                    for ch in chips:
                        ui.label(ch).classes("ss-chip")
            if asked:
                _asked_rows(asked)
            if conditions:
                with ui.element("div").classes("ss-evidence"):
                    _evidence_rows(conditions, hit.ledger.conditions)
            ui.label(r["product_id"]).classes("ss-sku")


def product_dialog(hit: ProductHit, conditions: list[Constraint]) -> None:
    r = hit.record
    with ui.dialog() as dialog, ui.card().classes("ss-dialog"):
        with ui.row().classes("w-full no-wrap gap-0"):
            with ui.element("div").classes("ss-thumb").style("width:280px;height:auto;min-height:280px;flex:none"):
                ui.icon(fmt.CATEGORY_ICON.get(r["category"], "inventory_2")).style("font-size:84px")
                ui.label("No image in catalogue").classes("ss-thumb-cap")
            with ui.column().classes("gap-2 p-6 flex-1"):
                with ui.row().classes("w-full items-start justify-between no-wrap"):
                    ui.label(f"{r['brand']} · {r['category']} › {r['sub_category']}").classes("ss-brand")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense")
                ui.label(r["title"]).style("font-size:20px;font-weight:700;line-height:1.3;color:#0F172A")
                _rating(r)
                _price_block(r, big=True)
                ui.label("Selling price incl. GST · catalogue snapshot 1 Oct 2026").style("font-size:11.5px;color:#94A3B8")
                _stock_pill(r["stock_status"])
                ui.label(r["description"]).style("font-size:13.5px;color:#334155;line-height:1.55;margin-top:6px")
        with ui.column().classes("w-full gap-3 px-6 pb-6"):
            if conditions:
                ui.label("Your conditions, checked against this record").classes("ss-kicker")
                with ui.element("div").classes("flex flex-col gap-1"):
                    _evidence_rows(conditions, hit.ledger.conditions)
            ui.label("Specifications").classes("ss-kicker")
            with ui.element("div").classes("ss-spec w-full"):
                for k, v in r["attributes"].items():
                    ui.label(fmt.label(k)).classes("k")
                    ui.label(fmt.value(k, v))
                if "warranty_months" not in r["attributes"]:
                    ui.label("Warranty").classes("k")
                    ui.label("No brand warranty listed, so none applies (policy §3.1)")
            ui.label(f"Source: catalogue record {r['product_id']}").classes("ss-sku")
    dialog.open()

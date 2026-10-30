"""Human-readable labels for catalogue fields, values and conditions. Display only: never changes a value."""
from __future__ import annotations

from typing import Any

from src.conversation.query_interpreter import Constraint

UNITS = [("_months", " months"), ("_hours", " h"), ("_min", " min"), ("_mah", " mAh"), ("_ml", " ml"), ("_mm", " mm"),
         ("_cm", " cm"), ("_kg", " kg"), ("_ft", " ft"), ("_in", " in"), ("_m", " m"), ("_l", " L"), ("_g", " g"),
         ("_w", " W"), ("_c", " °C")]
LABELS = {"price_inr": "Price", "mrp_inr": "MRP", "discount_inr": "Discount", "stock_status": "Stock",
          "line_name": "Product line", "upto_in": "up to", "fits_laptop_upto_in": "Fits laptop up to",
          "water_resistance_rating": "Water-resistance rating", "pack_of": "Pack of", "spf": "SPF",
          "pa_rating": "PA rating", "gsm": "GSM", "dpi": "DPI"}
STOCK = {"in_stock": ("In stock", "ok", "check_circle"), "low_stock": ("Only a few left", "warn", "schedule"),
         "out_of_stock": ("Out of stock", "bad", "block")}
CATEGORY_ICON = {"Apparel": "checkroom", "Footwear": "hiking", "Home & Kitchen": "soup_kitchen",
                 "Beauty & Personal Care": "spa", "Electronics Accessories": "headphones",
                 "Sports & Fitness": "sports_soccer", "Bags & Luggage": "luggage", "Small Appliances": "blender",
                 "Toys & Games": "toys", "Stationery & Office": "edit_note"}
OP_WORD = {"eq": "", "ne": "not ", "lte": "≤ ", "gte": "≥ "}


def label(field: str) -> str:
    if field in LABELS:
        return LABELS[field]
    base = field
    for suffix, _ in UNITS:
        if field.endswith(suffix):
            base = field[: -len(suffix)]
            break
    return base.replace("_", " ").capitalize()


def unit(field: str) -> str:
    return next((u for s, u in UNITS if field.endswith(s)), "")


def rupees(v: float) -> str:
    return f"₹{int(v):,}"


def value(field: str, v: Any) -> str:
    if v is None:
        return "Not listed in catalogue"
    if field in ("price_inr", "mrp_inr", "discount_inr"):
        return rupees(v)
    if field == "stock_status":
        return STOCK.get(v, (v,))[0]
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v}{unit(field)}"


def condition(c: Constraint) -> str:
    """'Up to ₹600', 'Colour: red', 'Insulated', 'Brand: Herbique' ..."""
    if c.field == "price_inr" and c.op in ("lte", "gte"):
        return f"{'Up to' if c.op == 'lte' else 'From'} {rupees(c.value)}"
    if c.field == "stock_status" and c.op == "ne" and c.value == "out_of_stock":
        return "Available to order"
    if isinstance(c.value, bool):
        positive = c.value if c.op == "eq" else not c.value
        return label(c.field) if positive else f"Not {label(c.field).lower()}"
    if c.op == "eq":
        return f"{label(c.field)}: {value(c.field, c.value)}"
    return f"{label(c.field)} {OP_WORD[c.op]}{value(c.field, c.value)}"


def compact_sizes(sizes: list) -> str:
    return f"{sizes[0]}–{sizes[-1]}" if len(sizes) > 2 else ", ".join(map(str, sizes))


KEY_ATTRS = ["colour", "material", "upper_material", "capacity_l", "capacity_ml", "volume_ml", "capacity_mah",
             "wattage_w", "output_w", "thickness_mm", "pack_of", "pieces", "sizes", "gender", "spf"]


def key_attributes(attrs: dict, limit: int = 4) -> list[str]:
    out = []
    for k in KEY_ATTRS:
        if k in attrs and len(out) < limit:
            v = attrs[k]
            out.append(compact_sizes(v) if k == "sizes" else value(k, v) if k != "gender" else str(v).capitalize())
    return out

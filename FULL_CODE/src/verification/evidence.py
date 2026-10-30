"""Evidence Ledger: deterministic, attribute-level verification of shopper conditions against catalogue records.

Every condition gets one of three states, with the catalogue field it came from:
  VERIFIED      the record explicitly satisfies it
  CONTRADICTED  the record explicitly conflicts with it
  UNKNOWN       the record does not contain the field (missing != false)
Matching follows the README: colours/materials match exactly ("blue" != "navy", "cotton" != "cotton blend"),
list attributes such as `sizes` match by membership. One policy-defined exception: a missing `warranty_months`
means "no brand warranty" (policy 3.1), so it is treated as 0 months, not unknown.
No LLM is involved here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.conversation.query_interpreter import Constraint

OP_TEXT = {"eq": "=", "ne": "≠", "lte": "≤", "gte": "≥"}


class Status(str, Enum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


@dataclass
class Evidence:
    field: str
    status: Status
    condition: str | None  # human-readable condition, e.g. "price_inr ≤ 600"; None for a plain lookup
    actual: Any            # catalogue value (None if the record doesn't have the field)
    source: str            # where `actual` came from: "price_inr", "attributes.colour", "policy 3.1", or "not in record"
    hard: bool = True


def field_value(product: dict, name: str) -> tuple[bool, Any, str]:
    """(found, value, source) for a catalogue column, derived field or attribute key."""
    if name == "discount_inr":
        return True, product["mrp_inr"] - product["price_inr"], "mrp_inr - price_inr"
    if name in product and name != "attributes":
        v = product[name]
        if v is None or (isinstance(v, float) and v != v):  # rating is null/NaN when there are no reviews
            return False, None, "not in record"
        return True, v, name
    attrs = product["attributes"]
    if name in attrs:
        return True, attrs[name], f"attributes.{name}"
    if name == "warranty_months":
        return True, 0, "policy 3.1 (no warranty listed = no brand warranty)"
    return False, None, "not in record"


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return True if s in {"true", "yes"} else False if s in {"false", "no"} else None


def _equal(actual: Any, want: Any) -> bool:
    if isinstance(actual, list):
        return any(_equal(a, want) for a in actual)
    if isinstance(actual, bool) or isinstance(want, bool):
        a, w = _bool(actual), _bool(want)
        return a is not None and a == w
    a, w = _num(actual), _num(want)
    if a is not None and w is not None:
        return abs(a - w) < 1e-9
    return str(actual).strip().lower() == str(want).strip().lower()


def check(product: dict, c: Constraint) -> Evidence:
    cond = f"{c.field} {OP_TEXT[c.op]} {c.value}"
    found, actual, source = field_value(product, c.field)
    if not found:
        return Evidence(c.field, Status.UNKNOWN, cond, None, source, c.hard)
    if c.op in ("eq", "ne"):
        ok = _equal(actual, c.value) if c.op == "eq" else not _equal(actual, c.value)
    else:
        a, w = _num(actual), _num(c.value)
        if a is None or w is None:  # can't compare numerically (e.g. a text field): don't guess
            return Evidence(c.field, Status.UNKNOWN, cond, actual, source, c.hard)
        ok = a <= w if c.op == "lte" else a >= w
    return Evidence(c.field, Status.VERIFIED if ok else Status.CONTRADICTED, cond, actual, source, c.hard)


def lookup(product: dict, name: str) -> Evidence:
    """A field the shopper asked about: its value if the record has it, otherwise UNKNOWN."""
    found, actual, source = field_value(product, name)
    return Evidence(name, Status.VERIFIED if found else Status.UNKNOWN, None, actual, source)


@dataclass
class ProductLedger:
    product_id: str
    conditions: list[Evidence] = field(default_factory=list)
    asked: list[Evidence] = field(default_factory=list)

    @property
    def group(self) -> int:
        """0 = every hard condition verified, 1 = none contradicted but some unknown, 2 = something contradicted."""
        hard = [e for e in self.conditions if e.hard]
        if any(e.status is Status.CONTRADICTED for e in hard):
            return 2
        if any(e.status is Status.UNKNOWN for e in hard):
            return 1
        return 0


def build_ledger(product: dict, conditions: list[Constraint], asked_fields: list[str]) -> ProductLedger:
    return ProductLedger(product["product_id"], [check(product, c) for c in conditions],
                         [lookup(product, f) for f in asked_fields])

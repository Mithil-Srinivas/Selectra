"""Last check before a prediction is written: no price may be hallucinated.

Mirrors the rules of the official evaluate.py (README §8.2): a stated price must match `price_inr` of a cited
product, and every rupee amount in answer_text must be the price, MRP or discount of a cited product, a ₹ amount
from the policy when a section is cited, or a budget number the shopper typed in this conversation.
The regular expressions are copied from evaluate.py so both sides detect the same amounts.
"""
from __future__ import annotations

import re
import unicodedata

CURRENCY_RE = re.compile(
    r"(?:₹|₨|\brs|\binr|\brup(?:ee|ees|aye|aiye|aiya|eya|iya|ye|yon)\b)[\s.:\-]*([0-9][0-9,]*(?:\.[0-9]+)?)(k(?![a-z]))?"
    r"|([0-9][0-9,]*(?:\.[0-9]+)?)(k(?![a-z]))?\s*(?:/-|rs\b\.?|inr\b|rup[aei]\w*)",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)(k(?![a-z]))?(\s*(?:w|watt|mm|cm|inch|in|l|ltr|litre|liter|ml|kg|g|mah|"
                       r"pcs|pieces?|gb|ton|saal|years?|y|spf|x|tc)\b)?", re.IGNORECASE)
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
TOLERANCE = 0.5


def _num(s: str, k: str | None) -> float:
    v = float(s.replace(",", ""))
    return v * 1000 if k else v


def text_amounts(text: str) -> list[float]:
    norm = unicodedata.normalize("NFKC", text or "").translate(DEVANAGARI_DIGITS)
    out = []
    for m in CURRENCY_RE.finditer(norm):
        if m.group(1):
            out.append(_num(m.group(1), m.group(2)))
        elif m.group(3):
            out.append(_num(m.group(3), m.group(4)))
    return out


def typed_budgets(texts: list[str]) -> set[float]:
    nums: set[float] = set()
    for t in texts:
        for m in NUMBER_RE.finditer(unicodedata.normalize("NFKC", t).translate(DEVANAGARI_DIGITS)):
            if m.group(3):  # a measurement such as 65W or 3 litre, not a budget
                continue
            try:
                nums.update({_num(m.group(1), m.group(2)), _num(m.group(1), None)})
            except ValueError:
                pass
    return nums


def price_problems(pred: dict, records: dict, policy_amounts: set[float], conversation: list[str]) -> list[str]:
    """Empty list = safe to write."""
    problems = []
    cited = set(pred["cited_product_ids"])
    for sp in pred["stated_prices"]:
        pid = sp["product_id"]
        if pid not in records or pid not in cited or abs(sp["price_inr"] - records[pid]["price_inr"]) > TOLERANCE:
            problems.append(f"stated price {sp} not backed by a cited catalogue record")
    allowed = typed_budgets(conversation)
    if pred["cited_policy_sections"]:
        allowed |= policy_amounts
    for pid in cited & set(records):
        r = records[pid]
        allowed |= {r["price_inr"], r["mrp_inr"], r["mrp_inr"] - r["price_inr"]}
    for a in text_amounts(pred["answer_text"]):
        if not any(abs(a - x) <= TOLERANCE for x in allowed):
            problems.append(f"₹{a:g} in answer_text is not a cited product's price/MRP/discount")
    return problems

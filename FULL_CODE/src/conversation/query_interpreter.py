"""LLM-first query understanding: shopper text -> validated, structured search plan.

The LLM sees the store's sub-categories and catalogue field names, plus spell-checker name hints, and returns a
`QueryInterpretation`. Ollama constrains `sub_categories` and every field name to the real catalogue vocabulary
(enums in the JSON schema), and Pydantic re-checks the same rules, so the plan can only reference things that exist.
What the LLM may NOT do: invent prices, budgets or attributes, or pick a "closest" sub-category for a product
the store doesn't sell (sub_categories must then be []). Numeric constraint values are additionally checked in code
against the numbers the shopper actually typed; ungrounded ones are dropped and reported.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ValidationInfo, field_validator
from rapidfuzz import fuzz, process

from src.models.llm import LLM, LLMUsage
from src.preprocessing.products import CatalogueVocab
from src.retrieval.name_matcher import NameHint, NameMatcher

log = logging.getLogger(__name__)

Operation = Literal["lookup", "browse", "cheapest", "most_expensive", "compare", "policy", "other"]


def _vocab(info: ValidationInfo) -> CatalogueVocab | None:
    return (info.context or {}).get("vocab")


class Constraint(BaseModel):
    field: str
    op: Literal["eq", "ne", "lte", "gte"]
    value: bool | int | float | str
    hard: bool  # False for soft preferences ("preferably blue", "ho sake to")

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str, info: ValidationInfo) -> str:
        if (vocab := _vocab(info)) and v not in vocab.fields:
            raise ValueError(f"unknown catalogue field {v!r}")
        return v


class QueryInterpretation(BaseModel):
    # Field order matters: the model writes structured fields first and the search phrase last.
    operation: Operation
    product_type: str | None
    sub_categories: list[str]  # every store sub-category that could hold the product; [] = store doesn't sell it
    brand: str | None
    product_line: str | None
    constraints: list[Constraint]
    asked_fields: list[str]
    unmapped_asks: list[str]
    compare_targets: list[str]
    policy_topic: str | None
    search_query: str

    @field_validator("sub_categories")
    @classmethod
    def _known_sub_categories(cls, v: list[str], info: ValidationInfo) -> list[str]:
        if (vocab := _vocab(info)) and (bad := [s for s in v if s not in vocab.all_sub_categories]):
            raise ValueError(f"unknown sub_categories {bad}")
        return list(dict.fromkeys(v))

    @field_validator("asked_fields")
    @classmethod
    def _known_asked_fields(cls, v: list[str], info: ValidationInfo) -> list[str]:
        if (vocab := _vocab(info)) and (bad := [f for f in v if f not in vocab.fields]):
            raise ValueError(f"unknown catalogue fields {bad}")
        return v


SYSTEM_TEMPLATE = """You are the query-understanding step of a shopping assistant for an Indian online store.
Shoppers write short, informal, misspelt, often Hinglish messages. Convert the message into a JSON search plan.
You do NOT answer the shopper and you do NOT know prices or stock; later steps look those up.
If earlier messages of the conversation are given, the new message may be a follow-up ("lavender wali",
"2000 ke andar wale?", "TPE wali"). Then return the complete plan for what the shopper wants now: carry over the
product type, sub-categories, brand, product line, constraints and asked fields from earlier messages unless the new
message changes or replaces them.

Fields:
- operation: lookup (asks about one specific product), browse (wants options / a list), cheapest, most_expensive,
  compare (two or more named products), policy (returns, delivery, warranty, payment, cancellation, GST, coupons...),
  other (anything else). "cheapest"/"sabse sasta" and "most expensive"/"sabse mehenga" are operations, NOT price
  constraints.
- product_type: the physical product in plain English (e.g. "hair dryer"), even if the shopper only described it.
  Only fill it if the message (or an earlier message in the conversation) names or describes the product. If it
  gives only brand/line names, or only a constraint ("cotton wala 800 ke andar") with no earlier message naming the
  product, set product_type to null and sub_categories to []. Never guess the product from a brand, line name or
  material. null for policy/other.
- sub_categories: every store sub-category (from the list below) whose products are this kind of item. A specific
  product has one ("air fryer" -> ["Air Fryers"]); a broad word has several ("shoes" -> all shoe sub-categories,
  "bag" -> all bag sub-categories). Everyday names and descriptions count: a "steam press" is an Iron, "joote" are
  shoes, "tiffin" is a Lunch Box. Use [] if the store does not sell that kind of product. Never add a merely related
  sub-category: a phone cover is not a Mobile Stand, a printer cartridge is not a Pen. Wireless Earbuds and Wired
  Earphones are different.
- brand / product_line: the names the shopper used. If a spell-checker hint clearly matches what they wrote, use
  the hint's catalogue spelling; otherwise copy the name as written (it may be a brand the store doesn't carry).
- constraints: every condition the shopper stated, using catalogue field names. Each colour, material, size,
  capacity, gender or feature word in the message becomes a constraint, also when implied by a description
  ("keeps water cold" -> insulated true, "blocks light" -> blackout true). Only conditions the shopper actually
  stated. Values lowercase, in
  catalogue style ("stainless steel", "black", "king"). Budgets: "2k", "2000 ke andar", "under 2000" ->
  price_inr lte 2000. "in stock" / "stock me ho" -> stock_status ne out_of_stock. hard=false only for soft
  wording ("preferably", "ho sake to"). Never invent a budget, colour, size or any other value: every number in a
  constraint must be a number the shopper typed.
- asked_fields: the catalogue fields whose VALUE the shopper wants to know. kitne ka / price / rate -> price_inr;
  stock / available / milega -> stock_status; discount -> discount_inr; "paani me chalega" -> water_resistant and
  water_resistance_rating; "kitni moti" -> thickness_mm; and so on.
- unmapped_asks: things the shopper asks that no catalogue field covers, as short English phrases.
- compare_targets: for compare, one phrase per product with everything the shopper said about it (brand, line,
  colour, size). brand/product_line then hold the first product's names.
- policy_topic: for policy, a short English phrase for the topic.
- search_query: an English, catalogue-style search phrase: brand, product line, product type and stated attributes.
  No filler words, no prices.

Store sub-categories (category: sub-categories):
{sub_categories}

Catalogue field names:
{fields}

Examples:
{examples}"""

EXAMPLES = [
    ("sonique zen go earbuds black kitne ka aur stock me hai?", "Sonique [brand], ZenGo [line]",
     {"operation": "lookup", "product_type": "wireless earbuds", "sub_categories": ["Wireless Earbuds"],
      "brand": "Sonique", "product_line": "ZenGo",
      "constraints": [{"field": "colour", "op": "eq", "value": "black", "hard": True}],
      "asked_fields": ["price_inr", "stock_status"], "unmapped_asks": [], "compare_targets": [], "policy_topic": None,
      "search_query": "Sonique ZenGo wireless earbuds black"}),
    ("baal sukhane wali machine 1500 ke andar dikhao", "(none)",
     {"operation": "browse", "product_type": "hair dryer", "sub_categories": ["Hair Dryers"], "brand": None,
      "product_line": None, "constraints": [{"field": "price_inr", "op": "lte", "value": 1500, "hard": True}],
      "asked_fields": [], "unmapped_asks": [], "compare_targets": [], "policy_topic": None,
      "search_query": "hair dryer"}),
    ("iphone 15 ka back cover", "(none)",
     {"operation": "browse", "product_type": "phone back cover", "sub_categories": [], "brand": "iPhone",
      "product_line": None, "constraints": [], "asked_fields": [], "unmapped_asks": [], "compare_targets": [],
      "policy_topic": None, "search_query": "iPhone 15 phone back cover"}),
    ("sabse sasta joota men ke liye", "(none)",
     {"operation": "cheapest", "product_type": "shoes",
      "sub_categories": ["Formal Shoes", "Running Shoes", "Sneakers", "Walking Shoes"], "brand": None,
      "product_line": None, "constraints": [{"field": "gender", "op": "eq", "value": "men", "hard": True}],
      "asked_fields": ["price_inr"], "unmapped_asks": [], "compare_targets": [], "policy_topic": None,
      "search_query": "men's shoes"}),
    ("sabse sasta 1.5 litre steel kettle jo stock me ho", "(none)",
     {"operation": "cheapest", "product_type": "electric kettle", "sub_categories": ["Electric Kettles"], "brand": None,
      "product_line": None, "constraints": [
          {"field": "capacity_l", "op": "eq", "value": 1.5, "hard": True},
          {"field": "material", "op": "eq", "value": "stainless steel", "hard": True},
          {"field": "stock_status", "op": "ne", "value": "out_of_stock", "hard": True}],
      "asked_fields": ["price_inr"], "unmapped_asks": [], "compare_targets": [], "policy_topic": None,
      "search_query": "stainless steel electric kettle 1.5 litre"}),
    ("chargit boom speaker barish me chalega? made in india hai?", "Chargit [brand]",
     {"operation": "lookup", "product_type": "bluetooth speaker", "sub_categories": ["Bluetooth Speakers"],
      "brand": "Chargit", "product_line": "Boom", "constraints": [],
      "asked_fields": ["water_resistant", "water_resistance_rating"], "unmapped_asks": ["country of manufacture"],
      "compare_targets": [], "policy_topic": None, "search_query": "Chargit Boom bluetooth speaker"}),
    ("runvex glide one red ya kadambh breeze fusion red kaunsa sasta",
     "Runvex [brand], GlideOne [line], Kadambh [brand], BreezeFusion [line]",
     {"operation": "compare", "product_type": None, "sub_categories": [], "brand": "Runvex", "product_line": "GlideOne",
      "constraints": [], "asked_fields": ["price_inr"], "unmapped_asks": [],
      "compare_targets": ["Runvex GlideOne red", "Kadambh BreezeFusion red"], "policy_topic": None,
      "search_query": "Runvex GlideOne red, Kadambh BreezeFusion red"}),
    ("cotton wala 800 ke andar", "(none)",
     {"operation": "browse", "product_type": None, "sub_categories": [], "brand": None, "product_line": None,
      "constraints": [{"field": "material", "op": "eq", "value": "cotton", "hard": True},
                      {"field": "price_inr", "op": "lte", "value": 800, "hard": True}],
      "asked_fields": [], "unmapped_asks": [], "compare_targets": [], "policy_topic": None,
      "search_query": "cotton"}),
    ("COD pe extra paisa lagta hai kya", "(none)",
     {"operation": "policy", "product_type": None, "sub_categories": [], "brand": None, "product_line": None,
      "constraints": [], "asked_fields": [], "unmapped_asks": [], "compare_targets": [],
      "policy_topic": "cash on delivery fee", "search_query": "cash on delivery extra fee"}),
]


def _user_message(text: str, hints: list[NameHint], history: list[str] | None = None) -> str:
    h = ", ".join(f"{x.canonical} [{x.kind}]" for x in hints) or "(none)"
    earlier = ("Earlier messages in this conversation (oldest first):\n" + "\n".join(f"- {t}" for t in history)
               + "\n") if history else ""
    return f"{earlier}Shopper message: {text}\nSpell-checker name hints (may be wrong): {h}"


def _restrict(node: dict, values: list[str]) -> None:
    """Add an enum to the string branch of a (possibly nullable) JSON-schema node."""
    for branch in node.get("anyOf", [node]):
        if branch.get("type") == "string":
            branch["enum"] = values


def numbers_in(text: str) -> set[float]:
    """Numbers the shopper typed. "2k"/"1.5k" also count as 2000/1500; "2,000" as 2000."""
    nums: set[float] = set()
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text.lower()):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        nums.add(v * 1000 if m.group(2) else v)
    return nums


def drop_ungrounded_numbers(plan: QueryInterpretation, text: str) -> list[Constraint]:
    """Remove constraints whose numeric value the shopper never typed (e.g. "cheapest" -> price_inr lte 0)."""
    typed = numbers_in(text)
    keep, dropped = [], []
    for c in plan.constraints:
        numeric = isinstance(c.value, (int, float)) and not isinstance(c.value, bool)
        (dropped if numeric and float(c.value) not in typed else keep).append(c)
    if dropped:
        log.warning("dropped ungrounded numeric constraints %s for %r", dropped, text)
        plan.constraints = keep
    return dropped


def add_missed_colours(plan: QueryInterpretation, text: str, colours: set[str]) -> list[Constraint]:
    """Backstop for an observed LLM miss ("red silk saree" -> no constraints): a catalogue colour typed as a whole
    word becomes a colour constraint if the LLM gave none. Not applied to compare questions (several colours)."""
    if plan.operation == "compare" or any(c.field == "colour" for c in plan.constraints):
        return []
    words = set(re.findall(r"[a-z]+", text.lower()))
    found = sorted(c for c in colours if c in words)
    added = [Constraint(field="colour", op="eq", value=found[0], hard=True)] if len(found) == 1 else []
    plan.constraints += added
    return added


def canonicalise_names(plan: QueryInterpretation, vocab: CatalogueVocab) -> None:
    """Map a near-miss brand / line name ("Kridaa " / "Ripple Flex") to its catalogue spelling, so a misspelling is
    never mistaken for a brand we don't carry. Names with no close catalogue match are left as written."""
    for attr, names in (("brand", vocab.brands), ("product_line", vocab.line_names)):
        value = getattr(plan, attr)
        if not value or value in names:
            continue
        key = re.sub(r"\s+", "", value).lower()
        m = process.extractOne(key, {n: n.lower() for n in names}, scorer=fuzz.ratio, score_cutoff=88)
        if m:
            setattr(plan, attr, m[2])


@dataclass
class Interpretation:
    plan: QueryInterpretation
    hints: list[NameHint]
    usage: LLMUsage
    dropped_constraints: list[Constraint] = field(default_factory=list)
    added_constraints: list[Constraint] = field(default_factory=list)
    raw_plan: dict = field(default_factory=dict)  # exactly what the LLM returned, before the code checks


class QueryInterpreter:
    def __init__(self, llm: LLM, vocab: CatalogueVocab, matcher: NameMatcher):
        self.llm, self.vocab, self.matcher = llm, vocab, matcher
        subs = "\n".join(f"- {c}: {', '.join(s)}" for c, s in vocab.sub_categories.items())
        examples = "\n".join(f"Shopper message: {q}\nSpell-checker name hints (may be wrong): {h}\n{json.dumps(o)}"
                             for q, h, o in EXAMPLES)
        self.system = SYSTEM_TEMPLATE.format(sub_categories=subs, fields=", ".join(vocab.fields), examples=examples)
        schema = QueryInterpretation.model_json_schema()
        _restrict(schema["properties"]["sub_categories"]["items"], vocab.all_sub_categories)
        _restrict(schema["properties"]["asked_fields"]["items"], vocab.fields)
        _restrict(schema["$defs"]["Constraint"]["properties"]["field"], vocab.fields)
        self.json_schema = schema

    def interpret(self, text: str, history: list[str] | None = None) -> Interpretation:
        """`history`: earlier shopper messages of the same conversation, oldest first."""
        history = history or []
        conversation = " ".join(history + [text])
        hints = self.matcher.find(conversation)
        plan, usage = self.llm.chat_json(self.system, _user_message(text, hints, history), QueryInterpretation,
                                         json_schema=self.json_schema, context={"vocab": self.vocab})
        raw = plan.model_dump()
        dropped = drop_ungrounded_numbers(plan, conversation)  # a budget typed in an earlier turn still counts
        added = add_missed_colours(plan, text, self.vocab.text_values.get("colour", set()))
        canonicalise_names(plan, self.vocab)
        return Interpretation(plan, hints, usage, dropped, added, raw)

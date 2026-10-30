"""Turn a search outcome into a submission line: action, answer text, citations, stated prices and facts.

Every decision here is a rule (README §6), and every value written comes from a catalogue record or the policy text:
  refuse   nothing we sell matches, a brand we don't carry, or the catalogue/policy doesn't hold the answer
  clarify  the shopper asks about ONE product, 2+ products match, and they differ in what was asked
  answer   otherwise: lookups, options, cheapest / most expensive, comparisons, policy
answer_text is written from templates by code (no LLM), then checked by guard.price_problems before it is returned.
"""
from __future__ import annotations

import logging
import re

from src.answering.guard import price_problems, text_amounts
from src.models.llm import LLMUsage
from src.policy import PolicyAnswerer, PolicySection
from src.search_service import ProductHit, SearchOutcome, SearchService
from src.verification.evidence import field_value

log = logging.getLogger(__name__)

STOCK_TEXT = {"in_stock": "in stock", "low_stock": "low stock (only a few left)", "out_of_stock": "out of stock"}
NOT_SOLD = "Sorry, I couldn't find that in our catalogue. We don't have a matching product."
NO_MATCH = "Sorry, no product in our catalogue matches all of that."
POLICY_GAP = "Our store policy doesn't cover this, so I can't answer it. Please check with customer support."
MAX_LIST = 10      # evaluate.py gives no product credit above 10 citations
BROWSE_SHOW = 5
CHEAPER = re.compile(r"sast|cheap|kam\b|kam price|lowest|less", re.I)
PRICIER = re.compile(r"mehe?n?g|expensive|costl|highest|zyada", re.I)


def rupees(v) -> str:
    return f"₹{int(v):,}"


def _label(field: str) -> str:
    return field.replace("_inr", "").replace("_", " ")


def _show(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def empty(action: str, text: str) -> dict:
    return {"action": action, "answer_text": text, "cited_product_ids": [], "cited_policy_sections": [],
            "stated_prices": [], "stated_facts": []}


class Responder:
    def __init__(self, service: SearchService, policy: PolicyAnswerer):
        self.service, self.policy = service, policy
        self.records = service.records
        self.policy_amounts = {a for s in policy.sections.values() for a in text_amounts(s.text)}

    # ------------------------------------------------------------------ entry point
    def respond(self, text: str, history: list[str]) -> tuple[dict, list[LLMUsage]]:
        out = self.service.search(text, history)
        usages = [out.result.interpretation.usage]
        pred = self._decide(text, history, out, usages)
        problems = price_problems(pred, self.records, self.policy_amounts, history + [text])
        if problems:  # cannot happen with catalogue-built text; if it ever does, drop the prose, keep the facts
            log.error("price guard rejected %r: %s", text, problems)
            pred["answer_text"] = "Please see the cited products: " + ", ".join(pred["cited_product_ids"]) + "."
        return pred, usages

    # ------------------------------------------------------------------ decision
    def _decide(self, text: str, history: list[str], out: SearchOutcome, usages: list[LLMUsage]) -> dict:
        plan = out.result.interpretation.plan
        if plan.operation == "policy" or out.state == "policy":
            return self._policy(text, history, usages)
        if out.state in ("other", "not_sold"):
            return empty("refuse", NOT_SOLD)
        vocab = self.service.vocab
        if plan.brand and plan.brand not in vocab.brands and plan.brand not in vocab.line_names:
            return empty("refuse", f"Sorry, we don't carry {plan.brand} products.")
        matches = [h for h in out.hits if h.ledger.group == 0] or [h for h in out.hits if h.ledger.group == 1]
        if out.state == "no_match" or not matches:
            return empty("refuse", NO_MATCH)

        op = plan.operation
        if op == "browse" and plan.asked_fields:  # "green running shoes kitne ke hai" asks a value of "the" product
            op = "lookup"
        if op == "compare":
            return self._compare(text, plan.compare_targets, plan.asked_fields, usages) or \
                self._lookup(matches, plan.asked_fields, plan.unmapped_asks)
        if op in ("cheapest", "most_expensive"):
            return self._superlative(matches, op)
        if op == "browse":
            return self._browse(matches)
        constrained = {c.field for c in plan.constraints}
        return self._lookup(matches, self._resolve_asked(text, matches, plan.asked_fields, constrained),
                            plan.unmapped_asks, text)

    @staticmethod
    def _resolve_asked(text: str, matches: list[ProductHit], asked: list[str], constrained: set[str]) -> list[str]:
        """If an asked field is missing from the record but a word the shopper typed is exactly the value of another
        attribute ("bluetooth hai?" -> connectivity: bluetooth), ask that attribute instead. Exact value match only,
        so "water resistant hai?" still finds nothing and is refused."""
        words = set(re.findall(r"[a-z]{4,}", text.lower()))
        attrs = matches[0].record["attributes"]
        out = []
        for f in asked:
            if f in ("price_inr", "stock_status", "warranty_months") or field_value(matches[0].record, f)[0]:
                out.append(f)
                continue
            alt = [k for k, v in attrs.items() if k not in constrained and isinstance(v, str) and v.lower() in words]
            out.append(alt[0] if alt else f)
        return list(dict.fromkeys(out))

    @staticmethod
    def _narrow_by_title_numbers(text: str, records: list[dict]) -> list[dict]:
        """Variants usually differ by a number in the title ("100 Pieces" vs "500 Pieces", "Pack of 10" vs "of 5").
        Keep the candidates whose title contains a number the shopper typed, if that singles out a strict subset."""
        for n in re.findall(r"\d+(?:\.\d+)?", text):
            subset = [r for r in records if re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.])", r["title"])]
            if 0 < len(subset) < len(records):
                records = subset
        return records

    # ------------------------------------------------------------------ actions
    def _lookup(self, matches: list[ProductHit], asked: list[str], unmapped: list[str], text: str = "") -> dict:
        records = self._narrow_by_title_numbers(text, [h.record for h in matches])
        if unmapped:
            pred = empty("refuse", "The catalogue doesn't say " + ", ".join(unmapped) +
                         (f" for {records[0]['title']} [{records[0]['product_id']}]" if len(records) == 1 else "") +
                         ", so I can't confirm it.")
            if len(records) == 1:
                pred["cited_product_ids"] = [records[0]["product_id"]]
            return pred
        fields = asked or ["price_inr"]
        if len(records) > 1:
            values = {f: {repr(field_value(r, f)[1]) for r in records} for f in fields}
            if all(not field_value(r, f)[0] for r in records for f in fields if f != "warranty_months"):
                return empty("refuse", f"The catalogue doesn't list {', '.join(map(_label, fields))} for these "
                                       "products, so I can't confirm it.")
            if any(len(v) > 1 for v in values.values()):
                return self._clarify(records[:MAX_LIST])
            return self._describe(records[:MAX_LIST], asked)  # every match gives the same answer
        return self._describe(records, asked)

    def _describe(self, records: list[dict], asked: list[str]) -> dict:
        r0 = records[0]
        extra = [f for f in asked if f not in ("price_inr", "stock_status")]
        missing = [f for f in extra if not field_value(r0, f)[0]]
        if missing:
            pred = empty("refuse", f"The catalogue entry for {r0['title']} [{r0['product_id']}] does not say "
                                   f"{', '.join(map(_label, missing))}, so I can't confirm it.")
            pred["cited_product_ids"] = [r0["product_id"]]
            return pred
        pred = empty("answer", "")
        sentences = []
        for r in records:
            pid = r["product_id"]
            pred["cited_product_ids"].append(pid)
            pred["stated_prices"].append({"product_id": pid, "price_inr": r["price_inr"]})
            pred["stated_facts"].append({"product_id": pid, "field": "stock_status", "value": r["stock_status"]})
            parts = [f"{r['title']} [{pid}] is {rupees(r['price_inr'])} and {STOCK_TEXT[r['stock_status']]}"]
            for f in extra:
                found, value, source = field_value(r, f)
                if source.startswith("policy"):  # warranty_months absent: policy 3.1 says no brand warranty
                    parts.append("it has no brand warranty listed, so no brand warranty applies (policy 3.1)")
                    if "3.1" not in pred["cited_policy_sections"]:
                        pred["cited_policy_sections"].append("3.1")
                    continue
                if f == "discount_inr":
                    parts.append(f"discount {rupees(value)} on an MRP of {rupees(r['mrp_inr'])}")
                elif f == "mrp_inr":
                    parts.append(f"MRP {rupees(value)}")
                else:
                    parts.append(f"{_label(f)}: {_show(value)}")
                pred["stated_facts"].append({"product_id": pid, "field": f, "value": value})
            sentences.append("; ".join(parts) + ".")
        lead = "" if len(records) == 1 else f"All {len(records)} matching products give the same answer. "
        pred["answer_text"] = lead + " ".join(sentences)
        return pred

    def _clarify(self, records: list[dict]) -> dict:
        pred = empty("clarify", "")
        items = []
        for r in records:
            pid = r["product_id"]
            pred["cited_product_ids"].append(pid)
            pred["stated_prices"].append({"product_id": pid, "price_inr": r["price_inr"]})
            items.append(f"{r['title']} [{pid}] {rupees(r['price_inr'])} ({STOCK_TEXT[r['stock_status']]})")
        pred["answer_text"] = f"{len(records)} products match: " + "; ".join(items) + ". Which one do you mean?"
        return pred

    def _browse(self, matches: list[ProductHit]) -> dict:
        shown = [h.record for h in matches[:BROWSE_SHOW]]
        pred = empty("answer", "")
        items = []
        for r in shown:
            pid = r["product_id"]
            pred["cited_product_ids"].append(pid)
            pred["stated_prices"].append({"product_id": pid, "price_inr": r["price_inr"]})
            items.append(f"{r['title']} [{pid}] {rupees(r['price_inr'])} ({STOCK_TEXT[r['stock_status']]})")
        pred["answer_text"] = (f"{len(matches)} matching products. Some options: " + "; ".join(items) + ".")
        return pred

    def _superlative(self, matches: list[ProductHit], op: str) -> dict:
        best = matches[0].record  # SearchService already ordered matches by price for these operations
        tied = [h.record for h in matches if h.record["price_inr"] == best["price_inr"]][:3]
        word = "cheapest" if op == "cheapest" else "most expensive"
        pred = empty("answer", "")
        for r in tied:
            pid = r["product_id"]
            pred["cited_product_ids"].append(pid)
            pred["stated_prices"].append({"product_id": pid, "price_inr": r["price_inr"]})
            pred["stated_facts"].append({"product_id": pid, "field": "stock_status", "value": r["stock_status"]})
        names = " and ".join(f"{r['title']} [{r['product_id']}]" for r in tied)
        pred["answer_text"] = (f"The {word} of {len(matches)} matching products is {names} at "
                               f"{rupees(best['price_inr'])} ({STOCK_TEXT[best['stock_status']]}).")
        return pred

    def _compare(self, text: str, targets: list[str], asked: list[str], usages: list[LLMUsage]) -> dict | None:
        """Look each named product up separately, then state each one's facts and which is cheaper / pricier."""
        if len(targets) < 2:
            return None
        picked: list[dict] = []
        for t in targets[:4]:
            sub = self.service.search(t)
            usages.append(sub.result.interpretation.usage)
            hits = [h for h in sub.hits if h.ledger.group == 0] or sub.hits
            if hits and hits[0].record["product_id"] not in {r["product_id"] for r in picked}:
                picked.append(hits[0].record)
        if len(picked) < 2:
            return None
        pred = self._describe(picked, [f for f in asked if f != "price_inr"])
        if pred["action"] != "answer":
            return pred
        pred["answer_text"] = pred["answer_text"].replace(f"All {len(picked)} matching products give the same answer. ", "")
        if CHEAPER.search(text) or PRICIER.search(text):
            pick = (min if CHEAPER.search(text) else max)(picked, key=lambda r: r["price_inr"])
            pred["answer_text"] += f" {'Cheaper' if CHEAPER.search(text) else 'More expensive'}: {pick['title']} [{pick['product_id']}]."
        return pred

    def _policy(self, text: str, history: list[str], usages: list[LLMUsage]) -> dict:
        sections, usage = self.policy.choose(text, history)
        usages.append(usage)
        if not sections:
            return empty("refuse", POLICY_GAP)
        pred = empty("answer", " ".join(f"Per policy section {s.id} ({s.title}): {s.text}" for s in sections))
        pred["cited_policy_sections"] = [s.id for s in sections]
        return pred

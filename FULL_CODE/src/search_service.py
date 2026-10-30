"""Search service used by the demo UI: interpret -> retrieve -> verify every candidate -> order.

Ordering: products whose hard conditions are all VERIFIED first, then ones with UNKNOWN conditions, then
CONTRADICTED ones (shown only when nothing better exists, clearly marked). Within a group: price for
cheapest / most_expensive, otherwise retrieval relevance.
Out-of-catalogue handling is deterministic: no store sub-category and no catalogue brand/line -> "not sold".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from src.config import ARTIFACT_DIR
from src.conversation.query_interpreter import Constraint, QueryInterpreter
from src.models.embedder import Embedder
from src.models.llm import LLM
from src.preprocessing.products import CatalogueVocab, load_catalogue, product_text
from src.retrieval.dense import DenseIndex
from src.retrieval.name_matcher import NameMatcher
from src.retrieval.product_search import Candidate, ProductSearcher, SearchResult
from src.verification.evidence import ProductLedger, build_ledger

PRODUCT_OPS = {"lookup", "browse", "cheapest", "most_expensive", "compare"}
POOL_UNRESTRICTED = 100  # candidates verified when the search could not be narrowed to sub-categories


@dataclass
class ProductHit:
    record: dict
    ledger: ProductLedger
    candidate: Candidate


@dataclass
class SearchOutcome:
    query: str
    result: SearchResult
    state: Literal["results", "no_match", "not_sold", "policy", "other"]
    hits: list[ProductHit]          # what the shopper sees, in display order
    counts: dict[str, int]          # match / unknown / contradicted
    conditions: list[Constraint]    # hard + soft conditions actually checked (incl. brand / line)
    notices: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    pool: list[ProductHit] = field(default_factory=list)  # every verified candidate, incl. contradicted (debug)


class SearchService:
    def __init__(self) -> None:
        self.catalogue = load_catalogue()
        self.vocab = CatalogueVocab(self.catalogue)
        embedder = Embedder()
        index = DenseIndex.load_or_build(self.catalogue.product_id.tolist(),
                                         [product_text(r) for _, r in self.catalogue.iterrows()],
                                         embedder, ARTIFACT_DIR / "dense_products")
        interpreter = QueryInterpreter(LLM(), self.vocab, NameMatcher(self.vocab.brands, self.vocab.line_names))
        self.searcher = ProductSearcher(self.catalogue, self.vocab, index, embedder, interpreter)
        self.records = {r["product_id"]: r for r in self.catalogue.to_dict("records")}

    def search(self, text: str, history: list[str] | None = None) -> SearchOutcome:
        res = self.searcher.search(text, k=len(self.records), history=history)
        t0 = time.perf_counter()
        plan = res.interpretation.plan
        notices: list[str] = []

        if plan.operation == "policy":
            return self._outcome(text, res, "policy", [], [], notices, t0)
        if plan.operation not in PRODUCT_OPS:
            return self._outcome(text, res, "other", [], [], notices, t0)

        brand_known = plan.brand in self.vocab.brands
        line_known = plan.product_line in self.vocab.line_names
        if not plan.sub_categories and not brand_known and not line_known:
            return self._outcome(text, res, "not_sold", [], [], notices, t0)

        conditions = []
        for c in plan.constraints:
            if examples := self._unsupported_value(c):
                notices.append(f"Couldn't apply “{c.field} = {c.value}”: the catalogue records {c.field} as values "
                               f"like {examples}.")
            else:
                conditions.append(c)
        if plan.brand and not brand_known:
            notices.append(f"We don't carry {plan.brand}. Showing other {plan.product_type or 'products'} instead.")
        elif brand_known:
            conditions.insert(0, Constraint(field="brand", op="eq", value=plan.brand, hard=True))
        if line_known and plan.operation != "compare":
            conditions.insert(1 if brand_known else 0,
                              Constraint(field="line_name", op="eq", value=plan.product_line, hard=True))

        pool = res.candidates if res.allowed_sub_categories else res.candidates[:POOL_UNRESTRICTED]
        hits = [ProductHit(self.records[c.product_id], build_ledger(self.records[c.product_id], conditions,
                                                                    plan.asked_fields), c) for c in pool]
        hits = self._order(hits, plan.operation)
        counts = {"match": sum(h.ledger.group == 0 for h in hits), "unknown": sum(h.ledger.group == 1 for h in hits),
                  "contradicted": sum(h.ledger.group == 2 for h in hits)}
        state, shown = "results", hits
        if counts["match"] == 0 and counts["unknown"] == 0:
            state = "no_match"
            notices.append("No product matches every condition. Closest products below; mismatches are marked.")
        else:
            shown = [h for h in hits if h.ledger.group < 2]  # never show contradicted products next to real matches
        out = self._outcome(text, res, state, shown, conditions, notices, t0, counts)
        out.pool = hits
        return out

    def _unsupported_value(self, c: Constraint) -> str | None:
        """Example catalogue values if `c` uses a text value the field never takes and nothing related to it
        (e.g. age_group "kids" vs "8+ years"); such a condition could only produce false "no match" results.
        Related wording ("silk" vs "silk blend") is kept, so exact matching stays strict and honest."""
        values = self.vocab.text_values.get(c.field)
        if c.op not in ("eq", "ne") or not isinstance(c.value, str) or not values:
            return None
        v = c.value.strip().lower()
        if v in values or any(v in val for val in values):
            return None
        return ", ".join(f"“{x}”" for x in sorted(values)[:3])

    @staticmethod
    def _order(hits: list[ProductHit], operation: str) -> list[ProductHit]:
        if operation == "cheapest":
            key = lambda h: (h.ledger.group, h.record["price_inr"], -h.candidate.fused_score)
        elif operation == "most_expensive":
            key = lambda h: (h.ledger.group, -h.record["price_inr"], -h.candidate.fused_score)
        elif operation == "browse":  # options the shopper can actually order come first
            key = lambda h: (h.ledger.group, h.record["stock_status"] == "out_of_stock", -h.candidate.fused_score)
        else:
            key = lambda h: (h.ledger.group, -h.candidate.fused_score)
        return sorted(hits, key=key)

    @staticmethod
    def _outcome(text, res, state, hits, conditions, notices, t0, counts=None) -> SearchOutcome:
        timings = dict(res.timings_ms)
        timings["verify"] = (time.perf_counter() - t0) * 1000
        timings["total"] = timings["total"] + timings["verify"]
        return SearchOutcome(text, res, state, hits, counts or {"match": 0, "unknown": 0, "contradicted": 0},
                             conditions, notices, timings)

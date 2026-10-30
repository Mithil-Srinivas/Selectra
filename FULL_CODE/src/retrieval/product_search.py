"""LLM-first product search.

    shopper text -> QueryInterpreter (LLM plan) -> dense search with BOTH the raw text and the LLM's search_query
    -> Reciprocal Rank Fusion -> restrict to grounded sub-categories -> top-k candidates

Sub-category grounding (measured in src/evaluation/retrieval_probe.py):
  - brand + product line named (and accepted by the LLM) -> the catalogue says which sub-category; the LLM's guess
    is ignored, because the LLM often guesses product types from names wrongly.
  - only a description ("baal sukhane wali machine") -> trust the LLM's sub_categories.
  - a bare line name that contradicts the LLM's sub_categories -> allow both.
Disagreement guard: if an LLM-chosen restriction leaves only products that BOTH similarity searches rank far down
(e.g. "Footballs" for "nike shoes"), the restriction is dropped and flagged rather than trusted.
Search finds *relevant* candidates only; whether they satisfy constraints is decided later from the records.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.conversation.query_interpreter import Interpretation, QueryInterpretation, QueryInterpreter
from src.models.embedder import Embedder
from src.preprocessing.products import CatalogueVocab
from src.retrieval.dense import DenseIndex

RRF_K = 60
# An LLM-chosen sub-category restriction is distrusted when its best product ranks worse than this in BOTH
# similarity searches (out of 5,000). Correct restrictions in the probe sets were all within the top 30.
DISAGREEMENT_RANK = 50


def ranks_of(scores: np.ndarray) -> np.ndarray:
    """1-based rank of every row (1 = highest score)."""
    r = np.empty(len(scores), dtype=np.int64)
    r[np.argsort(-scores)] = np.arange(1, len(scores) + 1)
    return r


def rrf(score_rows: list[np.ndarray]) -> np.ndarray:
    """Fuse several score vectors by rank position: sum of 1/(k + rank). Raw scores are never added."""
    return sum(1.0 / (RRF_K + ranks_of(s)) for s in score_rows)


def allowed_sub_categories(plan: QueryInterpretation, cat: pd.DataFrame, vocab: CatalogueVocab) -> tuple[set[str] | None, str]:
    """Which sub-categories the search may return, and a short reason (for diagnostics)."""
    line = plan.product_line if plan.product_line in vocab.line_names else None
    brand = plan.brand if plan.brand in vocab.brands else None
    llm_subs = set(plan.sub_categories)
    if line:
        m = cat.line_name == line
        if brand and (m & (cat.brand == brand)).any():
            return set(cat.sub_category[m & (cat.brand == brand)]), f"catalogue: {brand} {line}"
        subs = set(cat.sub_category[m])
        if llm_subs and not llm_subs & subs:
            return subs | llm_subs, f"line {line} conflicts with LLM sub_categories: allow both"
        return subs, f"catalogue: line {line}"
    if llm_subs:
        return llm_subs, "LLM sub_categories"
    return None, "unrestricted"


@dataclass
class Candidate:
    product_id: str
    fused_score: float
    raw_rank: int  # rank of this product when searching with the shopper's text (1 = best, out of all products)
    llm_rank: int  # rank when searching with the LLM's search_query


@dataclass
class SearchResult:
    interpretation: Interpretation
    allowed_sub_categories: set[str] | None
    grounding: str
    candidates: list[Candidate]
    timings_ms: dict[str, float] = field(default_factory=dict)


class ProductSearcher:
    def __init__(self, cat: pd.DataFrame, vocab: CatalogueVocab, index: DenseIndex, embedder: Embedder,
                 interpreter: QueryInterpreter):
        self.cat, self.vocab, self.index, self.embedder, self.interpreter = cat, vocab, index, embedder, interpreter
        self.ids = np.array(index.ids)
        self.sub_of_row = cat.set_index("product_id").loc[index.ids, "sub_category"].to_numpy()

    def rank(self, raw_s: np.ndarray, llm_s: np.ndarray, plan: QueryInterpretation) -> tuple[np.ndarray, set[str] | None, str]:
        """Fused scores (-inf = excluded), allowed sub-categories, and the grounding reason."""
        fused = rrf([raw_s, llm_s])
        subs, why = allowed_sub_categories(plan, self.cat, self.vocab)
        if not subs:
            return fused, None, why
        mask = np.isin(self.sub_of_row, list(subs))
        if not mask.any():
            return fused, None, why + " (matched nothing: unrestricted)"
        if why == "LLM sub_categories":
            best = np.minimum(ranks_of(raw_s), ranks_of(llm_s))[mask].min()
            if best > DISAGREEMENT_RANK:
                return fused, None, f"{why} {sorted(subs)} dropped: best product ranks {best} in both searches"
        return np.where(mask, fused, -np.inf), subs, why

    def search(self, text: str, k: int = 10, history: list[str] | None = None) -> SearchResult:
        t0 = time.perf_counter()
        interp = self.interpreter.interpret(text, history)
        t1 = time.perf_counter()
        # A follow-up ("lavender wali") means little alone, so the raw channel searches the whole conversation.
        raw_text = " ".join((history or []) + [text])
        q = self.embedder.embed_queries([raw_text, interp.plan.search_query])
        t2 = time.perf_counter()
        raw_s, llm_s = self.index.matrix @ q[0], self.index.matrix @ q[1]
        fused, subs, why = self.rank(raw_s, llm_s, interp.plan)
        raw_rank, llm_rank = ranks_of(raw_s), ranks_of(llm_s)
        top = [i for i in np.argsort(-fused)[:k] if np.isfinite(fused[i])]
        cands = [Candidate(self.ids[i], float(fused[i]), int(raw_rank[i]), int(llm_rank[i])) for i in top]
        t3 = time.perf_counter()
        return SearchResult(interp, subs, why, cands, {"interpret": (t1 - t0) * 1000, "embed": (t2 - t1) * 1000,
                                                       "search": (t3 - t2) * 1000, "total": (t3 - t0) * 1000})

"""Try the product search interactively.

    uv run python -m src.search_cli                     # interactive: type queries, empty line to quit
    uv run python -m src.search_cli "query one" "query two"
"""
from __future__ import annotations

import sys

from src.config import ARTIFACT_DIR
from src.conversation.query_interpreter import QueryInterpreter
from src.models.embedder import Embedder
from src.models.llm import LLM
from src.preprocessing.products import CatalogueVocab, load_catalogue, product_text
from src.retrieval.dense import DenseIndex
from src.retrieval.name_matcher import NameMatcher
from src.retrieval.product_search import ProductSearcher, SearchResult


def build_searcher() -> tuple[ProductSearcher, "pd.DataFrame"]:
    cat = load_catalogue()
    vocab = CatalogueVocab(cat)
    embedder = Embedder()
    index = DenseIndex.load_or_build(cat.product_id.tolist(), [product_text(r) for _, r in cat.iterrows()],
                                     embedder, ARTIFACT_DIR / "dense_products")
    interpreter = QueryInterpreter(LLM(), vocab, NameMatcher(vocab.brands, vocab.line_names))
    return ProductSearcher(cat, vocab, index, embedder, interpreter), cat


def show(res: SearchResult, cat, k: int) -> None:
    p, u = res.interpretation.plan, res.interpretation.usage
    hints = ", ".join(f"{h.text}->{h.canonical}" for h in res.interpretation.hints) or "-"
    print(f"  spell hints : {hints}")
    print(f"  operation   : {p.operation}   product_type: {p.product_type}   sub_categories: {p.sub_categories}")
    print(f"  brand/line  : {p.brand} / {p.product_line}")
    if p.constraints:
        print("  constraints : " + "; ".join(f"{c.field} {c.op} {c.value}{'' if c.hard else ' (soft)'}"
                                           for c in p.constraints))
    if res.interpretation.dropped_constraints:
        print("  DROPPED     : " + "; ".join(f"{c.field} {c.op} {c.value} (number not typed by shopper)"
                                           for c in res.interpretation.dropped_constraints))
    if p.asked_fields or p.unmapped_asks:
        print(f"  asks        : {p.asked_fields}  not-in-catalogue: {p.unmapped_asks}")
    if p.compare_targets:
        print(f"  compare     : {p.compare_targets}")
    if p.policy_topic:
        print(f"  policy      : {p.policy_topic}")
    print(f"  search_query: {p.search_query!r}")
    print(f"  restricted  : {sorted(res.allowed_sub_categories) if res.allowed_sub_categories else 'no'}  ({res.grounding})")
    rows = cat.set_index("product_id")
    print(f"  top {k} (fused | raw-text rank | llm-query rank):")
    for i, c in enumerate(res.candidates[:k], 1):
        r = rows.loc[c.product_id]
        print(f"   {i:>2}. {c.product_id}  Rs {r.price_inr:>6,}  {r.stock_status:<12} {r.title[:70]}"
              f"   [{c.raw_rank}|{c.llm_rank}]")
    t = res.timings_ms
    print(f"  tokens in/out {u.tokens_in}/{u.tokens_out}   ms: interpret {t['interpret']:.0f}, embed {t['embed']:.0f}, "
          f"search {t['search']:.0f}, total {t['total']:.0f}\n")


def main() -> None:
    searcher, cat = build_searcher()
    queries = sys.argv[1:]
    if queries:
        for q in queries:
            print(f"> {q}")
            show(searcher.search(q), cat, 10)
        return
    while (q := input("query> ").strip()):
        show(searcher.search(q), cat, 10)


if __name__ == "__main__":
    main()

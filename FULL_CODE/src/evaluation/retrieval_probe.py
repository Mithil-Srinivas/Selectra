"""Retrieval probe: raw-text embedding search vs LLM-first search.

    uv run python -m src.evaluation.retrieval_probe

Variants (all dense search over the 5,000 products):
  raw        embed the shopper text as typed
  llm        embed the LLM's search_query
  fused      Reciprocal Rank Fusion of raw + llm
  fused_sub  fused, restricted to the LLM's sub_category when it gave one
Metrics: hit@k = a gold product in the top k; p@10 = share of the top 10 that is gold (filter-style sets);
sub-category accuracy; for out-of-catalogue requests, the share where the LLM returned sub_category = null.
LLM interpretations are cached (keyed by system prompt + query), so re-runs only re-embed.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from src.config import ARTIFACT_DIR, DATA_DIR
from src.conversation.query_interpreter import QueryInterpreter
from src.evaluation.probe_sets import OUT_OF_CATALOGUE, TWISTED, synth_queries, twisted_gold
from src.models.embedder import Embedder
from src.models.llm import LLM
from src.preprocessing.products import CatalogueVocab, load_catalogue, product_text
from src.retrieval.dense import DenseIndex
from src.retrieval.name_matcher import NameMatcher
from src.retrieval.product_search import ProductSearcher, rrf
from src.conversation.query_interpreter import QueryInterpretation

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cat = load_catalogue()
    vocab = CatalogueVocab(cat)
    embedder = Embedder()
    index = DenseIndex.load_or_build(cat.product_id.tolist(), [product_text(r) for _, r in cat.iterrows()],
                                     embedder, ARTIFACT_DIR / "dense_products")
    pids = np.array(index.ids)
    sub_of = dict(zip(cat.product_id, cat.sub_category))
    matcher = NameMatcher(vocab.brands, vocab.line_names)
    interpreter = QueryInterpreter(LLM(), vocab, matcher)
    searcher = ProductSearcher(cat, vocab, index, embedder, interpreter)

    # ---- query sets
    truth = [json.loads(l) for l in open(DATA_DIR / "questions_dev_truth.jsonl", encoding="utf-8")]
    Q: list[dict] = []
    for t in truth:
        gold = set(t["acceptable_product_ids"]) | set(t["clarify_candidate_ids"])
        if t["turn"] == 1 and gold:
            Q.append({"set": "dev", "q": t["question_text"], "gold": gold})
        elif t["question_type"] == "refuse_out_of_catalogue":
            Q.append({"set": "ooc", "q": t["question_text"], "gold": set()})
    Q += [{"set": "twisted", "q": q, "gold": twisted_gold(cat, sub, attrs)} for q, sub, attrs in TWISTED]
    Q += [{"set": "ooc", "q": q, "gold": set()} for q in OUT_OF_CATALOGUE]
    Q += [{"set": "synth", **x} for x in synth_queries(cat)]
    assert all(x["gold"] for x in Q if x["set"] != "ooc"), "a probe query has no gold products"

    # ---- LLM interpretation (cached)
    cache_f = ARTIFACT_DIR / "cache" / "interpretations.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    prompt_id = hashlib.sha256(interpreter.system.encode()).hexdigest()[:12]
    key = lambda q: f"{prompt_id}|{q}"
    todo = [x["q"] for x in Q if key(x["q"]) not in cache]

    def run(q: str) -> dict:
        r = interpreter.interpret(q)
        return {"plan": r.plan.model_dump(), "tokens_in": r.usage.tokens_in, "tokens_out": r.usage.tokens_out,
                "latency_ms": r.usage.latency_ms, "attempts": r.usage.attempts, "dropped": len(r.dropped_constraints)}

    with ThreadPoolExecutor(4) as ex:
        for q, res in zip(todo, ex.map(run, todo)):
            cache[key(q)] = res
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in Q:
        x["interp"] = cache[key(x["q"])]
        x["plan"] = x["interp"]["plan"]

    # ---- retrieval
    raw_S = index.matrix @ embedder.embed_queries([x["q"] for x in Q]).T
    llm_S = index.matrix @ embedder.embed_queries([x["plan"]["search_query"] for x in Q]).T
    rows = []
    for i, x in enumerate(Q):
        if x["set"] == "ooc":
            continue
        raw, llm = raw_S[:, i], llm_S[:, i]
        fused = rrf([raw, llm])
        variants = {"raw": raw, "llm": llm, "fused": fused}
        llm_subs = set(x["plan"]["sub_categories"])
        mask = np.array([sub_of[p] in llm_subs for p in pids]) if llm_subs else np.ones(len(pids), bool)
        variants["fused_sub"] = np.where(mask, fused, -np.inf) if mask.any() else fused
        variants["fused_grounded"] = searcher.rank(raw, llm, QueryInterpretation.model_validate(x["plan"]))[0]
        for name, s in variants.items():
            order = pids[np.argsort(-s)]
            hit = np.flatnonzero(np.isin(order[:200], list(x["gold"])))
            rows.append({"set": x["set"], "variant": name, "qi": i,
                         "rank": int(hit[0]) + 1 if len(hit) else 999,
                         "p@10": float(np.isin(order[:10], list(x["gold"])).mean())})
    R = pd.DataFrame(rows)
    agg = {f"hit@{k}": ("rank", lambda s, k=k: round(float(np.mean(s <= k)), 3)) for k in (1, 5, 10, 30)}
    agg["p@10"] = ("p@10", lambda s: round(float(s.mean()), 3))
    print("\n=== retrieval")
    print(R.groupby(["set", "variant"]).agg(**agg).to_string())

    # ---- interpreter quality
    print("\n=== interpreter")
    for s in ("dev", "twisted", "synth"):
        xs = [x for x in Q if x["set"] == s]
        ok = [Counter(sub_of[g] for g in x["gold"]).most_common(1)[0][0] in x["plan"]["sub_categories"] for x in xs]
        empty = sum(not x["plan"]["sub_categories"] for x in xs)
        size = np.mean([len(x["plan"]["sub_categories"]) for x in xs])
        print(f"{s:8} gold sub-category included {np.mean(ok):.3f}  empty(=would refuse) {empty}/{len(xs)}  "
              f"mean list size {size:.2f}")
    ooc = [x for x in Q if x["set"] == "ooc"]
    print(f"ooc      sub_categories empty {sum(not x['plan']['sub_categories'] for x in ooc)}/{len(ooc)}")
    I = pd.DataFrame([x["interp"] for x in Q])
    print(f"tokens_in mean {I.tokens_in.mean():.0f}  tokens_out mean {I.tokens_out.mean():.0f}  "
          f"latency mean {I.latency_ms.mean():.0f} ms (4 concurrent)  retries {int((I.attempts > 1).sum())}  "
          f"queries with dropped numeric constraints {int((I.dropped > 0).sum())}")

    # ---- failures worth reading
    print("\n=== failures (fused_grounded rank > 5)")
    fs = R[R.variant == "fused_grounded"].set_index("qi")
    for i, x in enumerate(Q):
        if x["set"] == "ooc":
            if x["plan"]["sub_categories"]:
                print(f"[ooc] {x['q']!r} -> sub_categories {x['plan']['sub_categories']!r}")
            continue
        gold_sub = Counter(sub_of[g] for g in x["gold"]).most_common(1)[0][0]
        rank = int(fs.loc[i, "rank"])
        if rank > 5:
            print(f"[{x['set']}] rank={rank:>3} gold_sub={gold_sub!r} llm_subs={x['plan']['sub_categories']!r} "
                  f"| {x['q']!r} -> {x['plan']['search_query']!r}")


if __name__ == "__main__":
    main()

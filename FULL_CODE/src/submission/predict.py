"""Write the R3 submission file (README §7).

    uv run python -m src.submission.predict --questions ../data/questions_test.csv --out ../submission/R3_predictions.jsonl
    uv run python -m src.submission.predict --questions ../data/questions_dev.csv  --out ../submission/R3_dev_predictions.jsonl

One line per question with every required key. Conversations are answered turn by turn, each turn seeing the earlier
ones. latency_ms is the wall-clock time for that question; tokens_in/out sum every LLM call it made.
A question that fails (e.g. model server error) is written as a refusal, so the file is always complete.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from src.answering.responder import Responder, empty
from src.models.llm import LLM
from src.policy import PolicyAnswerer, load_policy
from src.search_service import SearchService

log = logging.getLogger(__name__)


def _native(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3,
                    help="conversations answered in parallel (1 gives the most honest per-question latency)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    llm = LLM()
    try:  # fail fast: an unreachable server would otherwise turn every question into a fallback refusal
        llm.client.list()
    except Exception as e:
        raise SystemExit(f"Model server not reachable ({e}). Start Ollama or set OLLAMA_URL, then re-run.")
    service = SearchService()
    responder = Responder(service, PolicyAnswerer(llm, load_policy()))
    failed: list[str] = []
    qs = pd.read_csv(args.questions, dtype=str)
    qs["turn_n"] = qs.turn.astype(int)
    conversations = [g.sort_values("turn_n") for _, g in qs.groupby("conversation_id", sort=False)]

    def run(conv: pd.DataFrame) -> list[dict]:
        history: list[str] = []
        rows = []
        for r in conv.itertuples(index=False):
            t0 = time.perf_counter()
            try:
                pred, usages = responder.respond(r.question_text, history)
            except Exception:  # keep the file complete; the error is logged for the report
                log.exception("question %s failed", r.question_id)
                failed.append(r.question_id)
                pred, usages = empty("refuse", "Sorry, I can't answer that right now."), []
            rows.append({"question_id": r.question_id, **pred,
                         "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                         "tokens_in": sum(u.tokens_in for u in usages),
                         "tokens_out": sum(u.tokens_out for u in usages)})
            history.append(r.question_text)
        return rows

    t0 = time.perf_counter()
    with ThreadPoolExecutor(args.workers) as ex:
        results = [row for rows in ex.map(run, conversations) for row in rows]
    by_id = {row["question_id"]: row for row in results}
    out = Path(args.out)
    if failed:  # never overwrite a good submission with fallback refusals
        out = out.with_suffix(out.suffix + ".partial")
        log.error("%d questions failed (%s...); wrote %s instead of %s", len(failed), failed[:3], out, args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for qid in qs.question_id:  # same order as the questions file
            f.write(json.dumps(by_id[qid], ensure_ascii=False, default=_native) + "\n")
    acts = pd.Series([r["action"] for r in results]).value_counts().to_dict()
    log.info("wrote %d predictions to %s in %.0f s; actions %s", len(results), out, time.perf_counter() - t0, acts)
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

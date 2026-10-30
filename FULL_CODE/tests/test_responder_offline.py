"""Offline test of the answer / clarify / refuse rules on dev questions, without the model server.

The LLM is replaced by fixed plans (what a correct interpretation looks like) and the embedding model by word
overlap with product titles. Everything after interpretation is the real code: catalogue, grounding, Evidence Ledger,
decision rules, answer text and the price guard. Expected outcomes come from data/questions_dev_truth.jsonl.

    uv run pytest tests/test_responder_offline.py -q        (from FULL_CODE/)
"""
from __future__ import annotations

import json
import re

import numpy as np
import pytest

from src.answering.guard import price_problems
from src.answering.responder import Responder
from src.config import DATA_DIR
from src.conversation.query_interpreter import QueryInterpretation
from src.models.llm import LLMUsage
from src.policy import PolicyAnswerer, PolicyChoice, load_policy

E = {"unmapped_asks": [], "compare_targets": [], "policy_topic": None, "constraints": [], "asked_fields": [],
     "brand": None, "product_line": None, "product_type": None, "sub_categories": []}


def plan(**kw) -> dict:
    p = {**E, **kw}
    p.setdefault("search_query", " ".join(filter(None, [p["brand"], p["product_line"], p["product_type"]])))
    return p


def c(field, value, op="eq"):
    return {"field": field, "op": op, "value": value, "hard": True}


PLANS = {
    "Sanchayo NimbusMax steel container set stock me hai?": plan(
        operation="lookup", product_type="storage container set", sub_categories=["Storage Containers"],
        brand="Sanchayo", product_line="NimbusMax", asked_fields=["stock_status"]),
    "Chargit QuillBolt red earphones kitne ke": plan(
        operation="lookup", product_type="wired earphones", sub_categories=["Wired Earphones"], brand="Chargit",
        product_line="QuillBolt", constraints=[c("colour", "red")], asked_fields=["price_inr"]),
    "Trailnest DriftAir pink running shoe water resistant hai?": plan(
        operation="lookup", product_type="running shoes", sub_categories=["Running Shoes"], brand="Trailnest",
        product_line="DriftAir", constraints=[c("colour", "pink")], asked_fields=["water_resistant"]),
    "king size cotton bedsheet sabse sasti jo stock me ho": plan(
        operation="cheapest", product_type="bedsheet", sub_categories=["Bedsheets"],
        constraints=[c("bed_size", "king"), c("material", "cotton"), c("stock_status", "out_of_stock", "ne")],
        asked_fields=["price_inr"]),
    "wavefin ripple loop purple ya teal earbuds kaunsa sasta": plan(
        operation="compare", product_type="wireless earbuds", sub_categories=["Wireless Earbuds"], brand="Wavefin",
        product_line="RippleLoop", asked_fields=["price_inr"],
        compare_targets=["Wavefin RippleLoop purple earbuds", "Wavefin RippleLoop teal earbuds"]),
    "Wavefin RippleLoop purple earbuds": plan(
        operation="lookup", product_type="wireless earbuds", sub_categories=["Wireless Earbuds"], brand="Wavefin",
        product_line="RippleLoop", constraints=[c("colour", "purple")]),
    "Wavefin RippleLoop teal earbuds": plan(
        operation="lookup", product_type="wireless earbuds", sub_categories=["Wireless Earbuds"], brand="Wavefin",
        product_line="RippleLoop", constraints=[c("colour", "teal")]),
    "free delivery kitne ke order pe milti hai": plan(operation="policy", policy_topic="free delivery threshold",
                                                      search_query="free delivery"),
    "saffron coins ya loyalty points kaise milte hai": plan(operation="policy", policy_topic="loyalty points",
                                                            search_query="loyalty points"),
    "redmi note 13 price": plan(operation="lookup", product_type="smartphone", brand="Redmi",
                                asked_fields=["price_inr"], search_query="Redmi Note 13 smartphone"),
    "strikeforce vistaair yoga mat kitne ki hai": plan(
        operation="lookup", product_type="yoga mat", sub_categories=["Yoga Mats"], brand="Strikeforce",
        product_line="VistaAir", asked_fields=["price_inr"]),
    "lavender wali": plan(
        operation="lookup", product_type="yoga mat", sub_categories=["Yoga Mats"], brand="Strikeforce",
        product_line="VistaAir", constraints=[c("colour", "lavender")], asked_fields=["price_inr"]),
    "6 mm yoga mat chahiye": plan(operation="browse", product_type="yoga mat", sub_categories=["Yoga Mats"],
                                  constraints=[c("thickness_mm", 6)]),
    "green running shoes kitne ke hai": plan(
        operation="browse", product_type="running shoes", sub_categories=["Running Shoes"],
        constraints=[c("colour", "green")], asked_fields=["price_inr"]),
    "Funkari TerraFusion 500 piece wala kitne ka hai aur stock me hai?": plan(
        operation="lookup", product_type="building blocks", sub_categories=["Building Blocks"], brand="Funkari",
        product_line="TerraFusion", constraints=[c("pieces", 500)], asked_fields=["price_inr", "stock_status"]),
}
POLICY = {"free delivery kitne ke order pe milti hai": (True, ["2.1"]),
          "saffron coins ya loyalty points kaise milte hai": (False, [])}
HISTORY = {"lavender wali": ["strikeforce vistaair yoga mat kitne ki hai"]}


class FakeLLM:
    def chat_json(self, system, user, schema, json_schema=None, context=None, retries=1):
        q = re.search(r"(?:Shopper message|Shopper question): (.*)", user).group(1).split("\nSpell-checker")[0]
        if schema is PolicyChoice:
            covered, ids = POLICY[q]
            return PolicyChoice(covered=covered, section_ids=ids), LLMUsage(10, 5, 1.0, 1)
        return QueryInterpretation.model_validate(PLANS[q], context=context), LLMUsage(10, 5, 1.0, 1)


class FakeEmbedder:
    """Query vector = mean of the products whose titles share the most words with the query."""
    model = "fake"

    def __init__(self, service):
        self.titles = [set(re.findall(r"[a-z0-9]+", r["title"].lower())) for r in service.catalogue.to_dict("records")]
        self.matrix = service.searcher.index.matrix

    def embed_queries(self, texts, instruction=None):
        out = []
        for t in texts:
            words = set(re.findall(r"[a-z0-9]+", t.lower()))
            overlap = np.array([len(words & ti) for ti in self.titles])
            top = np.argsort(-overlap)[:20]
            v = self.matrix[top].mean(axis=0)
            out.append(v / np.linalg.norm(v))
        return np.array(out)


@pytest.fixture(scope="module")
def responder():
    from src.search_service import SearchService
    svc = SearchService()  # loads the cached product index; no server call
    svc.searcher.interpreter.llm = FakeLLM()
    svc.searcher.embedder = FakeEmbedder(svc)
    return Responder(svc, PolicyAnswerer(FakeLLM(), load_policy()))


TRUTH = {t["question_text"]: t for t in map(json.loads, open(DATA_DIR / "questions_dev_truth.jsonl", encoding="utf-8"))}
CASES = [q for q in PLANS if q in TRUTH]


@pytest.mark.parametrize("question", CASES)
def test_dev_question(responder, question):
    t = TRUTH[question]
    history = HISTORY.get(question, [])
    pred, _ = responder.respond(question, history)
    assert pred["action"] == t["expected_action"], pred["answer_text"]
    assert not price_problems(pred, responder.records, responder.policy_amounts, history + [question])
    cited = set(pred["cited_product_ids"])
    assert len(cited) <= 10
    if t["expected_action"] == "answer" and t["acceptable_product_ids"]:
        assert cited & set(t["acceptable_product_ids"]), pred
    if t["expected_action"] == "clarify":
        assert len(cited & set(t["clarify_candidate_ids"])) >= 2, pred
    for rf in t["required_facts"]:
        stated = {(s["product_id"], "price_inr"): s["price_inr"] for s in pred["stated_prices"]}
        stated.update({(f["product_id"], f["field"]): f["value"] for f in pred["stated_facts"]})
        assert (rf["product_id"], rf["field"]) in stated, f"missing required fact {rf}"
    for s in t["policy_sections"]:
        assert set(s.split("|")) & set(pred["cited_policy_sections"])

# Selectra: the R3 shopping assistant that doesn't lie

**Team dino · Team ID 1086** · TalentAP Mega Hackathon 2026, problem R3

Selectra answers shopper questions (short, misspelt, often Hinglish) over the fixed 5,000-product catalogue and the
store policy. For every question it picks one action, `answer`, `clarify` or `refuse`, and every price, stock status
and attribute it states is copied by code from a catalogue record or the policy text, with the product ID or policy
section cited.

**Design rule:** the LLM interprets the question; code verifies every fact against the catalogue; the catalogue decides.
The LLM never sees or writes a price.

## Repository layout

```
README.md                         this file
submission/R3_predictions.jsonl   predictions for the 150 test questions (README §7 format)
FULL_CODE/
  src/                            the pipeline (see "How it works")
    submission/predict.py         writes the submission file
    answering/                    answer / clarify / refuse rules, answer text, price guard
    conversation/                 LLM query interpreter
    retrieval/                    name matcher, embedding index, hybrid product search
    verification/evidence.py      Evidence Ledger (verified / contradicted / unknown per condition)
    policy.py                     policy sections and section choice
    evaluation/                   retrieval probe and probe query sets
  app/                            demo web app (NiceGUI): Search and Debug tabs
  docs/                           team brief (HTML/PDF), slide deck and its generator
  tools/package_submission.py     checks the submission and builds <TEAM>_R3.zip
  pyproject.toml, uv.lock         dependencies (uv)
```

## Setup

1. **Python.** Install [uv](https://docs.astral.sh/uv/), then:
   ```
   cd FULL_CODE
   uv sync
   ```
   This creates `FULL_CODE/.venv` with Python 3.13 and the pinned dependencies.
2. **Data.** Copy the competition pack's `data/` folder to the project root, next to `FULL_CODE/`
   (`data/catalogue.jsonl`, `data/policy.md`, `data/questions_test.csv`, ...). Another location can be set with
   `R3_DATA_DIR`.
3. **Models.** Both models are served by [Ollama](https://ollama.com) (version 0.40 or later) on a GPU machine:
   ```
   ollama pull hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M
   ollama pull qwen3-embedding:0.6b
   ```
   Point the code at the server with `OLLAMA_URL` (default `http://10.10.37.186:11434`, our LAN server).
   `OLLAMA_MODEL` and `OLLAMA_EMBED_MODEL` override the model names. Once pulled, everything runs offline.

| Model | Role | Size | Licence |
|---|---|---|---|
| Qwen3.5-9B Instruct, GGUF Q4_K_M (unsloth build) | query interpretation, policy section choice | 6.2 GB file, ~5.9 GB VRAM loaded | Apache-2.0 as published by Qwen (check the model card before redistribution) |
| qwen3-embedding 0.6B, Q8_0 | product similarity search | 0.6 GB, ~1.2 GB VRAM loaded | Apache-2.0 |

No paid or external inference APIs are used.

## Run

All commands are run from `FULL_CODE/`.

| Task | Command |
|---|---|
| Test submission | `uv run python -m src.submission.predict --questions ../data/questions_test.csv --out ../submission/R3_predictions.jsonl` |
| Dev predictions | `uv run python -m src.submission.predict --questions ../data/questions_dev.csv --out ../submission/R3_dev_predictions.jsonl` |
| Score dev | `uv run python ../evaluate.py --submission ../submission/R3_dev_predictions.jsonl --truth ../data/questions_dev_truth.jsonl --details` |
| Demo web app | `uv run python -m app.main`, then open http://localhost:8080 |
| Terminal search with full trace | `uv run python -m src.search_cli "cheapest nike shoes"` |
| Retrieval probe (262 queries) | `uv run python -m src.evaluation.retrieval_probe` |
| Build the team zip | `uv run python tools/package_submission.py --team <TEAM_ID>` |

`predict` checks the model server before starting. If any question fails, it writes `<out>.partial` and exits with
code 2 instead of overwriting a good submission. `--workers 1` gives the most faithful per-question latency;
the default of 3 answers conversations in parallel.

## How it works

1. **Name spell-check (code).** RapidFuzz matches words against the 51 brands and 963 product-line names
   (`krida` → Kridaa). Matches are passed to the LLM as hints; the question text is never rewritten.
2. **Interpretation (LLM, one call).** Qwen3.5-9B returns a JSON plan: operation (lookup, browse, cheapest,
   most expensive, compare, policy), sub-categories, brand, product line, constraints, fields asked about. Ollama
   restricts sub-categories and field names to the real catalogue values; Pydantic validates the plan. Earlier turns
   of the same conversation are included, so follow-ups like "lavender wali" carry the context over.
3. **Code checks on the plan.** Numbers the shopper never typed are dropped (the LLM once turned "cheapest" into
   price ≤ 0); text values a field never takes are dropped with a notice; near-miss brand and line names are mapped
   to catalogue spelling.
4. **Search.** The raw question and the LLM's phrase are both embedded and searched against all 5,000 products
   (NumPy, ~1 ms); the two rankings are merged with Reciprocal Rank Fusion. If the shopper named a real brand and
   line, the catalogue decides the sub-category, not the LLM.
5. **Evidence Ledger (code).** Every condition is checked against each candidate record: verified, contradicted or
   unknown. Missing attributes stay unknown, colours and materials match exactly, and a missing `warranty_months`
   means no brand warranty (policy 3.1).
6. **Decision (code, README §6).**
   - refuse: nothing we sell matches, a brand we don't carry, or the record or policy doesn't hold the answer
   - clarify: a question about one product where 2+ products match and differ in what was asked
   - answer: everything else (lookups, options, cheapest / most expensive, comparisons, policy)
7. **Answer (code).** The text comes from templates filled with catalogue values; `stated_prices` and
   `stated_facts` use exact catalogue field names. Policy answers quote the chosen section and cite it.
   A final guard, a copy of `evaluate.py`'s price rules, rejects any rupee amount that isn't a cited product's
   price, MRP or discount, a cited policy amount, or a budget the shopper typed.

## Latency and token cost

Each line of the submission records `latency_ms` (wall-clock time for that question) and `tokens_in` /
`tokens_out` (all LLM calls for that question). `evaluate.py` prints the mean and p95.

| Question type | LLM calls | Tokens in / out (approx.) |
|---|---|---|
| Product question | 1 | ~3,000 / ~120 |
| Policy question | 2 | ~5,000 / ~150 |
| Comparison of 2 products | 3 | ~9,000 / ~360 |

Measured on the final test run (150 questions, one at a time, `--workers 1`): **mean 2.6 s, median 2.4 s,
p95 3.6 s per question; 3,402 tokens in and 136 out on average.** About 90% of the time is the LLM call; search and
verification take a few milliseconds. Cost is local GPU time only.

## Results

Official `evaluate.py` on the 40 dev questions (`submission/R3_dev_predictions.jsonl`):

| Metric | Organisers' baseline | Selectra |
|---|---|---|
| Primary score | 0.73 | **1.000** |
| Action accuracy | 0.83 | 1.000 |
| Grounded / helpful (action right) | 0.85 / 0.77 | 1.000 / 1.000 |
| Hallucinated prices | 0 | 0 |

Two rules (narrowing variants by a number in the title, and answering from the attribute whose value the shopper
typed) were added after reading dev failures, and dev has only 40 questions, so expect the hidden test score to be lower.

Retrieval, measured with `src/evaluation/retrieval_probe.py`:

| Measurement | Raw text only | Selectra |
|---|---|---|
| Correct product ranked first: 35 descriptive Hinglish questions | 0.51 | 0.89 |
| Correct product ranked first: 200 misspelt product names | 0.97 | 1.00 |
| Correct product ranked first: 27 dev questions | 0.93 | 0.93 |
| Out-of-catalogue requests recognised (16) | n/a | 16 / 16 |

The descriptive and misspelt-name sets were written by us, so they may flatter the system.

## Known limitations

- The models run on a LAN Ollama server. If the judging environment must be a single offline machine, the same
  models run on any machine with ~8 GB of GPU memory by changing `OLLAMA_URL`.
- The LLM sometimes drops a material word ("red silk saree"); colour has a code backstop, material does not yet.
- Only 40 dev questions have answers, so tuning is limited; the probe sets are self-written.

## Data and licences

The catalogue, policy and questions are synthetic data from the competition pack (CC BY 4.0). They are not committed
(see `.gitignore`). Model licences are listed under Setup.

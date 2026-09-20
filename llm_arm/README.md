# llm_arm: language-model comparison arm (whitepaper arm g)

Asks four language models to DTI-score the same synthetic teacher records the other arms see, and measures
accuracy vs the deployed engine, determinism across repeats, latency, and dollars per record. Providers
(`--provider`): `anthropic` (`claude-opus-5`), `openai` (`gpt-5`), `xai` (`grok-4`, served as `grok-4.3`), `gemini`
(`gemini-3-flash-preview`); the non-Anthropic ids are what the site's Gauntlet calls. One adapter per provider
(`adapters.py`): same system prompt text (sha256 asserted equal to the source run), same user turn, each vendor's
native JSON-schema mechanism, reasoning effort high everywhere, temperature 0 where the API accepts it (recorded).

```
.venv/bin/python -m llm_arm --n 3 --k 2                                            # smoke (anthropic)
.venv/bin/python -m llm_arm --n 300 --k 3 --seed 20260920 --ids splits/dti_seed1.json:test   # protocol run (N, k fixed by PROTOCOL.md section 6)
.venv/bin/python -m llm_arm --provider xai --n 300 --k 3 --ids-from-run llm_arm/llm_runs/20260920T154525Z   # same 300 ids as the Opus 5 run
.venv/bin/python -m pytest tests/test_llm_arm.py tests/test_llm_arm_providers.py tests/test_llm_arm_examples.py   # offline tests
.venv/bin/python scripts/choose_examples_e.py                                          # arm g2: pick E from the token budget -> examples_budget.json
.venv/bin/python -m llm_arm --provider xai --n 300 --k 3 --ids-from-run llm_arm/llm_runs/20260920T154525Z --examples 100   # arm g2-examples
```

Arm `g2-examples` (post-hoc; PROTOCOL amendment 1, row 17): identical to arm g except that the cached system prefix carries, between
the paper text and the instruction block, E = 100 engine-scored examples from the TRAIN split of seed 1 (`examples.py`: stratified by tier,
seed 20260920, identical across vendors and repeats; zero overlap with the 300 scored ids and with the whole TEST split, asserted before
the first call). E is the largest of {50, 100, 200} whose prefix stays under 150k tokens on every vendor's tokenizer (`examples_budget.json`).
Runs go to `llm_runs/<stamp>-examples/` with `examples.json` beside the usual files; Gemini holds one explicit CachedContent for the run
(`explicit_cache.json`, storage priced in), the other vendors cache as in arm g.

Keys: `source /Users/jas/.config/supertruth-connectome/providers.env` (OPENAI_API_KEY, XAI_API_KEY, GEMINI_API_KEY) plus the
Anthropic key from the environment; never printed, never copied into this tree. Prices (`prices.py`) come from each vendor's
public pricing page with URL and retrieval date; xAI's row is checked against the vendor's own `cost_in_usd_ticks` per call.

Input: `/tmp/connectome-paper/teachers/dti_teacher.jsonl` (gen_dti.ts rows). `--payload-field` names the field sent as
RECORD (default `text`; the current teacher rows carry no `text`, so use `--payload-field extracted` until the generator
emits it). `--as-of` defaults to the teacher's `frozen_clock` in `dti_teacher_summary.json`.

Each run writes `llm_runs/<UTC stamp>/`: `calls.jsonl` (one line per API call: latency, tokens incl. reasoning and cached,
cost, vendor-reported cost where offered, stop/finish reason, parsed output, parse failures, refusals), `summary.json`
(same shape for every provider), `prices.json` (that provider's price rows with sources), `system_prompt.txt`, and
`HOW_WE_RAN_THIS.md` (the paper's method note: model id requested, response model field, date, settings, prompt hash,
N, k, account). Auth is the SDK client reading the environment; no key is ever written to this tree.

Fixtures in `fixtures/providers/` are one captured raw response each for xAI and Gemini (2026-09-20) and hand-built
OpenAI and blocked-Gemini bodies, used by the adapter parsing tests.

Fixtures in `fixtures/` are three hand-built synthetic records scored by the deployed engine (`make_fixtures.ts`, run
with tsx from the website repo), plus one valid response. Test fixtures only.

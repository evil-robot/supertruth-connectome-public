"""Choose E for arm g2-examples from the token budget, with each vendor's own tokenizer or count endpoint.

  set -a; source /Users/jas/.config/supertruth-connectome/providers.env; set +a
  .venv/bin/python scripts/choose_examples_e.py [--as-of ...] [--out llm_arm/examples_budget.json]

For E in {50, 100, 200}: build the full system prefix (paper + E examples + instruction), count its tokens with
Anthropic count_tokens (claude-opus-5), tiktoken o200k_base (tiktoken.encoding_for_model("gpt-5")), xAI
POST /v1/tokenize-text (grok-4), and Gemini count_tokens (gemini-3-flash-preview; the Developer API counts
contents, not system_instruction, so the prefix is counted as contents). Pick the largest E whose prefix is under
150,000 tokens for every vendor and under every vendor's context limit with margin (prefix + record + max output).
Context limits are read from dated sources named in the output, never from memory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_arm.examples import E_CHOICES, EXAMPLES_SEED, PREFIX_BUDGET_TOKENS, assert_no_leakage, examples_block_sha256, select_examples  # noqa: E402
from llm_arm.loader import load_records, read_frozen_clock, read_ids_from_run  # noqa: E402
from llm_arm.prompt import build_system_prompt, sha256_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEACHER = ROOT / "teachers" / "dti_teacher.jsonl"
SPLIT = ROOT / "splits" / "dti_seed1.json"
OPUS_RUN = ROOT / "llm_arm" / "llm_runs" / "20260920T154525Z"
MAX_OUTPUT = 16_000
RECORD_ALLOWANCE = 6_000   # largest user turn in the corpus is under 6k chars; generous in tokens

# Context limits, read live on 2026-09-20 (source beside each; xAI's 200k is the long-context price threshold, treated as the binding limit
# because prices.py uses only the < 200k rows).
LIMITS = {
    "anthropic": {"context_tokens": 1_000_000, "source": "claude-api bundled skill 2.1.278 shared/models.md line 76: 'Claude Opus 5 ... 1M context window (default and maximum), 128K max output'"},
    "openai": {"context_tokens": 400_000, "source": "https://developers.openai.com/api/docs/models/gpt-5: '400,000 context window', '128,000 max output tokens'"},
    "xai": {"context_tokens": 200_000, "source": "https://docs.x.ai/docs/models: grok-4.3 context 1M; long-context pricing from 200k tokens (api.x.ai/v1/language-models/grok-4.3 long_context_threshold 200000); 200k is the binding limit so every call stays on the < 200k price row"},
    "gemini": {"context_tokens": 1_048_576, "source": "models.get gemini-3-flash-preview on 2026-09-20: input_token_limit 1048576, output_token_limit 65536"},
}


def count_anthropic(text: str) -> int:
    import anthropic
    c = anthropic.Anthropic()
    return c.messages.count_tokens(model="claude-opus-5", messages=[{"role": "user", "content": text}]).input_tokens


def count_openai(text: str) -> int:
    import tiktoken
    return len(tiktoken.encoding_for_model("gpt-5").encode(text))


def count_xai(text: str) -> int:
    import requests
    r = requests.post("https://api.x.ai/v1/tokenize-text", headers={"Authorization": f"Bearer {os.environ['XAI_API_KEY']}"},
                      json={"text": text, "model": "grok-4"}, timeout=300)
    r.raise_for_status()
    return len(r.json()["token_ids"])


def count_gemini(text: str) -> int:
    from google import genai
    c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return c.models.count_tokens(model="gemini-3-flash-preview", contents=text).total_tokens


COUNTERS = {"anthropic": (count_anthropic, "POST /v1/messages/count_tokens, model claude-opus-5, prefix counted as one user turn"),
            "openai": (count_openai, "tiktoken o200k_base (tiktoken.encoding_for_model('gpt-5'))"),
            "xai": (count_xai, "POST https://api.x.ai/v1/tokenize-text, model grok-4"),
            "gemini": (count_gemini, "models.count_tokens gemini-3-flash-preview (Developer API counts contents; prefix counted as contents)")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "llm_arm" / "examples_budget.json")
    a = ap.parse_args(argv)
    as_of = a.as_of or read_frozen_clock(TEACHER)
    records = load_records(TEACHER)
    scored_ids, _ = read_ids_from_run(OPUS_RUN)
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "as_of": as_of, "selection_seed": EXAMPLES_SEED,
           "budget_prefix_tokens": PREFIX_BUDGET_TOKENS, "max_output_tokens": MAX_OUTPUT, "record_allowance_tokens": RECORD_ALLOWANCE,
           "limits": LIMITS, "counters": {p: c[1] for p, c in COUNTERS.items()}, "candidates": {}}
    base = build_system_prompt(as_of)
    out["base_prompt_sha256"] = sha256_text(base)
    out["base_prefix_tokens"] = {p: fn(base) for p, (fn, _) in COUNTERS.items()}
    print("base prefix tokens:", out["base_prefix_tokens"], file=sys.stderr)
    chosen = None
    for e in E_CHOICES:
        ex, man = select_examples(records, SPLIT, e)
        leak = assert_no_leakage(man["record_ids"], scored_ids, SPLIT)
        prefix = build_system_prompt(as_of, examples=ex)
        counts = {p: fn(prefix) for p, (fn, _) in COUNTERS.items()}
        one_example = {p: round((counts[p] - out["base_prefix_tokens"][p]) / e, 1) for p in counts}
        fits = {p: counts[p] < PREFIX_BUDGET_TOKENS and counts[p] + RECORD_ALLOWANCE + MAX_OUTPUT < LIMITS[p]["context_tokens"] for p in counts}
        out["candidates"][str(e)] = {"prefix_tokens": counts, "tokens_per_example": one_example, "fits_every_vendor": all(fits.values()), "fits": fits,
                                     "prefix_sha256": sha256_text(prefix), "examples_block_sha256": examples_block_sha256(ex),
                                     "record_ids_sha256": man["record_ids_sha256"], "per_tier": man["per_tier"], "leakage_check": leak}
        print(f"E={e}: {counts} fits={fits}", file=sys.stderr)
        if all(fits.values()):
            chosen = e
    out["chosen_E"] = chosen
    out["rule"] = "largest E in {50, 100, 200} with prefix < 150,000 tokens for every vendor and prefix + record allowance + max output < each vendor's context limit"
    a.out.write_text(json.dumps(out, indent=2) + "\n")
    print(f"chosen E = {chosen}; wrote {a.out}", file=sys.stderr)
    return 0 if chosen else 1


if __name__ == "__main__":
    sys.exit(main())

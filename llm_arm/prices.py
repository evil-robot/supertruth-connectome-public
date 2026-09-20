"""Price tables for the LLM arm, one per provider. Every number was read from a
dated source (DECISION_RULES rule 14: prices come from a dated source, never
from memory). The run copies its provider's table into prices.json.

Anthropic rows: claude-api bundled skill, 2026-09-20.
OpenAI, xAI, Google rows: the vendors' public pricing pages, read live on
2026-09-20; URLs and the exact price text are in each table's `sources`.
"""

SKILL_DIR = (
    "/private/tmp/claude-501/bundled-skills/2.1.278/"
    "7b89acc11d1d4b21508b7dbdd229b3ad/claude-api"
)

RETRIEVED_ON = "2026-09-20"

# ---------------------------------------------------------------- Anthropic
MODEL = "claude-opus-5"  # kept for the original runner path and its tests

# USD per million tokens.
INPUT_PER_MTOK = 5.00
OUTPUT_PER_MTOK = 25.00
CACHE_READ_MULTIPLIER = 0.10       # of base input price
CACHE_WRITE_5M_MULTIPLIER = 1.25   # of base input price, 5-minute TTL
CACHE_READ_PER_MTOK = INPUT_PER_MTOK * CACHE_READ_MULTIPLIER          # 0.50
CACHE_WRITE_5M_PER_MTOK = INPUT_PER_MTOK * CACHE_WRITE_5M_MULTIPLIER  # 6.25

PRICE_TABLE = {
    "provider": "anthropic",
    "model": MODEL,
    "retrieved_from": "claude-api bundled skill, Claude Code 2.1.278",
    "retrieved_on": RETRIEVED_ON,
    "usd_per_mtok": {
        "input": INPUT_PER_MTOK,
        "output": OUTPUT_PER_MTOK,
        "cache_read": CACHE_READ_PER_MTOK,
        "cache_write_5m": CACHE_WRITE_5M_PER_MTOK,
    },
    "sources": [
        {
            "file": f"{SKILL_DIR}/shared/models.md",
            "line": 76,
            "row": "Claude Opus 5 ... A drop-in upgrade at Opus 4.8's pricing ($5/$25 per MTok)",
        },
        {
            "file": f"{SKILL_DIR}/shared/model-migration.md",
            "section": "Migrating to Claude Opus 5",
            "row": "$5 per million input tokens, $25 per million output",
        },
        {
            "file": f"{SKILL_DIR}/shared/prompt-caching.md",
            "line": 145,
            "row": "Cache reads cost ~0.1x base input price ... Cache writes cost 1.25x for 5-minute TTL, 2x for 1-hour TTL",
        },
        {
            "file": f"{SKILL_DIR}/shared/cost-optimization.md",
            "line": 25,
            "row": "cache writes (1.25x input for the 5-minute duration, 2x for 1-hour), cache reads (0.1x input)",
        },
    ],
    "notes": [
        "cache_read and cache_write_5m are derived: 0.10 x 5.00 and 1.25 x 5.00.",
        "This runner uses the default 5-minute cache TTL only.",
        "fallbacks='default' may re-run a refused request on another model, billed at that model's rates. "
        "Opus 4.8 shares the $5/$25 row (models.md line 76). Calls whose response model is not claude-opus-5 "
        "are flagged fallback_ran=true and priced here at the Opus 5 row; the summary counts them separately.",
    ],
}

# ---------------------------------------------------------------- OpenAI
OPENAI_TABLE = {
    "provider": "openai",
    "model": "gpt-5",
    "model_served_as": "gpt-5-2025-08-07",
    "vendor_flagship_on_retrieval_date": {"id": "gpt-6-astra", "usd_per_mtok": {"input": 10.00, "cache_read": 1.00, "output": 50.00},
                                          "source": "https://developers.openai.com/api/docs/models: 'use GPT-6 Astra, our flagship model for complex reasoning and coding'"},
    "retrieved_from": "developers.openai.com pricing and model pages",
    "retrieved_on": RETRIEVED_ON,
    "usd_per_mtok": {"input": 1.25, "cache_read": 0.125, "output": 10.00},
    "sources": [
        {"url": "https://developers.openai.com/api/docs/pricing",
         "row": "gpt-5: Input $1.25 | Cached input $0.125 | Output $10.00 (per 1M tokens, standard tier)"},
        {"url": "https://developers.openai.com/api/docs/models/gpt-5",
         "row": "Input $1.25 | 1M tokens; Cached input $0.125 | 1M tokens; Output $10 | 1M tokens; alias gpt-5 points to gpt-5-2025-08-07"},
        {"url": "https://developers.openai.com/api/docs/guides/reasoning",
         "row": "reasoning tokens ... are billed as output tokens (completion_tokens already includes them)"},
    ],
    "notes": [
        "input = prompt_tokens minus prompt_tokens_details.cached_tokens; cache_read = cached_tokens.",
        "output = completion_tokens, which already includes completion_tokens_details.reasoning_tokens.",
        "gpt-5 is the id the site's Gauntlet calls (st-homepage-refresh/src/lib/lift.ts); it is served today and kept. "
        "The vendor's flagship on the retrieval date is gpt-6-astra; not switched.",
    ],
}

# ---------------------------------------------------------------- xAI
XAI_TABLE = {
    "provider": "xai",
    "model": "grok-4",
    "model_served_as": "grok-4.3",
    "vendor_flagship_on_retrieval_date": {"id": "grok-4.6", "usd_per_mtok": {"input": 2.00, "cache_read": 0.50, "output": 6.00},
                                          "source": "https://docs.x.ai/docs/models: Grok 4.6 'is the most intelligent and fastest model we've built'"},
    "retrieved_from": "docs.x.ai models page and the API's language-models endpoint",
    "retrieved_on": RETRIEVED_ON,
    "usd_per_mtok": {"input": 1.25, "cache_read": 0.20, "output": 2.50},
    "long_context_threshold_tokens": 200_000,
    "sources": [
        {"url": "https://docs.x.ai/docs/models",
         "row": "grok-4.3 (< 200k): Input $1.25 | Cached Input $0.20 | Output $2.50; (>= 200k): $2.50 | $0.40 | $5.00"},
        {"url": "https://api.x.ai/v1/language-models/grok-4.3",
         "row": "prompt_text_token_price 12500, cached_prompt_text_token_price 2000, completion_text_token_price 25000 (ticks per token; "
                "1 tick = 1e-10 USD, since 12500 ticks per token is the page's $1.25 per MTok); long_context_threshold 200000"},
        {"url": "https://api.x.ai/v1/language-models/grok-4",
         "row": "resolves to id grok-4.3 (the request id grok-4 is served by grok-4.3; a chat completion requesting grok-4 returns model grok-4.3)"},
        {"url": "https://docs.x.ai/docs/guides/reasoning",
         "row": "When using a reasoning model, the reasoning tokens are billed as part of your total consumption."},
    ],
    "notes": [
        "input = prompt_tokens minus prompt_tokens_details.cached_tokens; cache_read = cached_tokens.",
        "output = completion_tokens + completion_tokens_details.reasoning_tokens: xAI reports reasoning tokens OUTSIDE completion_tokens "
        "and bills them at the completion price. Verified 2026-09-20 on a probe: usage.cost_in_usd_ticks reconciled to the tick only with "
        "reasoning tokens added ((375-128)*12500 + 128*2000 + (88+831)*25000 = 26318500 ticks).",
        "Every call also logs the vendor's own usage.cost_in_usd_ticks / 1e10 as vendor_cost_usd for cross-check.",
        "grok-4 is the id the site's Gauntlet calls (lift.ts). The models endpoint no longer lists grok-4 but still serves the id, "
        "as grok-4.3; requested id kept, response model recorded, priced at the grok-4.3 row. Vendor flagship on the retrieval date: grok-4.6.",
        "No call in this arm approaches the 200k long-context threshold; the long-context rows are not used.",
    ],
}

# ---------------------------------------------------------------- Google
GEMINI_TABLE = {
    "provider": "gemini",
    "model": "gemini-3-flash-preview",
    "model_served_as": "gemini-3-flash-preview (version 3-flash-preview-12-2025 per models.get)",
    "vendor_flagship_on_retrieval_date": {"id": "gemini-3.8-flash", "usd_per_mtok": {"input": 0.75, "cache_read": 0.075, "output": 3.75},
                                          "source": "https://ai.google.dev/gemini-api/docs/pricing presents Gemini 3.8 Flash as 'Our most intelligent Flash model'; "
                                                    "https://ai.google.dev/gemini-api/docs/models presents Gemini 3.1 Pro (preview) as the most capable"},
    "retrieved_from": "ai.google.dev pricing page",
    "retrieved_on": RETRIEVED_ON,
    "usd_per_mtok": {"input": 0.50, "cache_read": 0.05, "output": 3.00},
    "usd_per_mtok_hour_cache_storage": 1.00,
    "sources": [
        {"url": "https://ai.google.dev/gemini-api/docs/pricing",
         "row": "Gemini 3 Flash Preview, paid tier: Input $0.50 (text / image / video) $1.00 (audio); Output $3.00; Context caching $0.05 (text / image / video)"},
        {"url": "https://ai.google.dev/gemini-api/docs/pricing",
         "row": "Gemini 3 Flash Preview, context caching storage: $1.00 / 1,000,000 tokens per hour (read 2026-09-20; used only by arm g2-examples, which holds one explicit CachedContent for the run)"},
        {"url": "https://ai.google.dev/gemini-api/docs/thinking",
         "row": "When thinking is turned on, response pricing is the sum of output tokens and thinking tokens."},
    ],
    "notes": [
        "input = prompt_token_count minus cached_content_token_count; cache_read = cached_content_token_count (implicit caching, if any).",
        "output = candidates_token_count + thoughts_token_count (thinking tokens are billed as output).",
        "gemini-3-flash-preview is the id the site's Gauntlet calls (lift.ts); served today and kept. The vendor's pages name "
        "Gemini 3.8 Flash (pricing page) and Gemini 3.1 Pro preview (models page) as current top models; not switched.",
        "Text input only in this arm; the audio rows are not used.",
    ],
}

TABLES = {"anthropic": PRICE_TABLE, "openai": OPENAI_TABLE, "xai": XAI_TABLE, "gemini": GEMINI_TABLE}
MODEL_IDS = {p: t["model"] for p, t in TABLES.items()}


def cost_usd(usage: dict, provider: str = "anthropic") -> float:
    """usage keys (normalised across providers; missing keys count as 0):
    input_tokens (uncached prompt tokens), output_tokens (answer + reasoning),
    cache_read_input_tokens, cache_creation_input_tokens (Anthropic only)."""
    g = lambda k: usage.get(k) or 0
    p = TABLES[provider]["usd_per_mtok"]
    return (
        g("input_tokens") * p["input"]
        + g("cache_creation_input_tokens") * p.get("cache_write_5m", 0.0)
        + g("cache_read_input_tokens") * p["cache_read"]
        + g("output_tokens") * p["output"]
    ) / 1_000_000

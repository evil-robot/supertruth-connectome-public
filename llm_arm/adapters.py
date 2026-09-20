"""One adapter per provider. Each adapter builds the request from the same
system prompt text and user turn, calls the vendor SDK, and returns a
normalised dict via a pure `parse(raw)` function that the offline tests
exercise on fixtures.

Normalised result keys (every adapter fills all of them):
  model_response, request_id, finish_reason (vendor string), stop_reason
  (common vocabulary: end_turn | max_tokens | refusal | other), refused (bool),
  refusal_details, text (str | None), usage {input_tokens, output_tokens,
  cache_read_input_tokens, cache_creation_input_tokens, reasoning_tokens},
  usage_raw (vendor object as dict), vendor_cost_usd (xAI only), fallback_ran.

Token semantics are normalised to Anthropic's: input_tokens EXCLUDES cached
prompt tokens (they are cache_read_input_tokens); output_tokens INCLUDES
reasoning/thinking tokens, which every vendor bills at the output price.
"""
from __future__ import annotations

import os

from .prices import MODEL_IDS
from .prompt import SCHEMA

PROVIDERS = ("anthropic", "openai", "xai", "gemini")
XAI_BASE_URL = "https://api.x.ai/v1"
OPENAI_SCHEMA_NAME = "dti_score"
GEMINI_CACHE_TTL_S = 8 * 3600   # arm g2-examples: explicit CachedContent held for the run, deleted at the end


class _NoPrefixCache:
    """Vendors whose prefix caching is automatic (OpenAI, xAI) or per-request (Anthropic cache_control): nothing to prepare."""
    async def prepare(self, system: str) -> dict | None:
        return None

    async def close(self) -> dict | None:
        return None


def _stop(finish: str | None, refused: bool, vocab: dict[str, str]) -> str:
    if refused:
        return "refusal"
    return vocab.get(finish or "", "other")


# ---------------------------------------------------------------- Anthropic
class AnthropicAdapter(_NoPrefixCache):
    provider = "anthropic"
    BETAS = ["server-side-fallback-2026-07-01"]
    temperature_settable = False   # adaptive thinking: temperature is not accepted (Opus 5 run, PROTOCOL 6)

    def __init__(self, *, max_tokens: int, effort: str, temperature: float | None):
        import anthropic
        self.sdk = anthropic
        self.model = MODEL_IDS["anthropic"]
        self.max_tokens, self.effort = max_tokens, effort
        self.temperature_requested = temperature
        self.client = anthropic.AsyncAnthropic(max_retries=2)
        self.retryable = (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APITimeoutError)
        self.status_error = anthropic.APIStatusError
        self.sdk_version = f"anthropic {anthropic.__version__}"
        self.first_call_alone = True   # cache write must finish before parallel reads

    def settings(self) -> dict:
        return {"thinking": {"type": "adaptive"}, "effort": self.effort, "max_tokens": self.max_tokens,
                "temperature_requested": self.temperature_requested, "temperature_settable": False,
                "betas": self.BETAS, "fallbacks": "default", "structured_output": "output_config.format json_schema",
                "cache_control": "ephemeral (5m) on the system block", "sdk": self.sdk_version}

    async def call(self, system: str, user: str) -> dict:
        kwargs = dict(
            model=self.model, max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=self.BETAS, fallbacks="default",
        )
        async with self.client.beta.messages.stream(**kwargs) as stream:
            msg = await stream.get_final_message()
        raw = msg.model_dump()
        raw["_request_id"] = getattr(msg, "_request_id", None)
        return self.parse(raw)

    @classmethod
    def parse(cls, raw: dict) -> dict:
        u = raw.get("usage") or {}
        content = raw.get("content") or []
        refused = raw.get("stop_reason") == "refusal"
        text = next((b.get("text") for b in content if b.get("type") == "text"), None)
        return {
            "model_response": raw.get("model"), "request_id": raw.get("_request_id"),
            "finish_reason": raw.get("stop_reason"),
            "stop_reason": _stop(raw.get("stop_reason"), refused, {"end_turn": "end_turn", "max_tokens": "max_tokens", "stop_sequence": "end_turn"}),
            "refused": refused, "refusal_details": raw.get("stop_details") if refused else None,
            "text": None if refused else text,
            "usage": {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                      "cache_read_input_tokens": u.get("cache_read_input_tokens"),
                      "cache_creation_input_tokens": u.get("cache_creation_input_tokens"), "reasoning_tokens": None},
            "usage_raw": u, "vendor_cost_usd": None,
            "fallback_ran": (raw.get("model") != MODEL_IDS["anthropic"]) or any(b.get("type") == "fallback" for b in content),
        }


# ---------------------------------------------------------------- OpenAI-compatible (OpenAI, xAI)
class _OpenAICompatAdapter(_NoPrefixCache):
    provider = ""
    base_url: str | None = None
    api_key_env = "OPENAI_API_KEY"
    max_tokens_param = "max_completion_tokens"
    first_call_alone = False
    reasoning_outside_completion = False   # xAI reports reasoning tokens outside completion_tokens

    def __init__(self, *, max_tokens: int, effort: str, temperature: float | None):
        import openai
        self.sdk = openai
        self.model = MODEL_IDS[self.provider]
        self.max_tokens, self.effort = max_tokens, effort
        self.temperature_requested = temperature
        self.temperature_settable: bool | None = None if temperature is not None else False
        kw = dict(max_retries=2)   # SDK retries 429/5xx/connection errors with backoff
        if self.base_url:
            kw.update(base_url=self.base_url, api_key=os.environ[self.api_key_env])
        self.client = openai.AsyncOpenAI(**kw)
        self.retryable = (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError)
        self.status_error = openai.APIStatusError
        self.sdk_version = f"openai {openai.__version__}"

    def settings(self) -> dict:
        return {"thinking": {"type": f"reasoning_effort {self.effort}"}, "effort": self.effort, "max_tokens": self.max_tokens,
                "max_tokens_param": self.max_tokens_param,
                "temperature_requested": self.temperature_requested, "temperature_settable": self.temperature_settable,
                "structured_output": "response_format json_schema strict=true", "endpoint": (self.base_url or "https://api.openai.com/v1") + "/chat/completions",
                "sdk": self.sdk_version}

    def request_kwargs(self, system: str, user: str, with_temperature: bool) -> dict:
        kw = dict(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {"name": OPENAI_SCHEMA_NAME, "strict": True, "schema": SCHEMA}},
            reasoning_effort=self.effort,
        )
        kw[self.max_tokens_param] = self.max_tokens
        if with_temperature and self.temperature_requested is not None:
            kw["temperature"] = self.temperature_requested
        return kw

    async def call(self, system: str, user: str) -> dict:
        want_temp = self.temperature_requested is not None and self.temperature_settable is not False
        try:
            r = await self.client.chat.completions.with_raw_response.create(**self.request_kwargs(system, user, want_temp))
        except self.sdk.BadRequestError as e:
            # A 400 naming temperature means this model does not take it: record that, retry once without.
            if want_temp and "temperature" in str(e).lower():
                self.temperature_settable = False
                r = await self.client.chat.completions.with_raw_response.create(**self.request_kwargs(system, user, False))
            else:
                raise
        else:
            if want_temp:
                self.temperature_settable = True
        raw = r.parse().model_dump()
        raw["_request_id"] = r.request_id
        return self.parse(raw)

    @classmethod
    def parse(cls, raw: dict) -> dict:
        u = raw.get("usage") or {}
        ptd = u.get("prompt_tokens_details") or {}
        ctd = u.get("completion_tokens_details") or {}
        choice = (raw.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        refused = msg.get("refusal") is not None
        cached = ptd.get("cached_tokens") or 0
        reasoning = ctd.get("reasoning_tokens") or 0
        completion = u.get("completion_tokens") or 0
        output = completion + reasoning if cls.reasoning_outside_completion else completion
        ticks = u.get("cost_in_usd_ticks")
        return {
            "model_response": raw.get("model"), "request_id": raw.get("_request_id"),
            "finish_reason": choice.get("finish_reason"),
            "stop_reason": _stop(choice.get("finish_reason"), refused, {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}),
            "refused": refused or choice.get("finish_reason") == "content_filter",
            "refusal_details": {"refusal": msg.get("refusal"), "finish_reason": choice.get("finish_reason")} if (refused or choice.get("finish_reason") == "content_filter") else None,
            "text": None if refused else msg.get("content"),
            "usage": {"input_tokens": (u.get("prompt_tokens") or 0) - cached, "output_tokens": output,
                      "cache_read_input_tokens": cached, "cache_creation_input_tokens": None, "reasoning_tokens": reasoning},
            "usage_raw": u, "vendor_cost_usd": (ticks / 1e10) if isinstance(ticks, (int, float)) else None,
            "fallback_ran": False,
        }


class OpenAIAdapter(_OpenAICompatAdapter):
    provider = "openai"


class XAIAdapter(_OpenAICompatAdapter):
    provider = "xai"
    base_url = XAI_BASE_URL
    api_key_env = "XAI_API_KEY"
    max_tokens_param = "max_tokens"
    reasoning_outside_completion = True


# ---------------------------------------------------------------- Google Gemini
class GeminiAdapter:
    provider = "gemini"
    first_call_alone = False

    def __init__(self, *, max_tokens: int, effort: str, temperature: float | None, explicit_cache: bool = False):
        from google import genai
        from google.genai import types
        self.sdk, self.types = genai, types
        self.model = MODEL_IDS["gemini"]
        self.max_tokens, self.effort = max_tokens, effort
        self.temperature_requested = temperature
        self.explicit_cache = explicit_cache    # arm g2-examples: one CachedContent holding the system prefix (arm g used implicit caching)
        self.cache = None
        self.cache_info: dict | None = None
        self.temperature_settable = True if temperature is not None else False   # accepted by generateContent (probe 2026-09-20)
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=3, http_status_codes=[429, 500, 502, 503, 504])))
        from google.genai import errors
        self.retryable = (errors.ServerError,)        # 5xx after the SDK's own retries
        self.status_error = errors.APIError
        self.sdk_version = f"google-genai {genai.__version__}"

    def settings(self) -> dict:
        out = {"thinking": {"type": f"thinking_level {self.effort}"}, "effort": self.effort, "max_tokens": self.max_tokens,
               "temperature_requested": self.temperature_requested, "temperature_settable": self.temperature_settable,
               "temperature_vendor_advice": "ai.google.dev/gemini-api/docs/gemini-3: 'we strongly recommend keeping the temperature parameter at its default value of 1.0'",
               "structured_output": "response_mime_type application/json + response_json_schema",
               "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", "sdk": self.sdk_version}
        if self.explicit_cache:
            out["cache_control"] = f"explicit CachedContent (caches.create with system_instruction, ttl {GEMINI_CACHE_TTL_S}s, deleted at run end); generate_content passes cached_content"
        return out

    async def prepare(self, system: str) -> dict | None:
        if not self.explicit_cache:
            return None
        from datetime import datetime, timezone
        T = self.types
        c = await self.client.aio.caches.create(model=self.model, config=T.CreateCachedContentConfig(
            system_instruction=system, ttl=f"{GEMINI_CACHE_TTL_S}s", display_name="llm_arm g2-examples system prefix"))
        self.cache = c
        um = c.usage_metadata
        self.cache_info = {"name": c.name, "model": c.model, "token_count": getattr(um, "total_token_count", None),
                           "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ttl_s": GEMINI_CACHE_TTL_S,
                           "expire_time": str(c.expire_time)}
        return self.cache_info

    async def close(self) -> dict | None:
        if not self.cache:
            return None
        from datetime import datetime, timezone
        await self.client.aio.caches.delete(name=self.cache.name)
        deleted = datetime.now(timezone.utc)
        created = datetime.fromisoformat(self.cache_info["created_utc"])
        self.cache_info.update({"deleted_utc": deleted.isoformat(timespec="seconds"),
                                "hours_held": round((deleted - created).total_seconds() / 3600, 4)})
        return self.cache_info

    async def call(self, system: str, user: str) -> dict:
        T = self.types
        cfg = dict(max_output_tokens=self.max_tokens,
                   response_mime_type="application/json", response_json_schema=SCHEMA,
                   thinking_config=T.ThinkingConfig(thinking_level=self.effort.upper()))
        if self.cache is not None:
            cfg["cached_content"] = self.cache.name    # the system prefix lives in the cache; passing it again is a 400
        else:
            cfg["system_instruction"] = system
        if self.temperature_requested is not None:
            cfg["temperature"] = self.temperature_requested
        r = await self.client.aio.models.generate_content(model=self.model, contents=user, config=T.GenerateContentConfig(**cfg))
        return self.parse(r.model_dump(mode="json"))

    @classmethod
    def parse(cls, raw: dict) -> dict:
        um = raw.get("usage_metadata") or {}
        cands = raw.get("candidates") or []
        c0 = cands[0] if cands else {}
        finish = c0.get("finish_reason")
        pf = raw.get("prompt_feedback") or {}
        blocked = bool(pf.get("block_reason")) or finish in ("SAFETY", "PROHIBITED_CONTENT", "SPII", "BLOCKLIST", "IMAGE_SAFETY")
        parts = ((c0.get("content") or {}).get("parts")) or []
        text = "".join(p.get("text") or "" for p in parts if not p.get("thought")) or None
        cached = um.get("cached_content_token_count") or 0
        thoughts = um.get("thoughts_token_count") or 0
        return {
            "model_response": raw.get("model_version"), "request_id": raw.get("response_id"),
            "finish_reason": finish,
            "stop_reason": _stop(finish, blocked, {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}),
            "refused": blocked,
            "refusal_details": {"block_reason": pf.get("block_reason"), "finish_reason": finish} if blocked else None,
            "text": None if blocked else text,
            "usage": {"input_tokens": (um.get("prompt_token_count") or 0) - cached,
                      "output_tokens": (um.get("candidates_token_count") or 0) + thoughts,
                      "cache_read_input_tokens": cached, "cache_creation_input_tokens": None, "reasoning_tokens": thoughts},
            "usage_raw": um, "vendor_cost_usd": None, "fallback_ran": False,
        }


ADAPTERS = {"anthropic": AnthropicAdapter, "openai": OpenAIAdapter, "xai": XAIAdapter, "gemini": GeminiAdapter}


def make_adapter(provider: str, *, max_tokens: int, effort: str, temperature: float | None, explicit_cache: bool = False):
    if provider not in ADAPTERS:
        raise ValueError(f"provider must be one of {PROVIDERS}, got {provider!r}")
    if provider == "gemini":
        return GeminiAdapter(max_tokens=max_tokens, effort=effort, temperature=temperature, explicit_cache=explicit_cache)
    return ADAPTERS[provider](max_tokens=max_tokens, effort=effort, temperature=temperature)

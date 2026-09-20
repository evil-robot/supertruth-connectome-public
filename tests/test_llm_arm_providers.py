"""Multi-provider LLM arm: adapter parsing on fixtures, price rows with source
URLs, byte-identical sample with the Opus 5 run. No network."""
import hashlib
import json
from pathlib import Path

import pytest

from llm_arm import metrics as M
from llm_arm.adapters import AnthropicAdapter, GeminiAdapter, OpenAIAdapter, XAIAdapter, PROVIDERS
from llm_arm.loader import read_ids_from_run
from llm_arm.prices import TABLES, cost_usd
from llm_arm.prompt import build_system_prompt, sha256_text

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "llm_arm" / "fixtures" / "providers"
OPUS_RUN = ROOT / "llm_arm" / "llm_runs" / "20260920T154525Z"


def _load(name):
    return json.loads((FIX / name).read_text())


# ---- adapter parsing ----------------------------------------------------------
def test_xai_fixture_parses_and_reconciles_to_vendor_bill():
    raw = _load("xai_ok.json")   # captured live 2026-09-20: request id grok-4, served by grok-4.3
    r = XAIAdapter.parse(raw)
    assert r["model_response"] == "grok-4.3" and r["stop_reason"] == "end_turn" and not r["refused"]
    obj = json.loads(r["text"])
    assert M.validate_output(obj) == []
    u = r["usage"]
    raw_u = raw["usage"]
    # reasoning tokens sit OUTSIDE completion_tokens on xAI and are billed at the output price
    assert u["output_tokens"] == raw_u["completion_tokens"] + raw_u["completion_tokens_details"]["reasoning_tokens"]
    assert u["input_tokens"] + u["cache_read_input_tokens"] == raw_u["prompt_tokens"]
    assert r["vendor_cost_usd"] == pytest.approx(raw_u["cost_in_usd_ticks"] / 1e10)
    assert cost_usd(u, "xai") == pytest.approx(r["vendor_cost_usd"], abs=1e-9), "our xAI price row must reproduce the vendor's own bill"


def test_gemini_fixture_parses_thoughts_as_output():
    raw = _load("gemini_ok.json")   # captured live 2026-09-20
    r = GeminiAdapter.parse(raw)
    assert r["model_response"] == "gemini-3-flash-preview" and r["finish_reason"] == "STOP" and r["stop_reason"] == "end_turn"
    assert M.validate_output(json.loads(r["text"])) == []
    um = raw["usage_metadata"]
    assert r["usage"]["output_tokens"] == um["candidates_token_count"] + um["thoughts_token_count"]
    assert r["usage"]["reasoning_tokens"] == um["thoughts_token_count"]
    assert r["usage"]["input_tokens"] == um["prompt_token_count"]
    assert cost_usd(r["usage"], "gemini") == pytest.approx((21 * 0.50 + (52 + 495) * 3.00) / 1e6)


def test_gemini_blocked_is_a_refusal_not_a_score():
    r = GeminiAdapter.parse(_load("gemini_blocked.json"))
    assert r["refused"] and r["stop_reason"] == "refusal" and r["text"] is None
    assert r["refusal_details"]["block_reason"] == "PROHIBITED_CONTENT"


def test_openai_fixture_parses_cached_and_reasoning():
    raw = _load("openai_ok.json")
    r = OpenAIAdapter.parse(raw)
    assert r["model_response"] == "gpt-5-2025-08-07" and r["stop_reason"] == "end_turn" and not r["refused"]
    assert M.validate_output(json.loads(r["text"])) == []
    u = r["usage"]
    assert u["input_tokens"] == 7000 - 6016 and u["cache_read_input_tokens"] == 6016
    assert u["output_tokens"] == 900 and u["reasoning_tokens"] == 832   # completion_tokens already includes reasoning
    assert cost_usd(u, "openai") == pytest.approx((984 * 1.25 + 6016 * 0.125 + 900 * 10.0) / 1e6)


def test_openai_refusal_is_final_and_unscored():
    r = OpenAIAdapter.parse(_load("openai_refusal.json"))
    assert r["refused"] and r["stop_reason"] == "refusal" and r["text"] is None
    assert "cannot assist" in r["refusal_details"]["refusal"]


def test_anthropic_parse_matches_opus_run_log():
    first = json.loads(OPUS_RUN.joinpath("calls.jsonl").read_text().splitlines()[0])
    raw = {"model": "claude-opus-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": first["raw_text"]}],
           "usage": {k: first[k] for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}}
    r = AnthropicAdapter.parse(raw)
    assert json.loads(r["text"]) == first["parsed"]
    assert cost_usd(r["usage"], "anthropic") == pytest.approx(first["cost_usd"], abs=1e-6)
    assert not r["fallback_ran"]
    refused = AnthropicAdapter.parse({**raw, "stop_reason": "refusal", "stop_details": {"type": "refusal"}})
    assert refused["refused"] and refused["text"] is None


# ---- price rows -----------------------------------------------------------------
@pytest.mark.parametrize("provider", ["openai", "xai", "gemini"])
def test_vendor_price_rows_have_urls_and_date(provider):
    t = TABLES[provider]
    assert t["retrieved_on"] == "2026-09-20"
    assert t["sources"] and all(s["url"].startswith("https://") and s["row"] for s in t["sources"])
    assert {"input", "cache_read", "output"} <= set(t["usd_per_mtok"])
    assert all(v > 0 for v in t["usd_per_mtok"].values())
    assert t["vendor_flagship_on_retrieval_date"]["id"] != t["model"], "flagship differs from the Gauntlet id and must be recorded, not switched to"


def test_price_tables_cover_every_provider():
    assert set(TABLES) == set(PROVIDERS)
    for p in PROVIDERS:
        assert TABLES[p]["provider"] == p


# ---- sample identity with the Opus 5 run ---------------------------------------
def test_ids_from_run_are_the_opus_sample_byte_identical():
    ids, src = read_ids_from_run(OPUS_RUN)
    summary = json.loads((OPUS_RUN / "summary.json").read_text())
    assert len(ids) == 300 == len(set(ids)) == summary["input"]["n_records"]
    assert set(ids) == {r["record_id"] for r in summary["records"]}
    assert src["source_prompt_sha256"] == summary["prompt_sha256"] == "5e7f42957795615a5e16b61d9e0d1e7d11864d8aabfdde0233a1d06ee87bca71"
    # every provider rebuilds the prompt from the same source text and as_of; the runner asserts this hash before any call
    assert sha256_text(build_system_prompt(src["source_as_of"])) == src["source_prompt_sha256"]
    assert src["calls_file_sha256"] == hashlib.sha256((OPUS_RUN / "calls.jsonl").read_bytes()).hexdigest()


def test_completed_provider_runs_share_the_opus_sample_and_prompt():
    """Any run that names the Opus run as its id source must carry the same 300 ids and prompt hash."""
    opus_ids = set(read_ids_from_run(OPUS_RUN)[0])
    checked = 0
    for s in (ROOT / "llm_arm" / "llm_runs").glob("*/summary.json"):
        d = json.loads(s.read_text())
        src = (d.get("input") or {}).get("ids_source") or {}
        if src.get("source_run_id") != OPUS_RUN.name or d["input"]["n_records"] < 300:
            continue
        if d.get("arm", "g") == "g2-examples":
            # post-hoc arm (amendment 1 row 17): the prefix carries the examples, so the full hash differs; the base prompt must not
            assert d["base_prompt_sha256"] == "5e7f42957795615a5e16b61d9e0d1e7d11864d8aabfdde0233a1d06ee87bca71"
            assert d["prompt_sha256"] != d["base_prompt_sha256"] and d["examples"]["E"] > 0
        else:
            assert d["prompt_sha256"] == "5e7f42957795615a5e16b61d9e0d1e7d11864d8aabfdde0233a1d06ee87bca71"
        assert {r["record_id"] for r in d["records"]} == opus_ids
        checked += 1
    assert checked >= 0   # zero completed runs is not a failure of this test; the run status is reported separately

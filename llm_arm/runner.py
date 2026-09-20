"""LLM comparison arm: ask a language model to DTI-score teacher records; log
every call; summarise accuracy vs the teacher, determinism, latency, cost.

Four providers behind one runner (adapters.py): anthropic (claude-opus-5),
openai (gpt-5), xai (grok-4), gemini (gemini-3-flash-preview). Same system
prompt text (sha256 asserted equal to the source run when --ids-from-run is
used), same user turn, each vendor's native JSON-schema mechanism, temperature
0 where the API accepts it (recorded), k identical calls per record.

Anthropic path (unchanged from the Opus 5 run; claude-api skill rules):
  thinking adaptive; output_config effort high + json_schema; streaming with
  get_final_message; server-side-fallback beta with fallbacks "default";
  stop_reason == "refusal" checked before content is read; one cache_control
  breakpoint on the system block; first call alone so later calls read the
  cache it wrote.
Auth: SDK clients read the environment. No key in code or files.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import metrics as M
from .adapters import make_adapter
from .examples import assert_no_leakage
from .prices import TABLES, cost_usd
from .prompt import DIMS, build_system_prompt, build_user_content, sha256_text


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Runner:
    def __init__(self, *, records: list[dict], k: int, seed: int, n_requested: int,
                 payload_field: str, as_of: str, max_tokens: int, concurrency: int,
                 out_root: Path, input_path: Path, ids_source: dict | None = None,
                 provider: str = "anthropic", effort: str = "high", temperature: float | None = 0.0,
                 examples: list[dict] | None = None, examples_manifest: dict | None = None,
                 examples_budget: dict | None = None, split_path: Path | None = None):
        self.records, self.k, self.seed, self.n_requested = records, k, seed, n_requested
        self.ids_source = ids_source
        self.payload_field, self.as_of, self.max_tokens = payload_field, as_of, max_tokens
        self.concurrency, self.input_path = concurrency, input_path
        self.provider = provider
        self.price_table = TABLES[provider]
        self.model = self.price_table["model"]
        # arm g: paper + instruction. arm g2-examples (post-hoc, amendment 1 row 17): paper + E scored TRAIN examples + instruction.
        self.examples, self.examples_manifest, self.examples_budget = examples or [], examples_manifest, examples_budget
        self.arm = "g2-examples" if self.examples else "g"
        self.base_prompt_hash = sha256_text(build_system_prompt(as_of))
        self.system_prompt = build_system_prompt(as_of, examples=self.examples or None, payload_field=payload_field)
        self.prompt_hash = sha256_text(self.system_prompt)
        if ids_source and ids_source.get("source_prompt_sha256"):
            src = ids_source["source_prompt_sha256"]
            assert self.base_prompt_hash == src, f"base system prompt sha256 {self.base_prompt_hash} != source run's {src}; refusing to run a different prompt"
        self.leakage = None
        if self.examples:
            assert split_path is not None, "arm g2-examples needs the split file for the TEST-split leakage check"
            self.leakage = assert_no_leakage([r["record_id"] for r in self.examples], [r["record_id"] for r in records], split_path)
        self.adapter = make_adapter(provider, max_tokens=max_tokens, effort=effort,
                                    temperature=None if provider == "anthropic" else temperature,
                                    explicit_cache=(provider == "gemini" and self.arm == "g2-examples"))
        suffix = "-examples" if self.examples else ""
        t = datetime.now(timezone.utc)
        while (out_root / (t.strftime("%Y%m%dT%H%M%SZ") + suffix)).exists():   # two providers launched in the same second
            t += timedelta(seconds=1)
        self.run_id = t.strftime("%Y%m%dT%H%M%SZ") + suffix
        self.out_dir = out_root / self.run_id
        self.out_dir.mkdir(parents=True, exist_ok=False)
        self.calls_path = self.out_dir / "calls.jsonl"
        self.sem = asyncio.Semaphore(concurrency)
        self.lock = asyncio.Lock()
        self.calls: list[dict] = []

    # ---- request ---------------------------------------------------------
    async def one_call(self, record: dict, repeat: int) -> dict:
        log = {
            "provider": self.provider, "record_id": record["record_id"], "repeat": repeat, "request_ts": None,
            "model_requested": self.model, "model_response": None, "request_id": None,
            "latency_ms": None, "input_tokens": None, "output_tokens": None, "reasoning_tokens": None,
            "cache_creation_input_tokens": None, "cache_read_input_tokens": None, "usage_raw": None,
            "cost_usd": None, "vendor_cost_usd": None, "stop_reason": None, "finish_reason": None, "stop_details": None,
            "fallback_ran": None, "temperature_requested": self.adapter.temperature_requested, "temperature_settable": None,
            "parsed": None, "parse_error": None, "raw_text": None, "error": None, "attempts": 0,
        }
        user = build_user_content(record, self.payload_field)
        a = self.adapter
        for attempt in (1, 2):  # SDK retries inside, plus one outer retry on 429/5xx/connection
            log["attempts"] = attempt
            log["request_ts"] = utc_now()
            t0 = time.perf_counter()
            try:
                res = await a.call(self.system_prompt, user)
                log["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                log["error"] = None
                break
            except a.retryable as e:
                log["error"] = f"{type(e).__name__}: {e}"
            except a.status_error as e:
                code = getattr(e, "status_code", None) or getattr(e, "code", None)
                log["error"] = f"{type(e).__name__} {code}: {getattr(e, 'message', e)}"
                if code is not None and int(code) < 500 and int(code) != 429:
                    return log  # 4xx other than 429: not retryable
            except Exception as e:  # noqa: BLE001 - logged, never hidden
                log["error"] = f"{type(e).__name__}: {e}"
                return log
        else:
            return log

        log["temperature_settable"] = a.temperature_settable
        usage = res["usage"]
        log.update({k: usage.get(k) for k in ("input_tokens", "output_tokens", "reasoning_tokens",
                                              "cache_creation_input_tokens", "cache_read_input_tokens")})
        log["usage_raw"] = res["usage_raw"]
        log["cost_usd"] = round(cost_usd(usage, self.provider), 6)
        log["vendor_cost_usd"] = res["vendor_cost_usd"]
        log["model_response"] = res["model_response"]
        log["request_id"] = res["request_id"]
        log["stop_reason"] = res["stop_reason"]
        log["finish_reason"] = res["finish_reason"]
        log["fallback_ran"] = res["fallback_ran"]
        if res["refused"]:
            log["stop_details"] = res["refusal_details"]
            return log  # a refusal is final; never retried, content not read as a score
        text = res["text"]
        log["raw_text"] = text
        if text is None:
            log["parse_error"] = f"no text in response (finish_reason={res['finish_reason']})"
            return log
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            log["parse_error"] = f"invalid JSON: {e}"
            return log
        errs = M.validate_output(obj)
        if errs:
            log["parse_error"] = "; ".join(errs)
            return log
        log["parsed"] = obj
        return log

    async def guarded(self, record: dict, repeat: int) -> None:
        async with self.sem:
            log = await self.one_call(record, repeat)
        async with self.lock:
            self.calls.append(log)
            with open(self.calls_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log, sort_keys=True, default=str) + "\n")

    async def run(self) -> dict:
        plan = [(r, i) for r in self.records for i in range(self.k)]
        self.explicit_cache = await self.adapter.prepare(self.system_prompt)   # Gemini arm g2 only; None elsewhere
        if self.explicit_cache:
            (self.out_dir / "explicit_cache.json").write_text(json.dumps(self.explicit_cache, indent=2, default=str))
        try:
            if self.adapter.first_call_alone:
                # Anthropic: the cache entry is readable only once its response starts
                # streaming; parallel first calls would all pay the write price.
                await self.guarded(*plan[0])
                plan = plan[1:]
            await asyncio.gather(*(self.guarded(r, i) for r, i in plan))
        finally:
            closed = await self.adapter.close()
            if closed:
                self.explicit_cache = closed
                (self.out_dir / "explicit_cache.json").write_text(json.dumps(closed, indent=2, default=str))
        self.calls.sort(key=lambda c: (c["request_ts"], c["record_id"], c["repeat"]))
        summary = self.summarise()
        (self.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
        (self.out_dir / "prices.json").write_text(json.dumps(self.price_table, indent=2))
        (self.out_dir / "system_prompt.txt").write_text(self.system_prompt)
        if self.examples:
            (self.out_dir / "examples.json").write_text(json.dumps({**self.examples_manifest, "leakage_check": self.leakage,
                                                                   "budget": self.examples_budget}, indent=2))
        (self.out_dir / "HOW_WE_RAN_THIS.md").write_text(self.method_note(summary))
        return summary

    # ---- summary ---------------------------------------------------------
    def summarise(self) -> dict:
        calls = self.calls
        ok = [c for c in calls if c["parsed"] is not None]
        teacher = {r["record_id"]: r for r in self.records}
        by_rec: dict[str, list[dict]] = defaultdict(list)
        run1: dict[str, dict] = {}
        for c in ok:
            by_rec[c["record_id"]].append(c["parsed"])
            if c["repeat"] == 0:
                run1[c["record_id"]] = c["parsed"]

        def acc_block(pred_by_rec: dict[str, dict], label: str) -> dict:
            ids = sorted(pred_by_rec)
            if not ids:
                return {"basis": label, "records": 0}
            t = [teacher[i] for i in ids]
            p = [pred_by_rec[i] for i in ids]
            y_true = [x["tier"] for x in t]
            y_pred = [x["tier"] for x in p]
            return {
                "basis": label,
                "records": len(ids),
                "mae_per_dimension": {d: M.mae([(a["dimensions"][d], b["dimensions"][d]) for a, b in zip(t, p)]) for d in DIMS},
                "composite_mae_direct": M.mae([(a["composite"], b["composite"]) for a, b in zip(t, p)]),
                "composite_mae_recomputed_from_predicted_dims": M.mae(
                    [(a["composite"], M.recompute_composite(b["dimensions"])) for a, b in zip(t, p)]),
                "model_composite_equals_own_recompute_share": sum(
                    b["composite"] == M.recompute_composite(b["dimensions"]) for b in p) / len(p),
                "tier_accuracy": M.accuracy(y_true, y_pred),
                "tier_macro_f1": M.macro_f1(y_true, y_pred),
                "tier_labels_in_truth": sorted(set(y_true)),
                "tier_support_truth": {k: y_true.count(k) for k in sorted(set(y_true))},
            }

        # per-record mean of runs: dims/composite = mean rounded JS-style; tier = majority vote,
        # ties broken by the tier of the mean composite.
        mean_pred: dict[str, dict] = {}
        for rid, outs in by_rec.items():
            dims = {d: M.js_round(sum(o["dimensions"][d] for o in outs) / len(outs)) for d in DIMS}
            comp = M.js_round(sum(o["composite"] for o in outs) / len(outs))
            tier, tie = M.majority([o["tier"] for o in outs])
            mean_pred[rid] = {"dimensions": dims, "composite": comp,
                              "tier": M.tier_from_composite(comp) if tie else tier}

        lat = [c["latency_ms"] for c in calls if c["latency_ms"] is not None]
        tok = lambda k: sum(c[k] or 0 for c in calls if c[k] is not None)
        storage_usd = 0.0
        ec = getattr(self, "explicit_cache", None)
        if ec and ec.get("hours_held") is not None and ec.get("token_count"):
            storage_usd = round(ec["token_count"] * ec["hours_held"] * self.price_table["usd_per_mtok_hour_cache_storage"] / 1_000_000, 6)
        total_cost = round(sum(c["cost_usd"] or 0 for c in calls) + storage_usd, 6)
        vendor_costs = [c["vendor_cost_usd"] for c in calls if c["vendor_cost_usd"] is not None]
        later = calls[1:]
        cache_reads_later = [c for c in later if (c["cache_read_input_tokens"] or 0) > 0]
        resp_models = defaultdict(int)
        for c in calls:
            resp_models[c["model_response"] or "none"] += 1
        temps = {str(c["temperature_settable"]) for c in calls if c["error"] is None}

        return {
            "run_id": self.run_id,
            "arm": self.arm,
            "provider": self.provider,
            "model_requested": self.model,
            "response_models": dict(resp_models),
            "settings": {**self.adapter.settings(), "concurrency": self.concurrency,
                         "temperature_settable_observed": sorted(temps)},
            "input": {"path": str(self.input_path), "payload_field": self.payload_field, "as_of": self.as_of,
                      "n_requested": self.n_requested, "n_records": len(self.records), "k": self.k, "seed": self.seed,
                      "ids_source": self.ids_source},
            "prompt_sha256": self.prompt_hash,
            "base_prompt_sha256": self.base_prompt_hash,
            "examples": ({**self.examples_manifest, "leakage_check": self.leakage, "examples_block_in_prefix": True,
                          "prefix_tokens_measured": (self.examples_budget or {}).get("candidates", {}).get(str(len(self.examples)), {}).get("prefix_tokens"),
                          "prefix_token_counter": (self.examples_budget or {}).get("counters", {}).get(self.provider),
                          "prefix_tokens_observed_first_call": None if not calls else
                          ((calls[0]["cache_creation_input_tokens"] or 0) + (calls[0]["cache_read_input_tokens"] or 0) + (calls[0]["input_tokens"] or 0))}
                         if self.examples else None),
            "counts": {"calls_total": len(calls), "calls_parsed_ok": len(ok),
                       "parse_failures": sum(1 for c in calls if c["parse_error"]),
                       "refusals": sum(1 for c in calls if c["stop_reason"] == "refusal"),
                       "errors": sum(1 for c in calls if c["error"]),
                       "fallback_calls": sum(1 for c in calls if c["fallback_ran"]),
                       "stop_reasons": dict(defaultdict(int, {s: sum(1 for c in calls if c["stop_reason"] == s)
                                                              for s in {c["stop_reason"] for c in calls}})),
                       "finish_reasons": {str(s): sum(1 for c in calls if c["finish_reason"] == s)
                                          for s in {c["finish_reason"] for c in calls}}},
            "cache": {"mechanism": self.adapter.settings().get("cache_control", "vendor automatic prompt caching (cached tokens read from usage)"),
                      "first_call_cache_creation_input_tokens": calls[0]["cache_creation_input_tokens"] if calls else None,
                      "first_call_cache_read_input_tokens": calls[0]["cache_read_input_tokens"] if calls else None,
                      "later_calls": len(later),
                      "later_calls_with_cache_read": len(cache_reads_later),
                      "cache_verified_from_second_call": bool(later) and len(cache_reads_later) == len(later),
                      "calls_with_cache_read": sum(1 for c in calls if (c["cache_read_input_tokens"] or 0) > 0),
                      "explicit_cache": ec},
            "tokens": {"input": tok("input_tokens"), "output": tok("output_tokens"), "reasoning": tok("reasoning_tokens"),
                       "cache_creation": tok("cache_creation_input_tokens"), "cache_read": tok("cache_read_input_tokens")},
            "latency_ms": {"n": len(lat), "median": M.percentile(lat, 50), "p95": M.percentile(lat, 95),
                           "min": min(lat) if lat else None, "max": max(lat) if lat else None},
            "cost_usd": {"total": total_cost,
                         "calls_total": round(sum(c["cost_usd"] or 0 for c in calls), 6),
                         "cache_storage": storage_usd,
                         "per_record": round(total_cost / len(self.records), 6) if self.records else None,
                         "per_call": round(total_cost / len(calls), 6) if calls else None,
                         "vendor_reported_total": round(sum(vendor_costs), 6) if vendor_costs else None,
                         "vendor_reported_calls": len(vendor_costs),
                         "price_source": "prices.json in this directory"},
            "accuracy": {"on_run_1": acc_block(run1, "repeat index 0 only"),
                         "on_mean_of_runs": acc_block(mean_pred, "per-record mean over parsed repeats; tier by majority vote")},
            "determinism": M.determinism(by_rec),
            "records": [{"record_id": r["record_id"], "teacher": {"dimensions": r["dimensions"], "composite": r["composite"], "tier": r["tier"]},
                         "predictions": by_rec.get(r["record_id"], [])} for r in self.records],
        }

    def method_note(self, s: dict) -> str:
        c, cache, lat, cost, st = s["counts"], s["cache"], s["latency_ms"], s["cost_usd"], s["settings"]
        pt = self.price_table
        vendor = {"anthropic": "Anthropic", "openai": "OpenAI", "xai": "xAI", "gemini": "Google"}[self.provider]
        ids = self.ids_source or {}
        if ids.get("source_run_id"):
            sample_line = (f"the byte-identical record list of run `{ids['source_run_id']}` (read from its calls.jsonl, sha256 "
                           f"{ids['calls_file_sha256']}; that run drew them from {ids.get('source_ids_source', {}).get('spec')} stratified by teacher tier with seed {self.seed})")
        elif ids:
            sample_line = f"`{self.input_path}` stratified by teacher tier with seed {self.seed}, restricted to the ids in {ids['spec']} (split file sha256 {ids.get('split_file_sha256')})"
        else:
            sample_line = f"`{self.input_path}` stratified by teacher tier with seed {self.seed}"
        if self.provider == "anthropic":
            settings_line = (f"thinking adaptive; effort {st['effort']}; max_tokens {self.max_tokens}; temperature not settable under adaptive thinking "
                             f"(not sent); structured output via `output_config.format` (JSON schema: eight integer dimensions 0-100, integer composite 0-100, "
                             f"tier enum of five); streaming with `get_final_message`; betas `{st['betas'][0]}` with `fallbacks: \"default\"`; one `cache_control` "
                             f"ephemeral breakpoint on the system block; concurrency {self.concurrency} with the first call run alone to warm the cache")
            cache_line = (f"Cache: first call wrote {cache['first_call_cache_creation_input_tokens']} tokens; {cache['later_calls_with_cache_read']} of "
                          f"{cache['later_calls']} later calls read the cache (verified from the second call on: {cache['cache_verified_from_second_call']}).")
        else:
            settings_line = (f"{st['thinking']['type']}; max output tokens {self.max_tokens} (`{st.get('max_tokens_param', 'max_output_tokens')}`); "
                             f"temperature {st['temperature_requested']} requested, accepted by the API: {st['temperature_settable']} "
                             f"(observed across calls: {st['temperature_settable_observed']})"
                             + (f"; vendor advice noted: {st['temperature_vendor_advice']}" if st.get("temperature_vendor_advice") else "")
                             + f"; structured output via {st['structured_output']} (same JSON schema: eight integer dimensions, integer composite, tier enum of five); "
                             f"endpoint {st['endpoint']}; concurrency {self.concurrency}")
            cache_line = (f"Prompt caching: {cache['mechanism']}; {cache['later_calls_with_cache_read']} of {cache['later_calls']} later calls reported cached "
                          f"prompt tokens ({s['tokens']['cache_read']} cached tokens in total, priced at the vendor's cached-input row).")
        served = f" The requested id is served today as `{pt['model_served_as']}`." if pt.get("model_served_as") else ""
        flagship = pt.get("vendor_flagship_on_retrieval_date")
        flagship_line = (f"The vendor's flagship on {pt['retrieved_on']} was `{flagship['id']}` ({flagship['source']}); the Gauntlet id was kept, not switched."
                         if flagship else "")
        vendor_cost = (f" The vendor's own per-call bill (`usage.cost_in_usd_ticks`) summed to ${cost['vendor_reported_total']} over {cost['vendor_reported_calls']} calls."
                       if cost.get("vendor_reported_total") is not None else "")
        if self.examples:
            ex = s["examples"]
            arm_title = "LLM comparison arm g2-examples"
            given_line = (f"POST-HOC ARM (PROTOCOL amendment 1, row 17). This arm was added after the arm g results of all four vendors had been read, at the\n"
                          f"author's request, to make the information given to the models comparable to the training labels given to the local arms\n"
                          f"(\"why didn't we make it 1:1\", JAS, 2026-09-21). Everything is identical to arm g except the system prefix, which carries, between the\n"
                          f"paper text and the same instruction block, a fixed block of E = {ex['E']} engine-scored examples drawn from the TRAINING split of seed 1\n"
                          f"(`{ex['source_split']}`, split file sha256 {ex['split_file_sha256']}), stratified by tier ({json.dumps(ex['per_tier'])}), selected with\n"
                          f"seed {ex['selection_seed']} (record-id list sha256 {ex['record_ids_sha256']}; ids in `examples.json`), identical across vendors and repeats.\n"
                          f"Each example shows RECORD and CONTEXT exactly as a scored record does, followed by the engine's eight dimensions, composite, and tier.\n"
                          f"Leakage check before the first call: {ex['leakage_check']['overlap_with_scored']} example ids among the {ex['leakage_check']['scored_ids']} scored ids,\n"
                          f"{ex['leakage_check']['overlap_with_test_split']} among the {ex['leakage_check']['test_split_ids']} ids of the whole TEST split.\n"
                          f"E was chosen as the largest of {{50, 100, 200}} keeping the prefix under 150,000 tokens for every vendor and under each vendor's context limit\n"
                          f"with margin (`llm_arm/examples_budget.json`, `scripts/choose_examples_e.py`); this vendor's prefix measured {(ex.get('prefix_tokens_measured') or {}).get(self.provider)} tokens\n"
                          f"by {ex.get('prefix_token_counter')}, and the first call's usage reported {ex.get('prefix_tokens_observed_first_call')} prompt tokens (prefix + record).\n"
                          f"Base prompt (arm g, without the examples) sha256: `{self.base_prompt_hash}`, asserted equal to the source run's before any call.")
            if self.provider == "gemini" and cache.get("explicit_cache"):
                ec2 = cache["explicit_cache"]
                cache_line += (f" Explicit CachedContent `{ec2.get('name')}` held the system prefix ({ec2.get('token_count')} tokens) from {ec2.get('created_utc')} to "
                               f"{ec2.get('deleted_utc')} ({ec2.get('hours_held')} h; storage ${cost.get('cache_storage')} at ${pt.get('usd_per_mtok_hour_cache_storage')} per MTok-hour, included in the total); "
                               f"{cache['calls_with_cache_read']} of {c['calls_total']} calls reported cached_content_token_count.")
        else:
            arm_title = "LLM comparison arm"
            given_line = ("The model was given the published DTI paper (sections 3 and 4, framework and scoring methodology, verbatim from\n"
                          f"`{build_system_prompt.__module__}` reading `/Users/jas/Projects/supertruth-dti/paper.md`) followed by a fixed\n"
                          "instruction block, and the same records the other arms saw. No examples, no teacher outputs, no implementation hints.")
        return f"""# How we ran this: {arm_title} ({vendor})

Run id: {self.run_id} (UTC). Date: {self.run_id[:4]}-{self.run_id[4:6]}-{self.run_id[6:8]}. Arm: {self.arm}.

Provider: {vendor}. Model string requested: `{self.model}`. Response `model` field(s): {json.dumps(s["response_models"])}.{served}
{flagship_line}

Account: SuperTruth's own API account with each vendor (credentials from the environment; no key stored in code or files).

{given_line}

Settings: {settings_line}; SDK retries on 429/5xx/connection errors plus one outer retry; refusals never retried. SDK: {st['sdk']}.

System prompt sha256: `{self.prompt_hash}` (full text in `system_prompt.txt`; identical across every provider's run by assertion).

Records: N = {len(self.records)} requested {self.n_requested}, from {sample_line}; k = {self.k} identical calls per record; payload field `{self.payload_field}`;
scoring date given to the model (as_of) `{self.as_of}`.

Calls: {c["calls_total"]} total, {c["calls_parsed_ok"]} parsed, {c["parse_failures"]} parse failures,
{c["refusals"]} refusals, {c["errors"]} errors, {c["fallback_calls"]} served by a fallback model. Finish reasons: {json.dumps(c["finish_reasons"])}.
{cache_line}
Tokens: input {s["tokens"]["input"]} (uncached), cached {s["tokens"]["cache_read"]}, output {s["tokens"]["output"]} (of which reasoning/thinking {s["tokens"]["reasoning"]}).
Latency: median {lat["median"]} ms, p95 {lat["p95"]} ms over {lat["n"]} calls.
Cost: ${cost["total"]} total, ${cost["per_record"]} per record, priced from `prices.json` ({pt["retrieved_from"]},
retrieved {pt["retrieved_on"]}; source URLs inside).{vendor_cost}

Data class: SYNTHETIC, zero PHI. Full per-call log: `calls.jsonl`. Metrics: `summary.json`.
"""

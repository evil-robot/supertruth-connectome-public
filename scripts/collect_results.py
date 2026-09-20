"""Aggregate runs/{task}/{arm}/seed*/metrics.json + the LLM arm summary into results/results.json (the schema
viz/results.schema.json expects) and results/RESULTS.md (decision rules evaluated, provenance footer under every
table). Partial results are marked "awaiting run"; nothing is estimated.

  .venv/bin/python scripts/collect_results.py [--llm-run llm_arm/llm_runs/<id>]...

Language-model arms: one row per model (anthropic, openai, xai, gemini). By default the newest complete protocol run
(N = 300, k x N calls logged) per provider AND arm is used; --llm-run may be repeated to pin a run for its provider and arm.
Arm g2-examples (post-hoc, amendment 1 row 17) lands beside arm g as anthropic_ex, openai_ex, xai_ex, gemini_ex with the same
metrics plus extra.frontier.<id>_ex.gain_vs_g: the paired per-record comparison with arm g on the identical 300 records
(composite-error difference with a t-interval over records; tier-agreement difference with discordant counts and exact McNemar p).

Also written (for scripts/render_results.py): extra.paired = per-seed paired differences control - connectome on every
headline-adjacent metric with t-intervals; decision rows for the matched MLP (framing, descriptive) and for the composite
recomputed from predicted dimensions; raw and Holm-adjusted one-sided paired-t p-values for the primary family once n >= 2.

Headline composite (DECISIONS 2026-09-20 "composite head"): dti_mae = composite RECOMPUTED from the predicted dimensions with the
engine's weights; dti_mae_direct = the directly predicted head, kept beside it. Same-record block: extra.local.<arm>.dti.subset300
from runs/<task>/<arm>/seed*/metrics_subset300.json (scripts/eval_subset.py, the language-model arm's exact 300 ids).
Hierarchical bootstrap (PROTOCOL 8.2) runs from per_record.parquet once >= 2 seeds have it (ci_bootstrap on paired rows).

CI: two-sided 95% t-interval over seeds (mean +/- t_{0.975,n-1} * sd / sqrt(n)); null when n < 2. The protocol's
primary CI (hierarchical bootstrap, section 8.2) is for the full 5-seed analysis; this file says which it used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import t as student_t

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.data_adapters import DTI_DIMS, MANIFEST_SHA256, TEACHER_FILE   # noqa: E402
from flytrust.graph import ROOT, sha256_file                                  # noqa: E402
from llm_arm import metrics as LM                                             # noqa: E402  (the runner's mean-of-runs rule, for paired g vs g2)
from llm_arm.prompt import DIMS as LM_DIMS                                    # noqa: E402

ARM_ID = {"connectome": "connectome", "shuffle": "shuffled", "er": "random", "mlp": "mlp", "ridge": "linear"}
ARMS = [
    {"id": "connectome", "label": "Connectome (MaleCNS wiring, fixed)"},
    {"id": "shuffled", "label": "Degree-preserving shuffle"},
    {"id": "random", "label": "Random graph, matched density"},
    {"id": "mlp", "label": "MLP, matched parameters"},
    {"id": "linear", "label": "Linear readout"},
    {"id": "anthropic", "label": "Claude Opus 5 given the DTI paper", "provider": "anthropic", "model": "claude-opus-5", "arm": "g"},
    {"id": "openai", "label": "GPT-5 given the DTI paper", "provider": "openai", "model": "gpt-5", "arm": "g"},
    {"id": "xai", "label": "Grok 4 given the DTI paper", "provider": "xai", "model": "grok-4", "arm": "g"},
    {"id": "gemini", "label": "Gemini 3 Flash given the DTI paper", "provider": "gemini", "model": "gemini-3-flash-preview", "arm": "g"},
    # post-hoc arm g2-examples (amendment 1, row 17): same models, same 300 ids, same prompt plus E scored TRAIN examples in the prefix
    {"id": "anthropic_ex", "label": "Claude Opus 5 given the DTI paper and scored examples", "provider": "anthropic", "model": "claude-opus-5", "arm": "g2-examples", "base": "anthropic"},
    {"id": "openai_ex", "label": "GPT-5 given the DTI paper and scored examples", "provider": "openai", "model": "gpt-5", "arm": "g2-examples", "base": "openai"},
    {"id": "xai_ex", "label": "Grok 4 given the DTI paper and scored examples", "provider": "xai", "model": "grok-4", "arm": "g2-examples", "base": "xai"},
    {"id": "gemini_ex", "label": "Gemini 3 Flash given the DTI paper and scored examples", "provider": "gemini", "model": "gemini-3-flash-preview", "arm": "g2-examples", "base": "gemini"},
]
MODEL_ARMS = [a for a in ARMS if a.get("provider") and a["arm"] == "g"]
EXAMPLE_ARMS = [a for a in ARMS if a.get("provider") and a["arm"] == "g2-examples"]


def run_key(summary: dict) -> str:
    return f"{summary.get('provider', 'anthropic')}:{summary.get('arm', 'g')}"
PROTOCOL_N = 300
METRICS = [
    {"id": "dti_mae", "label": "DTI composite recomputed from the predicted dimensions, mean absolute error (headline; DECISIONS 'composite head')", "unit": "points (0 to 100)", "better": "lower", "domain": [0, None]},
    {"id": "dti_mae_direct", "label": "DTI composite, directly predicted head, mean absolute error", "unit": "points (0 to 100)", "better": "lower", "domain": [0, None]},
    {"id": "dti_dim_mae", "label": "DTI per-dimension mean absolute error", "unit": "points", "better": "lower", "domain": [0, None],
     "dimensions": [d.capitalize() for d in DTI_DIMS]},
    {"id": "dti_tier_accuracy", "label": "DTI tier agreement with teacher", "unit": "share of records", "better": "higher", "domain": [0, 1]},
    {"id": "bii_mae", "label": "BII, mean absolute error", "unit": "score units (0 to 1)", "better": "lower", "domain": [0, None]},
    {"id": "bii_gate_accuracy", "label": "BII gate agreement with teacher", "unit": "share of windows", "better": "higher", "domain": [0, 1]},
    {"id": "latency_ms", "label": "Latency per record", "unit": "ms", "better": "lower", "domain": [0, None]},
    {"id": "usd_per_record", "label": "Cost per record", "unit": "USD", "better": "lower", "domain": [0, None]},
    {"id": "determinism", "label": "Determinism: identical output on repeat", "unit": "share of records", "better": "higher", "domain": [0, 1]},
]
NULL = {"mean": None, "ci_low": None, "ci_high": None, "n": None}
AS_OF = "2026-09-20T00:00:00Z"
POLICY_DIGEST = "5d8db364...8573859"       # PROTOCOL 1.4; full digest pinned in vigil/tests/test_policy.py
FOOTER_SOURCE = "MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)"


# ------------------------------------------------------------------ statistics
def t_ci(values: list[float]) -> dict:
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n = len(vals)
    if n == 0:
        return dict(NULL)
    mean = statistics.fmean(vals)
    if n < 2:
        return {"mean": mean, "ci_low": None, "ci_high": None, "n": n}
    sd = statistics.stdev(vals)
    half = student_t.ppf(0.975, n - 1) * sd / math.sqrt(n)
    return {"mean": mean, "ci_low": mean - half, "ci_high": mean + half, "n": n, "sd": sd}


def determinism_verdict(connectome: float, model: float) -> str:
    """the comparative determinism claim is made (PASS) or not made, never 'failed': the gate is a claim gate, and the reason is printed"""
    if connectome == 1.0 and model < 0.90:
        return "PASS"
    if model >= 0.90:
        return f"NOT CLAIMED (model {model:.3f}, above 0.90)"
    return f"NOT CLAIMED (connectome {connectome:.3f}, below 1.00)"


def wilson(p: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


# ------------------------------------------------------------------ inputs
def load_runs() -> dict:
    """runs[task][arm] = {seed: metrics}"""
    runs = {"dti": {}, "bii": {}}
    for p in sorted((ROOT / "runs").glob("*/*/seed*/metrics.json")):
        task, arm, seed_dir = p.parts[-4], p.parts[-3], p.parts[-2]
        if task not in runs or arm not in ARM_ID:
            continue
        runs[task].setdefault(arm, {})[int(seed_dir[4:])] = json.loads(p.read_text())
    return runs


def _complete(summary: dict) -> bool:
    return summary["counts"]["calls_total"] >= summary["input"]["n_records"] * summary["input"]["k"]


def llm_runs_by_provider(explicit: list[Path]) -> dict[str, tuple[Path, dict]]:
    """'provider:arm' -> (run dir, summary). Protocol runs only: an id source and N >= PROTOCOL_N records (smoke runs are
    skipped). Newest complete run wins; a newest partial run is used only when no complete one exists."""
    out: dict[str, tuple[Path, dict]] = {}
    for c in sorted((ROOT / "llm_arm" / "llm_runs").glob("*/summary.json"), key=lambda p: p.parent.name):
        d = json.loads(c.read_text())
        inp = d.get("input", {})
        if not inp.get("ids_source") or inp.get("n_records", 0) < PROTOCOL_N:
            continue
        key = run_key(d)
        prev = out.get(key)
        if prev is None or _complete(d) or not _complete(prev[1]):
            out[key] = (c.parent, d)
    for e in explicit:
        d = json.loads((e / "summary.json").read_text())
        out[run_key(d)] = (e, d)
    return out


def _mean_of_runs(summary: dict) -> dict[str, dict]:
    """record_id -> the per-record mean-of-repeats prediction, by the runner's rule (llm_arm.runner.summarise)."""
    out = {}
    for rec in summary["records"]:
        outs = rec["predictions"]
        if not outs:
            continue
        dims = {d: LM.js_round(sum(o["dimensions"][d] for o in outs) / len(outs)) for d in LM_DIMS}
        comp = LM.js_round(sum(o["composite"] for o in outs) / len(outs))
        tier, tie = LM.majority([o["tier"] for o in outs])
        out[rec["record_id"]] = {"dimensions": dims, "composite": comp, "tier": LM.tier_from_composite(comp) if tie else tier,
                                 "teacher": rec["teacher"]}
    return out


def paired_gain(g: dict, g2: dict) -> dict:
    """Arm g2 against arm g on the identical records (both scored the same 300 ids): per-record differences, oriented so that a
    positive value means the examples helped. Composite: |err_g| - |err_g2| on the recomputed composite with a two-sided 95% t-interval
    over records. Tier: acc(g2) - acc(g) with the discordant counts and the exact (binomial) McNemar p, since the two arms are paired."""
    from scipy.stats import binomtest
    A, B = _mean_of_runs(g), _mean_of_runs(g2)
    ids = sorted(set(A) & set(B))
    if not ids:
        return {"n_records": 0}
    err = lambda p: abs(LM.recompute_composite(p["dimensions"]) - p["teacher"]["composite"])
    d_comp = [err(A[i]) - err(B[i]) for i in ids]
    d_direct = [abs(A[i]["composite"] - A[i]["teacher"]["composite"]) - abs(B[i]["composite"] - B[i]["teacher"]["composite"]) for i in ids]
    ok_a = [A[i]["tier"] == A[i]["teacher"]["tier"] for i in ids]
    ok_b = [B[i]["tier"] == B[i]["teacher"]["tier"] for i in ids]
    b = sum(1 for x, y in zip(ok_a, ok_b) if y and not x)   # g2 right, g wrong
    c = sum(1 for x, y in zip(ok_a, ok_b) if x and not y)   # g right, g2 wrong
    p = float(binomtest(min(b, c), b + c, 0.5).pvalue) if b + c else None
    return {"n_records": len(ids), "orientation": "positive = examples helped (g minus g2 on error; g2 minus g on agreement)",
            "composite_mae_gain": t_ci(d_comp), "composite_mae_direct_gain": t_ci(d_direct),
            "tier_acc_gain": {"mean": (sum(ok_b) - sum(ok_a)) / len(ids), "g": sum(ok_a) / len(ids), "g2": sum(ok_b) / len(ids),
                              "discordant_g2_only": b, "discordant_g_only": c, "mcnemar_exact_p": p,
                              "method": "paired on records; exact McNemar (two-sided binomial on the discordant pairs)"},
            "g_run": g["run_id"], "g2_run": g2["run_id"]}


def teacher_shas() -> dict:
    row = re.search(r"^\| Engine git SHA \| `([0-9a-f]+)`.*?\| `([0-9a-f]+)`", (ROOT / "teachers" / "MANIFEST.md").read_text(), re.M)
    return {"dti": row.group(1) if row else "unknown", "bii": row.group(2) if row else "unknown"}


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


# ------------------------------------------------------------------ aggregation
def aggregate(runs: dict, llm_runs: dict[str, tuple[Path, dict]], bench: dict | None) -> dict:
    results = {a["id"]: {m["id"]: (dict(NULL) if m["id"] != "dti_dim_mae" else {"per_dimension": []}) for m in METRICS} for a in ARMS}
    extra = {"local": {}, "frontier": {}}
    seeds_seen = set()
    for arm, aid in ARM_ID.items():
        for task in ("dti", "bii"):
            by_seed = runs[task].get(arm, {})
            if not by_seed:
                continue
            seeds = sorted(by_seed)
            seeds_seen.update(seeds)
            ms = [by_seed[s] for s in seeds]
            ex = extra["local"].setdefault(aid, {}).setdefault(task, {})
            ex.update({
                "seeds": seeds,
                "trainable_params": ms[0].get("trainable_params"), "fitted_params": ms[0].get("fitted_params"),
                "epochs_run": [m["epochs_run"] for m in ms], "best_epoch": [m["best_epoch"] for m in ms],
                "wall_seconds_total": [m["wall_seconds"]["total"] for m in ms],
                "peak_device_gb": [round(m["peak_device_bytes_sampled"] / 1e9, 2) for m in ms],
                "deterministic_test_forward": [m["deterministic_test_forward"] for m in ms],
                "macro_f1": t_ci([m[f"{'tier' if task == 'dti' else 'gate'}_macro_f1"] for m in ms]),
                "ece": t_ci([m["calibration"]["ece"] for m in ms]), "brier": t_ci([m["calibration"]["brier"] for m in ms]),
                "mean_confidence": t_ci([m["calibration"]["mean_confidence"] for m in ms]),
                "test_loss": t_ci([m["test_loss"] for m in ms]),
            })
            if task == "dti":
                results[aid]["dti_mae"] = t_ci([m["composite_mae_recomputed_from_dims"] for m in ms])
                results[aid]["dti_mae"]["per_seed"] = {str(s): by_seed[s]["composite_mae_recomputed_from_dims"] for s in seeds}
                results[aid]["dti_mae_direct"] = t_ci([m["composite_mae_direct"] for m in ms])
                results[aid]["dti_mae_direct"]["per_seed"] = {str(s): by_seed[s]["composite_mae_direct"] for s in seeds}
                ex["composite_mae_recomputed_from_dims"] = t_ci([m["composite_mae_recomputed_from_dims"] for m in ms])
                ex["composite_mae_direct"] = t_ci([m["composite_mae_direct"] for m in ms])
                sub = [json.loads((ROOT / "runs" / task / arm / f"seed{s}" / "metrics_subset300.json").read_text())
                       for s in seeds if (ROOT / "runs" / task / arm / f"seed{s}" / "metrics_subset300.json").exists()]
                sub = [x for x in sub if "tier_acc" in x]
                if sub:
                    n_sub = sub[0]["n_test"]
                    ex["subset300"] = {"seeds": [x["seed"] for x in sub], "n_records": n_sub, "ids_source": sub[0]["ids_source"],
                                       "record_ids_sha256": sub[0].get("record_ids_sha256"), "reason": sub[0].get("reason"),
                                       "composite_mae_recomputed_from_dims": t_ci([x["composite_mae_recomputed_from_dims"] for x in sub]),
                                       "composite_mae_direct": t_ci([x["composite_mae_direct"] for x in sub]),
                                       "tier_acc": t_ci([x["tier_acc"] for x in sub]), "tier_macro_f1": t_ci([x["tier_macro_f1"] for x in sub]),
                                       "dims_mae_mean": t_ci([x["dims_mae_mean"] for x in sub]),
                                       "tier_acc_wilson_mean_over_seeds": list(wilson(statistics.fmean(x["tier_acc"] for x in sub), n_sub))}
                results[aid]["dti_dim_mae"] = {"per_dimension": [t_ci([m["dims_mae"][d] for m in ms]) for d in DTI_DIMS], "n": len(seeds)}
                ex["dims_mae_per_seed"] = {d: [m["dims_mae"][d] for m in ms] for d in DTI_DIMS}
                results[aid]["dti_tier_accuracy"] = t_ci([m["tier_acc"] for m in ms])
                results[aid]["dti_tier_accuracy"]["per_seed"] = {str(s): by_seed[s]["tier_acc"] for s in seeds}
            else:
                results[aid]["bii_mae"] = t_ci([m["bii_mae"] for m in ms])
                results[aid]["bii_mae"]["per_seed"] = {str(s): by_seed[s]["bii_mae"] for s in seeds}
                results[aid]["bii_gate_accuracy"] = t_ci([m["gate_acc"] for m in ms])
                results[aid]["bii_gate_accuracy"]["per_seed"] = {str(s): by_seed[s]["gate_acc"] for s in seeds}
            # determinism: bitwise-identical repeat on one TEST batch per seed (all-or-nothing per batch)
            det = [1.0 if m["deterministic_test_forward"] else 0.0 for m in ms]
            n_rec = sum(m["batch"] for m in ms)
            prev = results[aid]["determinism"]
            if prev["mean"] is None:
                results[aid]["determinism"] = {"mean": statistics.fmean(det), "ci_low": None, "ci_high": None, "n": n_rec,
                                               "method": "two forward passes on one TEST batch per seed, bitwise equal (torch.equal)"}
            # cost: $0.00 marginal API spend (protocol 6); hardware line not measured
            results[aid]["usd_per_record"] = {"mean": 0.0, "ci_low": None, "ci_high": None, "n": ms[0]["n_test"],
                                              "note": "marginal API spend; hardware power not measured (protocol 6)"}
    # latency: measured by flytrust/bench_speed.py on the real graph (connectome forward); other arms not measured
    if bench:
        b1 = bench["forward"]["1"]; b256 = bench["forward"]["256"]
        results["connectome"]["latency_ms"] = {"mean": b1["latency_per_record_ms"], "ci_low": None, "ci_high": None, "n": 1,
                                               "method": "median forward latency at batch 1 (runs/bench_speed.json)",
                                               "batch_256_per_record_ms": b256["latency_per_record_ms"]}
    # language-model arms, one row per provider and arm (g, then the post-hoc g2-examples beside it)
    for arm in MODEL_ARMS + EXAMPLE_ARMS:
        key = f"{arm['provider']}:{arm['arm']}"
        if key not in llm_runs:
            continue
        llm_dir, llm = llm_runs[key]
        acc = llm["accuracy"]["on_mean_of_runs"]
        acc1 = llm["accuracy"]["on_run_1"]
        n_rec = acc.get("records", 0)
        f = results[arm["id"]]
        if n_rec:
            f["dti_mae"] = {"mean": acc["composite_mae_recomputed_from_predicted_dims"], "ci_low": None, "ci_high": None, "n": n_rec,
                            "basis": acc["basis"], "run_1_only": acc1.get("composite_mae_recomputed_from_predicted_dims")}
            f["dti_mae_direct"] = {"mean": acc["composite_mae_direct"], "ci_low": None, "ci_high": None, "n": n_rec,
                                   "basis": acc["basis"], "run_1_only": acc1.get("composite_mae_direct")}
            f["dti_dim_mae"] = {"per_dimension": [{"mean": acc["mae_per_dimension"][d], "ci_low": None, "ci_high": None} for d in DTI_DIMS], "n": n_rec}
            lo, hi = wilson(acc["tier_accuracy"], n_rec)
            f["dti_tier_accuracy"] = {"mean": acc["tier_accuracy"], "ci_low": lo, "ci_high": hi, "n": n_rec, "ci_method": "Wilson over records",
                                      "run_1_only": acc1.get("tier_accuracy")}
        lat = llm["latency_ms"]
        f["latency_ms"] = {"mean": lat["median"], "ci_low": None, "ci_high": None, "n": lat["n"], "p95": lat["p95"], "method": "median wall clock per call"}
        prices = json.loads((llm_dir / "prices.json").read_text())
        f["usd_per_record"] = {"mean": llm["cost_usd"]["per_record"], "ci_low": None, "ci_high": None, "n": llm["input"]["n_records"],
                               "price_source": f"{llm_dir.name}/prices.json ({prices['retrieved_from']}, retrieved {prices['retrieved_on']})"}
        det = llm["determinism"]
        n_det = det.get("records_with_2plus_outputs", 0)
        if n_det:
            lo, hi = wilson(det["tier_identical_share"], n_det)
            f["determinism"] = {"mean": det["tier_identical_share"], "ci_low": lo, "ci_high": hi, "n": n_det,
                                "composite_range_mean": det["composite_range_mean"], "method": "share of records with identical tier across k repeats"}
        tok = llm["tokens"]; n_rec_in = llm["input"]["n_records"] or 1
        extra["frontier"][arm["id"]] = {"determinism_exact_match_share": det.get("exact_match_share"), "determinism_tier_identical_share": det.get("tier_identical_share"),
                                        "determinism_records": n_det, "composite_range_mean": det.get("composite_range_mean"),
                                        "per_dimension_sd_mean": det.get("per_dimension_sd_mean"),
                                        "latency_ms_median": lat["median"], "latency_ms_p95": lat["p95"], "latency_calls": lat["n"],
                                        "tokens_per_record": {k: v / n_rec_in for k, v in tok.items()},
                                        "usd_per_record": llm["cost_usd"]["per_record"], "usd_per_call": llm["cost_usd"].get("per_call"),
                                        "run": llm_dir.name, "provider": arm["provider"], "model_requested": llm["model_requested"],
                                        "response_models": llm["response_models"],
                                        "settings": llm["settings"], "counts": llm["counts"], "cache": llm["cache"], "tokens": llm["tokens"],
                                        "cost_usd_total": llm["cost_usd"]["total"], "prompt_sha256": llm["prompt_sha256"],
                                        "ids_source": llm["input"].get("ids_source"), "macro_f1_mean_of_runs": acc.get("tier_macro_f1"),
                                        "n_records": llm["input"]["n_records"], "k": llm["input"]["k"], "complete": _complete(llm),
                                        "arm": arm["arm"], "post_hoc": arm["arm"] != "g"}
        if arm["arm"] == "g2-examples":
            fx = extra["frontier"][arm["id"]]
            fx.update({"base_arm": arm["base"], "examples": llm.get("examples"), "base_prompt_sha256": llm.get("base_prompt_sha256"),
                       "cost_usd_cache_storage": llm["cost_usd"].get("cache_storage"),
                       "cache_hit_share": (llm["cache"].get("calls_with_cache_read") or 0) / max(llm["counts"]["calls_total"], 1)})
            g_key = f"{arm['provider']}:g"
            fx["gain_vs_g"] = paired_gain(llm_runs[g_key][1], llm) if g_key in llm_runs else None
    extra["paired"] = paired_deltas(runs)
    return results, extra, sorted(seeds_seen)


PAIRED_METRICS = {"dti": ["composite_mae_direct", "composite_mae_recomputed_from_dims", "dims_mae_mean", "tier_acc"],
                  "bii": ["bii_mae", "gate_acc"]}
HIGHER_IS_BETTER = {"tier_acc", "gate_acc"}


def paired_deltas(runs: dict) -> dict:
    """paired[task][control_arm_id][metric] = per-seed differences on the seeds both arms have finished, oriented so that
    a positive value means the connectome did better (MAE(control) - MAE(connectome); acc(connectome) - acc(control)),
    with the t-interval over seeds (null when one seed) and the count of seeds on which the connectome was better."""
    out = {}
    for task, metrics in PAIRED_METRICS.items():
        A = runs[task].get("connectome", {})
        for arm, aid in ARM_ID.items():
            if arm == "connectome":
                continue
            B = runs[task].get(arm, {})
            common = sorted(set(A) & set(B))
            if not common:
                continue
            for key in metrics:
                if key in HIGHER_IS_BETTER:
                    d = {s: A[s][key] - B[s][key] for s in common}
                else:
                    d = {s: B[s][key] - A[s][key] for s in common}
                row = t_ci(list(d.values()))
                bs = hier_bootstrap(task, "connectome", arm, key)
                if bs:
                    row.update({"ci_bootstrap_low": bs["ci_low"], "ci_bootstrap_high": bs["ci_high"], "ci_bootstrap_method": bs["method"]})
                row.update({"per_seed": {str(s): v for s, v in d.items()}, "seeds": common,
                            "connectome_better_seeds": sum(v > 0 for v in d.values()),
                            "orientation": "positive = connectome better"})
                out.setdefault(task, {}).setdefault(aid, {})[key] = row
    return out


PER_RECORD_COL = {"composite_mae_recomputed_from_dims": "abs_err_composite_recomputed", "composite_mae_direct": "abs_err_composite_direct",
                  "bii_mae": "abs_err_bii", "dims_mae_mean": None, "tier_acc": "tier_correct", "gate_acc": "gate_correct"}


def hier_bootstrap(task: str, a_arm: str, b_arm: str, key: str, B: int = 10_000, seed: int = 20260920, min_seeds: int = 2) -> dict | None:
    """PROTOCOL 8.2 primary CI: percentile bootstrap resampling seeds with replacement, then records within TEST (paired: the
    same resampled records for both arms in a seed), B replicates, on the per-seed per-record paired difference
    control - connectome (positive = connectome better; accuracy columns are oriented the same way). Needs
    runs/<task>/<arm>/seed*/per_record.parquet (scripts/eval_subset.py) for >= min_seeds common seeds; returns None otherwise."""
    col = PER_RECORD_COL.get(key)
    if col is None:
        return None
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return None
    a_id = {v: k for k, v in ARM_ID.items()}.get(a_arm, a_arm); b_id = {v: k for k, v in ARM_ID.items()}.get(b_arm, b_arm)
    rows = []
    for pa_ in sorted((ROOT / "runs" / task / a_id).glob("seed*/per_record.parquet")):
        pb_ = ROOT / "runs" / task / b_id / pa_.parts[-2] / "per_record.parquet"
        if not pb_.exists():
            continue
        ta = pq.read_table(pa_, columns=["record_id", col]).to_pandas().set_index("record_id")
        tb = pq.read_table(pb_, columns=["record_id", col]).to_pandas().set_index("record_id").reindex(ta.index)
        if tb[col].isna().any():
            raise SystemExit(f"per_record.parquet record sets differ: {pa_} vs {pb_}")
        va, vb = ta[col].to_numpy(dtype=float), tb[col].to_numpy(dtype=float)
        rows.append((va - vb) if col.endswith("_correct") else (vb - va))
    if len(rows) < min_seeds:
        return None
    import numpy as np
    D = np.stack(rows); n, R = D.shape
    rng = np.random.default_rng(seed)
    stats = np.empty(B)
    for b in range(B):
        si = rng.integers(0, n, size=n)
        ri = rng.integers(0, R, size=(n, R))
        stats[b] = D[si[:, None], ri].mean()
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return {"ci_low": float(lo), "ci_high": float(hi), "mean": float(D.mean()), "n_seeds": n, "n_records": R, "B": B,
            "method": f"hierarchical percentile bootstrap, seeds then records, B={B}, rng seed {seed} (PROTOCOL 8.2)"}


def holm(pvals: dict) -> dict:
    """Holm step-down adjusted p-values for a family (rule 19)."""
    items = sorted((p, k) for k, p in pvals.items() if p is not None)
    m = len(items); adj = {}; running = 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return adj


# ------------------------------------------------------------------ decision rules (PROTOCOL 8.1)
def verdict(cond_point, cond_ci, n_seeds, need=5):
    if cond_point is None:
        return "AWAITING RUN"
    if n_seeds is not None and n_seeds < need:
        return f"INSUFFICIENT SEEDS ({n_seeds}/{need}; point estimate {'meets' if cond_point else 'misses'} the bar)"
    if cond_ci is False:
        return "FAIL"
    return "PASS" if cond_point else "FAIL"


def decision_rules(runs: dict, results: dict, extra: dict) -> list[dict]:
    rows = []
    a = results["connectome"]; ex = extra["local"].get("connectome", {})

    def paired_delta(task: str, other: str, key: str):
        A, B = runs[task].get("connectome", {}), runs[task].get(other, {})
        common = sorted(set(A) & set(B))
        if not common:
            return None, None, None
        d = [B[s][key] - A[s][key] for s in common]
        return t_ci(d), all(x > 0 for x in d), common

    # DTI: recovers the engine
    m = a["dti_mae"]; n = m["n"]
    rows.append({"task": "dti", "claim": "Fly recovers the DTI engine", "metric": "composite MAE, recomputed from predicted dims (headline; TEST, mean over seeds)",
                 "threshold": "<= 2.5 and CI upper <= 3.0", "value": m["mean"], "ci": [m["ci_low"], m["ci_high"]], "n_seeds": n,
                 "verdict": verdict(None if m["mean"] is None else m["mean"] <= 2.5, None if m["ci_high"] is None else m["ci_high"] <= 3.0, n)})
    acc = a["dti_tier_accuracy"]
    wl = wh = None
    if acc["mean"] is not None:
        n_test = runs["dti"]["connectome"][min(runs["dti"]["connectome"])]["n_test"]
        wl, wh = wilson(acc["mean"], n_test)
    rows.append({"task": "dti", "claim": "same", "metric": "tier accuracy", "threshold": ">= 0.90, Wilson lower >= 0.88 (n = TEST records)",
                 "value": acc["mean"], "ci": [wl, wh], "n_seeds": acc["n"],
                 "verdict": verdict(None if acc["mean"] is None else acc["mean"] >= 0.90, None if wl is None else wl >= 0.88, acc["n"])})
    f1 = ex.get("dti", {}).get("macro_f1", NULL)
    rows.append({"task": "dti", "claim": "same", "metric": "macro-F1 (tiers with support >= 30)", "threshold": ">= 0.85",
                 "value": f1["mean"], "ci": [f1.get("ci_low"), f1.get("ci_high")], "n_seeds": f1["n"],
                 "verdict": verdict(None if f1["mean"] is None else f1["mean"] >= 0.85, None, f1["n"])})
    ece = ex.get("dti", {}).get("ece", NULL)
    rows.append({"task": "dti", "claim": "same", "metric": "ECE (10 equal-mass bins)", "threshold": "<= 0.05",
                 "value": ece["mean"], "ci": [ece.get("ci_low"), ece.get("ci_high")], "n_seeds": ece["n"],
                 "verdict": verdict(None if ece["mean"] is None else ece["mean"] <= 0.05, None, ece["n"])})
    pd = a["dti_dim_mae"]["per_dimension"]
    worst = max((d["mean"] for d in pd if d["mean"] is not None), default=None)
    rows.append({"task": "dti", "claim": "same", "metric": "per-dimension MAE, worst of 8 (no dimension is degenerate)", "threshold": "<= 5.0 each",
                 "value": worst, "ci": [None, None], "n_seeds": a["dti_dim_mae"].get("n"),
                 "verdict": verdict(None if worst is None else worst <= 5.0, None, a["dti_dim_mae"].get("n"))})
    # BII
    m = a["bii_mae"]
    rows.append({"task": "bii", "claim": "Fly recovers the BII scorer", "metric": "BII MAE (0-1)", "threshold": "<= 0.0375 and CI upper <= 0.045",
                 "value": m["mean"], "ci": [m["ci_low"], m["ci_high"]], "n_seeds": m["n"],
                 "verdict": verdict(None if m["mean"] is None else m["mean"] <= 0.0375, None if m["ci_high"] is None else m["ci_high"] <= 0.045, m["n"])})
    acc = a["bii_gate_accuracy"]
    rows.append({"task": "bii", "claim": "same", "metric": "gate accuracy", "threshold": ">= 0.90", "value": acc["mean"],
                 "ci": [acc["ci_low"], acc["ci_high"]], "n_seeds": acc["n"],
                 "verdict": verdict(None if acc["mean"] is None else acc["mean"] >= 0.90, None, acc["n"])})
    f1 = ex.get("bii", {}).get("macro_f1", NULL); ece = ex.get("bii", {}).get("ece", NULL)
    rows.append({"task": "bii", "claim": "same", "metric": "gate macro-F1", "threshold": ">= 0.85", "value": f1["mean"], "ci": [None, None], "n_seeds": f1["n"],
                 "verdict": verdict(None if f1["mean"] is None else f1["mean"] >= 0.85, None, f1["n"])})
    rows.append({"task": "bii", "claim": "same", "metric": "ECE", "threshold": "<= 0.05", "value": ece["mean"], "ci": [None, None], "n_seeds": ece["n"],
                 "verdict": verdict(None if ece["mean"] is None else ece["mean"] <= 0.05, None, ece["n"])})
    # wiring matters + floor
    for task, key, margin in (("dti", "composite_mae_recomputed_from_dims", 1.0), ("bii", "bii_mae", 0.015)):
        for other, label in (("shuffle", "delta_b = MAE(shuffle) - MAE(connectome)"), ("er", "delta_c = MAE(ER) - MAE(connectome)")):
            d, every, common = paired_delta(task, other, key)
            rows.append({"task": task, "claim": "Wiring matters", "metric": label, "threshold": f">= {margin}, CI lower > 0, connectome better on every seed",
                         "value": None if d is None else d["mean"], "ci": [None, None] if d is None else [d["ci_low"], d["ci_high"]],
                         "n_seeds": None if d is None else d["n"], "per_seed_connectome_better": every,
                         "verdict": verdict(None if d is None else (d["mean"] >= margin and every), None if d is None or d["ci_low"] is None else d["ci_low"] > 0,
                                            None if d is None else d["n"])})
        d, every, common = paired_delta(task, "ridge", key)
        rows.append({"task": task, "claim": "Fly beats the floor", "metric": "MAE(ridge) - MAE(connectome)", "threshold": "> 0, CI lower > 0",
                     "value": None if d is None else d["mean"], "ci": [None, None] if d is None else [d["ci_low"], d["ci_high"]],
                     "n_seeds": None if d is None else d["n"],
                     "verdict": verdict(None if d is None else d["mean"] > 0, None if d is None or d["ci_low"] is None else d["ci_low"] > 0,
                                        None if d is None else d["n"])})
        # DECISIONS.md "results framing": arm d decides whether the fixed substrate has an edge over ordinary training.
        # Not a PROTOCOL 8.1 threshold; reported with the same margin as the wiring rule, labelled descriptive.
        d, every, common = paired_delta(task, "mlp", key)
        rows.append({"task": task, "claim": "Fixed graph beats matched network (framing, descriptive)", "metric": "MAE(MLP) - MAE(connectome)",
                     "threshold": f">= {margin}, CI lower > 0, connectome better on every seed (same margin as the wiring rule; not pre-registered)",
                     "value": None if d is None else d["mean"], "ci": [None, None] if d is None else [d["ci_low"], d["ci_high"]],
                     "n_seeds": None if d is None else d["n"], "per_seed_connectome_better": every,
                     "verdict": verdict(None if d is None else (d["mean"] >= margin and every), None if d is None or d["ci_low"] is None else d["ci_low"] > 0,
                                        None if d is None else d["n"])})
        if task == "dti":
            # DECISIONS "composite head": the rules above use the composite recomputed from the predicted dimensions (the engine's
            # own weighted sum). These rows repeat the comparisons on the directly predicted head so a reader sees whether a
            # verdict depends on which head is read; that head is unstable across neighbouring epochs (ER log epochs 9-11).
            for other, label in (("shuffle", "delta_b"), ("er", "delta_c"), ("ridge", "MAE(ridge) - MAE(connectome)"), ("mlp", "MAE(MLP) - MAE(connectome)")):
                d, every, common = paired_delta(task, other, "composite_mae_direct")
                rows.append({"task": task, "claim": "same, directly predicted composite head (descriptive)", "metric": f"{label}, direct head",
                             "threshold": "as above", "value": None if d is None else d["mean"],
                             "ci": [None, None] if d is None else [d["ci_low"], d["ci_high"]], "n_seeds": None if d is None else d["n"],
                             "per_seed_connectome_better": every, "verdict": "descriptive"})
    # rule 19: raw and Holm-adjusted p for the primary family {a-b, a-c, a-e} on the headline metric, paired t over seeds (n >= 2)
    from scipy.stats import ttest_1samp
    for task, key in (("dti", "composite_mae_recomputed_from_dims"), ("bii", "bii_mae")):
        fam = {}
        for other in ("shuffle", "er", "ridge"):
            A, B = runs[task].get("connectome", {}), runs[task].get(other, {})
            common = sorted(set(A) & set(B))
            if len(common) >= 2:
                dd = [B[s][key] - A[s][key] for s in common]
                fam[other] = float(ttest_1samp(dd, 0.0, alternative="greater").pvalue) if statistics.pstdev(dd) > 0 else None
        adj = holm(fam)
        for row in rows:
            if row["task"] != task or row["claim"] not in ("Wiring matters", "Fly beats the floor"):
                continue
            other = "shuffle" if "shuffle" in row["metric"] else ("er" if "ER" in row["metric"] else "ridge")
            row["p_raw_one_sided"] = fam.get(other)
            row["p_holm"] = adj.get(other)
            bs = hier_bootstrap(task, "connectome", other, key)
            if bs:
                row["ci_bootstrap"] = [bs["ci_low"], bs["ci_high"]]; row["ci_bootstrap_method"] = bs["method"]
    # vs each language model: descriptive, claim only at 10x / determinism 1.00 vs < 0.90; one row per model arm
    co = results["connectome"]
    for arm in MODEL_ARMS:
        fr = results[arm["id"]]; fx = extra["frontier"].get(arm["id"]) or {}
        incomplete = "" if fx.get("complete") else f" ({arm['model']} run incomplete)"
        if fr["latency_ms"]["mean"] is not None and co["latency_ms"]["mean"] is not None:
            ratio = fr["latency_ms"]["mean"] / co["latency_ms"]["mean"]
            rows.append({"task": "dti", "claim": f"Faster than {arm['model']}", "metric": f"p50 latency ratio {arm['model']} / connectome (batch 1)",
                         "threshold": ">= 10x to claim", "value": ratio, "ci": [None, None], "n_seeds": None,
                         "verdict": ("PASS" if ratio >= 10 else "FAIL") + incomplete})
        if fr["determinism"]["mean"] is not None and co["determinism"]["mean"] is not None:
            rows.append({"task": "dti", "claim": f"More deterministic than {arm['model']}", "metric": f"determinism share (connectome vs {arm['model']})",
                         "threshold": "connectome 1.00 and model < 0.90", "value": [co["determinism"]["mean"], fr["determinism"]["mean"]], "ci": [None, None],
                         "n_seeds": None, "verdict": determinism_verdict(co["determinism"]["mean"], fr["determinism"]["mean"]) + incomplete})
    return rows


def pilot_rule(runs: dict) -> dict:
    """PROTOCOL 8.3: 2 seeds of a and b on the DTI corpus; if s_seed of (MAE_b - MAE_a) > 0.5 points, go to 10 seeds."""
    A, B = runs["dti"].get("connectome", {}), runs["dti"].get("shuffle", {})
    common = sorted(set(A) & set(B))
    out = {"seeds_with_both_a_and_b": common, "s_seed_points": None, "verdict": "AWAITING RUN (needs connectome and shuffle on >= 2 seeds)"}
    if len(common) >= 2:
        d = [B[s]["composite_mae_recomputed_from_dims"] - A[s]["composite_mae_recomputed_from_dims"] for s in common]
        s = statistics.stdev(d)
        out.update({"per_seed_delta_b": dict(zip(map(str, common), d)), "s_seed_points": s,
                    "verdict": "raise seeds to 10 for all arms" if s > 0.5 else "5 seeds stand",
                    "min_detectable_margin_at_5_seeds_points": 1 + 1.24 * s})
    return out


# ------------------------------------------------------------------ footer + markdown
def _temp_line(arm: dict, st: dict) -> str:
    if arm["provider"] == "anthropic":
        return "not settable under adaptive thinking (not sent)"
    return f"{st.get('temperature_requested')} requested, accepted {st.get('temperature_settable')}"


def footer(task: str, runs: dict, seeds: list[int], shas: dict, llm_runs: dict[str, tuple[Path, dict]], evaluated: str) -> str:
    gm = json.loads((ROOT / "data" / "malecns" / "graph_meta.json").read_text())
    gsha = sha256_file(ROOT / "data" / "malecns" / "graph_meta.json")
    split = ROOT / "splits" / f"{task}_seed1.json"
    sp = json.loads(split.read_text())
    c = sp["counts"]
    teacher = (f"pipeline.ts commit {shas['dti']}" if task == "dti" else f"VIGIL commit {shas['bii']} + policy digest {POLICY_DIGEST}")
    gen = "gen_dti.ts" if task == "dti" else "gen_bii.py"
    n_test = c["test"]["total"]
    fs = sha256_file(ROOT / "teachers" / f"{task}_features_spec.md")
    if llm_runs and task == "dti":
        parts = []
        for arm in MODEL_ARMS:
            if f"{arm['provider']}:g" not in llm_runs:
                parts.append(f"{arm['model']}: awaiting run")
                continue
            llm_dir, llm = llm_runs[f"{arm['provider']}:g"]
            st = llm["settings"]
            prices = json.loads((llm_dir / "prices.json").read_text())
            parts.append(f"{llm['model_requested']} (served as {'/'.join(llm['response_models'])}), {st['thinking']['type']}, effort {st['effort']}, "
                         f"max_tokens {st['max_tokens']}, temperature {_temp_line(arm, st)}, "
                         f"k={llm['input']['k']}, N={llm['input']['n_records']}, prompt sha256 {llm['prompt_sha256'][:12]}, "
                         f"prices from {prices['retrieved_from']} retrieved {prices['retrieved_on']}")
        llm_line = "; ".join(parts)
    else:
        llm_line = "not run for this task"
    return (f"Source: {FOOTER_SOURCE}\n"
            f" | Graph: N={gm['n_neurons']} neurons (superclass non-null), E={gm['n_edges_at_threshold']} edges (weight>={gm['threshold']}), "
            f"sign policy {gm['modulatory_policy']}/{gm['unclear_policy']}, graph sha256 {gsha}\n"
            f" | Teacher: {teacher}, clock frozen at {AS_OF}\n"
            f" | Data: {TEACHER_FILE[task]} ({gen}) sha256 {MANIFEST_SHA256[task]}, run_seed {sp['split_seed']}, "
            f"{c['train']['total']}/{c['val']['total']}/{n_test} records, split sha256 {sha256_file(split)}, SYNTHETIC, zero PHI\n"
            f" | Coverage: TEST only, {n_test} records, {len(seeds)} seeds {{{','.join(map(str, seeds)) or 'none yet'}}} of protocol {{1..5}}; "
            f"teacher dimensions excluded as degenerate: none (splits/qa_report.json)\n"
            f" | Feature spec {fs} | Evaluated {evaluated} | Language-model arms: {llm_line}")


def fmt(x, nd=3):
    if x is None:
        return "awaiting run"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def cell(r: dict, nd=3) -> str:
    if r.get("mean") is None:
        return "awaiting run"
    s = fmt(r["mean"], nd)
    if r.get("ci_low") is not None:
        s += f" [{fmt(r['ci_low'], nd)}, {fmt(r['ci_high'], nd)}]"
    if r.get("n"):
        s += f" (n={r['n']})"
    return s


def markdown(doc: dict, runs: dict, footers: dict, health: dict) -> str:
    R, X = doc["results"], doc["extra"]
    L = [f"# Results: connectome distillation study", "",
         f"Status: **{doc['status']}**. Generated {doc['generated']} from git {doc['git_sha'][:12]}. CI: {doc['ci']}.",
         "Every number below is read from a run's metrics.json or the LLM run's summary.json; a cell that says "
         "\"awaiting run\" has no run behind it. SYNTHETIC data, zero PHI. Trainer settings for the pilot: AdamW lr 1e-3 cosine, "
         "batch 64 (measured choice), T=8, patience 3 on VAL loss, max 20 epochs, identical across gradient arms; shuffle swaps_per_edge=10; "
         "ridge closed form (lambda by VAL loss). These differ from PROTOCOL 5 (patience 10, max 200, lr 1e-4 on edge gains) and are the pilot's settings.", ""]
    for task in ("dti", "bii"):
        L += [f"## {task.upper()} arms (TEST)", ""]
        if task == "dti":
            L += ["| arm | composite MAE recomputed from dims (headline) | composite MAE direct head | tier accuracy | macro-F1 (support>=30) | ECE | epochs run | wall min / seed | params |", "|---|---|---|---|---|---|---|---|---|"]
        else:
            L += ["| arm | BII MAE (0-1) | gate accuracy | macro-F1 (support>=30) | ECE | epochs run | wall min / seed | params |", "|---|---|---|---|---|---|---|---|"]
        for arm in ARMS:
            aid = arm["id"]; r = R[aid]; ex = X["local"].get(aid, {}).get(task)
            if arm.get("provider"):
                if task == "dti" and r["dti_mae"]["mean"] is not None:
                    fr = X["frontier"][aid]
                    L.append(f"| {arm['label']} | {cell(r['dti_mae'], 2)} | {cell(r['dti_mae_direct'], 2)} | {cell(r['dti_tier_accuracy'])} | "
                             f"{fmt(fr.get('macro_f1_mean_of_runs'))} | not applicable | {fr['counts']['calls_total']} calls | "
                             f"{fr['counts']['calls_total'] / 60:.0f}+ min (API) | unknown |")
                else:
                    L.append(f"| {arm['label']} | awaiting run | | | | | | | |")
                continue
            if not ex:
                L.append(f"| {arm['label']} | awaiting run |" + " |" * (7 if task == "dti" else 6))
                continue
            wall = statistics.fmean(ex["wall_seconds_total"]) / 60
            params = ex["trainable_params"] if ex["trainable_params"] else f"{ex['fitted_params']} (closed form)"
            if task == "dti":
                L.append(f"| {arm['label']} | {cell(r['dti_mae'], 2)} | {cell(r['dti_mae_direct'], 2)} | {cell(r['dti_tier_accuracy'])} | "
                         f"{cell(ex['macro_f1'])} | {cell(ex['ece'])} | {ex['epochs_run']} | {wall:.1f} | {params} |")
            else:
                L.append(f"| {arm['label']} | {cell(r['bii_mae'], 4)} | {cell(r['bii_gate_accuracy'])} | {cell(ex['macro_f1'])} | {cell(ex['ece'])} | "
                         f"{ex['epochs_run']} | {wall:.1f} | {params} |")
        L += ["", "```", footers[task], "```", ""]
        if task == "dti":
            L += ["### DTI per-dimension MAE (points, TEST; no dimension is degenerate, all SD >= 12.4)", "",
                  "| arm | " + " | ".join(DTI_DIMS) + " |", "|---|" + "---|" * len(DTI_DIMS)]
            for arm in ARMS:
                pdim = R[arm["id"]]["dti_dim_mae"]["per_dimension"]
                L.append(f"| {arm['label']} | " + " | ".join((cell(p, 2) for p in pdim) if pdim else ["awaiting run"] * len(DTI_DIMS)) + " |")
            L += ["", "```", footers["dti"], "```", ""]
    L += ["## Latency, cost, determinism (same records where measured)", "",
          "| arm | latency per record (ms) | USD per record | determinism |", "|---|---|---|---|"]
    for arm in ARMS:
        r = R[arm["id"]]
        lat = r["latency_ms"]; s_lat = cell(lat, 2) if lat["mean"] is not None else ("not measured (bench covers the connectome forward only)" if arm["id"] in ("shuffled", "random", "mlp", "linear") else "awaiting run")
        if lat.get("p95") is not None:
            s_lat += f", p95 {lat['p95']:.0f}"
        if lat.get("batch_256_per_record_ms") is not None:
            s_lat += f" (batch 256: {lat['batch_256_per_record_ms']:.2f} ms/record)"
        usd = r["usd_per_record"]; s_usd = ("awaiting run" if usd["mean"] is None else (f"{usd['mean']:.4f}" + (f" ({usd['price_source']})" if usd.get("price_source") else " marginal API; hardware not measured")))
        det = r["determinism"]; s_det = cell(det) if det["mean"] is not None else "awaiting run"
        if det.get("method"):
            s_det += f" ({det['method']})"
        L.append(f"| {arm['label']} | {s_lat} | {s_usd} | {s_det} |")
    L += ["", "```", footers["dti"], "```", ""]
    L += ["## Decision rules (PROTOCOL 8.1), evaluated", "", "| task | claim | metric | threshold | value | 95% CI | seeds | verdict |", "|---|---|---|---|---|---|---|---|"]
    for row in doc["decision_rules"]:
        v = row["value"]; v = fmt(v, 4) if not isinstance(v, list) else ", ".join(fmt(x, 3) for x in v)
        ci = row["ci"]; ci_s = "" if ci[0] is None and ci[1] is None else f"[{fmt(ci[0], 4)}, {fmt(ci[1], 4)}]"
        L.append(f"| {row['task']} | {row['claim']} | {row['metric']} | {row['threshold']} | {v} | {ci_s} | {fmt(row['n_seeds'])} | **{row['verdict']}** |")
    pr = doc["pilot_rule"]
    L += ["", f"Wiring sentence (PROTOCOL 9.4): {doc['wiring_sentence'] or 'not yet sayable (fewer than 5 seeds)'}", "",
          f"Pilot rule (PROTOCOL 8.3): seeds with both connectome and shuffle on DTI = {pr['seeds_with_both_a_and_b']}; "
          f"s_seed of delta_b = {fmt(pr['s_seed_points'], 3)} points; verdict: **{pr['verdict']}**.", "",
          "```", footers["dti"], "```", ""]
    L += ["## Dataset health (splits/qa_report.json, DECISION_RULES checklist)", ""]
    for task in ("dti", "bii"):
        h = health[task]["health"]; ch = health[task]["checks"]
        L.append(f"- **{task}**: QA {'PASS' if health[task]['PASS'] else 'FAIL'}; checks: " + ", ".join(f"{k} {'PASS' if v['pass'] else 'FAIL'}" for k, v in ch.items())
                 + f"; rows {h['rows']}, split {h['counts']['train']['total']}/{h['counts']['val']['total']}/{h['counts']['test']['total']}; "
                 f"exact duplicate feature rows {h['exact_duplicate_feature_rows']}; missing {h['missing_values']}; constant features {h['constant_features'] or 'none'}; "
                 f"exactly collinear columns {h['multicollinearity']['exactly_collinear_columns']} (one-hot groups); id AUROC {ch['id_not_predictive']['max_one_vs_rest_auroc']}; "
                 f"max |corr(feature, target)| {ch['no_target_in_features']['max_abs_corr']}; KS train vs test {h['ks_train_vs_test']}; degenerate targets {h['degenerate_targets'] or 'none'}.")
    L += ["", "```", footers["dti"], "```", ""]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm-run", type=Path, action="append", default=[], help="pin a run dir for its provider; repeatable")
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    a = ap.parse_args(argv)
    a.out.mkdir(exist_ok=True)
    runs = load_runs()
    llm_runs = llm_runs_by_provider(a.llm_run)
    bench_p = ROOT / "runs" / "bench_speed.json"
    bench = json.loads(bench_p.read_text()) if bench_p.exists() else None
    results, extra, seeds = aggregate(runs, llm_runs, bench)
    n_runs = sum(len(v) for t in runs.values() for v in t.values())
    total_expected = 5 * 2 * 5
    models_complete = all(extra["frontier"].get(a["id"], {}).get("complete") for a in MODEL_ARMS)
    status = "awaiting run" if n_runs == 0 else ("complete" if n_runs >= total_expected and models_complete else "partial")
    evaluated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    shas = teacher_shas()
    footers = {t: footer(t, runs, seeds, shas, llm_runs, evaluated) for t in ("dti", "bii")}
    rules = decision_rules(runs, results, extra)
    wiring = None
    if all(r["n_seeds"] is not None and r["n_seeds"] >= 5 for r in rules if r["claim"] == "Wiring matters" and r["task"] == "dti"):
        ws = [r for r in rules if r["claim"] == "Wiring matters" and r["task"] == "dti"]
        wiring = "wiring mattered" if all(r["verdict"] == "PASS" for r in ws) else ("wiring did not matter" if all(r["verdict"] == "FAIL" for r in ws) else "inconclusive at 5 seeds")
    doc = {
        "status": status, "generated": evaluated, "run_manifest": "runs/*/*/seed*/run.json; runs/eval_ledger.jsonl",
        "seeds": seeds, "ci": "95% t-interval over seeds (null when fewer than 2 seeds); language-model arms: Wilson over records",
        "teacher": {"dti_mae": 0.0, "dti_mae_direct": 0.0, "dti_tier_accuracy": 1.0, "bii_mae": 0.0, "bii_gate_accuracy": 1.0, "latency_ms": None, "usd_per_record": None, "determinism": None},
        "arms": [{**arm, "label": (arm["label"].replace("scored examples", f"{extra['frontier'][arm['id']]['examples']['E']} scored examples")
                                   if arm.get("arm") == "g2-examples" and extra["frontier"].get(arm["id"], {}).get("examples") else arm["label"]),
                  "trainable_parameters": next((ex.get("trainable_params") for ex in extra["local"].get(arm["id"], {}).values() if ex.get("trainable_params")), None)} for arm in ARMS],
        "metrics": METRICS, "results": results,
        "git_sha": git_sha(), "runs_completed": n_runs, "runs_expected_full_protocol": total_expected,
        "decision_rules": rules, "wiring_sentence": wiring, "pilot_rule": pilot_rule(runs),
        "extra": extra, "footers": footers, "health_report": "splits/qa_report.json",
    }
    (a.out / "results.json").write_text(json.dumps(doc, indent=2, default=str) + "\n")
    health = json.loads((ROOT / "splits" / "qa_report.json").read_text())
    (a.out / "RESULTS.md").write_text(markdown(doc, runs, footers, health))
    models = ", ".join(f"{p}={d.name}{'' if _complete(s) else ' (partial)'}" for p, (d, s) in sorted(llm_runs.items())) or "none"
    print(f"{status}: {n_runs} local runs, seeds {seeds}, model arms {models} -> {a.out / 'results.json'}, RESULTS.md")


if __name__ == "__main__":
    main()

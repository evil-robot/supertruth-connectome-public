"""Render Section 4 of the connectome whitepaper from the runs that have finished.

  uv run --project ~/Projects/ds-lab python scripts/render_results.py [--no-refresh]

Steps (idempotent; rerun as seeds land):
  1. refresh results/results.json + results/RESULTS.md via scripts/collect_results.py (run in the project .venv, which has
     torch for the flytrust imports; this script itself runs in ds-lab for matplotlib and scipy)
  2. read results/results.json only (one assembly path per figure: every number below comes from that file)
  3. write paper/results/section4.md  (Tables 8-11, Figure 3 and 4 captions, prose that follows the DECISIONS.md framing rule)
  4. write paper/results/abstract_sentences.md and paper/results/page_sentences.json (four sentences, each <= 240 chars)
  5. render paper/figures/fig3_paired_differences.{png,svg} and fig4_dimension_mae.{png,svg} at 300 dpi
  6. copy results/results.json to viz/dist/results/results.json and validate it against viz/results.schema.json

Statistics: mean over finished seeds with a two-sided 95% t-interval when n_seeds >= 2; one seed prints as a point marked
"single seed, no interval". The protocol's primary interval (hierarchical bootstrap over seeds then records, 8.2) needs
per-record errors that evaluate.py does not yet write; until it does, the seed-level t-interval is what is printed and
the text says so. Paired differences are oriented so that a positive value means the connectome did better.
Nothing here is estimated: a cell with no run behind it says "awaiting run".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "viz"))
from figures import FOOTER as FIG_FOOTER   # noqa: E402  (viz/figures.py: the footer figures 1 and 2 carry)
RESULTS = ROOT / "results" / "results.json"
OUT_MD = ROOT / "paper" / "results"
OUT_FIG = ROOT / "paper" / "figures"
DIST = ROOT / "viz" / "dist" / "results" / "results.json"
SNAPSHOT = "2026-09-20"
MARGIN_DTI = 1.0
HEAD = "composite_mae_recomputed_from_dims"      # headline composite (DECISIONS 2026-09-20 "composite head")
DIRECT = "composite_mae_direct"
DISCLOSURE = ("Composite head, disclosed: two composite estimates exist per arm, the directly predicted head and the composite recomputed "
              "from the eight predicted dimensions with the engine's own weights. The recomputed composite is the headline in this section and "
              "the direct head is printed beside it in every table. That choice was made after seed 1 was read, because the direct head moved by "
              "about a point between neighbouring epochs (random graph, runs/dti/er/seed1/log.txt: validation composite error 2.80 at the selected "
              "epoch 9, 1.80 at epoch 10, 1.77 at epoch 11; the matched network similar) while the recomputed composite did not; it does not touch "
              "tier agreement or the per-dimension errors, which are the primary evidence (docs/DECISIONS.md, row \"composite head\").")
MARGIN_BII = 0.015
N_SEEDS_PROTOCOL = 5
PAGE_SENTENCE_MAX = 240

LOCAL = [("connectome", "Fly wiring (a)"), ("shuffled", "Degree-preserving shuffle (b)"), ("random", "Random graph, matched density (c)"),
         ("mlp", "Matched-parameter network (d)"), ("linear", "Linear floor, ridge (e)")]
CONTROLS = LOCAL[1:]
SHORT = {"connectome": "Fly wiring (a)", "shuffled": "Shuffle (b)", "random": "Random graph (c)", "mlp": "Matched network (d)", "linear": "Linear floor (e)"}
DIMS = ["provenance", "consent", "recency", "quality", "concordance", "validation", "breadth", "stability"]

# viz/figures.py palette (palette.md slots, validated 20 Sep 2026)
C = {"fly": "#2a78d6", "ctl": "#52514e", "muted": "#898781", "hairline": "#e1e0d9", "ink": "#0b0b0b", "ink2": "#52514e",
     "surface": "#fcfcfb", "accent": "#eb6834"}
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
                     "font.size": 8, "axes.edgecolor": C["hairline"], "axes.labelcolor": C["ink2"], "xtick.color": C["ink2"],
                     "ytick.color": C["ink2"], "text.color": C["ink"], "figure.facecolor": C["surface"], "axes.facecolor": C["surface"],
                     "savefig.facecolor": C["surface"], "svg.fonttype": "none", "svg.hashsalt": "connectome-results"})


# ------------------------------------------------------------------ formatting
def f(x, nd=2, unit=""):
    if x is None:
        return "awaiting run"
    return f"{x:.{nd}f}{unit}"


def cell(r: dict | None, nd=2, unit="") -> str:
    """mean with interval, or the single-seed mark. Language-model rows carry Wilson intervals over records (their n is records)."""
    if not r or r.get("mean") is None:
        return "awaiting run"
    s = f(r["mean"], nd, unit)
    if r.get("ci_low") is not None:
        s += f" [{f(r['ci_low'], nd)}, {f(r['ci_high'], nd)}]"
    return s


def seeds_cell(n: int) -> str:
    """the Seeds column carries the single-seed mark once per row"""
    if n == 0:
        return "0"
    return f"{n} of {N_SEEDS_PROTOCOL}" + (", single seed" if n == 1 else "")


def row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def rule(aligns: str) -> str:
    """pipe-table delimiter row: 'l' left, 'r' right (numbers), one letter per column"""
    return "|" + "|".join("---:" if a == "r" else "---" for a in aligns) + "|"


def pv(r: dict | None, nd=2) -> str:
    """prose value: mean, with the interval when one exists; the single-seed status is stated once, not per number"""
    if not r or r.get("mean") is None:
        return "awaiting run"
    s = f(r["mean"], nd)
    if r.get("ci_low") is not None:
        s += f" [{f(r['ci_low'], nd)}, {f(r['ci_high'], nd)}]"
    return s


def pdlt(r: dict | None, nd=2) -> str:
    if not r or r.get("mean") is None:
        return "awaiting run"
    s = f"{r['mean']:+.{nd}f}"
    if r.get("ci_low") is not None:
        s += f" [{r['ci_low']:+.{nd}f}, {r['ci_high']:+.{nd}f}]"
    return s


def delta_cell(r: dict | None, nd=2) -> str:
    if not r or r.get("mean") is None:
        return "awaiting run"
    s = f"{r['mean']:+.{nd}f}"
    if r.get("ci_low") is not None:
        s += f" [{r['ci_low']:+.{nd}f}, {r['ci_high']:+.{nd}f}]"
    else:
        s += " (single seed)"
    return s


GLYPHS = [("<=", "\u2264"), (">=", "\u2265"), ("delta_b", "\u03b4_b"), ("delta_c", "\u03b4_c"), (" - ", " \u2212 "), ("10x", "10\u00d7"), ("(0-1)", "(0 to 1)"), (" vs ", " against ")]


def glyphs(text: str) -> str:
    """the decision-rule strings in results.json are ASCII; Section 3 writes them with the mathematical glyphs"""
    for a, b in GLYPHS:
        text = text.replace(a, b)
    return text


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------ data access
class Data:
    def __init__(self, doc: dict):
        self.doc = doc
        self.R = doc["results"]
        self.X = doc["extra"]
        self.P = doc["extra"].get("paired", {})
        self.local = doc["extra"]["local"]
        self.frontier = doc["extra"]["frontier"]
        self.seeds = doc["seeds"]

    def m(self, arm, metric):
        return self.R[arm][metric]

    def ex(self, arm, task, key):
        return self.local.get(arm, {}).get(task, {}).get(key)

    def n_seeds(self, arm, task):
        return len(self.local.get(arm, {}).get(task, {}).get("seeds", []))

    def pair(self, task, arm, metric):
        return self.P.get(task, {}).get(arm, {}).get(metric)

    def has(self, arm, task):
        return bool(self.local.get(arm, {}).get(task))


# ------------------------------------------------------------------ framing (DECISIONS.md "results framing")
def framing(D: Data) -> dict:
    """Which of the pre-written framings the DTI data support, from the headline metric (directly predicted composite MAE).
    within(control) = control did not trail the fly by the pre-registered margin. n < 5 makes every verdict provisional."""
    out = {"n": D.n_seeds("connectome", "dti"), "case": "awaiting", "provisional": True}
    db = D.pair("dti", "shuffled", HEAD); dc = D.pair("dti", "random", HEAD)
    if not db or not dc:
        return out
    n_pairs = min(db["n"], dc["n"])
    out.update({"n": n_pairs, "provisional": n_pairs < N_SEEDS_PROTOCOL})
    b_within = db["mean"] < MARGIN_DTI
    c_within = dc["mean"] < MARGIN_DTI
    every = lambda r: r["connectome_better_seeds"] == r["n"]
    ci_pos = lambda r: r.get("ci_low") is not None and r["ci_low"] > 0
    if b_within and c_within:
        out["case"] = "substrate"
    elif b_within and not c_within:
        out["case"] = "substrate_c_caveat"
    elif (not b_within and not c_within) and every(db) and every(dc) and (out["provisional"] or (ci_pos(db) and ci_pos(dc))):
        out["case"] = "wiring"
    else:
        out["case"] = "mixed"
    return out


# ------------------------------------------------------------------ model arms as a group
VENDORS = ("anthropic", "openai", "xai", "gemini")
EX = {v: f"{v}_ex" for v in VENDORS}      # post-hoc arm g2-examples beside each arm g row (amendment 1, row 17)


def gain_cell(r: dict | None, nd=2, sign=True) -> str:
    """paired difference over records: mean with its t-interval; a positive value means the examples helped"""
    if not r or r.get("mean") is None:
        return "awaiting run"
    s = f"{r['mean']:+.{nd}f}" if sign else f(r["mean"], nd)
    if r.get("ci_low") is not None:
        s += f" [{r['ci_low']:+.{nd}f}, {r['ci_high']:+.{nd}f}]"
    return s


def short_name(D: Data, aid: str) -> str:
    return next(a for a in D.doc["arms"] if a["id"] == aid)["label"].split(" given ")[0]


def model_rows(D: Data) -> list[dict]:
    """one dict per model arm with a summary, sorted by tier agreement descending; nothing typed, everything from results.json"""
    rows = []
    for aid in VENDORS:
        fx = D.frontier.get(aid)
        if not fx:
            continue
        r = D.R[aid]
        rows.append({"aid": aid, "name": short_name(D, aid), "fx": fx, "tier": r["dti_tier_accuracy"]["mean"], "mae": r["dti_mae"]["mean"],
                     "lat_s": fx["latency_ms_median"] / 1000, "usd": fx["usd_per_record"]})
    return sorted(rows, key=lambda x: -x["tier"])


def span(rows: list[dict], key: str, fmt) -> str:
    lo, hi = min(r[key] for r in rows), max(r[key] for r in rows)
    return fmt(lo) if fmt(lo) == fmt(hi) else f"{fmt(lo)} to {fmt(hi)}"


def lat_fmt(x: float) -> str:
    return f"{x:.0f} s" if x >= 10 else f"{x:.1f} s"


# ------------------------------------------------------------------ prose
def prose_headline(D: Data, F: dict) -> str:
    n = F["n"]
    a = D.m("connectome", "dti_mae"); b = D.m("shuffled", "dti_mae"); c = D.m("random", "dti_mae"); d = D.m("mlp", "dti_mae")
    ad = D.m("connectome", "dti_mae_direct"); bd = D.m("shuffled", "dti_mae_direct"); cd = D.m("random", "dti_mae_direct"); dd_ = D.m("mlp", "dti_mae_direct")
    at = D.m("connectome", "dti_tier_accuracy"); bt = D.m("shuffled", "dti_tier_accuracy"); ct = D.m("random", "dti_tier_accuracy"); dt = D.m("mlp", "dti_tier_accuracy")
    db = D.pair("dti", "shuffled", HEAD); dc = D.pair("dti", "random", HEAD)
    db_d = D.pair("dti", "shuffled", DIRECT); dc_d = D.pair("dti", "random", DIRECT)
    n_test = f"{int(D.doc['footers']['dti'].split('Coverage: TEST only, ')[1].split(' records')[0]):,}"
    lead = (f"**Provisional: {n} of {N_SEEDS_PROTOCOL} seeds{'; every figure in this subsection is a single-seed point with no interval' if n == 1 else ''}.** "
            if F["provisional"] else f"**{n} seeds.** ")
    if F["case"] == "awaiting":
        return lead + "The fly, shuffle, and random-graph arms have not all finished on the DTI task; no framing sentence is sayable yet."
    seeds_word = "the seed finished so far" if n == 1 else f"the {n} seeds finished so far"
    shuffle_sentence = (f"The degree-preserving shuffle, which keeps every neuron's connection counts and every sign and destroys only who "
                        f"connects to whom, matched the fly wiring: composite error {pv(b)} against {pv(a)} points on {n_test} synthetic test records "
                        f"(shuffle minus fly {pdlt(db)}), tier agreement {pv(bt, 3)} against {pv(at, 3)}.")
    direct_note = (f"On the directly predicted composite head the same reading is {pv(bd)} (shuffle) and {pv(cd)} (random graph) against {pv(ad)} (fly): "
                   f"shuffle minus fly {pdlt(db_d)}, random minus fly {pdlt(dc_d)}"
                   + (f"; the random graph's direct head trails by more than the margin there, and the disclosure paragraph below says why that head is not the headline." if dc_d["mean"] >= MARGIN_DTI else "."))
    mlp_gap = D.pair("dti", "mlp", HEAD); mlp_tier = D.pair("dti", "mlp", "tier_acc")
    b_vs_d = d["mean"] - b["mean"]; c_vs_d = d["mean"] - c["mean"]
    fixed_sentence = (f"What did matter is having a fixed, sparse, signed recurrent graph at all. The network with the same number of trainable "
                      f"parameters ({D.ex('mlp', 'dti', 'trainable_params'):,} against {D.ex('connectome', 'dti', 'trainable_params'):,}) reached "
                      f"{pv(d)} points and tier agreement {pv(dt, 3)}; the fly beat it by {pv(mlp_gap)} points of composite error and "
                      f"{pv(mlp_tier, 3)} of tier agreement, the shuffle by {b_vs_d:.2f} points and the random graph by {c_vs_d:.2f} points (arm means). "
                      f"Trained on only 65 inputs, that network overfits (training loss 0.12 against validation loss 0.37 at the stop, "
                      f"runs/dti/mlp/seed1/log.txt epoch 7), as assumption A12 predicted; the small 2 \u00d7 256 reference network (d') has not been run.")
    rule_sentence = (f"Under the pre-registered rule the wiring claim needs both controls to trail the fly by at least {MARGIN_DTI:.1f} point on every seed; "
                     f"neither did, so the answer to \"does the fly's specific wiring matter\" is no on this evidence.")
    if F["case"] == "substrate":
        core = (f"On {seeds_word} the finding is the substrate, not the anatomy. {shuffle_sentence} The random graph at matched density and "
                f"matched sign fraction matched as well: composite error {pv(c)} (random minus fly {pdlt(dc)}), tier agreement {pv(ct, 3)} against {pv(at, 3)}, "
                f"and every per-dimension error within a point of the fly's (Table 8c). {direct_note} {rule_sentence} {fixed_sentence}")
    elif F["case"] == "substrate_c_caveat":
        core = (f"On {seeds_word} the finding points to the substrate, not the anatomy, with one caveat. {shuffle_sentence} "
                f"The random graph at matched density matched the fly on tier agreement ({pv(ct, 3)} against {pv(at, 3)}) but trailed by {pdlt(dc)} points "
                f"of composite error ({pv(c)} against {pv(a)}). {direct_note} Under the pre-registered rule the wiring claim needs both controls to trail "
                f"the fly by at least {MARGIN_DTI:.1f} point on every seed; the shuffle did not trail at all, so the answer to \"does the fly's specific wiring "
                f"matter\" is no on this evidence. {fixed_sentence}")
    elif F["case"] == "wiring":
        core = (f"On {seeds_word} the fly's wiring beat both null substrates by the pre-registered margin: shuffle minus fly {pdlt(db)} points, "
                f"random graph minus fly {pdlt(dc)} points, the fly better on every seed pair. Composite error {pv(a)} (fly), {pv(b)} (shuffle), "
                f"{pv(c)} (random graph); tier agreement {pv(at, 3)}, {pv(bt, 3)}, {pv(ct, 3)}. {direct_note} {fixed_sentence}")
    else:
        core = (f"On {seeds_word} the two null substrates disagree: shuffle minus fly {pdlt(db)} points, random graph minus fly {pdlt(dc)} points "
                f"(fly better on {db['connectome_better_seeds']} of {db['n']} and {dc['connectome_better_seeds']} of {dc['n']} seeds). None of the three "
                f"pre-written sentences is sayable; the ten-seed rule of Section 3.9 is the next step. {direct_note} {fixed_sentence}")
    return lead + core + "\n\n" + DISCLOSURE


def prose_engine(D: Data) -> str:
    a = D.m("connectome", "dti_mae"); at = D.m("connectome", "dti_tier_accuracy")
    f1 = D.ex("connectome", "dti", "macro_f1"); ece = D.ex("connectome", "dti", "ece")
    pd = D.m("connectome", "dti_dim_mae")["per_dimension"]
    if a["mean"] is None:
        return "Engine recovery: awaiting the fly's DTI run."
    over = [(DIMS[i], p["mean"]) for i, p in enumerate(pd) if p["mean"] is not None and p["mean"] > 5.0]
    worst = max(((DIMS[i], p["mean"]) for i, p in enumerate(pd) if p["mean"] is not None), key=lambda t: t[1])
    bars = [("recomputed composite MAE", a["mean"], a["mean"] <= 2.5, "at most 2.5 points"), ("tier agreement", at["mean"], at["mean"] >= 0.90, "at least 0.90"),
            ("macro-F1", f1["mean"], f1["mean"] >= 0.85, "at least 0.85"), ("calibration error", ece["mean"], ece["mean"] <= 0.05, "at most 0.05"),
            ("worst per-dimension MAE", worst[1], worst[1] <= 5.0, "at most 5.0 points on every dimension")]
    met = [b for b in bars if b[2]]; missed = [b for b in bars if not b[2]]
    s = (f"**Recovering the engine.** Against the exact teacher on the test split the fly reached composite error {pv(a)} points (recomputed; direct head {pv(D.m('connectome', 'dti_mae_direct'))}), tier agreement "
         f"{pv(at, 3)}, macro-F1 {pv(f1, 3)}, and expected calibration error {pv(ece, 3)}; per-dimension error ran from "
         f"{min(p['mean'] for p in pd if p['mean'] is not None):.2f} to {worst[1]:.2f} points (worst: {worst[0]}). Of the five pre-registered bars "
         f"(Table 4) the point estimates meet {len(met)} ({'; '.join(b[0] for b in met)}) and miss {len(missed)}"
         + (f" ({'; '.join(f'{b[0]} {b[1]:.3f} against {b[3]}' for b in missed)})" if missed else "") + ".")
    if over:
        s += f" The dimensions above the 5.0-point bar are {', '.join(f'{d} ({v:.2f})' for d, v in over)}; recency is the dimension with the most thresholds (seven distinct values, a 999-day sentinel, element dates that can only lower it)."
    s += " The fly's composite is well inside a tier width, its tier agreement is just under the bar, and the verdicts wait for five seeds."
    e = D.pair("dti", "linear", HEAD); et = D.pair("dti", "linear", "tier_acc")
    if e:
        s += (f" It beat the linear floor by {pv(e)} points of composite error and {pv(et, 3)} of tier agreement, so the engine-recovery "
              f"claim is not reducible to \"matches a linear map\".")
    return s


def prose_floor_note(D: Data) -> str:
    r = D.m("linear", "dti_dim_mae")["per_dimension"]; m = D.m("mlp", "dti_dim_mae")["per_dimension"]
    if not r or not m or r[0]["mean"] is None or m[0]["mean"] is None:
        return ""
    r_mean = np.mean([p["mean"] for p in r]); m_mean = np.mean([p["mean"] for p in m])
    rt = D.m("linear", "dti_tier_accuracy")["mean"]; mt = D.m("mlp", "dti_tier_accuracy")["mean"]
    rc = D.m("linear", "dti_mae")["mean"]; mc = D.m("mlp", "dti_mae")["mean"]   # recomputed composite
    rd = dict(zip(DIMS, [p["mean"] for p in r])); md = dict(zip(DIMS, [p["mean"] for p in m]))
    r_ece = D.ex("linear", "dti", "ece")["mean"]
    return (f"**Reading the floor against the matched network.** The linear floor's mean per-dimension error ({r_mean:.2f} points) and composite error "
            f"({rc:.2f}) are both lower than the matched network's ({m_mean:.2f} and {mc:.2f}) while its tier agreement is far lower ({rt:.3f} against {mt:.3f}). "
            f"Both follow from what each head is. The ridge dimension heads are least-squares fits: on the engine's coarse ordinal dimensions a linear map "
            f"lands near the right step (stability {rd['stability']:.2f}, quality {rd['quality']:.2f}, concordance {rd['concordance']:.2f} points) and on the stepwise "
            f"ones (recency {rd['recency']:.2f}, consent {rd['consent']:.2f}) it cannot follow the thresholds. Its tier head is one-hot regression read as logits, "
            f"not a trained classifier: mean confidence {D.ex('linear', 'dti', 'mean_confidence')['mean']:.2f}, calibration error {r_ece:.2f}, so the argmax is wrong on "
            f"four records in ten even where the dimensions are close. The matched network is trained by cross-entropy on the tier, which is why it wins that "
            f"column, and is a uniform {min(md.values()):.1f} to {max(md.values()):.1f} points off on every dimension: {D.ex('mlp', 'dti', 'trainable_params'):,} "
            f"parameters on 65 inputs, best validation loss at epoch {D.ex('mlp', 'dti', 'best_epoch')[0]} of {D.ex('mlp', 'dti', 'epochs_run')[0]}, training loss a third of "
            f"validation loss at the stop. It is a weak control by construction and the paper reports it as such; the ridge floor is the fairer reference for the dimension heads.")


def prose_models(D: Data) -> str:
    rows = model_rows(D)
    sentences = []
    for x in rows:
        fx, r = x["fx"], D.R[x["aid"]]
        served = "/".join(fx["response_models"])
        sentences.append(f"{x['name']} ({fx['model_requested']}, served as {served}; N = {fx['n_records']}, k = {fx['k']}{'' if fx['complete'] else ', run incomplete'}): "
                         f"composite error {f(r['dti_mae']['mean'])} points (recomputed; direct {f(r['dti_mae_direct']['mean'])}), tier agreement {f(x['tier'], 3)} "
                         f"(Wilson 95% {f(r['dti_tier_accuracy']['ci_low'], 3)} to {f(r['dti_tier_accuracy']['ci_high'], 3)}), median latency {x['lat_s']:.1f} s per call "
                         f"(p95 {fx['latency_ms_p95'] / 1000:.1f} s), ${x['usd']:.3f} per record.")
    for aid in VENDORS:
        if not D.frontier.get(aid):
            sentences.append(f"{short_name(D, aid)}: awaiting run.")
    a = D.m("connectome", "dti_mae"); at = D.m("connectome", "dti_tier_accuracy"); lat = D.m("connectome", "latency_ms")
    sub = D.ex("connectome", "dti", "subset300")
    fly = (f"The fly on the full test split: composite error {f(a['mean'])} points, tier agreement {f(at['mean'], 3)}, "
           f"{f(lat['mean'])} ms per record at batch 1 ({f(lat.get('batch_256_per_record_ms'))} ms at batch 256), $0.00 marginal API spend (electricity not measured)."
           if a["mean"] is not None else "The fly's figures are awaiting run.")
    same = (f" On the identical {sub['n_records']} records (runs/dti/connectome/seed*/metrics_subset300.json, a logged second read of the test split under rule 9, "
            f"reason \"{sub['reason']}\"), the fly's composite error is {pv(sub['composite_mae_recomputed_from_dims'])} points and its tier agreement "
            f"{pv(sub['tier_acc'], 3)} (Wilson 95% {sub['tier_acc_wilson_mean_over_seeds'][0]:.3f} to {sub['tier_acc_wilson_mean_over_seeds'][1]:.3f}); Table 9 gives every arm on those records." if sub else
            " The same-record comparison (every arm on the model arms' 300 ids) is awaiting scripts/eval_subset.py.")
    det = D.m("connectome", "determinism")
    determinism = ""
    if rows and det["mean"] is not None:
        fly_det = "byte-identical output on every repeat" if det["mean"] == 1.0 else f"byte-identical output on {det['mean']:.1%} of repeats"
        parts = []
        for x in rows:
            exact = x["fx"]["determinism_exact_match_share"]
            parts.append(f"{x['name']} {'none' if exact == 0 else f'{exact:.1%}'} and {x['fx']['determinism_tier_identical_share']:.1%}")
        gates = {row["claim"].split("More deterministic than ")[1]: row["verdict"] for row in D.doc["decision_rules"] if row["claim"].startswith("More deterministic than ")}
        passed = [x["name"] for x in rows if gates.get(x["fx"]["model_requested"], "").startswith("PASS")]
        held = [f"{x['name']} at {x['fx']['determinism_tier_identical_share']:.3f}" for x in rows if not gates.get(x["fx"]["model_requested"], "").startswith("PASS")]
        gate = ((f" the comparative determinism claim is made for {', '.join(passed)}" if passed else "")
                + (" and" if passed and held else "")
                + (f" not made for {', '.join(held)}" if held else ""))
        determinism = (f" The fly returned {fly_det}; the model arms returned byte-identical output and the same tier on, respectively, "
                       f"{'; '.join(parts)} of records across the repeats, so by the pre-registered gate (fly 1.00 and model below 0.90 on tier identity){gate}.")
    return ("**The language-model arms beside the fly.** " + " ".join(sentences) + " " + fly + same + determinism +
            " The model arms' 300 records are a tier-stratified subset (60 per tier), so their error is not comparable with a full-split figure; "
            "the same-record rows are the fair comparison. Latency and cost are on different footings by design: an API call over the network against a "
            "forward pass on the laptop that trained the model.")


def prose_examples(D: Data) -> str:
    """Section 4.1 paragraph for the post-hoc arm g2-examples; every number from results.json, the post-hoc status stated first."""
    ex_rows = [(v, D.frontier.get(EX[v])) for v in VENDORS]
    have = [(v, fx) for v, fx in ex_rows if fx]
    head = ("**The post-hoc examples arm.** After the four arm g results above had been read, a second model arm was run at the author's request "
            "(g2-examples; amendment 1, row 17): the same four models and served ids, the same 300 records, k = 3, the same schema, validator, and "
            "instruction block, plus a fixed block of engine-scored records from the training split in the cached system prefix, so that the models, like the "
            "local arms, saw the engine's outputs and not only its published description. It is post-hoc: it changes no pre-registered rule and no headline, "
            "and it is reported beside arm g, not in place of it.")
    if not have:
        return head + " Its runs are awaiting completion; Table 9 will carry them beside arm g."
    e0 = have[0][1]["examples"]
    split_rel = "/".join(e0["source_split"].split(":")[0].split("/")[-2:]) + ":train"   # splits/dti_seed1.json:train, not the absolute path
    design = (f" The block holds E = {e0['E']} records, {e0['E'] // 5} per tier, drawn from `{split_rel}` with seed {e0['selection_seed']} "
              f"(record-id digest {e0['record_ids_sha256'][:12]}), identical across vendors and repeats; none of them is among the 300 scored records or anywhere in "
              f"the test split (checked before the first call). E is the largest of 50, 100, and 200 that keeps the prefix under 150,000 tokens on every vendor's own "
              f"tokenizer or count endpoint; the prefix measured "
              + ", ".join(f"{short_name(D, v)} {fx['examples']['prefix_tokens_measured'][v]:,}" for v, fx in have if fx["examples"].get("prefix_tokens_measured"))
              + " tokens. The local arms were trained on 13,999 scored records; the models saw 100.")
    sentences = []
    for v, fx in have:
        r2, r1 = D.R[EX[v]], D.R[v]
        g = fx.get("gain_vs_g") or {}
        gc, gt = g.get("composite_mae_gain") or {}, g.get("tier_acc_gain") or {}
        cache = f"{fx['cache_hit_share']:.0%} of calls read the cached prefix"
        s_ = (f"{short_name(D, v)}: composite error {f(r1['dti_mae']['mean'])} with the paper alone against {f(r2['dti_mae']['mean'])} with the examples "
              f"(paired gain {gain_cell(gc)} points over {g.get('n_records', 0)} records), tier agreement {f(r1['dti_tier_accuracy']['mean'], 3)} against "
              f"{f(r2['dti_tier_accuracy']['mean'], 3)} (Wilson 95% {f(r2['dti_tier_accuracy']['ci_low'], 3)} to {f(r2['dti_tier_accuracy']['ci_high'], 3)}; "
              f"{gt.get('discordant_g2_only', 0)} records right only with examples, {gt.get('discordant_g_only', 0)} right only without, exact McNemar p "
              f"{'not defined' if gt.get('mcnemar_exact_p') is None else f'{gt['mcnemar_exact_p']:.3f}'}); "
              f"median latency {fx['latency_ms_median'] / 1000:.1f} s per call, ${fx['usd_per_record']:.3f} per record, {cache}"
              f"{'' if fx['complete'] else '; run incomplete'}.")
        sentences.append(s_)
    missing = [short_name(D, v) for v, fx in ex_rows if not fx]
    tail = (f" Awaiting run: {', '.join(missing)}." if missing else "")
    return head + design + " " + " ".join(sentences) + tail


def prose_bii(D: Data) -> str:
    a = D.m("connectome", "bii_mae")
    if a["mean"] is None:
        done = [lbl for aid, lbl in LOCAL if D.has(aid, "bii")]
        lin = D.m("linear", "bii_mae")
        return ("**BII.** The fly's BII run has not finished. Arms finished so far: " + (", ".join(done) or "none") + "."
                + (f" The linear floor reached score error {pv(lin, 4)} and gate agreement {pv(D.m('linear', 'bii_gate_accuracy'), 3)} on 4,000 synthetic windows."
                   if lin["mean"] is not None else ""))
    b = D.pair("bii", "shuffled", "bii_mae"); c = D.pair("bii", "random", "bii_mae")
    return (f"**BII.** Under the seed policy with empty registries the fly reached score error {pv(a, 4)} (\u00d7100: {f(a['mean'] * 100)}) and gate agreement "
            f"{pv(D.m('connectome', 'bii_gate_accuracy'), 3)}; shuffle minus fly {pdlt(b, 4) if b else 'awaiting run'}, random graph minus fly "
            f"{pdlt(c, 4) if c else 'awaiting run'} (pre-registered margin {MARGIN_BII}).")


# ------------------------------------------------------------------ work per record (Table 10)
def work_rows(D: Data) -> tuple[list[dict], list[str]]:
    """short cells for Table 10; every derivation and source goes to the notes list printed under the table"""
    rows, notes = [], []
    run_p = ROOT / "runs" / "dti" / "connectome" / "seed1" / "run.json"
    run = json.loads(run_p.read_text()) if run_p.exists() else None
    bench_p = ROOT / "runs" / "bench_speed.json"
    bench = json.loads(bench_p.read_text()) if bench_p.exists() else None
    lat = D.m("connectome", "latency_ms")
    if run:
        g = run["run_meta"]["graph"]; T = run["config"]["T"]
        E, n_sens, n_ro = g["e"], g["n_sensory"], g["n_descending"] + g["n_motor"]
        d_in = len(run["run_meta"]["standardization"]["mean"]); d_out = 14  # 8 dims + composite + 5 tiers (flytrust DTI_SPEC)
        edge = 2 * E * T; w_in = d_in * n_sens; ro = n_ro * d_out
        total = edge + w_in + ro
        rows.append({"arm": "Fly wiring, shuffle, random graph (a, b, c; identical by construction)", "work": f"{total:,}",
                     "latency": f"{f(lat['mean'])} at batch 1; {f(lat.get('batch_256_per_record_ms'))} at batch 256" if bench else "not measured",
                     "usd": "$0.00 marginal, on-device", "tokens": "not applicable"})
        notes.append(f"Fixed graphs: 2\u00b7E\u00b7T = 2\u00b7{E:,}\u00b7{T} = {edge:,}; W_in = {d_in}\u00b7{n_sens:,} = {w_in:,}; readout = {n_ro:,}\u00b7{d_out} = {ro:,}."
                     + (f" Latency from runs/bench_speed.json (median forward, in_dim {bench['in_dim']}, MPS, torch {bench['torch']}); the bench covers the connectome forward only, so the matched network and the linear floor are not measured." if bench else ""))
    if D.has("mlp", "dti"):
        mrun = json.loads((ROOT / "runs" / "dti" / "mlp" / "seed1" / "run.json").read_text())["run_meta"]
        h = mrun["hidden_width"]; d_in = len(mrun["standardization"]["mean"]); w = d_in * h + h * h + h * 14
        rows.append({"arm": "Matched-parameter network (d)", "work": f"{w:,}", "latency": "not measured", "usd": "$0.00 marginal, on-device", "tokens": "not applicable"})
        notes.append(f"Matched network: {d_in}\u00b7{h:,} + {h:,}\u00b7{h:,} + {h:,}\u00b714.")
    if D.has("linear", "dti"):
        rows.append({"arm": "Linear floor (e)", "work": f"{65 * 14:,}", "latency": "not measured", "usd": "$0.00 marginal, on-device", "tokens": "not applicable"})
        notes.append("Linear floor: 65\u00b714. Electricity is not measured for any on-device arm.")
    for aid in ("anthropic", "openai", "xai", "gemini"):
        arm = next(a for a in D.doc["arms"] if a["id"] == aid); fx = D.frontier.get(aid)
        if not fx:
            rows.append({"arm": f"{arm['model']} (g)", "work": "not public", "latency": "awaiting run", "usd": "awaiting run", "tokens": "awaiting run"}); continue
        t = fx["tokens_per_record"]
        served = "/".join(fx["response_models"])
        rows.append({"arm": f"{fx['model_requested']} (g)" + ("" if served == fx["model_requested"] else f", served as {served}"), "work": "not public",
                     "latency": f"{fx['latency_ms_median']:,.0f} median per call; p95 {fx['latency_ms_p95']:,.0f}",
                     "usd": f"${fx['usd_per_record']:.4f}", "tokens": f"{t.get('input', 0):,.0f} + {t.get('cache_read', 0):,.0f} / {t.get('output', 0):,.0f}"})
        notes.append(f"{fx['model_requested']}: {fx['latency_calls']} calls; ${fx['usd_per_call']:.4f} per call over k = {fx['k']} calls per record; "
                     f"prices from {D.R[aid]['usd_per_record']['price_source']}; output tokens include thinking.")
    return rows, notes


# ------------------------------------------------------------------ provenance (PROTOCOL 13) on the surface, once
import re as _re

DIGESTS_NOTE = "Full digests in results/results.json (footers) and teachers/MANIFEST.md."


def footer_parts(D: Data, task: str) -> dict:
    """the PROTOCOL 13 footer string from results.json, split into its labelled segments"""
    segs = [x.strip() for x in _re.split(r"\s*\|\s*", D.doc["footers"][task].replace("\n", " ")) if x.strip()]
    out = {}
    for seg in segs:
        key = seg.split(":")[0] if ":" in seg.split(" ")[0] + ":" or seg.startswith(("Feature spec", "Evaluated", "Language-model arms")) else seg
        if seg.startswith("Feature spec"):
            out["feature_spec"] = seg[len("Feature spec"):].strip()
        elif seg.startswith("Evaluated"):
            out["evaluated"] = seg[len("Evaluated"):].strip()
        elif seg.startswith("Language-model arms:"):
            out["models"] = seg[len("Language-model arms:"):].strip()
        else:
            k, _, v = seg.partition(":")
            out[k.strip().lower()] = v.strip()
    return out


def short_hashes(text: str) -> str:
    return _re.sub(r"\b([0-9a-f]{12})[0-9a-f]{28,52}\b", r"\1", text)


def coverage_prose(cov: str) -> str:
    """'TEST only, 4001 records, 1 seeds {1} of protocol {1..5}; ...' -> 'TEST split only, 4,001 records, seed 1 of the protocol's five; ...'"""
    m = _re.match(r"TEST only, (\d+) records, (\d+) seeds \{([^}]*)\} of protocol \{1\.\.(\d+)\}(.*)", cov)
    if not m:
        return cov
    n_rec, n, seeds, total, rest = int(m.group(1)), int(m.group(2)), m.group(3).replace(",", ", "), int(m.group(4)), m.group(5)
    words = {5: "five"}.get(total, str(total))
    if n == 0:
        seed_txt = f"no seed finished of the protocol's {words}"
    elif n == total:
        seed_txt = f"all {words} seeds"
    else:
        seed_txt = f"seed{'s' if n > 1 else ''} {seeds} of the protocol's {words}"
    return f"TEST split only, {n_rec:,} records, {seed_txt}{rest}"


def data_prose(data: str) -> str:
    data = _re.sub(r"(\d+)/(\d+)/(\d+) records", lambda m: f"{int(m.group(1)):,} / {int(m.group(2)):,} / {int(m.group(3)):,} records (train / validation / test)", data)
    return short_hashes(data.replace("SYNTHETIC, zero PHI", "synthetic, zero PHI"))


def graph_prose(graph: str) -> str:
    graph = _re.sub(r"N=(\d+)", lambda m: f"N = {int(m.group(1)):,}", graph)
    graph = _re.sub(r"E=(\d+)", lambda m: f"E = {int(m.group(1)):,}", graph)
    return short_hashes(graph.replace("weight>=5", "weight \u2265 5"))


def provenance_full(D: Data) -> str:
    """the whole PROTOCOL 13 footer for the DTI task as one small paragraph under Table 8a; the model-arm line sits under Table 9"""
    f = footer_parts(D, "dti")
    return ("<small>*Provenance (PROTOCOL 13) for Table 8a and, unless its own line says otherwise, every table below. "
            f"Snapshot {SNAPSHOT} (substrate download, teacher labels, protocol freeze). Source: {f['source']}. Graph: {graph_prose(f['graph'])}. "
            f"Teacher: {short_hashes(f['teacher'])}. Data: {data_prose(f['data'])}. Coverage: {coverage_prose(f['coverage'])}. "
            f"Feature spec {short_hashes(f['feature_spec'])}. Evaluated {f['evaluated']}. {DIGESTS_NOTE}*</small>")


def provenance_line(D: Data, task: str = "dti", extra: str = "") -> str:
    """one line under every later table: what is shared, then only what differs"""
    f = footer_parts(D, task)
    n = int(_re.search(r"(\d+) seeds", f["coverage"]).group(1)) if _re.search(r"(\d+) seeds", f["coverage"]) else 0
    line = f"Provenance: as Table 8a; snapshot {SNAPSHOT}; seeds {n} of {N_SEEDS_PROTOCOL}; evaluated {f['evaluated']}."
    return f"<small>*{line}{(' ' + extra) if extra else ''}*</small>"


def provenance_bii(D: Data) -> str:
    """what the BII footer changes against the DTI one, stated once under Table 8b"""
    f = footer_parts(D, "bii")
    return (f"BII differs: teacher {short_hashes(f['teacher'])}; data {data_prose(f['data'])}; coverage {coverage_prose(f['coverage'])}; "
            f"feature spec {short_hashes(f['feature_spec'])}; language-model arms {f['models']}.")


def provenance_models(D: Data) -> str:
    return "Language-model arms: " + short_hashes(footer_parts(D, "dti")["models"]) + "."


# ------------------------------------------------------------------ section 4 markdown
def params_cell(D: Data, aid: str, task: str) -> str:
    params = D.ex(aid, task, "trainable_params")
    return f"{params:,}" if params else f"{D.ex(aid, task, 'fitted_params'):,} (closed form)"


def table8(D: Data) -> list[str]:
    """Tables 8a to 8c: one comparison per table, at most six columns after the arm label, numbers right-aligned."""
    L = ["**Table 8: Main results by arm, test split, mean over finished seeds with 95% t-interval in brackets; a row with one seed is a point and its Seeds cell says single seed.** Lower error is better; higher agreement is better. The headline composite is the one recomputed from the predicted dimensions with the engine's weights; the directly predicted head is beside it (DECISIONS \"composite head\", chosen after seed 1 for the instability stated in Section 4.1). SYNTHETIC records, zero PHI.", "",
         "*8a. DTI error against the deployed engine. Units: points on the 0 to 100 scale.*", "",
         row(["Arm", "Composite, headline", "Composite, direct head", "Per-dimension, mean of 8", "Trainable parameters", "Seeds"]), rule("lrrrrl")]
    for aid, lbl in LOCAL:
        if not D.has(aid, "dti"):
            L.append(row([lbl, "awaiting run", "", "", "", "0"])); continue
        dims_mean = np.mean([p["mean"] for p in D.m(aid, "dti_dim_mae")["per_dimension"]])
        L.append(row([lbl, cell(D.m(aid, "dti_mae")), cell(D.m(aid, "dti_mae_direct")), f"{dims_mean:.2f}", params_cell(D, aid, "dti"), seeds_cell(D.n_seeds(aid, "dti"))]))
    L += [row(["Teacher (f)", "0", "0", "0", "0", "by construction"]), "", provenance_full(D), "",
          "*8a\u2032. DTI agreement with the engine's tier (5 classes). Units: share of test records; ECE on the same 0 to 1 scale.*", "",
          row(["Arm", "Tier agreement", "Macro-F1", "ECE", "Seeds"]), rule("lrrrl")]
    for aid, lbl in LOCAL:
        if not D.has(aid, "dti"):
            L.append(row([lbl, "awaiting run", "", "", "0"])); continue
        L.append(row([lbl, cell(D.m(aid, "dti_tier_accuracy"), 3), cell(D.ex(aid, "dti", "macro_f1"), 3), cell(D.ex(aid, "dti", "ece"), 3), seeds_cell(D.n_seeds(aid, "dti"))]))
    L += [row(["Teacher (f)", "1.000", "1.000", "0", "by construction"]), "", provenance_line(D), "",
          "*8b. BII error under the seed policy with empty registries (teacher = VIGIL scorer). Units: score on the 0 to 1 scale; the \u00d7100 column is the same error in points.*", "",
          row(["Arm", "BII MAE", "BII MAE \u00d7100", "Trainable parameters", "Seeds"]), rule("lrrrl")]
    for aid, lbl in LOCAL:
        if not D.has(aid, "bii"):
            L.append(row([lbl, "awaiting run", "", "", "0"])); continue
        r = D.m(aid, "bii_mae")
        L.append(row([lbl, cell(r, 4), f(r["mean"] * 100), params_cell(D, aid, "bii"), seeds_cell(D.n_seeds(aid, "bii"))]))
    L += [row(["Teacher (f)", "0", "0", "0", "by construction"]), "", provenance_line(D, "bii", provenance_bii(D)), "",
          "*8b\u2032. BII agreement with the scorer's gate (4 classes). Units: share of test windows; ECE on the 0 to 1 scale.*", "",
          row(["Arm", "Gate agreement", "Macro-F1", "ECE", "Seeds"]), rule("lrrrl")]
    for aid, lbl in LOCAL:
        if not D.has(aid, "bii"):
            L.append(row([lbl, "awaiting run", "", "", "0"])); continue
        L.append(row([lbl, cell(D.m(aid, "bii_gate_accuracy"), 3), cell(D.ex(aid, "bii", "macro_f1"), 3), cell(D.ex(aid, "bii", "ece"), 3), seeds_cell(D.n_seeds(aid, "bii"))]))
    L += [row(["Teacher (f)", "1.000", "1.000", "0", "by construction"]), "", provenance_line(D, "bii", "BII rows as Table 8b."), "",
          "*8c. DTI per-dimension MAE, one row per dimension, arms across. Units: points; no dimension is degenerate, every teacher SD is at least 12.4 points. The Opus 5 column is its 300 records, k = 3, mean of repeats.*", ""]
    cols = LOCAL + [("anthropic", "Opus 5 (g)")]
    heads = {aid: SHORT[aid] for aid in SHORT}; heads["anthropic"] = "Opus 5 (g)"
    L += [row(["Dimension"] + [heads[aid] for aid, _ in cols]), rule("l" + "r" * len(cols))]
    per = {aid: D.m(aid, "dti_dim_mae")["per_dimension"] for aid, _ in cols}
    live = {aid: bool(per[aid]) and per[aid][0]["mean"] is not None for aid, _ in cols}
    for i, d in enumerate(DIMS):
        L.append(row([d.capitalize()] + [("awaiting run" if not live[aid] else (f(per[aid][i]["mean"]) if aid == "anthropic" else cell(per[aid][i]))) for aid, _ in cols]))
    L.append(row(["Seeds"] + [("0" if not live[aid] else ("300 records, k = 3" if aid == "anthropic" else seeds_cell(D.n_seeds(aid, "dti")))) for aid, _ in cols]))
    L += ["", provenance_line(D)]
    return L


def model_label(D: Data, aid: str) -> str:
    arm = next(a for a in D.doc["arms"] if a["id"] == aid); fx = D.frontier.get(aid)
    if not fx:
        return f"{arm['label']} ({arm['model']})"
    served = "/".join(fx["response_models"])
    tail = "" if served == fx["model_requested"] else f", served as {served}"
    return f"{arm['label']} ({fx['model_requested']}{tail}{'' if fx['complete'] else '; run incomplete'})"


def table9(D: Data) -> list[str]:
    """Table 9 (agreement) and Table 9\u2032 (determinism, latency, cost): the same arm order in both."""
    L = ["**Table 9: Language-model arms beside the fly: agreement with the engine.** One row per vendor; a vendor whose protocol run (N = 300, k = 3) has no summary yet says \"awaiting run\". Units: composite error in points on the 0 to 100 scale, mean of repeats, direct head in parentheses; tier agreement as a share with its Wilson 95% interval over records. The fly row is the full test split; the same-record block below is the fair comparison.", "",
         row(["Arm", "Records \u00d7 repeats", "Composite MAE (direct)", "Tier agreement, Wilson 95%", "Macro-F1"]), rule("lrrrr")]
    for aid in ("anthropic", "openai", "xai", "gemini"):
        fx = D.frontier.get(aid)
        if not fx:
            L.append(row([model_label(D, aid), "awaiting run", "", "", ""])); continue
        r = D.R[aid]
        L.append(row([model_label(D, aid), f"{fx['n_records']} \u00d7 {fx['k']}", f"{f(r['dti_mae']['mean'])} ({f(r['dti_mae_direct']['mean'])})",
                      f"{f(r['dti_tier_accuracy']['mean'], 3)} [{f(r['dti_tier_accuracy']['ci_low'], 3)}, {f(r['dti_tier_accuracy']['ci_high'], 3)}]", f(fx.get("macro_f1_mean_of_runs"), 3)]))
    a = D.m("connectome", "dti_mae"); at = D.m("connectome", "dti_tier_accuracy"); lat = D.m("connectome", "latency_ms"); det = D.m("connectome", "determinism")
    if a["mean"] is not None:
        n_test = int(D.doc["footers"]["dti"].split("Coverage: TEST only, ")[1].split(" records")[0])
        L.append(row(["Fly wiring (a), full test split (the 300 above are a stratified subset; the same-record block below is the fair comparison)",
                      f"{n_test:,} \u00d7 2 passes; {seeds_cell(D.n_seeds('connectome', 'dti'))}",
                      f"{cell(a)} ({cell(D.m('connectome', 'dti_mae_direct'))})", cell(at, 3), cell(D.ex("connectome", "dti", "macro_f1"), 3)]))
    L += table9_same_records(D)
    L += table9_examples(D)
    L += ["", provenance_line(D, "dti", provenance_models(D) + provenance_examples(D))]
    L += ["", "**Table 9\u2032: Language-model arms beside the fly: determinism, latency, cost, tokens.** Same arms and order as Table 9. Units: determinism as the share of records (repeat columns) and the mean composite range across repeats in points; latency in ms per call (median / p95); cost in USD per record over k calls, prices from each run's prices.json (source and retrieval date in the provenance line under Table 9), never from memory (rule 14); tokens per record as input uncached + cache read / output. The fly's repeat is two forward passes on one test batch of 64 per seed, compared bitwise (torch.equal), not yet k = 3 on the 300 records; its marginal cost is on-device, electricity not measured.", "",
          row(["Arm", "Same tier, every repeat", "Byte-identical, every repeat", "Composite range, points", "Latency ms, median / p95", "USD per record", "Tokens in + cached / out"]), rule("lrrrrrr")]
    for aid in ("anthropic", "openai", "xai", "gemini"):
        fx = D.frontier.get(aid)
        if not fx:
            L.append(row([model_label(D, aid), "awaiting run", "", "", "", "", ""])); continue
        t = fx["tokens_per_record"]
        L.append(row([model_label(D, aid), f"{f(fx['determinism_tier_identical_share'], 3)} (n = {fx['determinism_records']})", f(fx["determinism_exact_match_share"], 3),
                      f(fx["composite_range_mean"]), f"{fx['latency_ms_median']:,.0f} / {fx['latency_ms_p95']:,.0f}", f"${fx['usd_per_record']:.4f}",
                      f"{t.get('input', 0):,.0f} + {t.get('cache_read', 0):,.0f} / {t.get('output', 0):,.0f}"]))
    if a["mean"] is not None:
        L.append(row(["Fly wiring (a), full test split", f"{f(det['mean'], 3)} (n = {det['n']} per seed)", f(det["mean"], 3), "0",
                      f"{f(lat['mean'])} / not measured", "$0.00 marginal", "not applicable"]))
    ex_live = [v for v in VENDORS if D.frontier.get(EX[v])]
    if ex_live:
        L += ["", "*Post-hoc arm g2-examples (amendment 1, row 17), same columns; tokens per record now include the example prefix read from cache; the cache column is the share of calls whose usage reported cached prompt tokens.*", "",
              row(["Arm", "Same tier, every repeat", "Byte-identical, every repeat", "Composite range, points", "Latency ms, median / p95", "USD per record", "Tokens in + cached / out", "Calls reading the cache"]), rule("lrrrrrrr")]
        for v in ex_live:
            fx = D.frontier[EX[v]]; t = fx["tokens_per_record"]
            L.append(row([model_label(D, EX[v]), f"{f(fx['determinism_tier_identical_share'], 3)} (n = {fx['determinism_records']})", f(fx["determinism_exact_match_share"], 3),
                          f(fx["composite_range_mean"]), f"{fx['latency_ms_median']:,.0f} / {fx['latency_ms_p95']:,.0f}", f"${fx['usd_per_record']:.4f}",
                          f"{t.get('input', 0):,.0f} + {t.get('cache_read', 0):,.0f} / {t.get('output', 0):,.0f}", f"{fx['cache_hit_share']:.1%}"]))
    L += ["", provenance_line(D, "dti", "Model-arm settings and prices as the line under Table 9.")]
    return L


def table9_examples(D: Data) -> list[str]:
    """Arm g and the post-hoc arm g2-examples side by side per vendor, with the gain from the examples as a paired difference over the same records."""
    live = [v for v in VENDORS if D.frontier.get(EX[v])]
    if not live:
        return ["", "*Post-hoc block (arm g2-examples, amendment 1, row 17): awaiting run; it will show arm g and arm g2 side by side per vendor with the gain from the examples.*"]
    e0 = D.frontier[EX[live[0]]]["examples"]
    L = ["", f"*Post-hoc block: arm g (paper only) and arm g2-examples (paper plus E = {e0['E']} engine-scored training records in the cached prefix, "
         f"{e0['E'] // 5} per tier, seed {e0['selection_seed']}, id digest {e0['record_ids_sha256'][:12]}; amendment 1, row 17) side by side on the identical 300 records. "
         f"Added after the arm g results were read, at the author's request; post-hoc, no pre-registered rule depends on it. Gain is the paired per-record difference, "
         f"positive when the examples helped: composite error g minus g2 with a 95% t-interval over records; tier agreement g2 minus g with the discordant counts "
         f"(right only with examples / right only without) and the exact McNemar p.*", "",
         row(["Vendor, id requested", "Composite MAE, g", "Composite MAE, g2", "Gain, points [95% CI]", "Tier agreement, g [Wilson 95%]", "Tier agreement, g2 [Wilson 95%]", "Gain, share (discordant; McNemar p)"]),
         rule("lrrrrrr")]
    for v in VENDORS:
        fx2 = D.frontier.get(EX[v]); fx1 = D.frontier.get(v)
        name = f"{short_name(D, v)}, `{fx1['model_requested'] if fx1 else next(a for a in D.doc['arms'] if a['id'] == v)['model']}`"
        if not fx2 or not fx1:
            L.append(row([name, cell(D.R[v]["dti_mae"]) if fx1 else "awaiting run", "awaiting run", "", cell(D.R[v]["dti_tier_accuracy"], 3) if fx1 else "", "", ""])); continue
        g = fx2.get("gain_vs_g") or {}
        gt = g.get("tier_acc_gain") or {}
        r1, r2 = D.R[v], D.R[EX[v]]
        tier_gain = ("awaiting run" if gt.get("mean") is None else
                     f"{gt['mean']:+.3f} ({gt['discordant_g2_only']} / {gt['discordant_g_only']}; p {'n/a' if gt.get('mcnemar_exact_p') is None else f'{gt['mcnemar_exact_p']:.3f}'})")
        L.append(row([name + ("" if fx2["complete"] else " (g2 run incomplete)"), f(r1["dti_mae"]["mean"]), f(r2["dti_mae"]["mean"]), gain_cell(g.get("composite_mae_gain")),
                      f"{f(r1['dti_tier_accuracy']['mean'], 3)} [{f(r1['dti_tier_accuracy']['ci_low'], 3)}, {f(r1['dti_tier_accuracy']['ci_high'], 3)}]",
                      f"{f(r2['dti_tier_accuracy']['mean'], 3)} [{f(r2['dti_tier_accuracy']['ci_low'], 3)}, {f(r2['dti_tier_accuracy']['ci_high'], 3)}]", tier_gain]))
    return L


def provenance_examples(D: Data) -> str:
    live = [v for v in VENDORS if D.frontier.get(EX[v])]
    if not live:
        return ""
    parts = []
    for v in live:
        fx = D.frontier[EX[v]]; ex = fx["examples"]
        parts.append(f"{fx['model_requested']} run {fx['run']}, E={ex['E']}, prefix sha256 {fx['prompt_sha256'][:12]}, base prompt sha256 {fx['base_prompt_sha256'][:12]}, "
                     f"prefix {ex['prefix_tokens_measured'][v]:,} tokens by {ex['prefix_token_counter'].split(',')[0].split(' (')[0]}, cache reads on {fx['cache_hit_share']:.1%} of calls")
    return " Post-hoc arm g2-examples: " + "; ".join(parts) + "."


def table9_same_records(D: Data) -> list[str]:
    """Every arm on the identical record ids the language-model arms scored (metrics_subset300.json), the fair comparison."""
    subs = {aid: D.ex(aid, "dti", "subset300") for aid, _ in LOCAL}
    if not any(subs.values()):
        return ["", "*Same-record block: awaiting scripts/eval_subset.py (every local arm re-scored on the language-model arms' 300 ids).*"]
    any_sub = next(v for v in subs.values() if v)
    L = ["", f"*Same-record block: every arm on the identical {any_sub['n_records']} test records the language-model arms scored (ids from "
         f"{any_sub['ids_source']['run']}/calls.jsonl, sha256 {any_sub['ids_source']['calls_file_sha256'][:12]}; a logged second read of the test split, rule 9, reason "
         f"\"{any_sub['reason']}\"). Units as above; Wilson 95% intervals are over the {any_sub['n_records']} records; local arms show the mean over their finished seeds.*", "",
         row(["Arm, same 300 records", "Composite, headline", "Composite, direct head", "Per-dimension, mean of 8", "Tier agreement, Wilson 95%", "Macro-F1", "Seeds or repeats"]), rule("lrrrrrl")]
    for aid, lbl in LOCAL:
        sub = subs[aid]
        if not sub:
            L.append(row([lbl, "awaiting run", "", "", "", "", ""])); continue
        w = sub["tier_acc_wilson_mean_over_seeds"]
        L.append(row([lbl, cell(sub["composite_mae_recomputed_from_dims"]), cell(sub["composite_mae_direct"]), cell(sub["dims_mae_mean"]),
                      f"{f(sub['tier_acc']['mean'], 3)} [{w[0]:.3f}, {w[1]:.3f}]", cell(sub["tier_macro_f1"], 3), seeds_cell(len(sub["seeds"]))]))
    for aid in ("anthropic", "openai", "xai", "gemini"):
        fx = D.frontier.get(aid)
        if not fx:
            L.append(row([model_label(D, aid), "awaiting run", "", "", "", "", ""])); continue
        r = D.R[aid]
        pdm = np.mean([p["mean"] for p in r["dti_dim_mae"]["per_dimension"]])
        L.append(row([model_label(D, aid), f(r["dti_mae"]["mean"]), f(r["dti_mae_direct"]["mean"]), f"{pdm:.2f}",
                      f"{f(r['dti_tier_accuracy']['mean'], 3)} [{f(r['dti_tier_accuracy']['ci_low'], 3)}, {f(r['dti_tier_accuracy']['ci_high'], 3)}]",
                      f(fx.get("macro_f1_mean_of_runs"), 3), f"k = {fx['k']} repeats, mean"]))
    return L


def table10(D: Data) -> list[str]:
    L = ["**Table 10: Work per record.** The fly's count is exact from run.json and graph_meta.json: 2\u00b7E\u00b7T counts one multiply and one add per edge per unrolled step for the signed edge sum; the input projection is applied once per record; per-neuron pointwise work (gain, leak, bias, rectifier; about 6\u00b7N\u00b7T = 8 million) is not in the count. The model arms' compute is not public; their tokens are measured from the API usage objects. Units: multiply-adds per record; latency in ms per record (on-device arms) or per call (model arms); cost in USD per record; tokens per record as input uncached + cache read / output. Derivations and sources are in the notes under the table.", "",
         row(["Arm", "Multiply-adds per record", "Latency, ms", "USD per record", "Tokens in + cached / out"]), rule("lrrrr")]
    rows, notes = work_rows(D)
    for r in rows:
        L.append(row([r["arm"], r["work"], r["latency"], r["usd"], r["tokens"]]))
    L += [""] + [f"Notes: {n}" if i == 0 else n for i, n in enumerate(notes)]
    L += ["", provenance_line(D)]
    return L


def table11(D: Data) -> list[str]:
    """Table 11 (every rule against its bar) and Table 11\u2032 (seed-level evidence for the paired claims)."""
    L = ["**Table 11: Pre-registered decision rules (Table 4 / PROTOCOL 8.1), evaluated on the finished seeds.** A verdict is PASS or FAIL only at five seeds; below that it reads INSUFFICIENT SEEDS and the next column says whether the point estimate meets the bar. Rows marked descriptive are not pre-registered thresholds. Units follow the metric: error in points, agreement as a share, latency as a ratio. A 95% CI is printed beside the value when a bound exists.", "",
         row(["Task", "Claim", "Metric", "Threshold", "Value [95% CI]", "Verdict", "Point vs bar"]), rule("lllllll")]
    import re as _re
    paired = []
    for rw in D.doc["decision_rules"]:
        v = rw["value"]
        v_s = "awaiting run" if v is None else (", ".join(f"{x:.3f}" for x in v) if isinstance(v, list) else (f"{v:,.0f}\u00d7" if "ratio" in rw["metric"] else f"{v:.4f}"))
        ci = rw["ci"]
        if not (ci[0] is None and ci[1] is None):
            v_s += f" [{f(ci[0], 4)}, {f(ci[1], 4)}]"
        m = _re.match(r"^INSUFFICIENT SEEDS \((\d+)/(\d+); point estimate (meets|misses) the bar\)$", rw["verdict"])
        verdict, point = (f"INSUFFICIENT SEEDS ({m.group(1)}/{m.group(2)})", m.group(3)) if m else (rw["verdict"], "")
        L.append(row([rw["task"].upper(), rw["claim"], glyphs(rw["metric"]), glyphs(rw["threshold"]), v_s, f"**{verdict}**", point]))
        if "per_seed_connectome_better" in rw or "p_raw_one_sided" in rw:
            paired.append(rw)
    L += ["", provenance_line(D, "dti", "BII rows as Table 8b.")]
    if paired:
        L += ["", "**Table 11\u2032: Seed-level evidence for the paired claims in Table 11.** Seeds is the count finished; \"fly better on every seed\" is the per-seed sign of the difference; p-values are the one-sided paired t over seeds for the primary family {a-b, a-c, a-e}, raw and Holm-adjusted (rule 19), printed once two seeds exist.", "",
              row(["Task", "Claim", "Metric", "Seeds", "Fly better on every seed", "p raw / Holm"]), rule("lllrll")]
        for rw in paired:
            every = rw.get("per_seed_connectome_better"); every_s = "" if every is None else ("yes" if every else "no")
            p_s = "" if rw.get("p_raw_one_sided") is None else f"{rw['p_raw_one_sided']:.4f} / {rw['p_holm']:.4f}"
            if rw.get("p_raw_one_sided") is None and rw["n_seeds"] == 1:
                p_s = "n/a (one seed)"
            L.append(row([rw["task"].upper(), rw["claim"], glyphs(rw["metric"]), f(rw["n_seeds"], 0) if rw["n_seeds"] is not None else "awaiting run", every_s, p_s]))
        L += ["", provenance_line(D, "dti", "BII rows as Table 8b.")]
    pr = D.doc["pilot_rule"]
    ws = D.doc["wiring_sentence"] or f"not yet sayable ({D.n_seeds('connectome', 'dti')} of {N_SEEDS_PROTOCOL} seeds)"
    L += ["", f"Wiring sentence (rule 22, one of three pre-written strings): **{ws}**.",
          "", f"Pilot rule (Section 3.9): seeds with both the fly and the shuffle finished on DTI = {('{' + ', '.join(map(str, pr['seeds_with_both_a_and_b'])) + '}') if pr['seeds_with_both_a_and_b'] else 'none yet'}; "
          f"s_seed of the shuffle-minus-fly difference = {f(pr['s_seed_points'], 3)} points; verdict: **{glyphs(pr['verdict'])}**"
          + (f"; minimum detectable margin at five seeds about {pr['min_detectable_margin_at_5_seeds_points']:.2f} points" if pr.get("min_detectable_margin_at_5_seeds_points") else "") + "."]
    return L


def fig_captions(D: Data, F: dict) -> list[str]:
    n = D.n_seeds("connectome", "dti")
    single = " With one seed the panels show points only; intervals appear when two or more seeds have finished." if n == 1 else ""
    return [f"**Figure 3: Per-seed paired differences, control minus fly, on the same test records (paper/figures/fig3_paired_differences.png).** "
            f"Four small multiples, one per metric, at one scale for the three error metrics; each row is a control arm; each point is one seed; the bar is the "
            f"mean with its 95% t-interval over seeds when two or more exist (bootstrap interval from per_record.parquet in Table 11 once two seeds have it). Positive means the fly did better. The headline composite is the recomputed one; the direct head is the second panel. The dotted line on the composite panels is the "
            f"pre-registered margin of {MARGIN_DTI:.1f} point.{single} The interval is the seed-level t-interval until per-record errors exist for two seeds; "
            f"the protocol's hierarchical bootstrap (Section 3.9) replaces it then.",
            "",
            "**Figure 4: Per-dimension MAE by arm, eight small multiples at one scale, teacher at zero (paper/figures/fig4_dimension_mae.png).** One panel per "
            "DTI dimension, arms on the rows, error in points on a shared axis; the fly hollow blue, controls grey; the large marker is the mean over seeds"
            + (" (one seed: no per-seed points)" if n == 1 else ", the small points are seeds with a 95% t-interval bar") + ". Claude Opus 5's per-dimension error on its 300 records lies beyond the shared axis and is printed as a number at the right edge of each "
            "panel rather than plotted, so the comparison the figure exists to make (fixed graphs against trained controls) keeps its resolution."]


def section4(D: Data, F: dict) -> str:
    st = D.doc["status"]
    L = ["## 4. Results", "",
         f"Status **{st}**: {D.doc['runs_completed']} of {D.doc['runs_expected_full_protocol']} local runs finished (seeds {{{', '.join(map(str, D.seeds)) or 'none'}}} of the protocol's "
         f"{{1..{N_SEEDS_PROTOCOL}}}); language-model arms complete: {', '.join(k for k, v in D.frontier.items() if v.get('complete')) or 'none'}. "
         f"Every number in this section is read from results/results.json, regenerated by scripts/render_results.py on {D.doc['generated']} from git "
         f"{D.doc['git_sha'][:12]}; a cell that says \"awaiting run\" has no run behind it. Means are over finished seeds with a two-sided 95% t-interval "
         f"when two or more seeds exist; a single seed is a point marked as such. Paired differences are control minus fly on the same test records, so a "
         f"positive difference means the fly did better. The dataset health report (splits/qa_report.json) passed every line for both tasks before "
         f"any score below was computed. All records are SYNTHETIC; zero PHI.", "",
         "### 4.1 What the finished seeds say", "", prose_headline(D, F), "", prose_engine(D), "", prose_models(D), "", prose_examples(D), "", prose_bii(D), "",
         "### 4.2 Main results", ""] + table8(D) + [""]
    note = prose_floor_note(D)
    if note:
        L += [note, ""]
    L += ["### 4.3 Paired differences and per-dimension error", ""] + fig_captions(D, F) + ["", provenance_line(D), "",
          "### 4.4 The language-model arms", ""] + table9(D) + ["",
          "### 4.5 Work per record", ""] + table10(D) + ["",
          "### 4.6 Decision rules", ""] + table11(D) + [""]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ abstract + page sentences
ABSTRACT_MAX_WORDS = 110


def gap_range(D: Data, task: str = "dti", metric: str = "dti_mae") -> str:
    """matched network minus each fixed graph (a, b, c), arm means, printed as a range: 'by 1.9 to 2.2 points' or 'by about 2.2 points'"""
    d = D.m("mlp", metric)["mean"]
    gaps = sorted(d - D.m(aid, metric)["mean"] for aid in ("connectome", "shuffled", "random"))
    lo, hi = f"{gaps[0]:.1f}", f"{gaps[-1]:.1f}"
    return f"by about {hi} points" if lo == hi else f"by {lo} to {hi} points"


def abstract_sentences(D: Data, F: dict) -> str:
    """three sentences, at most ABSTRACT_MAX_WORDS words in total; the fixed abstract text around them lives in paper/paper.md"""
    n = F["n"]
    a = D.m("connectome", "dti_mae"); b = D.m("shuffled", "dti_mae")
    at = D.m("connectome", "dti_tier_accuracy")
    db = D.pair("dti", "shuffled", HEAD); dc = D.pair("dti", "random", HEAD)
    if F["case"] == "awaiting":
        return "[RESULTS SENTENCES: awaiting the fly, shuffle, and random-graph runs.]\n"
    prov = "On the first of five seeds, " if n == 1 else (f"On {n} of five seeds, " if F["provisional"] else "Over five seeds, ")
    ci = lambda r, nd=2: f" (95% CI {r['ci_low']:+.{nd}f} to {r['ci_high']:+.{nd}f})" if r.get("ci_low") is not None else ""
    status = "provisional until five seeds" if F["provisional"] else "at five seeds"
    if F["case"] in ("substrate", "substrate_c_caveat"):
        s1 = (f"{prov}the degree-preserving shuffle matched the fly's wiring against the DTI engine (composite error {b['mean']:.2f} against {a['mean']:.2f} points{ci(db)}); "
              f"the random graph matched on tier agreement and every dimension"
              + ("" if F["case"] == "substrate" else f" while trailing by {dc['mean']:.1f} points of composite error") + ".")
        s2 = f"Every fixed graph beat the parameter-matched network {gap_range(D)}: {status}, the substrate carries the computation."
    elif F["case"] == "wiring":
        s1 = (f"{prov}the fly's wiring beat its degree-preserving shuffle by {db['mean']:.2f} points{ci(db)} and the random graph by {dc['mean']:.2f} points{ci(dc)} "
              f"of composite error against the DTI engine, better on every seed, with tier agreement {at['mean']:.3f}.")
        s2 = f"Every fixed graph beat the parameter-matched network {gap_range(D)}; the finding is {status}."
    else:
        s1 = (f"{prov}the two null substrates disagreed: shuffle minus fly {db['mean']:+.2f} points{ci(db)}, random graph minus fly {dc['mean']:+.2f} points{ci(dc)}, "
              f"so none of the three pre-written wiring sentences is sayable and the ten-seed rule applies.")
        s2 = f"Every fixed graph beat the parameter-matched network {gap_range(D)}; the finding is {status}."
    rows = model_rows(D)
    s3 = ""
    if rows:
        lat = D.m("connectome", "latency_ms"); sub = D.ex("connectome", "dti", "subset300")
        fly_part = (f"the fly, {sub['tier_acc']['mean']:.0%}" if sub else f"the fly, {at['mean']:.0%} on the full test split")
        who = {1: rows[0]["name"], 2: "both models", 3: "the three models", 4: "the four models"}[len(rows)]
        n_rec = rows[0]["fx"]["n_records"]
        s3 = (f" On {n_rec} identical records {who} matched the engine's tier on {span(rows, 'tier', lambda x: f'{x:.0%}')} at "
              f"{span(rows, 'lat_s', lat_fmt)} and {span(rows, 'usd', lambda x: f'${x:.2f}')} per record; {fly_part} at {lat['mean']:.0f} ms and no marginal cost.")
        assert len(s3.split()) <= 45, f"abstract model sentence is {len(s3.split())} words (> 45)"
    out = s1 + " " + s2 + s3
    n_words = len(out.split())
    assert n_words <= ABSTRACT_MAX_WORDS, f"abstract sentences are {n_words} words (> {ABSTRACT_MAX_WORDS}); shorten the templates in abstract_sentences()"
    return out + "\n"


def page_sentences(D: Data, F: dict) -> dict:
    n = F["n"]
    a = D.m("connectome", "dti_mae"); b = D.m("shuffled", "dti_mae"); c = D.m("random", "dti_mae"); d = D.m("mlp", "dti_mae")
    at = D.m("connectome", "dti_tier_accuracy"); bt = D.m("shuffled", "dti_tier_accuracy"); ct = D.m("random", "dti_tier_accuracy"); dt = D.m("mlp", "dti_tier_accuracy")
    db = D.pair("dti", "shuffled", HEAD); dc = D.pair("dti", "random", HEAD)
    seeds = f"the first of {N_SEEDS_PROTOCOL} seeds" if n == 1 else (f"{n} of {N_SEEDS_PROTOCOL} seeds" if n < N_SEEDS_PROTOCOL else f"{n} seeds")
    ci = lambda r: f", 95% CI {r['ci_low']:+.2f} to {r['ci_high']:+.2f}" if r.get("ci_low") is not None else ""
    if F["case"] == "awaiting":
        s1 = "Wiring against its shuffle: awaiting run."; s2 = "Wiring against the random graph and the matched network: awaiting run."
    else:
        if db["mean"] < MARGIN_DTI:
            s1 = (f"On {seeds}, the fly's wiring and its degree-preserving shuffle reproduced the DTI engine equally well: composite error {a['mean']:.2f} vs "
                  f"{b['mean']:.2f} points (difference {db['mean']:+.2f}{ci(db)}), tier agreement {at['mean']:.3f} vs {bt['mean']:.3f}.")
        else:
            s1 = (f"On {seeds}, the fly's wiring beat its degree-preserving shuffle at reproducing the DTI engine by {db['mean']:.2f} points of composite error"
                  f"{ci(db)} ({a['mean']:.2f} vs {b['mean']:.2f}); tier agreement {at['mean']:.3f} vs {bt['mean']:.3f}.")
        c_part = (f"matched the fly on tier agreement ({ct['mean']:.3f} vs {at['mean']:.3f})" + (f" and trailed by {dc['mean']:.1f} points of composite error"
                  if dc["mean"] >= MARGIN_DTI else f" and composite error ({c['mean']:.2f} vs {a['mean']:.2f} points)"))
        s2 = (f"The random graph at matched density {c_part}; all three fixed graphs beat the same-size trained network ({d['mean']:.2f} points, {dt['mean']:.3f}).")
    rows = model_rows(D)
    if rows:
        lat = D.m("connectome", "latency_ms"); sub = D.ex("connectome", "dti", "subset300")
        fly_t, where = (sub["tier_acc"]["mean"], "same records") if sub else (at["mean"], "full test split")
        lo, hi = rows[-1], rows[0]
        n_rec = hi["fx"]["n_records"]
        count = {1: "One model", 2: "Two models", 3: "Three models", 4: "Four models"}[len(rows)]
        tier = f"{lo['tier']:.0%} ({lo['name']}) to {hi['tier']:.0%} ({hi['name']})" if len(rows) > 1 else f"{hi['tier']:.0%} ({hi['name']})"
        s3 = (f"{count} given the DTI paper and {n_rec} of the same records matched the engine's tier on {tier}, at {span(rows, 'lat_s', lat_fmt)} and "
              f"{span(rows, 'usd', lambda x: f'${x:.2f}')} per record. The fly, {where}: {fly_t:.0%}, {lat['mean']:.0f} ms, $0 marginal.")
    else:
        s3 = "Language-model arms: awaiting run."
    bii = D.m("connectome", "bii_mae")
    if bii["mean"] is not None:
        bb = D.pair("bii", "shuffled", "bii_mae")
        s4 = (f"BII, under the seed policy with empty registries: the fly's score error {bii['mean']:.4f} and gate agreement {D.m('connectome', 'bii_gate_accuracy')['mean']:.3f} "
              f"on 4,000 synthetic windows" + (f"; shuffle minus fly {bb['mean']:+.4f}{ci(bb)}" if bb else "") + ".")
    else:
        lin = D.m("linear", "bii_mae")
        s4 = ("BII task: the fly's run has not finished." + (f" Linear floor so far: score error {lin['mean']:.3f}, gate agreement "
              f"{D.m('linear', 'bii_gate_accuracy')['mean']:.3f} on 4,000 synthetic windows." if lin["mean"] is not None else ""))
    out = {"wiring_vs_shuffle": s1, "wiring_vs_random_and_matched_network": s2, "model_arms_beside_fly": s3, "bii": s4}
    for k, v in out.items():
        assert len(v) <= PAGE_SENTENCE_MAX, f"page sentence {k} is {len(v)} chars (> {PAGE_SENTENCE_MAX}): {v}"
        assert "—" not in v and "–" not in v, f"dash in page sentence {k}"
    return {"generated": D.doc["generated"], "seeds": D.seeds, "status": D.doc["status"], "max_chars": PAGE_SENTENCE_MAX,
            "source": "results/results.json via scripts/render_results.py", "sentences": out, "chars": {k: len(v) for k, v in out.items()}}


# ------------------------------------------------------------------ figures
def wrap_footer(text: str, width=190) -> str:
    lines = []
    for part in text.split("\n"):
        lines += textwrap.wrap(part.strip(" |"), width) or [""]
    return "\n".join(lines)


def fig_footer(D: Data, task: str) -> str:
    """the shared figure footer (viz/figures.py FOOTER) plus this figure's coverage; the full PROTOCOL 13 footer sits in the caption"""
    n = D.n_seeds("connectome", task)
    n_test = D.doc["footers"][task].split("Coverage: TEST only, ")[1].split(" records")[0]
    teacher = D.doc["footers"][task].split("Teacher: ")[1].split(",")[0]
    return (FIG_FOOTER + f"\nSnapshot 2026-09-20; seeds {n}/{N_SEEDS_PROTOCOL}; TEST split, {int(n_test):,} SYNTHETIC records, zero PHI; teacher {teacher}; "
            f"evaluated {D.doc['generated'][:19]}Z. Full provenance (PROTOCOL 13): Section 4, under Table 8a.")


def save(fig, name):
    OUT_FIG.mkdir(exist_ok=True, parents=True)
    fig.savefig(OUT_FIG / f"{name}.png", dpi=300, metadata={"Software": None})
    fig.savefig(OUT_FIG / f"{name}.svg", metadata={"Date": None})
    plt.close(fig)


def fig3(D: Data, F: dict):
    panels = [("composite_mae_recomputed_from_dims", "Composite MAE, recomputed\n(headline); control minus fly", True),
              ("composite_mae_direct", "Composite MAE, direct head\ncontrol minus fly", True),
              ("dims_mae_mean", "Mean per-dimension MAE\ncontrol minus fly", True),
              ("tier_acc", "Tier agreement (share)\nfly minus control", False)]
    rows = [(aid, SHORT[aid]) for aid, _ in CONTROLS]
    fig, axes = plt.subplots(1, 4, figsize=(7.2, 4.2), sharey=True)
    fig.subplots_adjust(left=0.17, right=0.985, top=0.72, bottom=0.30, wspace=0.14)
    # one scale for the three point-valued panels
    vals = [v for key, _, pts in panels if pts for aid, _ in rows for v in ((D.pair("dti", aid, key) or {}).get("per_seed", {}).values())]
    lo = min(vals + [0.0]) - 0.3; hi = max(vals + [MARGIN_DTI]) + 0.3
    n_any = max((D.pair("dti", aid, HEAD) or {}).get("n", 0) for aid, _ in rows)
    for ax, (key, title, pts) in zip(axes, panels):
        ax.axvline(0, color=C["fly"], lw=0.8, zorder=0)
        if key.startswith("composite"):
            ax.axvline(MARGIN_DTI, color=C["muted"], lw=0.8, ls=(0, (2, 2)), zorder=0)
            ax.text(MARGIN_DTI, len(rows) - 0.45, f"margin {MARGIN_DTI:.1f}", fontsize=6, color=C["muted"], ha="center", va="bottom")
        for i, (aid, lbl) in enumerate(rows):
            y = len(rows) - 1 - i
            r = D.pair("dti", aid, key)
            if not r:
                ax.text(0, y, "awaiting run", fontsize=6.5, color=C["muted"], va="center", ha="left"); continue
            xs = list(r["per_seed"].values()); seeds = list(r["per_seed"].keys())
            if r.get("ci_low") is not None:
                ax.plot([r["ci_low"], r["ci_high"]], [y, y], color=C["ink2"], lw=1.4, solid_capstyle="butt", zorder=2)
                ax.plot(r["mean"], y, marker="|", color=C["ink"], ms=7, mew=1.2, zorder=3)
            for s, x in zip(seeds, xs):
                ax.plot(x, y, "o", ms=4.2, color=C["ctl"], mec=C["surface"], mew=0.6, zorder=4)
                if 2 <= len(xs) <= 5:
                    ax.text(x, y + 0.16, s, fontsize=5.5, color=C["ink2"], ha="center", va="bottom")
            span = (hi - lo) if pts else None
            ax.text(r["mean"] + 0.02 * (span if span else 0.36), y - 0.28, f"{r['mean']:+.2f}" if pts else f"{r['mean']:+.3f}",
                    fontsize=6.3, color=C["ink2"], ha="left", va="center", bbox=dict(facecolor=C["surface"], edgecolor="none", pad=0.3))
        ax.set_title(title, loc="left", fontsize=6.6, color=C["ink"], linespacing=1.25)
        for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
        ax.tick_params(length=2, labelsize=6.5)
        ax.tick_params(axis="y", length=0)
        ax.set_ylim(-0.6, len(rows) - 0.3)
        if pts:
            ax.set_xlim(lo, hi)
        else:
            tv = [v for aid, _ in rows for v in ((D.pair("dti", aid, key) or {}).get("per_seed", {}).values())]
            tspan = max(tv + [0]) - min(tv + [0]) or 0.1
            ax.set_xlim(min(tv + [0]) - 0.1 * tspan, max(tv + [0]) + 0.28 * tspan)
    axes[0].set_yticks(range(len(rows)))
    axes[0].set_yticklabels([lbl for _, lbl in reversed(rows)], fontsize=7)
    axes[0].tick_params(axis="y", length=0)
    n = F["n"]
    # headline computed from what the panels draw: the fly against each control, per metric
    mae_keys = [k for k, _, pts in panels if pts]
    mlp_gaps = [D.pair("dti", "mlp", k)["mean"] for k in mae_keys if D.pair("dti", "mlp", k)]
    PHRASE = {"composite_mae_recomputed_from_dims": "the recomputed composite", "composite_mae_direct": "the direct composite head",
              "dims_mae_mean": "mean per-dimension error"}
    over = [(SHORT[aid], PHRASE[key]) for key, title, pts in panels if pts for aid, _ in CONTROLS[:2]
            if D.pair("dti", aid, key) and D.pair("dti", aid, key)["mean"] >= MARGIN_DTI]
    seeds_txt = "one seed" if n == 1 else f"{n} seeds"
    if F["case"] in ("substrate", "substrate_c_caveat") and mlp_gaps:
        net = f"the fly beats the network with the same parameter count by about {round(min(mlp_gaps)):.0f} points on every error metric" if min(mlp_gaps) >= 1.5 \
            else f"the fly beats the network with the same parameter count by {min(mlp_gaps):.1f} to {max(mlp_gaps):.1f} points"
        if not over:
            null_txt = "the shuffled wiring and the random graph match the fly on every metric drawn"
        else:
            null_txt = ("the shuffled wiring matches the fly; the random graph trails by the pre-registered margin only on "
                        + " and ".join(sorted({t for _, t in over})) if all(a == "Random graph (c)" for a, _ in over)
                        else "a null substrate trails by the pre-registered margin on " + ", ".join(f"{a}: {t}" for a, t in over))
        head = f"On {seeds_txt} {null_txt};\n{net}"
    elif F["case"] == "wiring":
        head = f"On {seeds_txt} the fly's wiring beats both null substrates by the pre-registered margin;\nthe fly beats the matched network by {min(mlp_gaps):.1f} to {max(mlp_gaps):.1f} points"
    else:
        head = f"On {seeds_txt} the controls give mixed answers; see Table 11"
    head = "\n".join(textwrap.fill(part, 118) for part in head.split("\n"))
    n_lines = head.count("\n") + 1
    fig.text(0.02, 0.985, head, fontsize=9.2, weight="semibold", color=C["ink"], va="top", linespacing=1.3)
    sub = ("Each row a control, each point one seed" + (", number = seed" if 2 <= n_any <= 5 else "") + "; "
           + ("single seed: points only, no interval" if n_any < 2 else "bar = 95% t-interval over seeds, tick = mean")
           + ". Blue line: fly = control. Positive = fly did better. Differences in points except tier agreement (share).")
    sub_wrapped = textwrap.wrap(sub, 150); sub_y = 0.985 - 0.058 * n_lines - 0.012
    fig.text(0.02, sub_y, "\n".join(sub_wrapped), fontsize=6.6, color=C["ink2"], va="top", linespacing=1.3)
    fig.subplots_adjust(top=sub_y - 0.042 * len(sub_wrapped) - 0.11)
    fig.text(0.02, 0.19, wrap_footer(fig_footer(D, "dti"), 150), fontsize=6.2, color=C["ink2"], va="top", linespacing=1.35)
    save(fig, "fig3_paired_differences")


def fig4(D: Data):
    fig, axes = plt.subplots(2, 4, figsize=(7.2, 5.0), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.16, right=0.985, top=0.765, bottom=0.25, wspace=0.10, hspace=0.42)
    arms = [(aid, SHORT[aid]) for aid, _ in LOCAL]
    allv = [p["mean"] for aid, _ in arms for p in D.m(aid, "dti_dim_mae")["per_dimension"] if p and p.get("mean") is not None]
    xmax = (int(max(allv + [5.0]) / 2) + 1) * 2 if allv else 12
    fx = D.frontier.get("anthropic")
    for k, (ax, dim) in enumerate(zip(axes.flat, DIMS)):
        ax.axvline(0, color=C["ink2"], lw=1.0, zorder=0)
        ax.axvline(5.0, color=C["muted"], lw=0.8, ls=(0, (2, 2)), zorder=0)
        for i, (aid, lbl) in enumerate(arms):
            y = len(arms) - 1 - i
            pdm = D.m(aid, "dti_dim_mae")["per_dimension"]
            if not pdm or pdm[k].get("mean") is None:
                ax.text(0.3, y, "awaiting run", fontsize=5.8, color=C["muted"], va="center"); continue
            r = pdm[k]
            col = C["fly"] if aid == "connectome" else C["ctl"]
            per_seed = D.local.get(aid, {}).get("dti", {}).get("dims_mae_per_seed", {}).get(dim, [])
            if r.get("ci_low") is not None:
                ax.plot([r["ci_low"], r["ci_high"]], [y, y], color=col, lw=1.2, zorder=2)
            if len(per_seed) >= 2:
                ax.plot(per_seed, [y] * len(per_seed), "o", ms=2.2, color=col, alpha=0.6, mec="none", zorder=2.5)
            if aid == "connectome":
                ax.plot(r["mean"], y, "o", ms=4.6, mfc=C["surface"], mec=C["fly"], mew=1.2, zorder=3)
            else:
                ax.plot(r["mean"], y, "o", ms=4.4, color=col, mec=C["surface"], mew=0.6, zorder=3)
            ax.text(r["mean"], y + 0.18, f"{r['mean']:.1f}", fontsize=5.4, color=C["ink2"], ha="center", va="bottom")
        if fx:
            v = D.R["anthropic"]["dti_dim_mae"]["per_dimension"][k]["mean"]
            ax.text(0.99, -0.55, f"Opus 5: {v:.0f} points, beyond axis", transform=ax.get_yaxis_transform(), fontsize=5.4, color=C["muted"], ha="right", va="center")
        ax.set_title(dim.capitalize(), loc="left", fontsize=8, color=C["ink"])
        for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
        ax.tick_params(length=2, labelsize=6.5)
        ax.tick_params(axis="y", length=0)
        ax.set_xlim(-0.3, xmax); ax.set_ylim(-0.9, len(arms) - 0.4)
        if k == 0:
            ax.text(0.15, len(arms) - 0.45, "teacher = 0", fontsize=5.8, color=C["ink2"], ha="left", va="bottom")
            ax.text(5.25, len(arms) - 0.45, "5.0 bar", fontsize=5.8, color=C["muted"], ha="left", va="bottom")
    for ax in axes[:, 0]:
        ax.set_yticks(range(len(arms))); ax.set_yticklabels([lbl for _, lbl in reversed(arms)], fontsize=6.6); ax.tick_params(axis="y", length=0)
    for ax in axes[0]:
        ax.tick_params(axis="x", length=0)
    for ax in axes[1]:
        ax.set_xlabel("MAE against the teacher, points", fontsize=6.8)
    n = D.n_seeds("connectome", "dti")
    a = D.m("connectome", "dti_dim_mae")["per_dimension"]; b = D.m("shuffled", "dti_dim_mae")["per_dimension"]
    c = D.m("random", "dti_dim_mae")["per_dimension"]; m = D.m("mlp", "dti_dim_mae")["per_dimension"]
    if all(x and x[0].get("mean") is not None for x in (a, b, c, m)):
        wa = max(range(8), key=lambda i: a[i]["mean"]); ba = min(range(8), key=lambda i: a[i]["mean"])
        spread = max(max(a[i]["mean"], b[i]["mean"], c[i]["mean"]) - min(a[i]["mean"], b[i]["mean"], c[i]["mean"]) for i in range(8))
        gaps = [m[i]["mean"] - a[i]["mean"] for i in range(8)]
        assert spread > 0 and all(isinstance(g, float) for g in gaps)
        fixed_txt = (f"the three fixed graphs sit within {spread:.1f} point{'s' if spread >= 1.05 else ''} of one another")
        net_txt = (f"the matched network is {min(gaps):.1f} to {max(gaps):.1f} points worse than the fly" if min(gaps) > 0
                   else f"the matched network is {min(gaps):+.1f} to {max(gaps):+.1f} points against the fly")
        n_over = sum(x["mean"] > 5 for x in a)
        head = (f"Per dimension {fixed_txt}; {net_txt}.\n"
                f"The fly's best dimension is {DIMS[ba]} ({a[ba]['mean']:.1f} points), its worst {DIMS[wa]} ({a[wa]['mean']:.1f}, "
                + (f"the one dimension above the 5.0 bar)" if n_over == 1 else f"one of {n_over} dimensions above the 5.0 bar)" if n_over else "under the 5.0 bar)"))
    else:
        head = "Per-dimension MAE by arm: awaiting runs"
    head = "\n".join(textwrap.fill(part, 118) for part in head.split("\n"))
    n_lines = head.count("\n") + 1
    fig.text(0.02, 0.985, head, fontsize=9.0, weight="semibold", color=C["ink"], va="top", linespacing=1.3)
    sub4 = (f"Eight small multiples at one scale. Hollow blue: fly wiring; grey: controls; the large marker is the mean over {n} seed{'s' if n != 1 else ''}"
            + (" (single seed: no interval, no per-seed points)" if n == 1 else ", small points are seeds, bar = 95% t-interval") + ". Dotted line: pre-registered 5.0-point bar per dimension. "
            "Claude Opus 5's error on its 300 records is printed at the right edge of each panel; it lies beyond the shared axis.")
    sub_y = 0.985 - 0.043 * n_lines - 0.012
    fig.text(0.02, sub_y, "\n".join(textwrap.wrap(sub4, 165)), fontsize=6.4, color=C["ink2"], va="top", linespacing=1.3)
    fig.subplots_adjust(top=sub_y - 0.115)
    fig.text(0.02, 0.135, wrap_footer(fig_footer(D, "dti"), 150), fontsize=6.2, color=C["ink2"], va="top", linespacing=1.35)
    save(fig, "fig4_dimension_mae")


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-refresh", action="store_true", help="skip collect_results (use the results.json on disk)")
    args = ap.parse_args(argv)
    if not args.no_refresh:
        subprocess.run([str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "collect_results.py")], check=True, cwd=ROOT)
    D = Data(json.loads(RESULTS.read_text()))
    F = framing(D)
    OUT_MD.mkdir(parents=True, exist_ok=True)
    (OUT_MD / "section4.md").write_text(section4(D, F))
    (OUT_MD / "abstract_sentences.md").write_text(abstract_sentences(D, F))
    ps = page_sentences(D, F)
    (OUT_MD / "page_sentences.json").write_text(json.dumps(ps, indent=2, ensure_ascii=False) + "\n")
    fig3(D, F); fig4(D)
    DIST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RESULTS, DIST)
    import jsonschema
    jsonschema.validate(json.loads(DIST.read_text()), json.loads((ROOT / "viz" / "results.schema.json").read_text()))
    outputs = [OUT_MD / "section4.md", OUT_MD / "abstract_sentences.md", OUT_MD / "page_sentences.json",
               OUT_FIG / "fig3_paired_differences.png", OUT_FIG / "fig3_paired_differences.svg", OUT_FIG / "fig4_dimension_mae.png", OUT_FIG / "fig4_dimension_mae.svg", DIST]
    manifest = {"generated": D.doc["generated"], "status": D.doc["status"], "seeds": D.seeds, "framing": F,
                "outputs": {str(p.relative_to(ROOT)): sha(p) for p in outputs}}
    (ROOT / "results" / "render_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{D.doc['status']}: seeds {D.seeds}; framing {F['case']} (n={F['n']}, provisional={F['provisional']}); wrote {len(outputs)} files + results/render_manifest.json")
    for k, v in ps["sentences"].items():
        print(f"  [{len(v):3d}] {k}: {v}")


if __name__ == "__main__":
    main()

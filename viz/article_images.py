"""Images for the LinkedIn article and other plain-language surfaces (21 Sep 2026).

1  cover:   the fly's wiring, three views, plain caption, source line; no technical header
2  models:  right trust level out of 100 on the same 300 records; fly as a reference; two rounds per model (dot plot)
3  wiring:  the fly's exact wiring did not matter; error in points, five seeds per arm, mean marked

Every number is read from results/results.json (written by scripts/collect_results.py). Palette from viz/figures.py.
Run: uv run --project ~/Projects/ds-lab python viz/article_images.py [--wording counsel|beat]
  counsel (default): the company-page wording counsel asked for (22 Sep 2026), written to viz/article_company/
  beat: JAS's own first-person wording, written to viz/article/
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "viz"))
from figures import C, load_points, FOOTER  # noqa: E402

_ap = argparse.ArgumentParser(); _ap.add_argument("--wording", choices=("counsel", "beat"), default="counsel"); WORDING = _ap.parse_args().wording
OUT = ROOT / "viz" / ("article" if WORDING == "beat" else "article_company"); OUT.mkdir(exist_ok=True)
R = json.load(open(ROOT / "results" / "results.json"))
RES = R["results"]; FX = R["extra"]["frontier"]
SRC = "Source: SuperTruth, Intelligence Is Structure, Not Scale, v1.2 (results.json, 22 Sep 2026), doi:10.5281/zenodo.22865214. Synthetic records only."
COVER_HEAD = {"beat": "A fruit fly's brain beat\nClaude, GPT-5, Grok and Gemini\nat judging health records.",
              "counsel": "A fruit fly's brain matched\nSuperTruth's health data trust\nscore more often than four\nleading AI models."}[WORDING]
MODELS_TITLE = {"beat": "The fly beat all four models, with or without help",
                "counsel": "Agreement with the DTI score: the fly and the four models, both rounds"}[WORDING]

plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
                     "figure.facecolor": C["surface"], "axes.facecolor": C["surface"], "savefig.facecolor": C["surface"],
                     "text.color": C["ink"], "axes.edgecolor": C["hairline"], "xtick.color": C["ink2"], "ytick.color": C["ink2"]})

def save(fig, name):
    p = OUT / f"{name}.png"; fig.savefig(p, dpi=200); plt.close(fig); print("wrote", p)

def cover():
    xyz, role, meta = load_points(); rc = meta["role_counts"]
    x, y = xyz[:, 0], xyz[:, 1]
    fig = plt.figure(figsize=(19.2, 10.8))
    ax = fig.add_axes([0.50, 0.06, 0.48, 0.90])
    order = [(0, C["other"], 5.0, 0.30), (1, C["sensory"], 5.0, 0.90), (2, C["readout"], 5.0, 0.95), (3, C["readout"], 5.0, 0.95)]
    for r, col, sz, a in order:
        m = role == r; ax.scatter(x[m], -y[m], s=sz, c=col, alpha=a, linewidths=0, rasterized=True)
    ax.set_aspect("equal"); ax.set_axis_off()
    ax.set_xlim(x.min() - 10, x.max() + 10); ax.set_ylim((-y).min() - 10, (-y).max() + 10)
    xr = x.min() + 20; yb = (-y).min() + 10
    ax.plot([xr, xr + 200], [yb, yb], color=C["ink2"], lw=2.0, solid_capstyle="butt")
    ax.text(xr, yb + 10, "0.2 mm", fontsize=14, color=C["ink2"], va="bottom")
    fig.text(0.045, 0.86, COVER_HEAD, fontsize=44 if WORDING == "beat" else 40, weight="bold", va="top", linespacing=1.15)
    fig.text(0.045, 0.52, "Same 300 medical records. The fly's fixed wiring put 84 in 100\nin the same trust level SuperTruth's engine did. The four\nmodels: 20 to 45. Given 100 scored examples to learn from,\nthe best of them reached 76. The fly gave the same answer\nevery time it was asked.",
             fontsize=19, color=C["ink2"], va="top", linespacing=1.4)
    for fy, col, txt in ((0.285, C["sensory"], f"Where a record goes in: {rc['sensory']:,} sensory cells"),
                         (0.245, C["readout"], f"Where the score comes out: {rc['descending'] + rc['motor']:,} descending and motor cells"),
                         (0.205, C["other"], f"The fixed wiring between: {rc['other']:,} cells. Not one connection moved.")):
        fig.patches.append(matplotlib.patches.Circle((0.052, fy), 0.0075, transform=fig.transFigure, color=col, figure=fig))
        fig.text(0.066, fy, txt, color=C["ink2"], fontsize=16, va="center")
    fig.text(0.045, 0.105, f"Seen from the front: {meta['n_neurons'] - meta['n_unpositioned']:,} of {meta['n_neurons']:,} nerve cells at their recorded positions, 6,242,118 connections. Synthetic records only; no real patient's data.\n" + FOOTER +
             "\nThe test measures agreement with SuperTruth's own DTI score and ranks no vendor. SuperTruth, Intelligence Is Structure, Not Scale (2026), doi:10.5281/zenodo.22865214. All five planned runs complete.",
             fontsize=11, color=C["ink2"], va="top", linespacing=1.45)
    save(fig, "cover_fly_wiring")

def models():
    names = [("anthropic", "Claude Opus 5"), ("gemini", "Gemini 3 Flash"), ("xai", "Grok 4"), ("openai", "GPT-5")]
    g = {k: 100 * RES[k]["dti_tier_accuracy"]["mean"] for k, _ in names}
    g2 = {k: 100 * RES[k + "_ex"]["dti_tier_accuracy"]["mean"] for k, _ in names}
    fly = 100 * R["extra"]["local"]["connectome"]["dti"]["subset300"]["tier_acc"]["mean"] if "subset300" in R["extra"]["local"]["connectome"]["dti"] else 84.0
    order = names  # fixed order (alphabetical by vendor); the chart ranks no one
    ci = {k: (100 * RES[k + "_ex"]["dti_tier_accuracy"]["ci_low"], 100 * RES[k + "_ex"]["dti_tier_accuracy"]["ci_high"]) for k, _ in names}
    ci1 = {k: (100 * RES[k]["dti_tier_accuracy"]["ci_low"], 100 * RES[k]["dti_tier_accuracy"]["ci_high"]) for k, _ in names}
    fig, ax = plt.subplots(figsize=(12, 8.0)); fig.subplots_adjust(left=0.20, right=0.90, top=0.77, bottom=0.27)
    ys = np.arange(len(order))[::-1]
    for y, (k, label) in zip(ys, order):
        ax.plot([g[k], g2[k]], [y, y], color=C["hairline"], lw=3, zorder=1)
        ax.plot(ci1[k], [y - 0.16, y - 0.16], color=C["muted"], lw=1.0, zorder=1, alpha=0.8)
        ax.plot(ci[k], [y + 0.16, y + 0.16], color=C["muted"], lw=1.0, zorder=1, alpha=0.8)
        ax.scatter([g[k]], [y], s=140, color=C["surface"], edgecolor=C["readout"], linewidth=2.2, zorder=3)
        ax.scatter([g2[k]], [y], s=140, color=C["readout"], zorder=3)
        ax.text(g[k] - 1.8, y, f"{g[k]:.0f}", ha="right", va="center", fontsize=12, color=C["ink2"])
        ax.text(g2[k] + 1.8, y, f"{g2[k]:.0f}", ha="left", va="center", fontsize=12, color=C["ink"], weight="semibold")
    ax.axvline(fly, color=C["sensory"], lw=2.4, zorder=2)
    ax.text(fly + 1.2, ys[0] + 0.55, f"The fly's wiring: {fly:.0f}", color=C["sensory"], fontsize=13, weight="semibold", va="center", clip_on=False)
    ax.set_ylim(-0.6, len(order) - 0.2)
    ax.set_yticks(ys); ax.set_yticklabels([l for _, l in order], fontsize=13)
    ax.set_xlim(0, 100); ax.set_xticks([0, 25, 50, 75, 100]); ax.tick_params(axis="x", labelsize=11)
    ax.set_xlabel("Records placed in the engine's trust level, out of 100 (same 300 test records)", fontsize=12, color=C["ink2"])
    for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
    ax.grid(axis="x", color=C["hairline"], lw=0.8); ax.set_axisbelow(True)
    fig.text(0.03, 0.965, MODELS_TITLE, fontsize=20, weight="semibold", va="top")
    fig.text(0.03, 0.895, "Hollow dot: the model was given the published DTI paper. Solid dot: the paper plus 100 scored example records\n"
             "(a second round, run after the rules were set). Thin grey bars: 95% intervals over the 300 records; gaps under about\n"
             "6 points are within noise. The blue line is the fly's fixed wiring on the same records.",
             fontsize=12, color=C["ink2"], va="top", linespacing=1.45)
    fig.text(0.03, 0.125, "The engine's trust level means the same level SuperTruth's own DTI engine assigned; the test does not judge who was right about the records and ranks no vendor.\n"
             "Fly: seed 1 on these 300 records; its full-test result is stable across all five seeds (86.6% to 88.0% agreement); bitwise identical on repeat.\n"
             "Models: identical trust level on 67% to 95% of records across three repeats; temperature 0 was requested from every service and accepted by two of the four.\n" + SRC,
             fontsize=9, color=C["ink2"], va="top", linespacing=1.4)
    save(fig, "chart_fly_vs_models")

def wiring():
    arms = [("connectome", "The fly's real wiring"), ("shuffled", "The fly's wiring, scrambled"), ("random", "A random web, same size"),
            ("mlp", "Ordinary trained network, same size"), ("linear", "Straight-line fit (five identical runs)")]
    fig, ax = plt.subplots(figsize=(12, 7.2)); fig.subplots_adjust(left=0.30, right=0.95, top=0.74, bottom=0.17)
    ys = np.arange(len(arms))[::-1]
    for y, (k, label) in zip(ys, arms):
        m = RES[k]["dti_mae"]; seeds = [v for v in m["per_seed"].values()]
        fixed = k in ("connectome", "shuffled", "random")
        col = C["sensory"] if k == "connectome" else (C["ink2"] if fixed else C["muted"])
        ax.scatter(seeds, [y] * len(seeds), s=60, color=col, alpha=0.55, zorder=2)
        ax.scatter([m["mean"]], [y], s=220, marker="|", color=col, linewidths=3, zorder=3)
        ax.text(m["mean"], y + 0.28, f"{m['mean']:.2f}", ha="center", fontsize=12, color=col, weight="semibold" if fixed else "normal")
    ax.set_yticks(ys); ax.set_yticklabels([l for _, l in arms], fontsize=13)
    ax.get_yticklabels()[0].set_fontweight("semibold"); ax.get_yticklabels()[0].set_color(C["sensory"])
    ax.set_xlim(0, 5.5); ax.set_xticks([0, 1, 2, 3, 4, 5]); ax.tick_params(axis="x", labelsize=11)
    ax.set_xlabel("Average error against SuperTruth's score, in points on the 0 to 100 scale (lower is better; 4,001 test records)", fontsize=12, color=C["ink2"])
    for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
    ax.grid(axis="x", color=C["hairline"], lw=0.8); ax.set_axisbelow(True)
    fig.text(0.03, 0.965, "The fly's exact wiring did not matter. The kind of wiring did.", fontsize=20, weight="semibold", va="top")
    fig.text(0.03, 0.895, "Scrambling the fly's wiring gave the same result, and a random web of the same size matched it within a tenth of a point.\n"
             "All three fixed webs came closer to the score than an ordinary trained network with the same number of adjustable parts.\n"
             "Small dots: the five runs. Bar: their average.",
             fontsize=12, color=C["ink2"], va="top", linespacing=1.45)
    fig.text(0.03, 0.05, "All five planned runs complete. " + SRC, fontsize=9.5, color=C["ink2"], va="top")
    save(fig, "chart_wiring_did_not_matter")

if __name__ == "__main__":
    cover(); models(); wiring()

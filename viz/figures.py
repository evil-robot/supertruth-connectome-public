"""Static figures for the PDF, 300 dpi PNG + SVG.

Fig 1  three orthographic projections of the neuron point cloud (dorsal, lateral, front), same role colors as
       connectome.html.  Reads viz/points.bin + viz/points_meta.json (build_points.py).
Fig 2  in-degree and out-degree distributions (log-log, two small multiples) with the quantiles from
       data/malecns/graph_meta.json annotated.  Reads data/malecns/graph.npz.

The project venv has no matplotlib; run in the ds-lab environment:
  uv run --project ~/Projects/ds-lab python viz/figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VIZ = ROOT / "viz"
DATA = ROOT / "data" / "malecns"
OUT = VIZ / "figures"

# palette.md slots, validated 20 Sep 2026 (dataviz validate_palette.js, light surface #fcfcfb, --pairs all)
C = {"sensory": "#2a78d6", "readout": "#eb6834", "other": "#b8b6ae", "ink": "#0b0b0b", "ink2": "#52514e",
     "muted": "#898781", "hairline": "#e1e0d9", "surface": "#fcfcfb"}
FOOTER = ("Source: MaleCNS v1.0 (HHMI Janelia, Cambridge, MRC LMB, Google Research), CC BY 4.0, released 8 Jun 2026; "
          "edges ≥5 synapses; built 20 Sep 2026.")

plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
                     "font.size": 8, "axes.edgecolor": C["hairline"], "axes.labelcolor": C["ink2"], "xtick.color": C["ink2"],
                     "ytick.color": C["ink2"], "text.color": C["ink"], "figure.facecolor": C["surface"], "axes.facecolor": C["surface"],
                     "savefig.facecolor": C["surface"], "svg.fonttype": "none"})


def load_points():
    meta = json.loads((VIZ / "points_meta.json").read_text())
    n = meta["n_neurons"]; o = meta["points_bin"]
    buf = (VIZ / "points.bin").read_bytes()
    xyz = np.frombuffer(buf, dtype=np.float32, count=n * 3).reshape(n, 3)
    role = np.frombuffer(buf, dtype=np.uint8, count=n, offset=o["role_offset"])
    ok = ~np.isnan(xyz).any(axis=1)
    return xyz[ok], role[ok], meta


def save(fig, name):
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=300)
    fig.savefig(OUT / f"{name}.svg")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png", OUT / f"{name}.svg")


def fig1():
    xyz, role, meta = load_points()
    rc = meta["role_counts"]; ps = meta["position_sources"]
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    # Data axes: x lateral (animal's left = +x), y dorsal (low) to ventral (high), z anterior (low) to posterior (high).
    # Each panel: (horizontal, vertical) so that brain is left and dorsal / the animal's right is up.
    panels = [("Dorsal view", "brain left, nerve cord right; the animal's right side up", z, -x),
              ("Lateral view from the animal's left", "brain left, nerve cord right; dorsal up", z, -y),
              ("Front view", "the animal's left on your right; dorsal up", x, -y)]
    fig = plt.figure(figsize=(7.2, 4.9))
    gs = fig.add_gridspec(2, 2, left=0.03, right=0.99, top=0.795, bottom=0.17, hspace=0.30, wspace=0.08,
                          width_ratios=[1, 1], height_ratios=[1, 1])
    axes = [fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]
    order = [(0, C["other"], 1.2, 0.25), (1, C["sensory"], 1.2, 0.85), (2, C["readout"], 1.2, 0.95), (3, C["readout"], 1.2, 0.95)]
    for ax, (title, orient, h, v) in zip(axes, panels):
        for r, col, s, a in order:            # muted first, highlights on top
            m = role == r
            ax.scatter(h[m], v[m], s=s, c=col, alpha=a, linewidths=0, rasterized=True)
        ax.set_aspect("equal"); ax.set_axis_off()
        ax.set_title(title, loc="left", fontsize=8.5, color=C["ink"], pad=3)
        ax.text(0, -0.02, orient, transform=ax.transAxes, fontsize=6.5, color=C["muted"], va="top")
        ax.set_xlim(h.min() - 10, h.max() + 10); ax.set_ylim(v.min() - 10, v.max() + 10)
        # 200 um scale bar in data units at the panel's top right (equal aspect keeps it true)
        xr = ax.get_xlim()[1]; yt = ax.get_ylim()[1]
        ax.plot([xr - 200, xr], [yt, yt], color=C["ink2"], lw=1.2, solid_capstyle="butt", clip_on=False)
        ax.text(xr, yt + 6, "200 \u00b5m", fontsize=7, color=C["ink2"], va="bottom", ha="right", clip_on=False)
    fig.text(0.03, 0.985, f"Where the {rc['sensory']:,} sensory input neurons sit against the {rc['descending'] + rc['motor']:,} "
             "descending and motor readout neurons;\nthe other neurons are the fixed wiring between them",
             fontsize=9.5, color=C["ink"], weight="semibold", va="top", linespacing=1.3)
    # legend: swatch carries the color, text stays in ink
    for fx, col, txt in ((0.03, C["sensory"], f"Sensory input {rc['sensory']:,}"),
                         (0.22, C["readout"], f"Descending {rc['descending']:,} and motor {rc['motor']:,} readout"),
                         (0.56, C["other"], f"All other neurons {rc['other']:,}")):
        fig.patches.append(matplotlib.patches.Circle((fx, 0.878), 0.0045, transform=fig.transFigure, color=col, figure=fig))
        fig.text(fx + 0.012, 0.878, txt, color=C["ink2"], fontsize=8, va="center")
    fig.text(0.03, 0.105, f"Positions: soma location {ps['soma']:,}; tracing-to-soma location {ps['tosoma']:,}; centroid of the neuron's own synapses "
             f"{ps['synapse_centroid']:,} (mostly sensory neurons,\ncell bodies outside the volume); not drawn {meta['n_unpositioned']:,}. "
             "8 nm voxels converted to micrometres. Positions from body-annotations-male-cns-v1.0-minconf-0.5.feather\n(soma) and "
             "syn-points-male-cns-v1.0-minconf-0.5.feather (synapses). Every neuron is drawn at the same marker size.\n" + FOOTER, fontsize=6.3, color=C["ink2"], va="top", linespacing=1.35)
    save(fig, "fig1_projections")


def fig2():
    g = np.load(DATA / "graph.npz", allow_pickle=False)
    meta = json.loads((DATA / "graph_meta.json").read_text())
    indptr = g["indptr"]; indices = g["indices"]
    n = len(indptr) - 1
    out_deg = np.diff(indptr); in_deg = np.bincount(indices, minlength=n)
    n_in_1k, n_out_1k = int((in_deg >= 1000).sum()), int((out_deg >= 1000).sum())
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.3), sharey=True)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.76, bottom=0.27, wspace=0.08)
    for ax, deg, name, qd in ((axes[0], in_deg, "In-degree (presynaptic partners)", meta["in_degree_quantiles"]),
                              (axes[1], out_deg, "Out-degree (postsynaptic partners)", meta["out_degree_quantiles"])):
        d = deg[deg > 0]
        vals, counts = np.unique(d, return_counts=True)
        ax.scatter(vals, counts, s=5, c=C["ink2"], linewidths=0, alpha=0.85, rasterized=True)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(name, loc="left", fontsize=8.5, color=C["ink"])
        ax.set_xlabel("Connections per neuron (edges ≥5 synapses)")
        for sp in ("top", "right"): ax.spines[sp].set_visible(False)
        ax.tick_params(length=2)
        ax.grid(False)
        # quantiles from graph_meta.json, annotated on the axis
        top = counts.max()
        for qk, label, lift in (("0.5", "median", 1.9), ("0.95", "95th", 1.9), ("0.99", "99th", 5.5), ("1.0", "max", 1.9)):
            qv = qd[qk]
            if qv <= 0: continue
            ax.axvline(qv, color=C["hairline"], lw=0.8, zorder=0)
            ax.text(qv, top * lift, f"{label}\n{qv:,}", fontsize=6.5, color=C["ink2"], ha="center", va="bottom")
        ax.text(0.98, 0.42, f"{int((deg == 0).sum()):,} neurons with none\n(not plotted)", transform=ax.transAxes,
                fontsize=6.5, color=C["muted"], ha="right", va="top", linespacing=1.3)
        ax.minorticks_off()
        ax.set_ylim(0.7, top * 20)
    axes[0].set_ylabel("Neurons with that many")
    fig.text(0.09, 0.975, f"Most neurons have a few dozen partners; about a hundred have a thousand or more\n(median in-degree "
             f"{meta['in_degree_quantiles']['0.5']}, out-degree {meta['out_degree_quantiles']['0.5']}; at least 1,000: {n_in_1k} in, {n_out_1k} out; "
             f"maximum in {meta['in_degree_quantiles']['1.0']:,}, out {meta['out_degree_quantiles']['1.0']:,})",
             fontsize=9.5, weight="semibold", color=C["ink"], va="top", linespacing=1.3)
    fig.text(0.09, 0.085, FOOTER + f"\n{n:,} neurons, {meta['n_edges_at_threshold']:,} edges; quantiles from graph_meta.json.",
             fontsize=6.5, color=C["ink2"], va="top", linespacing=1.3)
    save(fig, "fig2_degree")


if __name__ == "__main__":
    fig1(); fig2()
    sys.exit(0)

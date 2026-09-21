"""LinkedIn video: the fly's wiring rotating, 1920x1080, 30 fps, ~25 s. Frames from matplotlib, encoded with ffmpeg (H.264).
Run: uv run --project ~/Projects/ds-lab python viz/article_video.py
"""
from __future__ import annotations
import subprocess, sys, tempfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "viz"))
from figures import C, load_points, FOOTER  # noqa: E402

FPS, ROT_S, HOLD_S = 30, 20, 5
OUT = ROOT / "viz" / "article" / "fly_wiring_rotation_1080p.mp4"

xyz, role, meta = load_points(); rc = meta["role_counts"]
xyz = xyz - xyz.mean(axis=0)
# data axes: x lateral, y dorsal(low)->ventral(high), z anterior->posterior. Screen: up = -y. Rotate about the vertical (y) axis.
order = [(0, C["other"], 3.0, 0.28), (1, C["sensory"], 3.0, 0.9), (2, C["readout"], 3.0, 0.95), (3, C["readout"], 3.0, 0.95)]
Rv = np.sqrt((xyz[:, 0] ** 2 + xyz[:, 1] ** 2).max()) + 20   # radius about the long (z) axis
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
                     "figure.facecolor": C["surface"], "axes.facecolor": C["surface"], "savefig.facecolor": C["surface"], "text.color": C["ink"]})

def frame(theta, path, hold_alpha=0.0):
    c, s = np.cos(theta), np.sin(theta)
    # rotisserie: long axis (z) stays horizontal, brain left; the cross-section (x, y) turns. theta=0 is the view from above.
    h = xyz[:, 2]
    v = xyz[:, 0] * c - xyz[:, 1] * s          # screen vertical
    depth = xyz[:, 0] * s + xyz[:, 1] * c      # toward viewer (draw order)
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    ax = fig.add_axes([0.53, 0.12, 0.46, 0.76]); ax.set_axis_off(); ax.set_aspect("equal")
    ax.set_xlim(h.min() - 20, h.max() + 20); ax.set_ylim(-Rv, Rv)
    idx = np.argsort(depth)                      # back to front
    for r, col, sz, a in order:
        m = role[idx] == r
        ax.scatter(h[idx][m], v[idx][m], s=sz, c=col, alpha=a, linewidths=0, rasterized=True)
    fig.text(0.04, 0.86, "A fruit fly's brain beat\nClaude, GPT-5, Grok and Gemini\nat judging health records.", fontsize=36, weight="bold", va="top", linespacing=1.15)
    for fy, col, txt in ((0.50, C["sensory"], f"Where a record goes in: {rc['sensory']:,} sensory cells"),
                         (0.455, C["readout"], f"Where the score comes out: {rc['descending'] + rc['motor']:,} descending and motor cells"),
                         (0.41, C["other"], f"The fixed wiring between: {rc['other']:,} cells. Not one connection moved.")):
        fig.patches.append(matplotlib.patches.Circle((0.047, fy), 0.0075, transform=fig.transFigure, color=col, figure=fig))
        fig.text(0.061, fy, txt, color=C["ink2"], fontsize=16, va="center")
    if hold_alpha > 0:
        fig.text(0.04, 0.34, "Same 300 medical records. The fly's fixed wiring matched\nSuperTruth's trust level on 84 in 100. The four models: 20 to 45.\nGiven 100 scored examples, the best reached 76. The fly gave\nthe same answer every time it was asked.",
                 fontsize=17, color=C["ink2"], va="top", linespacing=1.45, alpha=hold_alpha)
    fig.text(0.04, 0.085, f"{meta['n_neurons'] - meta['n_unpositioned']:,} of {meta['n_neurons']:,} nerve cells at their recorded positions; 6,242,118 connections. Synthetic records only.\n"
             + FOOTER + "\nAgreement with SuperTruth's own DTI score; ranks no vendor. doi:10.5281/zenodo.22865215. Two of five planned runs; provisional.",
             fontsize=10.5, color=C["ink2"], va="top", linespacing=1.45)
    fig.savefig(path, dpi=100); plt.close(fig)

with tempfile.TemporaryDirectory() as td:
    n_rot = FPS * ROT_S; n_hold = FPS * HOLD_S
    for i in range(n_rot):
        frame(2 * np.pi * i / n_rot, f"{td}/f{i:05d}.png")
        if i % 60 == 0: print("frame", i, flush=True)
    for j in range(n_hold):
        frame(0.0, f"{td}/f{n_rot + j:05d}.png", hold_alpha=min(1.0, j / (FPS * 0.8)))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{td}/f%05d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-b:v", "8M", "-maxrate", "10M", "-bufsize", "16M", "-movflags", "+faststart", str(OUT)], check=True)
print("wrote", OUT)

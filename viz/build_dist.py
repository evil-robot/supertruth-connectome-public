"""Assemble the drop-in folders for supertruth.ai.

dist/viewer/   -> public/research/connectome/viewer/   (connectome.html at the root, data and vendor beside it, relative paths only)
dist/results/  -> the arms-comparison page and its schema (drop wherever the results page lives)

Each folder gets a README.md with every file's bytes and sha256, the vendored library versions, and the size ceilings
(HTML < 2 MB, folder < 25 MB) checked here. Run: .venv/bin/python viz/build_dist.py
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

VIZ = Path(__file__).resolve().parent
DIST = VIZ / "dist"
VIEWER = {"connectome.html": "connectome.html", "points.bin": "points.bin", "activity_frames.bin": "activity_frames.bin",
          "sample40k.bin": "sample40k.bin", "points_meta.json": "points_meta.json",
          "vendor/three.module.min.js": "vendor/three.module.min.js", "vendor/OrbitControls.js": "vendor/OrbitControls.js"}
RESULTS = {"results_charts.html": "results_charts.html", "results.schema.json": "results.schema.json",
           "results.sample.json": "results.sample.json", "vendor/plotly-basic.min.js": "vendor/plotly-basic.min.js"}
VENDORED = {"vendor/three.module.min.js": "three.js 0.169.0, build/three.module.min.js from https://cdn.jsdelivr.net/npm/three@0.169.0/ (MIT)",
            "vendor/OrbitControls.js": "three.js 0.169.0, examples/jsm/controls/OrbitControls.js (MIT); one edit: the import specifier "
                                       "'three' rewritten to './three.module.min.js' so no import map is needed",
            "vendor/plotly-basic.min.js": "plotly.js-basic-dist-min 2.35.2 from https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@2.35.2/ (MIT)"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(name: str, files: dict, note: str) -> int:
    out = DIST / name
    if out.exists():
        shutil.rmtree(out)
    rows, total = [], 0
    for src, dst in files.items():
        s, d = VIZ / src, out / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        n = d.stat().st_size; total += n
        rows.append((dst, n, sha256(d)))
        if dst.endswith(".html") and n >= 2_000_000:
            sys.exit(f"{dst} is {n:,} bytes, over the 2 MB HTML ceiling")
    if total >= 25_000_000:
        sys.exit(f"{name} is {total:,} bytes, over the 25 MB folder ceiling")
    lines = [f"# {name}", "", note, "",
             "Serving notes: static files, relative paths only, no CDN, no external requests. The viewer runs inside a same-origin iframe with "
             "sandbox=\"allow-scripts\" (opaque origin), so its relative fetches are CORS requests without credentials; the folder must send "
             "Access-Control-Allow-Origin: *. Cache-Control public, max-age 86400 is fine: rebuilding replaces files in place.", "",
             "| file | bytes | sha256 |", "|---|---:|---|"]
    lines += [f"| {f} | {n:,} | {h} |" for f, n, h in rows]
    lines += ["", f"Total: {total:,} bytes ({total / 1e6:.2f} MB). Ceilings: HTML under 2 MB, folder under 25 MB.", "", "## Vendored libraries", ""]
    lines += [f"- `{k}`: {v}" for k, v in VENDORED.items() if k in files]
    lines += ["", "Built by viz/build_dist.py on 20 Sep 2026 from the files in viz/."]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print(f"{name}: {total:,} bytes in {len(rows)} files -> {out}")
    for f, n, _ in rows:
        print(f"  {n:>10,}  {f}")
    return total


if __name__ == "__main__":
    build("viewer", VIEWER, "Drop this folder at public/research/connectome/viewer/. Entry point: connectome.html. Data: points.bin "
          "(Float32 xyz in micrometres + Uint8 role, neurotransmitter class, position source), activity_frames.bin (8 Uint8 frames; the "
          "trained run replaces this file, same layout, or point data-frames on <main> at a new path), sample40k.bin (stratified 40,000 "
          "fallback), points_meta.json (counts, offsets, provenance). Address parameters for deep links and QA: ?view=roles|activity|nt, "
          "?cam=dorsal|lateral|front|reset, ?step=1..8, ?sample=1 (force the 40,000 sample), ?full=1 (force the full set). Under 560 px "
          "of stage width the header compacts and the excitatory/inhibitory halves stack top and bottom; under 480 px the scale bar and "
          "orientation caption move under the canvas. The page posts its content height to the parent frame (connectome-viewer-height).")
    build("results", RESULTS, "The arms-comparison page. results_charts.html reads results.sample.json (all null: 'awaiting run') until "
          "results.json from the run is dropped beside it and data-results on <main> (or ?results=) points to it. Schema: results.schema.json.")

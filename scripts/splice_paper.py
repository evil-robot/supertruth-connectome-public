"""Assemble the whitepaper and the site page from the results pipeline.

  uv run --project ~/Projects/ds-lab python scripts/splice_paper.py [--site /path/to/st-connectome]

Idempotent: every substitution is bounded by a marker, so a rerun after more seeds land replaces last night's text
with tonight's and changes nothing else.

  (a) paper/paper.md "## 4. Results" body (heading to the next "---") <- paper/results/section4.md, its own "## 4. Results"
      line dropped, any "## " heading demoted to "### ", Figures 3 and 4 embedded as ![](figures/...) above their captions,
      table and figure numbers checked against the paper (Tables 1-7 and Figures 1-2 belong to Sections 2-3).
  (b) the abstract's [RESULTS SENTENCES.] placeholder, or the block between <!-- RESULTS-ABSTRACT-START/END -->,
      <- paper/results/abstract_sentences.md.
  (c) the site page's five <ResultPlaceholder> texts <- paper/results/page_sentences.json, each preceded by {/* RESULT-n */};
      CONNECTOME_UPDATED_DATE <- today.
  (d) every [RUN: ...] placeholder the pipeline can answer <- runs/, results/results.json, llm_arm/llm_runs/; the filled value is
      wrapped as <!-- RUN: key -->value<!-- /RUN --> so it is recomputed on every run; a key with no evidence stays [RUN: key].
  (e) a report of every substitution, the literal numbers in Section 3 checked against their files, and the [RUN: ...]
      placeholders that remain.
  (f) --dataset-doi <doi>: the [DATASET DOI] placeholder <- the Zenodo dataset DOI, in paper/paper.md, README.md, dataset/README.md,
      dataset/zenodo-dataset.json (metadata.doi) and paper/zenodo.json (related_identifiers, isSupplementedBy) in one go; without
      the flag the placeholder stays.

Version mode: when results/render_manifest.json carries a "version" (render_results.py --version), every fill that would say
"awaiting run" says "not in this version" instead, so the paper and Section 4 use one phrase.

Nothing here is estimated: a value with no file behind it is not written.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "paper.md"
SEC4 = ROOT / "paper" / "results" / "section4.md"
ABSTRACT = ROOT / "paper" / "results" / "abstract_sentences.md"
PAGE_SENTENCES = ROOT / "paper" / "results" / "page_sentences.json"
RESULTS = ROOT / "results" / "results.json"
REACH = ROOT / "results" / "reachability.json"
MANIFEST = ROOT / "results" / "render_manifest.json"
LLM_RUNS = ROOT / "llm_arm" / "llm_runs"
DOI_FILES = [ROOT / "README.md", ROOT / "dataset" / "README.md"]          # prose files with the [DATASET DOI] placeholder besides paper.md
DOI_JSON_DATASET = ROOT / "dataset" / "zenodo-dataset.json"
DOI_JSON_PAPER = ROOT / "paper" / "zenodo.json"
DOI_PLACEHOLDER = "[DATASET DOI]"
SITE_DEFAULT = Path("/Users/jas/Projects/st-connectome")
PAGE_TSX = Path("src/app/research/connectome/page.tsx")
PAGE_DATA = Path("src/data/connectome-paper.ts")

FIRST_RESULTS_TABLE = 8     # Tables 1-7 are Sections 2-3 (Table 5-7 are named by the Methods' provenance footers)
FIRST_RESULTS_FIGURE = 3    # Figures 1-2 are Sections 2-3
SECTION4_MARK = "<!-- RESULTS-SECTION4: spliced by scripts/splice_paper.py from paper/results/section4.md; edit scripts/render_results.py, not this block -->"
ABS_START, ABS_END = "<!-- RESULTS-ABSTRACT-START -->", "<!-- RESULTS-ABSTRACT-END -->"
PAGE_KEYS = ["wiring_vs_shuffle", "wiring_vs_random_and_matched_network", "model_arms_beside_fly", "bii", "model_arms_with_examples"]
DASH = re.compile("[–—]")
ARM_LABEL = {"connectome": "fly wiring (a)", "shuffle": "shuffle (b)", "er": "random graph (c)", "mlp": "matched network (d)"}
VENDOR_NAME = {"anthropic": "Anthropic", "openai": "OpenAI", "xai": "xAI", "gemini": "Google"}

report: list[str] = []


def say(line: str) -> None:
    report.append(line)
    print(line)


def no_dashes(text: str, where: str) -> None:
    if DASH.search(text):
        sys.exit(f"em or en dash in {where}; the house voice has none. Fix the source, not the paper.")


# ------------------------------------------------------------------ (a) Section 4
def splice_section4(paper: str, sec4: str) -> str:
    lines = sec4.strip("\n").split("\n")
    if lines and re.match(r"^## 4\. Results\s*$", lines[0]):
        lines = lines[1:]
    demoted = 0
    out = []
    for ln in lines:
        if ln.startswith("## "):
            ln = "#" + ln
            demoted += 1
        out.append(ln)
    body = "\n".join(out).strip("\n")

    # figure and table numbering against the rest of the paper
    m_head = re.search(r"^## 4\. Results\s*$", paper, re.M)
    if not m_head:
        sys.exit("paper.md has no '## 4. Results' heading")
    m_end = re.compile(r"^---\s*$", re.M).search(paper, m_head.end())
    if not m_end:
        sys.exit("no '---' after '## 4. Results'")
    outside = paper[:m_head.start()] + paper[m_end.start():]
    out_tables = [int(n) for n in re.findall(r"\*\*Table (\d+):", outside)]
    out_figs = [int(n) for n in re.findall(r"\*\*Figure (\d+):", outside)]
    if out_tables and max(out_tables) >= FIRST_RESULTS_TABLE:
        sys.exit(f"a table outside Section 4 is numbered {max(out_tables)}; results tables start at {FIRST_RESULTS_TABLE}")
    if out_figs and max(out_figs) >= FIRST_RESULTS_FIGURE:
        sys.exit(f"a figure outside Section 4 is numbered {max(out_figs)}; results figures start at {FIRST_RESULTS_FIGURE}")
    body, t_shift = renumber(body, "Table", FIRST_RESULTS_TABLE)
    body, f_shift = renumber(body, "Figure", FIRST_RESULTS_FIGURE)
    in_tables = sorted({int(n) for n in re.findall(r"\*\*Table (\d+)", body)})
    in_figs = sorted({int(n) for n in re.findall(r"\*\*Figure (\d+)", body)})
    for ref in sorted({int(n) for n in re.findall(r"Table (\d+)", outside) if int(n) >= FIRST_RESULTS_TABLE}):
        if ref not in in_tables:
            say(f"  WARNING: Section 3 refers to Table {ref}, which Section 4 does not define")
    for ref in sorted({int(n) for n in re.findall(r"Figure (\d+)", outside) if int(n) >= FIRST_RESULTS_FIGURE}):
        if ref not in in_figs:
            say(f"  WARNING: Section 3 refers to Figure {ref}, which Section 4 does not define")

    # embed the figure files above their captions
    embeds = 0
    def embed(m: re.Match) -> str:
        nonlocal embeds
        embeds += 1
        return f"![](figures/{m.group(2)})\n\n{m.group(0)}"
    body = re.sub(r"^\*\*Figure (\d+): [^\n]*?\(paper/figures/([^)]+\.png)\)\.\*\*", embed, body, flags=re.M)
    for fig in re.findall(r"!\[\]\(figures/([^)]+)\)", body):
        if not (ROOT / "paper" / "figures" / fig).exists():
            sys.exit(f"Section 4 embeds figures/{fig}, which is not on disk")

    new = paper[:m_head.end()] + "\n" + SECTION4_MARK + "\n\n" + body + "\n\n" + paper[m_end.start():]
    say(f"(a) Section 4: {len(body.splitlines())} lines from {SEC4.relative_to(ROOT)}; {demoted} '##' headings demoted; "
        f"tables {in_tables} (shift {t_shift}); figures {in_figs} (shift {f_shift}); {embeds} figures embedded")
    return new


def renumber(body: str, word: str, first: int) -> tuple[str, int]:
    nums = sorted({int(n) for n in re.findall(rf"\*\*{word} (\d+)", body)})
    if not nums or nums[0] == first:
        return body, 0
    shift = first - nums[0]
    return re.sub(rf"\b{word} (\d+)", lambda m: f"{word} {int(m.group(1)) + shift}", body), shift


# ------------------------------------------------------------------ (b) abstract
def splice_abstract(paper: str, sentences: str) -> str:
    sentences = sentences.strip()
    no_dashes(sentences, str(ABSTRACT))
    block = f"{ABS_START}{sentences}{ABS_END}"
    marked = re.compile(re.escape(ABS_START) + r".*?" + re.escape(ABS_END), re.S)
    if marked.search(paper):
        n = len(marked.findall(paper))
        if n != 1:
            sys.exit(f"{n} RESULTS-ABSTRACT blocks in paper.md; expected 1")
        paper = marked.sub(lambda _: block, paper)
        how = "replaced the marked block"
    elif paper.count("[RESULTS SENTENCES.]") == 1:
        paper = paper.replace("[RESULTS SENTENCES.]", block)
        how = "replaced [RESULTS SENTENCES.]"
    else:
        sys.exit("abstract has neither [RESULTS SENTENCES.] nor a RESULTS-ABSTRACT block")
    words = len(re.sub(r"<!--.*?-->", "", paper.split("## Abstract")[1].split("**Keywords")[0]).split())
    say(f"(b) Abstract: {how} with {len(sentences)} chars from {ABSTRACT.relative_to(ROOT)}; abstract now {words} words")
    return paper


# ------------------------------------------------------------------ (c) site page
def jsx_text(s: str) -> str:
    return (s.replace("&", "&amp;").replace("'", "&apos;").replace('"', "&quot;")
             .replace("<", "&lt;").replace(">", "&gt;").replace("{", "&#123;").replace("}", "&#125;"))


def splice_page(site: Path) -> None:
    doc = json.loads(PAGE_SENTENCES.read_text())
    sents = doc["sentences"]
    missing = [k for k in PAGE_KEYS if k not in sents]
    if missing:
        sys.exit(f"page_sentences.json lacks {missing}")
    tsx_path = site / PAGE_TSX
    tsx = tsx_path.read_text()
    pat = re.compile(r"^([ \t]*)(?:\{/\* RESULT-\d \*/\}\n[ \t]*)?<ResultPlaceholder>[\s\S]*?</ResultPlaceholder>", re.M)
    blocks = list(pat.finditer(tsx))
    if len(blocks) != len(PAGE_KEYS):
        sys.exit(f"{tsx_path}: found {len(blocks)} <ResultPlaceholder> blocks, expected {len(PAGE_KEYS)}")
    pieces, last = [], 0
    for i, (m, key) in enumerate(zip(blocks, PAGE_KEYS), start=1):
        text = sents[key].strip()
        no_dashes(text, f"page sentence {key}")
        indent = m.group(1)
        pieces.append(tsx[last:m.start()])
        pieces.append(f"{indent}{{/* RESULT-{i} */}}\n{indent}<ResultPlaceholder>{jsx_text(text)}</ResultPlaceholder>")
        last = m.end()
        say(f"(c) page RESULT-{i} <- {key} ({len(text)} chars): {text}")
    pieces.append(tsx[last:])
    new_tsx = "".join(pieces)
    if new_tsx != tsx:
        tsx_path.write_text(new_tsx)
    data_path = site / PAGE_DATA
    data = data_path.read_text()
    today = dt.date.today().isoformat()
    pat_date = re.compile(r'(export const CONNECTOME_UPDATED_DATE = ")(\d{4}-\d{2}-\d{2})(";)')
    if not pat_date.search(data):
        sys.exit(f"{data_path}: CONNECTOME_UPDATED_DATE not found")
    new_data = pat_date.sub(lambda m: f"{m.group(1)}{today}{m.group(3)}", data)
    if new_data != data:
        data_path.write_text(new_data)
    say(f"(c) {PAGE_DATA}: CONNECTOME_UPDATED_DATE = {today}")
    left = [ln.strip() for ln in new_tsx.splitlines() if "[RESULT" in ln]
    say(f"(c) [RESULT placeholders left in page.tsx: {len(left)}")


# ------------------------------------------------------------------ (d) [RUN: ...] fills
def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def run_jsons() -> list[dict]:
    out = []
    for p in sorted(ROOT.glob("runs/*/*/seed*/run.json")):
        r = load(p)
        if r:
            r["_path"] = p.relative_to(ROOT).as_posix()
            out.append(r)
    return out


def fill_count_params(runs: list[dict]) -> tuple[str | None, str | None]:
    """returns (long form for Section 3.2, short form for Table 2)"""
    per = {}
    for r in runs:
        task = r["run_meta"]["task"]
        arm = r["arm"]
        if arm not in ("connectome", "mlp") or (arm, task) in per:
            continue
        d_in = len(r["run_meta"]["standardization"]["mean"])
        d_out = r["param_breakdown"].get("readout.bias") if arm == "connectome" else None
        per[(arm, task)] = (r["trainable_params"], d_in, d_out, r["_path"])
    if ("connectome", "dti") not in per:
        return None, None
    parts, short = [], []
    fixed = [(t, per[("connectome", t)]) for t in ("dti", "bii") if ("connectome", t) in per]
    for i, (t, (n, d_in, d_out, _)) in enumerate(fixed):
        head = "for arms a to c on " if i == 0 else "on "
        parts.append(f"{n:,} {head}{t.upper()} (d_in = {d_in}, d_out = {d_out})")
        short.append(f"{n:,} ({t.upper()}, d_in = {d_in})")
    for t in ("dti", "bii"):
        if ("mlp", t) in per:
            n, d_in, _, _ = per[("mlp", t)]
            parts.append(f"{n:,} for the matched network on {t.upper()}")
    long = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]
    return long + " (runs/{task}/{arm}/seed1/run.json)", "; ".join(short)


def fill_batch() -> str | None:
    b = load(ROOT / "runs" / "batch_choice.json")
    if not b:
        return None
    r64, r128 = b["measured"]["64"]["records_per_sec"], b["measured"]["128"]["records_per_sec"]
    why = ("128 was at least 5% faster per record and fit under the memory cap" if b["choice"] == 128 else
           f"128 was not at least 5% faster per record ({r128:.1f} against {r64:.1f} records per second), so 64 is kept")
    return f"B = {b['choice']}, measured {b['measured_at_utc']} at d_in = {b['in_dim']}: {why}"


def fill_epochs(runs: list[dict]) -> str | None:
    by_task: dict[str, list[str]] = {}
    for r in runs:
        if not r.get("finished") or r["arm"] not in ARM_LABEL:
            continue
        n_ep, best, cfg = len(r["history"]), r["best_epoch"], r["config"]
        if n_ep == cfg["epochs"]:
            stop = "ran the full budget"
        elif n_ep == best + 1 + cfg["patience"]:
            stop = f"stopped after {n_ep} epochs, checkpoint from epoch {best}"
        else:
            stop = f"{n_ep} epochs, checkpoint from epoch {best}"
        by_task.setdefault(f"{r['run_meta']['task'].upper()} seed {r['run_meta']['seed']}", []).append(f"{ARM_LABEL[r['arm']]} {stop}")
    if not by_task:
        return None
    body = "; ".join(f"{k}: " + ", ".join(v) for k, v in by_task.items())
    return (f"{body} (run.json counts epochs from 0; \"stopped\" means validation loss had not improved for "
            f"{runs[0]['config']['patience']} epochs, the pre-registered patience)")


def fill_degenerate(results: dict | None) -> str | None:
    if not results:
        return None
    found = []
    for task in ("dti", "bii"):
        m = re.search(r"excluded as degenerate: (.*?) \(", results["footers"].get(task, ""))
        if m:
            found.append(f"{m.group(1)} for {task.upper()}")
    return (" and ".join(found) + " (results/results.json dataset health lines; splits/qa_report.json)") if found else None


def fill_reachability() -> str | None:
    """rule 13: readout neurons reachable from the sensory set within T hops (results/reachability.json, scripts/reachability.py)"""
    r = load(REACH)
    if not r:
        return None
    ro, al, T = r["readout"], r["all_neurons"], r["T"]
    k = ro["count_within_hops"][str(T)]
    unreach_ro = ro["count_at_hop"]["unreachable"]
    by_hop = ", ".join(f"{c:,} at {h}" for h, c in ro["count_at_hop"].items() if h != "unreachable" and c > 0)
    med = ro["median_hops_reachable"]
    return (f"{ro['share_within_T']:.4f}: {k:,} of the {ro['n']:,} descending and motor neurons lie within {T} directed hops of a sensory neuron, "
            f"and the other {unreach_ro} have no path from the sensory set at any length; {al['count_within_hops'][str(T)]:,} of all {al['n']:,} neurons "
            f"({al['share_within_T']:.4f}) are within {T} hops and {al['count_at_hop']['unreachable']} are unreachable. The median shortest path from the sensory set to a "
            f"readout neuron is {med:.0f} hop{'' if med == 1 else 's'} and the longest {ro['max_hops_reachable']} (readout neurons by hop count: {by_hop}). "
            f"The synchronous update delivers input to a neuron d hops away at step d + 1, so the readout after T = {T} steps carries input from every neuron "
            f"within {T - 1} hops, the same {ro['share_within_T_minus_1']:.4f} (scripts/reachability.py, results/reachability.json)")


def fill_pilot(results: dict | None) -> str | None:
    if not results:
        return None
    pr = results.get("pilot_rule") or {}
    seeds = pr.get("seeds_with_both_a_and_b") or []
    if pr.get("s_seed_points") is None:
        return (f"s_seed awaiting run (fly and shuffle both finished on DTI seeds {{{', '.join(map(str, seeds))}}}; two are needed); "
                f"the seed count stays at five until it is measured")
    s = pr["s_seed_points"]
    return f"s_seed = {s:.3f} points over DTI seeds {{{', '.join(map(str, seeds))}}}; verdict {pr.get('verdict')}"


def model_runs(results: dict | None) -> dict[str, dict]:
    """per provider: the protocol run (N >= 300, complete) if one exists, else the latest run that parsed at least one call"""
    if not results:
        return {}
    provider_of = {a["model"]: a["provider"] for a in results["arms"] if a.get("provider")}
    chosen: dict[str, dict] = {}
    for d in sorted(LLM_RUNS.iterdir()) if LLM_RUNS.exists() else []:
        s, how, prices = load(d / "summary.json"), d / "HOW_WE_RAN_THIS.md", load(d / "prices.json")
        if not s or not how.exists() or s["counts"]["calls_parsed_ok"] == 0:
            continue
        if s.get("arm", "g") != "g":
            continue   # the Section 3.8 table is arm g; the post-hoc g2-examples runs are reported in Section 4 (amendment 1, row 17)
        prov = provider_of.get(s["model_requested"])
        if not prov:
            continue
        n, k = s["input"]["n_records"], s["input"]["k"]
        complete = s["input"]["n_requested"] >= 300 and s["counts"]["calls_total"] == n * k   # every call made; parse failures are printed in the cell
        cur = chosen.get(prov)
        if cur is None or complete or not cur["complete"]:
            chosen[prov] = {"run": d.name, "summary": s, "how": how.read_text(), "prices": prices, "complete": complete, "n": n, "k": k}
    return chosen


def parse_how(h: str) -> dict:
    out = {}
    m = re.search(r"Response `model` field\(s\): (\{.*?\})", h)
    served = "/".join(json.loads(m.group(1)).keys()) if m else None
    m2 = re.search(r"served today as `([^`]+)`", h)
    out["served"] = m2.group(1) if m2 else served
    m = re.search(r"Settings: ([^;]+);\s*([^;]+);", h)
    reasoning = m.group(1).strip() if m else None
    if m and m.group(2).strip().startswith("effort"):
        reasoning += ", " + m.group(2).strip()
    out["reasoning"] = reasoning
    m = re.search(r"temperature ([\d.]+) requested, accepted by the API: (True|False)", h)
    out["temperature"] = (f"{m.group(1)} / {'accepted' if m.group(2) == 'True' else 'not accepted, the API rejects it for this model'}" if m
                          else "not settable under adaptive thinking (not sent)" if "thinking adaptive" in h else None)
    m = re.search(r"structured output via ([^;(\n]+)", h)
    out["structured"] = m.group(1).strip().strip("`") if m else None
    m = re.search(r"System prompt sha256: `([0-9a-f]{64})`", h)
    out["prompt_sha"] = m.group(1) if m else None
    return out


def fill_how_table(results: dict | None) -> str | None:
    chosen = model_runs(results)
    if not chosen:
        return None
    provider_model = {a["provider"]: a["model"] for a in results["arms"] if a.get("provider")}
    rows = ["| Vendor, id requested | Served as (API `model`) | Run (UTC) | Reasoning | Temperature 0 requested / accepted | Structured output | N × k (calls, errors) | Prices (source, retrieved) |",
            "|---|---|---|---|---|---|---|---|"]
    shas = {}
    for prov in ("anthropic", "openai", "xai", "gemini"):
        model = provider_model.get(prov, "?")
        c = chosen.get(prov)
        if not c:
            rows.append(f"| {VENDOR_NAME.get(prov, prov)}, `{model}` | awaiting run | | | | | awaiting run (protocol N = 300, k = 3) | |")
            continue
        p = parse_how(c["how"])
        rid = c["run"]
        when = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]} {rid[9:11]}:{rid[11:13]}"
        cnt = c["summary"]["counts"]
        if c["complete"]:
            pf = cnt.get("parse_failures", 0)
            nk = f"{c['n']} × {c['k']} ({cnt['calls_total']} calls, {cnt['errors']} errors" + (f", {pf} parse failure{'s' if pf != 1 else ''}" if pf else "") + ")"
        else:
            nk = f"awaiting run (protocol N = 300, k = 3); probe of {c['n']} × {c['k']} on this date recorded the served model"
        pr = c["prices"] or {}
        price = f"{pr.get('retrieved_from', 'see prices.json')}; retrieved {pr.get('retrieved_on', '?')}"
        shas[prov] = p["prompt_sha"]
        cells = [f"{VENDOR_NAME.get(prov, prov)}, `{model}`", f"`{p['served']}`" if p["served"] else "see HOW_WE_RAN_THIS.md", when,
                 p["reasoning"] or "see HOW_WE_RAN_THIS.md", p["temperature"] or "see HOW_WE_RAN_THIS.md",
                 p["structured"] or "see HOW_WE_RAN_THIS.md", nk, price]
        rows.append("| " + " | ".join(cells) + " |")
    uniq = {v for v in shas.values() if v}
    if len(uniq) == 1:
        tail = f"System prompt sha256, identical across the vendors run so far: `{uniq.pop()}`."
    else:
        tail = "System prompt sha256 per vendor: " + "; ".join(f"{k} `{v}`" for k, v in shas.items()) + "."
    return "\n".join(rows) + "\n\n" + tail + " Run ids are the llm_arm/llm_runs/ directory names; each holds HOW_WE_RAN_THIS.md, prices.json, system_prompt.txt, calls.jsonl, and summary.json."


def paper_version() -> str | None:
    m = load(MANIFEST)
    return (m or {}).get("version")


def fills(results: dict | None, runs: list[dict]) -> dict[str, str | None]:
    long_count, short_count = fill_count_params(runs)
    # the live spot check, the window-cap parity check and the floor-edit list are resolved in the Methods text itself
    # (SKIPPED with reason / None), not filled here
    out = {
        "count_params() per arm and task": long_count,
        "count_params()": short_count,
        "B from runs/batch_choice.json": fill_batch(),
        "realized epochs and best checkpoint per finished run": fill_epochs(runs),
        "readout reachable share within T": fill_reachability(),
        "degenerate dimension list per corpus, or none": fill_degenerate(results),
        "how we ran this table, one row per vendor": fill_how_table(results),
        "pilot s_seed and final seed count": fill_pilot(results),
    }
    if paper_version():
        out = {k: (v.replace("awaiting run", "not in this version").replace("AWAITING RUN", "NOT IN THIS VERSION") if v else v) for k, v in out.items()}
    return out


def apply_fills(paper: str, values: dict[str, str | None]) -> str:
    def wrap(key: str, val: str) -> str:
        return f"<!-- RUN: {key} -->\n\n{val}\n\n<!-- /RUN -->" if "\n" in val else f"<!-- RUN: {key} -->{val}<!-- /RUN -->"

    # previously filled blocks: recompute or revert
    def redo(m: re.Match) -> str:
        key = m.group(1)
        val = values.get(key)
        if val is None:
            say(f"(d) [RUN: {key}] reverted to placeholder (no evidence tonight)")
            return f"[RUN: {key}]"
        say(f"(d) [RUN: {key}] refreshed -> {val.splitlines()[0][:110]}{'...' if len(val) > 110 or chr(10) in val else ''}")
        return wrap(key, val)
    paper = re.sub(r"<!-- RUN: (.+?) -->.*?<!-- /RUN -->", redo, paper, flags=re.S)

    # bracketed placeholders still standing
    def fill(m: re.Match) -> str:
        key = m.group(1)
        val = values.get(key)
        if val is None:
            return m.group(0)
        no_dashes(val, f"RUN fill {key}")
        say(f"(d) [RUN: {key}] -> {val.splitlines()[0][:110]}{'...' if len(val) > 110 or chr(10) in val else ''}")
        return wrap(key, val)
    paper = re.sub(r"\[RUN: ([^\]]+)\]", fill, paper)
    return paper


# ------------------------------------------------------------------ (f) dataset DOI
def normalise_doi(doi: str) -> str:
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    if not re.match(r"^10\.\d{4,9}/\S+$", doi):
        sys.exit(f"--dataset-doi {doi!r} is not a DOI (expected 10.NNNN/...)")
    return doi


def fill_dataset_doi(paper: str, doi: str) -> str:
    """[DATASET DOI] -> https://doi.org/<doi> in the prose files; the bare DOI into the two Zenodo metadata files"""
    url = f"https://doi.org/{doi}"
    n = paper.count(DOI_PLACEHOLDER)
    paper = paper.replace(DOI_PLACEHOLDER, url)
    say(f"(f) paper.md: {n} {DOI_PLACEHOLDER} -> {url}")
    for p in DOI_FILES:
        text = p.read_text()
        n = text.count(DOI_PLACEHOLDER) + text.count("(Zenodo dataset, DOI in the paper)")
        new = text.replace(DOI_PLACEHOLDER, url).replace("(Zenodo dataset, DOI in the paper)", f"(Zenodo dataset, {url})")
        if new != text:
            p.write_text(new)
        say(f"(f) {p.relative_to(ROOT)}: {n} placeholder{'s' if n != 1 else ''} -> {url}")
    ds = json.loads(DOI_JSON_DATASET.read_text())
    ds["metadata"]["doi"] = doi
    DOI_JSON_DATASET.write_text(json.dumps(ds, indent=2, ensure_ascii=False) + "\n")
    say(f"(f) {DOI_JSON_DATASET.relative_to(ROOT)}: metadata.doi = {doi}")
    pz = json.loads(DOI_JSON_PAPER.read_text())
    rel = pz["metadata"].setdefault("related_identifiers", [])
    entry = {"identifier": doi, "relation": "isSupplementedBy", "resource_type": "dataset", "scheme": "doi"}
    rel[:] = [r for r in rel if not (r.get("relation") == "isSupplementedBy" and r.get("resource_type") == "dataset" and r.get("scheme") == "doi")] + [entry]
    DOI_JSON_PAPER.write_text(json.dumps(pz, indent=2, ensure_ascii=False) + "\n")
    say(f"(f) {DOI_JSON_PAPER.relative_to(ROOT)}: related_identifiers isSupplementedBy dataset {doi}")
    return paper


# ------------------------------------------------------------------ (e) literal checks
def verify_literals(paper: str, runs: list[dict]) -> None:
    checks: list[tuple[str, str]] = []
    bench = load(ROOT / "runs" / "bench_speed.json")
    if bench:
        checks += [("bench training step", f"{bench['train_step']['64']['median_step_s']:.3f} s at batch 64"),
                   ("bench forward batch 1", f"{bench['forward']['1']['latency_per_record_ms']:.1f} ms per record at batch 1"),
                   ("bench forward batch 256", f"{bench['forward']['256']['latency_per_record_ms']:.2f} ms per record at batch 256"),
                   ("bench device memory", f"{bench['train_step']['64']['device_bytes_after'] / 1e9:.1f} GB of device memory"),
                   ("bench padded edges", f"{bench['padded_edges']:,} padded edge slots for {bench['graph']['e']:,} edges"),
                   ("bench parameters at d_in 64", f"{bench['trainable_params']:,} trainable parameters"),
                   ("graph digest", bench["graph"]["meta_sha256"])]
    for r in runs:
        if r["arm"] != "connectome":
            continue
        sc = r["run_meta"]["split_counts"]
        task = r["run_meta"]["task"].upper()
        checks.append((f"{task} split counts", f"{task} {sc['train']['total']:,} / {sc['val']['total']:,} / {sc['test']['total']:,}"))
        checks.append((f"{task} corpus N", f"{r['run_meta']['split_meta']['n']:,} "))
        checks.append((f"{task} run graph digest", r["graph_meta_sha256"]))
    for name, lit in checks:
        say(f"(e) literal {name}: {'verified' if lit in paper else 'MISMATCH, paper.md lacks'} \"{lit.strip()}\"")


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=SITE_DEFAULT, help="st-connectome checkout (page.tsx, connectome-paper.ts)")
    ap.add_argument("--dataset-doi", default=None, help="Zenodo dataset DOI (10.5281/zenodo.NNN); fills [DATASET DOI] in the paper, READMEs and Zenodo metadata")
    a = ap.parse_args(argv)

    paper = PAPER.read_text()
    results = load(RESULTS)
    runs = run_jsons()
    say(f"splice_paper: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}; results.json status {results.get('status') if results else 'missing'}, "
        f"seeds {results.get('seeds') if results else '?'}; {len(runs)} run.json files; paper version {paper_version() or 'unset (no version mode)'}")

    paper = splice_section4(paper, SEC4.read_text())
    paper = splice_abstract(paper, ABSTRACT.read_text())
    paper = apply_fills(paper, fills(results, runs))
    if a.dataset_doi:
        paper = fill_dataset_doi(paper, normalise_doi(a.dataset_doi))
    no_dashes(paper.split("## 4. Results")[1].split("\n---")[0], "spliced Section 4")
    if paper != PAPER.read_text():
        PAPER.write_text(paper)
        say(f"wrote {PAPER.relative_to(ROOT)}")
    else:
        say(f"{PAPER.relative_to(ROOT)} unchanged (idempotent rerun)")

    if a.site.exists():
        splice_page(a.site)
    else:
        say(f"(c) site checkout not found at {a.site}; page not touched")

    verify_literals(paper, runs)
    left = re.findall(r"\[RUN: ([^\]]+)\]", paper)
    say(f"(e) [RUN: ...] placeholders remaining: {len(left)}")
    for k in left:
        say(f"      [RUN: {k}]")
    say(f"(e) {DOI_PLACEHOLDER} in paper.md: {paper.count(DOI_PLACEHOLDER)} (expected 1, in Data and Code Availability, until --dataset-doi is given)")
    say(f"(e) \"awaiting run\" in paper.md: {paper.lower().count('awaiting run')}")
    en_lines = [i for i, ln in enumerate(paper.splitlines(), 1) if chr(0x2013) in ln]
    say(f"(e) em dashes in paper.md: {paper.count(chr(0x2014))}; en dashes: {paper.count(chr(0x2013))} on lines {en_lines} (citation page ranges)")


if __name__ == "__main__":
    main()

"""CLI: .venv/bin/python -m llm_arm --provider xai --n 3 --k 1
     .venv/bin/python -m llm_arm --provider gemini --n 300 --k 3 --ids-from-run llm_arm/llm_runs/20260920T154525Z
     .venv/bin/python -m llm_arm --provider openai --n 300 --k 3 --ids-from-run llm_arm/llm_runs/20260920T154525Z --examples 100   # arm g2-examples"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from .adapters import PROVIDERS
from .examples import EXAMPLES_SEED, select_examples
from .loader import filter_records, load_records, read_frozen_clock, read_id_list, read_ids_from_run, stratified_sample
from .prompt import render_payload
from .runner import Runner

DEFAULT_INPUT = Path("/tmp/connectome-paper/teachers/dti_teacher.jsonl")
DEFAULT_OUT = Path(__file__).resolve().parent / "llm_runs"
DEFAULT_SPLIT = Path(__file__).resolve().parent.parent / "splits" / "dti_seed1.json"
DEFAULT_BUDGET = Path(__file__).resolve().parent / "examples_budget.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="llm_arm")
    ap.add_argument("--provider", choices=PROVIDERS, default="anthropic")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--n", type=int, required=True, help="records to sample, stratified by teacher tier (with --ids-from-run: the first n ids of that run)")
    ap.add_argument("--k", type=int, default=3, help="identical calls per record")
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--payload-field", default="text",
                    help="record field sent as RECORD (string verbatim; object rendered as sorted JSON)")
    ap.add_argument("--as-of", default=None,
                    help="scoring date given to the model; default: frozen_clock from dti_teacher_summary.json (or the source run's as_of)")
    ap.add_argument("--max-tokens", type=int, default=16000,
                    help="hard cap on thinking + answer (reasoning tokens count against the cap on every provider)")
    ap.add_argument("--effort", default="high", help="reasoning effort / thinking level sent to every provider (Opus 5 run: high)")
    ap.add_argument("--temperature", type=lambda v: None if v.lower() == "none" else float(v), default=0.0,
                    help="sent where the API accepts it (openai, xai, gemini); Anthropic adaptive thinking does not take it; use 'none' to omit")
    ap.add_argument("--ids", default=None,
                    help="PATH:PART restricts sampling to the ids listed under PART of a split file, e.g. splits/dti_seed1.json:test")
    ap.add_argument("--ids-from-run", type=Path, default=None,
                    help="score exactly the record ids of an earlier run (read from its calls.jsonl); asserts the same system prompt sha256")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--examples", type=int, default=0,
                    help="arm g2-examples: E engine-scored TRAIN examples in the system prefix (0 = arm g). Must equal chosen_E in --examples-budget")
    ap.add_argument("--examples-split", type=Path, default=DEFAULT_SPLIT, help="split file: TRAIN part supplies the examples, TEST part is the leakage check")
    ap.add_argument("--examples-seed", type=int, default=EXAMPLES_SEED)
    ap.add_argument("--examples-budget", type=Path, default=DEFAULT_BUDGET, help="scripts/choose_examples_e.py output; records E and the prefix token counts")
    a = ap.parse_args(argv)

    records = load_records(a.input)
    examples, examples_manifest, budget = None, None, None
    if a.examples:
        budget = json.loads(a.examples_budget.read_text())
        if budget.get("chosen_E") != a.examples:
            print(f"--examples {a.examples} != chosen_E {budget.get('chosen_E')} in {a.examples_budget}; rerun scripts/choose_examples_e.py or pass the chosen E", file=sys.stderr)
            return 2
        examples, examples_manifest = select_examples(records, a.examples_split, a.examples, a.examples_seed)
        if examples_manifest["record_ids_sha256"] != budget["candidates"][str(a.examples)]["record_ids_sha256"]:
            print("example id list differs from the one the budget measured; refusing", file=sys.stderr)
            return 2
    ids_source = None
    if a.ids_from_run:
        id_list, ids_source = read_ids_from_run(a.ids_from_run)
        if a.n < len(id_list):
            id_list = id_list[: a.n]   # smoke: first n ids of the source run, in that run's order
        by_id = {r["record_id"]: r for r in records}
        missing = [i for i in id_list if i not in by_id]
        if missing:
            print(f"{len(missing)} ids from {a.ids_from_run} are not in the input", file=sys.stderr)
            return 2
        sample = [by_id[i] for i in id_list]
        ids_source["n_ids_used"] = len(sample)
        if a.as_of is None:
            a.as_of = ids_source.get("source_as_of")
        print(f"scoring the {len(sample)} record ids of run {a.ids_from_run.name}", file=sys.stderr)
    else:
        if a.ids:
            id_list, sha = read_id_list(a.ids)
            records = filter_records(records, id_list)
            ids_source = {"spec": a.ids, "n_ids": len(id_list), "split_file_sha256": sha}
            print(f"restricted to {len(records)} records from {a.ids}", file=sys.stderr)
        sample = stratified_sample(records, a.n, a.seed)
    as_of = a.as_of or read_frozen_clock(a.input)
    if not as_of:
        print("no --as-of and no dti_teacher_summary.json next to the input; refusing to score without a date", file=sys.stderr)
        return 2
    for r in sample:
        render_payload(r, a.payload_field)  # fail before the first API call if the field is missing

    runner = Runner(records=sample, k=a.k, seed=a.seed, n_requested=a.n, payload_field=a.payload_field,
                    as_of=as_of, max_tokens=a.max_tokens, concurrency=a.concurrency,
                    out_root=a.out, input_path=a.input, ids_source=ids_source,
                    provider=a.provider, effort=a.effort, temperature=a.temperature,
                    examples=examples, examples_manifest=examples_manifest, examples_budget=budget, split_path=a.examples_split)
    print(f"run {runner.run_id} [{a.provider} {runner.model}] arm {runner.arm}: {len(sample)} records x k={a.k} -> {runner.out_dir}", file=sys.stderr)
    summary = asyncio.run(runner.run())
    print(json.dumps({k: summary[k] for k in ("counts", "cache", "tokens", "latency_ms", "cost_usd", "accuracy", "determinism")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

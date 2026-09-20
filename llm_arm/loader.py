"""Teacher JSONL loader and tier-stratified sampling."""
import json
import random
from collections import defaultdict
from pathlib import Path


def load_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stratified_sample(records: list[dict], n: int, seed: int) -> list[dict]:
    """Round-robin over teacher tiers so every tier present gets a share.
    Deterministic for a given (records order, n, seed)."""
    if n >= len(records):
        return list(records)
    rng = random.Random(seed)
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_tier[r["tier"]].append(r)
    tiers = sorted(by_tier)
    rng.shuffle(tiers)
    for t in tiers:
        rng.shuffle(by_tier[t])
    out: list[dict] = []
    i = 0
    while len(out) < n:
        t = tiers[i % len(tiers)]
        if by_tier[t]:
            out.append(by_tier[t].pop())
        i += 1
        if all(not v for v in by_tier.values()):
            break
    return out


def read_frozen_clock(jsonl_path: Path) -> str | None:
    """gen_dti.ts writes dti_teacher_summary.json next to the JSONL with the
    frozen clock every teacher day-count used."""
    p = jsonl_path.with_name("dti_teacher_summary.json")
    if not p.exists():
        return None
    return json.loads(p.read_text()).get("frozen_clock")


def read_id_list(spec: str) -> tuple[list[str], str]:
    """--ids PATH:PART -> (ids listed under PART in the split file, sha256 of that file)."""
    import hashlib
    path, _, part = spec.rpartition(":")
    if not path or part not in ("train", "val", "test"):
        raise ValueError(f"--ids wants PATH:{{train|val|test}}, got {spec!r}")
    p = Path(path)
    doc = json.loads(p.read_text())
    return list(doc[part]), hashlib.sha256(p.read_bytes()).hexdigest()


def filter_records(records: list[dict], ids: list[str], id_field: str = "record_id") -> list[dict]:
    """Keep only records whose id is in ids, in file order; every id must be found."""
    want = set(ids)
    kept = [r for r in records if r[id_field] in want]
    if len(kept) != len(want):
        raise ValueError(f"{len(want) - len(kept)} ids from the split file are not in the input")
    return kept


def read_ids_from_run(run_dir: Path) -> tuple[list[str], dict]:
    """Record ids of an earlier run, in order of first appearance in its
    calls.jsonl, so a second provider scores the byte-identical sample.
    Returns (ids, source) where source carries the run id, the file sha256,
    the run's system prompt sha256 and as_of for the caller to assert on."""
    import hashlib
    calls = run_dir / "calls.jsonl"
    ids: list[str] = []
    seen: set[str] = set()
    with open(calls, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rid = json.loads(line)["record_id"]
            if rid not in seen:
                seen.add(rid)
                ids.append(rid)
    summary = json.loads((run_dir / "summary.json").read_text())
    sp = run_dir / "system_prompt.txt"
    return ids, {
        "spec": f"ids-from-run:{run_dir.name}",
        "source_run_id": run_dir.name,
        "n_ids": len(ids),
        "calls_file_sha256": hashlib.sha256(calls.read_bytes()).hexdigest(),
        "source_prompt_sha256": hashlib.sha256(sp.read_bytes()).hexdigest() if sp.exists() else summary.get("prompt_sha256"),
        "source_as_of": summary.get("input", {}).get("as_of"),
        "source_ids_source": summary.get("input", {}).get("ids_source"),
        "split_file_sha256": (summary.get("input", {}).get("ids_source") or {}).get("split_file_sha256"),
    }

"""Scored-example block for arm g2-examples (post-hoc; PROTOCOL amendment 1, row 17).

E engine-scored records are drawn from the TRAINING split of seed 1, stratified
by teacher tier (E/5 per tier), with a fixed seed, and rendered into the system
prefix after the paper text. The same E records, in the same order, go to every
vendor and every repeat. Nothing from the TEST split may appear in the block:
`assert_no_leakage` is called before the first API call and by the tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .loader import filter_records, read_id_list, stratified_sample
from .prompt import TIERS, build_examples_block, sha256_text

EXAMPLES_SEED = 20260920
E_CHOICES = (50, 100, 200)
PREFIX_BUDGET_TOKENS = 150_000


def select_examples(records: list[dict], split_path: Path, e: int, seed: int = EXAMPLES_SEED) -> tuple[list[dict], dict]:
    """E records from the TRAIN part of split_path, E/5 per tier, deterministic in (records order, e, seed).
    Returns (examples, manifest)."""
    if e % len(TIERS):
        raise ValueError(f"E must be a multiple of {len(TIERS)} tiers, got {e}")
    train_ids, split_sha = read_id_list(f"{split_path}:train")
    train = filter_records(records, train_ids)
    examples = stratified_sample(train, e, seed)
    per_tier = {t: sum(r["tier"] == t for r in examples) for t in TIERS}
    if any(v != e // len(TIERS) for v in per_tier.values()):
        raise ValueError(f"stratification failed: {per_tier}")
    ids = [r["record_id"] for r in examples]
    manifest = {
        "arm": "g2-examples", "E": e, "selection_seed": seed,
        "source_split": f"{split_path}:train", "split_file_sha256": split_sha,
        "per_tier": per_tier, "record_ids": ids,
        "record_ids_sha256": hashlib.sha256(json.dumps(ids).encode()).hexdigest(),
    }
    return examples, manifest


def assert_no_leakage(example_ids: list[str], scored_ids: list[str], split_path: Path) -> dict:
    """Zero overlap with the records being scored AND with the whole TEST split of split_path.
    Returns the counts it checked so the run can log them."""
    ex = set(example_ids)
    if len(ex) != len(example_ids):
        raise AssertionError("duplicate example ids")
    test_ids, _ = read_id_list(f"{split_path}:test")
    hit_scored = ex & set(scored_ids)
    hit_test = ex & set(test_ids)
    if hit_scored or hit_test:
        raise AssertionError(f"example ids leak: {len(hit_scored)} in the scored set, {len(hit_test)} in the TEST split")
    return {"examples": len(ex), "scored_ids": len(set(scored_ids)), "test_split_ids": len(test_ids),
            "overlap_with_scored": 0, "overlap_with_test_split": 0}


def examples_block_sha256(examples: list[dict], payload_field: str = "text") -> str:
    return sha256_text(build_examples_block(examples, payload_field))

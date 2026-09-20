"""Arm g2-examples: the scored-example block. No network."""
import json
from pathlib import Path

import pytest

from llm_arm import metrics as M
from llm_arm.examples import assert_no_leakage, examples_block_sha256, select_examples
from llm_arm.loader import load_records, read_id_list, read_ids_from_run
from llm_arm.prompt import INSTRUCTION, TIERS, build_examples_block, build_system_prompt, sha256_text

ROOT = Path(__file__).resolve().parent.parent
TEACHER = ROOT / "teachers" / "dti_teacher.jsonl"
SPLIT = ROOT / "splits" / "dti_seed1.json"
OPUS_RUN = ROOT / "llm_arm" / "llm_runs" / "20260920T154525Z"
BUDGET = ROOT / "llm_arm" / "examples_budget.json"
AS_OF = "2026-09-20T00:00:00.000Z"
G_HASH = "5e7f42957795615a5e16b61d9e0d1e7d11864d8aabfdde0233a1d06ee87bca71"


@pytest.fixture(scope="module")
def records():
    return load_records(TEACHER)


@pytest.fixture(scope="module")
def picked(records):
    return select_examples(records, SPLIT, 100)


def test_stratified_twenty_per_tier(picked):
    ex, man = picked
    assert len(ex) == 100 == man["E"]
    per = {t: sum(r["tier"] == t for r in ex) for t in TIERS}
    assert per == {t: 20 for t in TIERS} == man["per_tier"]
    assert len({r["record_id"] for r in ex}) == 100


def test_deterministic_in_seed(records, picked):
    ex, man = picked
    ex2, man2 = select_examples(records, SPLIT, 100)
    assert [r["record_id"] for r in ex] == [r["record_id"] for r in ex2] == man["record_ids"] == man2["record_ids"]
    assert examples_block_sha256(ex) == examples_block_sha256(ex2)
    ex3, _ = select_examples(records, SPLIT, 100, seed=1)
    assert [r["record_id"] for r in ex3] != man["record_ids"]
    assert man["selection_seed"] == 20260920


def test_no_leakage_into_the_300_scored_ids_or_the_test_split(picked):
    ex, man = picked
    scored, _ = read_ids_from_run(OPUS_RUN)
    assert len(scored) == 300
    test_ids, _ = read_id_list(f"{SPLIT}:test")
    train_ids, _ = read_id_list(f"{SPLIT}:train")
    ids = set(man["record_ids"])
    assert ids & set(scored) == set()
    assert ids & set(test_ids) == set()
    assert ids <= set(train_ids)
    report = assert_no_leakage(man["record_ids"], scored, SPLIT)
    assert report == {"examples": 100, "scored_ids": 300, "test_split_ids": 4001, "overlap_with_scored": 0, "overlap_with_test_split": 0}


def test_leakage_check_catches_an_induced_leak(picked):
    ex, man = picked
    scored, _ = read_ids_from_run(OPUS_RUN)
    with pytest.raises(AssertionError, match="1 in the scored set"):
        assert_no_leakage(man["record_ids"][:-1] + [scored[0]], scored, SPLIT)
    test_ids, _ = read_id_list(f"{SPLIT}:test")
    with pytest.raises(AssertionError, match="1 in the TEST split"):
        assert_no_leakage(man["record_ids"][:-1] + [test_ids[0]], scored, SPLIT)
    with pytest.raises(AssertionError, match="duplicate"):
        assert_no_leakage(man["record_ids"][:-1] + [man["record_ids"][0]], scored, SPLIT)


def test_e_must_be_a_multiple_of_the_tier_count(records):
    with pytest.raises(ValueError):
        select_examples(records, SPLIT, 33)


def test_block_sits_after_the_paper_and_before_the_instruction(picked):
    ex, _ = picked
    sp = build_system_prompt(AS_OF, examples=ex)
    block = build_examples_block(ex)
    i_paper_end = sp.index("### 4.4 Confidence Intervals and Propagation")
    i_block = sp.index(block)
    i_instr = sp.index(INSTRUCTION.format(as_of=AS_OF))
    assert i_paper_end < i_block < i_instr
    assert sp.endswith(INSTRUCTION.format(as_of=AS_OF))   # the instruction block is byte-identical to arm g's
    assert "SCORED EXAMPLES" in block and block.count("\n\nENGINE OUTPUT\n") == 100 and "EXAMPLE 100\n" in block


def test_base_prompt_unchanged_and_examples_change_the_hash(picked):
    ex, _ = picked
    assert sha256_text(build_system_prompt(AS_OF)) == G_HASH
    assert sha256_text(build_system_prompt(AS_OF, examples=None)) == G_HASH
    assert sha256_text(build_system_prompt(AS_OF, examples=ex)) != G_HASH


def test_every_example_output_validates_and_matches_the_engine_arithmetic(picked):
    ex, _ = picked
    block = build_examples_block(ex)
    outs = [seg.split("\n\nENGINE OUTPUT\n", 1)[1].split("\n\n", 1)[0] for seg in block.split("EXAMPLE ")[1:]]
    assert len(outs) == 100
    for txt, r in zip(outs, ex):
        obj = json.loads(txt)
        assert M.validate_output(obj) == []
        assert obj == {"dimensions": r["dimensions"], "composite": r["composite"], "tier": r["tier"]}
        assert M.recompute_composite(obj["dimensions"]) == obj["composite"]
        assert M.tier_from_composite(obj["composite"]) == obj["tier"]
    # each example carries RECORD and CONTEXT in the scored record's exact form
    assert block.count("\nRECORD\n") == 100 and block.count("\n\nCONTEXT\n") == 100


def test_budget_file_pins_e_and_the_measured_prefix(picked):
    ex, man = picked
    b = json.loads(BUDGET.read_text())
    assert b["chosen_E"] == 100 and b["selection_seed"] == 20260920 and b["base_prompt_sha256"] == G_HASH
    c = b["candidates"]["100"]
    assert c["record_ids_sha256"] == man["record_ids_sha256"]
    assert c["examples_block_sha256"] == examples_block_sha256(ex)
    assert c["prefix_sha256"] == sha256_text(build_system_prompt(b["as_of"], examples=ex))
    assert all(v < b["budget_prefix_tokens"] for v in c["prefix_tokens"].values())
    assert set(c["prefix_tokens"]) == {"anthropic", "openai", "xai", "gemini"}
    assert not b["candidates"]["200"]["fits_every_vendor"]

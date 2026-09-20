"""LLM arm unit tests. No network: nothing here constructs an API client."""
import json
from pathlib import Path

import pytest

from llm_arm import metrics as M
from llm_arm.loader import load_records, stratified_sample
from llm_arm.prices import PRICE_TABLE, cost_usd
from llm_arm.prompt import DIMS, SCHEMA, TIERS, build_system_prompt, build_user_content, render_payload, sha256_text

FIX = Path(__file__).resolve().parent.parent / "llm_arm" / "fixtures"


# ---- schema ---------------------------------------------------------------
def test_fixture_response_validates():
    obj = json.loads((FIX / "response_ok.json").read_text())
    assert M.validate_output(obj) == []
    # the fixture is internally consistent with the paper's arithmetic
    assert M.recompute_composite(obj["dimensions"]) == obj["composite"]
    assert M.tier_from_composite(obj["composite"]) == obj["tier"]


@pytest.mark.parametrize("mutate,needle", [
    (lambda o: o["dimensions"].pop("breadth"), "dimensions.breadth"),
    (lambda o: o["dimensions"].__setitem__("quality", 101), "dimensions.quality"),
    (lambda o: o["dimensions"].__setitem__("quality", 88.0), "dimensions.quality"),
    (lambda o: o.__setitem__("tier", "Gold"), "tier"),
    (lambda o: o.__setitem__("composite", "82"), "composite"),
    (lambda o: o.__setitem__("note", "x"), "unexpected keys"),
    (lambda o: o["dimensions"].__setitem__("quality", True), "dimensions.quality"),
])
def test_schema_rejects(mutate, needle):
    obj = json.loads((FIX / "response_ok.json").read_text())
    mutate(obj)
    errs = M.validate_output(obj)
    assert errs and any(needle in e for e in errs)


def test_schema_constants_match():
    assert SCHEMA["properties"]["tier"]["enum"] == TIERS == ["BELOW THRESHOLD", "BRONZE", "SILVER", "GOLD", "PLATINUM"]
    assert SCHEMA["properties"]["dimensions"]["required"] == DIMS
    assert sum(M.WEIGHTS.values()) == 100


# ---- composite arithmetic ---------------------------------------------------
def test_js_round_half_up():
    assert M.js_round(2.5) == 3 and M.js_round(3.5) == 4  # Python round(2.5) would be 2
    assert M.js_round(2.4999) == 2


def test_recompute_composite_matches_engine_rows():
    for r in load_records(FIX / "records.jsonl"):
        assert M.recompute_composite(r["dimensions"]) == r["composite"]
        assert M.tier_from_composite(r["composite"]) == r["tier"]


# ---- cost -------------------------------------------------------------------
def test_cost_computation():
    usage = {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 4000, "cache_read_input_tokens": 0}
    # 1000*5 + 4000*6.25 + 200*25 = 5000 + 25000 + 5000 = 35000 micro-dollars
    assert cost_usd(usage) == pytest.approx(0.035)
    usage2 = {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 4000}
    # 5000 + 4000*0.5 + 5000 = 12000
    assert cost_usd(usage2) == pytest.approx(0.012)
    assert cost_usd({"input_tokens": 1}) == pytest.approx(5e-6)  # missing keys count as 0
    p = PRICE_TABLE["usd_per_mtok"]
    assert p["cache_read"] == pytest.approx(0.1 * p["input"]) and p["cache_write_5m"] == pytest.approx(1.25 * p["input"])
    assert all(Path(s["file"]).exists() for s in PRICE_TABLE["sources"]), "price source files must exist on disk"


# ---- metrics ----------------------------------------------------------------
def _out(dims_val, comp, tier):
    return {"dimensions": {d: dims_val for d in DIMS}, "composite": comp, "tier": tier}


def test_mae():
    assert M.mae([(10, 12), (20, 17), (5, 5)]) == pytest.approx((2 + 3 + 0) / 3)
    assert M.mae([]) is None


def test_tier_accuracy_and_macro_f1():
    y_true = ["GOLD", "GOLD", "SILVER", "BRONZE"]
    y_pred = ["GOLD", "SILVER", "SILVER", "GOLD"]
    assert M.accuracy(y_true, y_pred) == 0.5
    # GOLD: tp1 fp1 fn1 -> f1 0.5 ; SILVER: tp1 fp1 fn0 -> 2/3 ; BRONZE: tp0 fp0 fn1 -> 0
    assert M.macro_f1(y_true, y_pred) == pytest.approx((0.5 + 2 / 3 + 0) / 3)
    assert M.macro_f1(y_true, y_true) == 1.0
    assert M.macro_f1([], []) is None


def test_determinism_metric():
    same = {"a": [_out(80, 80, "GOLD"), _out(80, 80, "GOLD"), _out(80, 80, "GOLD")]}
    d = M.determinism(same)
    assert d["exact_match_share"] == 1.0 and d["tier_identical_share"] == 1.0
    assert all(v == 0 for v in d["per_dimension_sd_mean"].values()) and d["composite_range_mean"] == 0
    mixed = {
        "a": [_out(80, 80, "GOLD"), _out(82, 82, "GOLD")],          # dims differ, tier same
        "b": [_out(70, 70, "SILVER"), _out(70, 69, "BRONZE")],      # composite/tier differ
        "c": [_out(50, 50, "BELOW THRESHOLD")],                    # single output: excluded
    }
    d = M.determinism(mixed)
    assert d["records_with_2plus_outputs"] == 2
    assert d["exact_match_share"] == 0.0 and d["tier_identical_share"] == 0.5
    assert d["per_dimension_sd_mean"]["quality"] == pytest.approx((2 ** 0.5 + 0) / 2)  # stdev([80,82]) = 1.414
    assert d["composite_range_mean"] == pytest.approx((2 + 1) / 2)


def test_percentile_and_majority():
    assert M.percentile([5, 1, 3], 50) == 3 and M.percentile([5, 1, 3], 95) == 5
    assert M.majority(["GOLD", "GOLD", "SILVER"]) == ("GOLD", False)
    assert M.majority(["GOLD", "SILVER"])[1] is True


# ---- prompt -----------------------------------------------------------------
def test_system_prompt_is_paper_sections_3_and_4_only():
    sp = build_system_prompt("2026-09-20T00:00:00.000Z")
    assert "## 3. The DTI Framework" in sp and "### 4.4 Confidence Intervals and Propagation" in sp
    assert "## 5." not in sp and "## 2." not in sp and "Abstract" not in sp
    assert "BELOW THRESHOLD" in sp and "2026-09-20T00:00:00.000Z" in sp
    assert "Output JSON only" in sp
    assert sha256_text(sp) == sha256_text(build_system_prompt("2026-09-20T00:00:00.000Z"))  # stable hash


def test_user_content_and_payload_field():
    recs = load_records(FIX / "records.jsonl")
    r = recs[0]
    assert render_payload(r, "text") == r["text"]
    as_json = render_payload(r, "extracted")
    assert json.loads(as_json) == r["extracted"]
    uc = build_user_content(r, "text")
    assert uc.startswith("RECORD\n") and "\n\nCONTEXT\n" in uc
    assert '"source_consent"' in uc and '"element_scores"' in uc
    with pytest.raises(KeyError):
        render_payload(r, "no_such_field")


# ---- loader -----------------------------------------------------------------
def test_stratified_sample_deterministic_and_covers_tiers():
    recs = load_records(FIX / "records.jsonl")
    assert len(recs) == 3 and len({r["tier"] for r in recs}) == 3
    big = recs * 10
    s1 = stratified_sample(big, 3, seed=1)
    s2 = stratified_sample(big, 3, seed=1)
    assert [r["record_id"] for r in s1] == [r["record_id"] for r in s2]
    assert len({r["tier"] for r in s1}) == 3  # one from each tier present
    assert len(stratified_sample(big, 7, seed=2)) == 7
    assert stratified_sample(recs, 99, seed=0) == recs

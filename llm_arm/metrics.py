"""Metrics for the LLM arm: schema check, composite recompute, MAE, tier
accuracy and macro-F1, determinism across repeats, percentiles."""
import math
import statistics
from collections import Counter, defaultdict

from .prompt import DIMS, TIERS

WEIGHTS = {
    "provenance": 25, "consent": 20, "recency": 15, "quality": 10,
    "concordance": 10, "validation": 10, "breadth": 5, "stability": 5,
}


def validate_output(obj) -> list[str]:
    """Return a list of schema violations (empty = valid). Mirrors SCHEMA in
    prompt.py without a jsonschema dependency."""
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["output is not an object"]
    extra = set(obj) - {"dimensions", "composite", "tier"}
    if extra:
        errs.append(f"unexpected keys {sorted(extra)}")
    dims = obj.get("dimensions")
    if not isinstance(dims, dict):
        errs.append("dimensions missing or not an object")
    else:
        for d in DIMS:
            v = dims.get(d)
            if not (isinstance(v, int) and not isinstance(v, bool)) or not 0 <= v <= 100:
                errs.append(f"dimensions.{d} must be int 0-100, got {v!r}")
        extra_d = set(dims) - set(DIMS)
        if extra_d:
            errs.append(f"unexpected dimension keys {sorted(extra_d)}")
    c = obj.get("composite")
    if not (isinstance(c, int) and not isinstance(c, bool)) or not 0 <= c <= 100:
        errs.append(f"composite must be int 0-100, got {c!r}")
    if obj.get("tier") not in TIERS:
        errs.append(f"tier must be one of {TIERS}, got {obj.get('tier')!r}")
    return errs


def js_round(x: float) -> int:
    """JavaScript Math.round: half rounds toward +infinity (pipeline.ts
    computeDTIResult). Python's round() is banker's rounding, so not that."""
    return math.floor(x + 0.5)


def recompute_composite(dims: dict) -> int:
    return js_round(sum(dims[d] * WEIGHTS[d] for d in DIMS) / 100)


def tier_from_composite(c: int) -> str:
    if c >= 90:
        return "PLATINUM"
    if c >= 80:
        return "GOLD"
    if c >= 70:
        return "SILVER"
    if c >= 55:
        return "BRONZE"
    return "BELOW THRESHOLD"


def mae(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return sum(abs(a - b) for a, b in pairs) / len(pairs)


def accuracy(y_true: list[str], y_pred: list[str]) -> float | None:
    if not y_true:
        return None
    return sum(a == b for a, b in zip(y_true, y_pred)) / len(y_true)


def macro_f1(y_true: list[str], y_pred: list[str], labels: list[str] | None = None) -> float | None:
    """Macro-F1 over `labels` (default: labels present in y_true). A label
    with no predictions and no truths would be undefined, so defaulting to
    truth-present labels avoids padding the mean with zeros for absent tiers."""
    if not y_true:
        return None
    if labels is None:
        labels = sorted(set(y_true))
    f1s = []
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        denom = 2 * tp + fp + fn
        f1s.append(0.0 if denom == 0 else 2 * tp / denom)
    return sum(f1s) / len(f1s)


def determinism(outputs_by_record: dict[str, list[dict]]) -> dict:
    """outputs_by_record: record_id -> list of parsed outputs (k repeats).
    Records with fewer than 2 parsed outputs are excluded and counted.
    SD is the sample SD (ddof=1) across repeats, averaged over records."""
    exact, tier_same, n = 0, 0, 0
    dim_sds: dict[str, list[float]] = defaultdict(list)
    comp_ranges: list[float] = []
    for _, outs in outputs_by_record.items():
        if len(outs) < 2:
            continue
        n += 1
        canon = [_canon(o) for o in outs]
        exact += all(c == canon[0] for c in canon)
        tier_same += len({o["tier"] for o in outs}) == 1
        for d in DIMS:
            dim_sds[d].append(statistics.stdev(o["dimensions"][d] for o in outs))
        comps = [o["composite"] for o in outs]
        comp_ranges.append(max(comps) - min(comps))
    if n == 0:
        return {"records_with_2plus_outputs": 0}
    return {
        "records_with_2plus_outputs": n,
        "exact_match_share": exact / n,
        "tier_identical_share": tier_same / n,
        "per_dimension_sd_mean": {d: sum(v) / n for d, v in dim_sds.items()},
        "composite_range_mean": sum(comp_ranges) / n,
        "sd_definition": "sample SD (ddof=1) across repeats, mean over records",
    }


def _canon(o: dict) -> tuple:
    return (tuple(o["dimensions"][d] for d in DIMS), o["composite"], o["tier"])


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile, p in [0, 100]."""
    if not values:
        return None
    s = sorted(values)
    k = max(1, math.ceil(p / 100 * len(s)))
    return s[k - 1]


def majority(items: list[str]) -> tuple[str, bool]:
    """(winner, tie?)"""
    c = Counter(items).most_common()
    tie = len(c) > 1 and c[0][1] == c[1][1]
    return c[0][0], tie

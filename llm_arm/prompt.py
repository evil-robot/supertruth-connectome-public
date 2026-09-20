"""System prompt and output schema for the LLM arm.

System prompt = published DTI paper sections 3 and 4 verbatim + a fixed
instruction block. It is byte-identical across every call in a run so the
whole block sits behind one cache_control breakpoint (prompt-caching.md:
"Large system prompt shared across many requests").

Arm g2-examples (post-hoc, amendment 1 row 17) inserts a fixed block of E
engine-scored TRAINING examples between the paper text and the instruction
block; with examples=None the prompt is byte-identical to arm g's.
"""
import hashlib
import json
from pathlib import Path

PAPER_PATH = Path("/Users/jas/Projects/supertruth-dti/paper.md")

DIMS = ["provenance", "consent", "recency", "quality", "concordance", "validation", "breadth", "stability"]
TIERS = ["BELOW THRESHOLD", "BRONZE", "SILVER", "GOLD", "PLATINUM"]

SCHEMA = {
    "type": "object",
    "properties": {
        "dimensions": {
            "type": "object",
            # The API rejects minimum/maximum on integers (400 on 2026-09-20:
            # "For 'integer' type, properties maximum, minimum are not supported").
            # The 0-100 range is stated in INSTRUCTION and enforced by metrics.validate_output.
            "properties": {d: {"type": "integer"} for d in DIMS},
            "required": DIMS,
            "additionalProperties": False,
        },
        "composite": {"type": "integer"},
        "tier": {"type": "string", "enum": TIERS},
    },
    "required": ["dimensions", "composite", "tier"],
    "additionalProperties": False,
}

INSTRUCTION = """INSTRUCTIONS

You are scoring one health data record with the Data Trust Index (DTI) defined in the paper text above.

Score the record below on the eight dimensions (provenance, consent, recency, quality, concordance, validation, breadth, stability), the composite, and the tier exactly per the paper: each dimension an integer from 0 to 100; composite = the weighted sum of the eight dimension scores with the Table 1 weights, rounded to the nearest integer; tier from the composite per Section 3.3, with a composite below 55 labelled BELOW THRESHOLD.

Treat the current date as {as_of} for every recency and consent-age calculation.

The input arrives in two parts. RECORD is the record payload as the scoring system received it. CONTEXT is connector-side structured context supplied with the record: per-element corroboration counts, source types and collection dates (element_scores); per-source consent level (source_consent); per-source consent scope (consent_scope). Use only what is in RECORD and CONTEXT. Do not assume facts that are not stated.

Output JSON only, matching the required schema. No prose."""


def paper_sections_3_4(text: str) -> str:
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## 3. "))
    end = next(i for i, l in enumerate(lines) if l.startswith("## 5. "))
    body = lines[start:end]
    while body and body[-1].strip() in ("", "---"):
        body.pop()
    return "\n".join(body)


EXAMPLES_HEADER = """SCORED EXAMPLES

The {n} records below were drawn from the same synthetic generator as the record you will score and were scored by the deployed DTI engine. Each example shows RECORD and CONTEXT in the exact form the record to score will take, followed by ENGINE OUTPUT: the engine's eight dimension scores, composite, and tier for that record. None of these examples is the record you will score."""


def render_engine_output(record: dict) -> str:
    return json.dumps({"dimensions": {d: record["dimensions"][d] for d in DIMS},
                       "composite": record["composite"], "tier": record["tier"]})


def build_examples_block(examples: list[dict], payload_field: str = "text") -> str:
    parts = [EXAMPLES_HEADER.format(n=len(examples))]
    for i, r in enumerate(examples, start=1):
        parts.append(f"EXAMPLE {i}\n" + build_user_content(r, payload_field) + "\n\nENGINE OUTPUT\n" + render_engine_output(r))
    return "\n\n".join(parts)


def build_system_prompt(as_of: str, paper_path: Path = PAPER_PATH, examples: list[dict] | None = None,
                        payload_field: str = "text") -> str:
    paper = paper_sections_3_4(paper_path.read_text(encoding="utf-8"))
    block = ("\n\n" + build_examples_block(examples, payload_field)) if examples else ""
    return (
        "PUBLISHED DTI PAPER, SECTIONS 3 AND 4 (framework and scoring methodology), verbatim:\n\n"
        + paper
        + block
        + "\n\n"
        + INSTRUCTION.format(as_of=as_of)
    )


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def render_payload(record: dict, payload_field: str) -> str:
    if payload_field not in record:
        raise KeyError(
            f"record {record.get('record_id')} has no field '{payload_field}'; "
            f"available: {sorted(record.keys())}. Pass --payload-field to name the payload."
        )
    v = record[payload_field]
    if isinstance(v, str):
        return v
    return json.dumps(v, sort_keys=True, indent=1)


def render_context(record: dict) -> str:
    ctx = {
        "element_scores": record.get("element_scores", []),
        "source_consent": record.get("source_consent", {}),
        "consent_scope": record.get("consent_scope", {}),
    }
    return json.dumps(ctx, sort_keys=True, indent=1)


def build_user_content(record: dict, payload_field: str) -> str:
    return (
        "RECORD\n" + render_payload(record, payload_field)
        + "\n\nCONTEXT\n" + render_context(record)
    )

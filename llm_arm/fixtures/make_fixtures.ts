/**
 * Three hand-built synthetic records (shape of st-homepage-refresh
 * src/lib/synthetic-records.ts) scored by the deployed DTI engine with the
 * clock frozen to the teacher's FROZEN_CLOCK. Output rows carry the same
 * field names as gen_dti.ts rows PLUS `text`, so the loader's --payload-field
 * text path is exercised offline. Test fixtures only; zero PHI.
 *
 * Run: cd /Users/jas/Projects/st-homepage-refresh && node_modules/.bin/tsx \
 *   /Users/jas/Projects/supertruth-connectome/llm_arm/fixtures/make_fixtures.ts \
 *   > /Users/jas/Projects/supertruth-connectome/llm_arm/fixtures/records.jsonl
 */
import * as crypto from "crypto";
import { extractFields, scoreDTI, computeDTIResult, type ScoringContext } from "/Users/jas/Projects/st-homepage-refresh/src/lib/pipeline";

const FROZEN_CLOCK_ISO = "2026-09-20T00:00:00.000Z";
Date.now = () => Date.parse(FROZEN_CLOCK_ISO);

const RECORDS: Array<{ id: string; lines: string[]; ctx: ScoringContext }> = [
  {
    id: "FIX-DTI-000001",
    lines: [
      "[recap_header]", "Record ID: FIX-DTI-000001", "Export: MedSync RECAP flat file, consolidated across connected sources",
      "Hospital Name: SYN Facility A", "Hospital Name: SYN Facility B", "",
      "[recap_patient]", "Name: SYN-Alpha Testcase", "Date of Birth: 03/15/1952", "Medicare Beneficiary Identifier: 1SYN4-TST-0001", "Sex: Female", "",
      "[recap_consent]", "HIPAA Authorization signed January 15, 2026.", "Release to treating care team. Status: ACTIVE.", "",
      "[recap_care_team]", "Dr. Quinn Synthprov  NPI: 0000123456  Primary Care", "Dr. Reed Fakemd  NPI: 0000234567  Cardiology", "Dr. Sloan Mockdoc  NPI: 0000345678  Endocrinology", "",
      "[recap_conditions] (3)", "Type 2 diabetes mellitus without complications; Essential hypertension; Hyperlipidemia, unspecified", "",
      "[recap_medications]", "Medication: Metformin 1000 mg PO BID", "Medication: Lisinopril 10 mg PO QD", "Medication: Atorvastatin 40 mg PO QHS", "",
      "[recap_allergies]", "Allergen: Penicillin [reaction: hives]", "",
      "[recap_vitals]", "Recorded: 09/10/2026", "Blood Pressure: 138/82 mmHg  Heart Rate: 74 bpm  Weight: 168 lbs", "",
      "[recap_labs]", "HbA1c: 7.2 %  09/10/2026", "LDL: 98 mg/dL  09/10/2026", "eGFR: 48 mL/min  09/10/2026", "",
      "[recap_imaging]", "2026-01-20  Chest X-ray  no acute process", "",
      "[recap_encounters]", "2026-09-10, 2026-01-20", "",
      "[recap_footer]", "Synthetic record for engineering test only. Not a real person.",
    ],
    ctx: {
      elementScores: [
        { corroborationCount: 4, sourceType: "lab", field: "a1c", collectedAt: "2026-09-10" },
        { corroborationCount: 3, sourceType: "ehr", field: "ldl", collectedAt: "2026-09-10" },
        { corroborationCount: 3, sourceType: "lab", field: "egfr", collectedAt: "2026-09-10" },
        { corroborationCount: 2, sourceType: "pharmacy", field: "medication" },
      ],
      sourceConsent: { "syn-source-1": "explicit", "syn-source-2": "explicit" },
      consentScope: { "syn-source-1": "care_coordination", "syn-source-2": "research_eligible" },
    } as ScoringContext,
  },
  {
    id: "FIX-DTI-000002",
    lines: [
      "Cerner EHR continuity of care export", "Chart ID: FIX-DTI-000002", "",
      "DEMOGRAPHICS", "Name: SYN-Bravo Fixture", "Date of Birth: 06/08/1955", "Medicare Beneficiary Identifier: NOT ON FILE", "Sex: Female", "",
      "AUTHORIZATION", "Consent: on file. Release to treating care team.", "",
      "CARE TEAM", "Dr. Tate Testphys  NPI: 0000456789  Primary Care", "Dr. Vale Stubcare  (identifier not on file)", "",
      "ACTIVE DIAGNOSES (ICD-10-CM)", "M06.9 - Rheumatoid arthritis, unspecified", "E11.65 - Type 2 diabetes mellitus with hyperglycemia", "",
      "CURRENT MEDICATIONS", "1. Methotrexate 15 mg PO weekly", "2. Metformin 500 mg PO BID", "",
      "VITAL SIGNS", "Recorded: 05/14/2026", "Blood Pressure: 142/88 mmHg  Heart Rate: 68 bpm  Weight: 154 lbs", "",
      "LABORATORY RESULTS", "HbA1c: 8.4 %  05/14/2026", "",
      "ENCOUNTER DATES", "2026-05-14, 2025-11-02", "",
      "!! CONFLICT: dosage discrepancy between connected sources. Reconciliation required. !!", "",
      "----", "Synthetic record for engineering test only. Not a real person.",
    ],
    ctx: {
      elementScores: [
        { corroborationCount: 1, sourceType: "ehr", field: "a1c", collectedAt: "2026-05-14" },
        { corroborationCount: 1, field: "medication" },
        { corroborationCount: 0, sourceType: "patient_reported" },
      ],
      sourceConsent: { "syn-source-1": "inherited" },
      consentScope: { "syn-source-1": "treatment_only" },
    } as ScoringContext,
  },
  {
    id: "FIX-DTI-000003",
    lines: [
      "Faxed summary, origin not identified", "Record ID: FIX-DTI-000003", "",
      "DEMOGRAPHICS", "Name: [not retrieved]", "Date of Birth: not retrieved", "Medicare Beneficiary Identifier: NOT ON FILE", "Sex: Male", "",
      "AUTHORIZATION", "Formal HIPAA Authorization: NOT ON FILE.", "Verbal agreement noted at intake. Written form requested.", "",
      "Diagnosis: Coronary artery disease, native vessel, Essential hypertension", "",
      "CURRENT MEDICATIONS", "1. Aspirin 81 mg PO QD", "",
      "LABORATORY RESULTS", "HbA1c: 9.1 %  not recorded", "",
      "----", "Synthetic record for engineering test only. Not a real person.",
    ],
    ctx: {
      elementScores: [{ corroborationCount: 0, sourceType: "patient_reported" }, { corroborationCount: 0 }],
      sourceConsent: { "syn-source-1": "none" },
      consentScope: {},
    } as ScoringContext,
  },
];

for (const r of RECORDS) {
  const text = r.lines.join("\n");
  const fields = extractFields(text, 1);
  const dims = scoreDTI(fields, r.ctx);
  const result = computeDTIResult(dims);
  const dimScores: Record<string, number> = {};
  for (const d of dims) dimScores[d.name.toLowerCase()] = d.score;
  const row = {
    record_id: r.id,
    seed: 0,
    knobs: { fixture: true },
    text,
    extracted: { ...fields, mostRecentDate: fields.mostRecentDate ? fields.mostRecentDate.toISOString() : null, oldestDate: fields.oldestDate ? fields.oldestDate.toISOString() : null },
    element_scores: r.ctx.elementScores ?? [],
    source_consent: r.ctx.sourceConsent ?? {},
    consent_scope: r.ctx.consentScope ?? {},
    dimensions: dimScores,
    composite: result.composite,
    tier: result.tier,
    flags: result.flags,
    text_sha256: crypto.createHash("sha256").update(text).digest("hex"),
    text_chars: text.length,
    frozen_clock: FROZEN_CLOCK_ISO,
    data_class: "synthetic",
  };
  process.stdout.write(JSON.stringify(row) + "\n");
}

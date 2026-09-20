/**
 * gen_dti.ts -- DTI teacher-label dataset for the SuperTruth connectome whitepaper.
 *
 * Synthetic only. Every name, MRN, MBI, NPI carries an obvious SYN prefix or a
 * 0000-leading digit block. Zero PHI.
 *
 * Engine: /Users/jas/Projects/st-homepage-refresh/src/lib/pipeline.ts (main)
 *   extractFields(text, 1)  -> ExtractedFields
 *   scoreDTI(fields, ctx)   -> 8 dimensions
 *   computeDTIResult(dims)  -> composite, tier, flags
 *
 * Clock: Date.now is frozen to FROZEN_CLOCK_ISO so daysSince() is reproducible.
 *
 * Run (from the website repo so tsx resolves):
 *   cd /Users/jas/Projects/st-homepage-refresh && node_modules/.bin/tsx \
 *     /tmp/connectome-paper/teachers/gen_dti.ts --n 20000 --seed 20260920 \
 *     --out /tmp/connectome-paper/teachers
 * Regenerate a slice (QA):  --start 0 --n 200 --rows-only /path/rows.jsonl
 */
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import {
  extractFields,
  scoreDTI,
  computeDTIResult,
  getModalityWindow,
  type ExtractedFields,
  type ScoringContext,
} from "/Users/jas/Projects/st-homepage-refresh/src/lib/pipeline";

// ─── Frozen clock ─────────────────────────────────────────────────────────────
export const FROZEN_CLOCK_ISO = "2026-09-20T00:00:00.000Z";
const FROZEN_MS = Date.parse(FROZEN_CLOCK_ISO);
Date.now = () => FROZEN_MS;

// ─── Seeded PRNG (xmur3 hash -> sfc32) ────────────────────────────────────────
function xmur3(str: string) {
  let h = 1779033703 ^ str.length;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return (h ^= h >>> 16) >>> 0;
  };
}
class RNG {
  private a: number; private b: number; private c: number; private d: number;
  constructor(key: string) {
    const s = xmur3(key);
    this.a = s(); this.b = s(); this.c = s(); this.d = s();
    for (let i = 0; i < 12; i++) this.next();
  }
  next(): number { // sfc32, [0,1)
    this.a >>>= 0; this.b >>>= 0; this.c >>>= 0; this.d >>>= 0;
    let t = (this.a + this.b) | 0;
    this.a = this.b ^ (this.b >>> 9);
    this.b = (this.c + (this.c << 3)) | 0;
    this.c = (this.c << 21) | (this.c >>> 11);
    this.d = (this.d + 1) | 0;
    t = (t + this.d) | 0;
    this.c = (this.c + t) | 0;
    return (t >>> 0) / 4294967296;
  }
  uniform(lo: number, hi: number) { return lo + (hi - lo) * this.next(); }
  int(lo: number, hi: number) { return lo + Math.floor(this.next() * (hi - lo + 1)); } // inclusive
  bern(p: number) { return this.next() < p; }
  pick<T>(arr: readonly T[]): T { return arr[Math.floor(this.next() * arr.length)]; }
  weighted<T>(items: readonly T[], weights: number[]): T {
    const tot = weights.reduce((a, b) => a + b, 0);
    let r = this.next() * tot;
    for (let i = 0; i < items.length; i++) { r -= weights[i]; if (r <= 0) return items[i]; }
    return items[items.length - 1];
  }
  shuffle<T>(arr: T[]): T[] {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(this.next() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }
}

// ─── Vocab (all synthetic) ────────────────────────────────────────────────────
const FIRST = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa"];
const LAST = ["Testcase", "Fixture", "Sample", "Placeholder", "Dummy", "Synthetic", "Mockdata", "Stub"];
const PROVIDER_FIRST = ["Quinn", "Reed", "Sloan", "Tate", "Vale", "Wren", "Xavier", "Yael"];
const PROVIDER_LAST = ["Synthprov", "Fakemd", "Mockdoc", "Testphys", "Stubcare", "Dummyclin"];

type Family = "diabetes" | "ckd" | "cardiology" | "oncology" | "respiratory" | "hypertension" | "filler";
const CONDITIONS: Record<Family, Array<{ icd: string; label: string }>> = {
  diabetes:     [{ icd: "E11.9", label: "Type 2 diabetes mellitus without complications" }, { icd: "E11.65", label: "Type 2 diabetes mellitus with hyperglycemia" }],
  ckd:          [{ icd: "N18.3", label: "Chronic kidney disease, stage 3" }, { icd: "N18.4", label: "Chronic kidney disease, stage 4" }],
  cardiology:   [{ icd: "I25.10", label: "Coronary artery disease, native vessel" }, { icd: "I50.9", label: "Heart failure, unspecified" }, { icd: "I48.91", label: "Atrial fibrillation, unspecified" }],
  oncology:     [{ icd: "C50.911", label: "Malignant carcinoma of breast, unspecified" }, { icd: "C61", label: "Malignant tumor of prostate" }],
  respiratory:  [{ icd: "J44.9", label: "COPD, unspecified" }, { icd: "J45.50", label: "Severe persistent asthma" }],
  hypertension: [{ icd: "I10", label: "Essential hypertension" }],
  filler:       [{ icd: "E78.5", label: "Hyperlipidemia, unspecified" }, { icd: "M81.0", label: "Age-related osteoporosis" }, { icd: "F32.9", label: "Depressive disorder, single episode" }, { icd: "E03.9", label: "Hypothyroidism, unspecified" }, { icd: "K21.9", label: "Gastro-esophageal reflux disease" }],
};
const MEDS: Record<Family, string[]> = {
  diabetes:     ["Metformin 1000 mg PO BID", "Insulin glargine 20 units SC QHS", "Glipizide 5 mg PO QD"],
  ckd:          ["Sevelamer 800 mg PO TID", "Calcitriol 0.25 mcg PO QD"],
  cardiology:   ["Metoprolol 25 mg PO BID", "Carvedilol 12.5 mg PO BID", "Atorvastatin 40 mg PO QHS"],
  oncology:     ["Tamoxifen 20 mg PO QD", "Ondansetron 8 mg PO PRN"],
  respiratory:  ["Albuterol HFA 90 mcg INH PRN", "Fluticasone 110 mcg INH BID"],
  hypertension: ["Lisinopril 10 mg PO QD", "Amlodipine 5 mg PO QD", "Losartan 50 mg PO QD"],
  filler:       ["Aspirin 81 mg PO QD", "Omeprazole 20 mg PO QD", "Levothyroxine 50 mcg PO QD", "Gabapentin 300 mg PO TID", "Acetaminophen 500 mg PO PRN"],
};
// Lab panels by engine recency class (pipeline.ts detectConditionAndRecency :100-108)
type Panel = "chronic" | "semiannual" | "acute" | "none";
const LABS: Record<Exclude<Panel, "none">, Array<{ name: string; value: string }>> = {
  chronic:    [{ name: "HbA1c", value: "7.2 %" }, { name: "eGFR", value: "48 mL/min" }, { name: "LDL", value: "98 mg/dL" }, { name: "HDL", value: "52 mg/dL" }, { name: "Creatinine", value: "1.4 mg/dL" }, { name: "Triglyceride", value: "148 mg/dL" }, { name: "Total cholesterol", value: "182 mg/dL" }],
  semiannual: [{ name: "TSH", value: "2.1 mIU/L" }, { name: "PSA", value: "1.8 ng/mL" }, { name: "Vitamin D", value: "31 ng/mL" }, { name: "Ferritin", value: "88 ng/mL" }, { name: "Uric acid", value: "5.9 mg/dL" }],
  acute:      [{ name: "CBC", value: "within limits" }, { name: "BMP", value: "within limits" }, { name: "INR", value: "1.1" }, { name: "Platelet", value: "242 K/uL" }, { name: "Sodium", value: "138 mEq/L" }, { name: "Potassium", value: "4.2 mEq/L" }, { name: "ALT", value: "24 U/L" }, { name: "AST", value: "22 U/L" }],
};
const ELEMENT_FIELDS = ["a1c", "ldl", "egfr", "creatinine", "tsh", "psa", "cbc", "sodium", "hemoglobin", "blood pressure", "weight", "diagnosis", "medication", "allergy", "encounter"];
const SOURCE_TYPES = ["lab", "ehr", "hie", "payer", "pharmacy", "patient_reported", "other"] as const;
const CONSENT_LEVELS = ["explicit", "inherited", "implicit", "none"] as const;
const SCOPES = ["treatment_only", "care_coordination", "research_eligible", "commercial_eligible", "unknown"] as const;
type Format = "recap" | "labcorp" | "quest" | "epic" | "cerner" | "generic" | "none";
type ConsentKind = "signed_dated" | "on_file_undated" | "verbal_unsigned" | "absent";
type ConflictKind = "none" | "keyword" | "allergy_med";

// ─── Knobs (the structured truth) ─────────────────────────────────────────────
export interface Knobs {
  latent_q: number;
  format: Format;
  facility_count: number;
  npi_count: number;
  providers_without_npi: number;
  name_present: boolean; dob_present: boolean; mbi_present: boolean;
  families: Family[];
  n_conditions: number;
  icd_style: "dash" | "plain" | "recap_list" | "none";
  n_meds: number;
  panel: Panel; n_labs: number;
  vitals: boolean; allergies: boolean; imaging: boolean; procedures: boolean; sdoh: boolean; care_gaps: number;
  has_dates: boolean; days_ago_most_recent: number; span_months: number; n_intermediate_dates: number;
  consent_kind: ConsentKind; consent_age_days: number;
  conflict: ConflictKind;
  n_elements: number; corroboration_mean_target: number; typed_share: number; source_type_bias: "trusted" | "mixed" | "weak";
  element_dates_share: number; element_age_spread_days: number;
  source_consent_n: number; source_consent_levels: string[];
  consent_scope_n: number; consent_scope_values: string[];
}

function fmtUS(d: Date) { return `${String(d.getUTCMonth() + 1).padStart(2, "0")}/${String(d.getUTCDate()).padStart(2, "0")}/${d.getUTCFullYear()}`; }
function fmtISO(d: Date) { return d.toISOString().slice(0, 10); }
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
function fmtLong(d: Date) { return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`; }
function daysAgo(n: number) { return new Date(FROZEN_MS - n * 86400000); }

// Knob distributions: a latent quality q drives the tendencies, each knob keeps
// its own noise so the eight dimensions do not collapse onto one axis.
// Tuned so every tier holds between 8% and 40% (see dti_teacher_summary.json).
export function drawKnobs(r: RNG): Knobs {
  // Fat-tailed latent: mixture of uniform and the two edges so BELOW and PLATINUM both fill.
  const u = r.next();
  const q = u < 0.19 ? r.uniform(0, 0.25) : u < 0.70 ? r.uniform(0.2, 0.95) : r.uniform(0.88, 1.0);

  const format = r.weighted<Format>(
    ["recap", "labcorp", "quest", "epic", "cerner", "generic", "none"],
    [0.10 + 0.20 * q, 0.06 + 0.10 * q, 0.06 + 0.10 * q, 0.05 + 0.12 * q, 0.05 + 0.08 * q, 0.15 - 0.05 * q, 0.35 * (1 - q) + 0.03],
  );
  const nFam = r.weighted([0, 1, 2, 3], [0.18, 0.42, 0.28, 0.12]);
  const families = r.shuffle<Family>(["diabetes", "ckd", "cardiology", "oncology", "respiratory", "hypertension"]).slice(0, nFam);
  const nConditions = Math.min(6, Math.max(0, Math.round(r.uniform(-0.5, 2.5) + 3.5 * q)));
  const icdStyle = format === "recap"
    ? r.weighted(["recap_list", "none"] as const, [0.85, 0.15])
    : r.weighted(["dash", "plain", "none"] as const, [0.2 + 0.6 * q, 0.35, 0.45 * (1 - q) + 0.05]);
  const hasDates = r.bern(0.12 + 0.85 * q);
  const daysAgoMostRecent = r.bern(0.30 + 0.6 * q) ? (r.bern(0.6) ? r.int(0, 30) : r.int(0, 90)) : r.bern(0.5) ? r.int(45, 600) : r.int(300, 2000);
  const consentKind = r.weighted<ConsentKind>(
    ["signed_dated", "on_file_undated", "verbal_unsigned", "absent"],
    [0.08 + 0.72 * q, 0.15, 0.25 * (1 - q) + 0.05, 0.35 * (1 - q) + 0.05],
  );
  const nElements = r.bern(0.22) ? 0 : r.int(3, 30);
  const sourceConsentN = r.bern(0.30) ? 0 : r.int(1, 3);
  const consentScopeN = r.bern(0.35) ? 0 : r.int(1, 3);
  const sourceTypeBias = r.weighted(["trusted", "mixed", "weak"] as const, [0.15 + 0.6 * q, 0.3, 0.5 * (1 - q) + 0.05]);
  return {
    latent_q: Math.round(q * 1e4) / 1e4,
    format,
    facility_count: format === "recap" ? r.weighted([0, 1, 2, 3, 4], [0.15, 0.25, 0.25, 0.2 + 0.1 * q, 0.15 * q]) : 0,
    npi_count: r.weighted([0, 1, 2, 3, 4, 5], [0.45 * (1 - q) + 0.05, 0.2, 0.2, 0.15 + 0.15 * q, 0.1 * q, 0.1 * q]),
    providers_without_npi: r.weighted([0, 1, 2], [0.6, 0.3, 0.1]),
    name_present: r.bern(0.25 + 0.7 * q), dob_present: r.bern(0.25 + 0.7 * q), mbi_present: r.bern(0.15 + 0.75 * q),
    families, n_conditions: nConditions, icd_style: icdStyle,
    n_meds: Math.min(10, Math.max(0, Math.round(r.uniform(-1, 3) + 6 * q))),
    panel: r.weighted<Panel>(["chronic", "semiannual", "acute", "none"], [0.35, 0.15, 0.25, 0.25]),
    n_labs: Math.min(8, Math.max(0, Math.round(r.uniform(-1, 3) + 5 * q))),
    vitals: r.bern(0.5), allergies: r.bern(0.45), imaging: r.bern(0.3), procedures: r.bern(0.3), sdoh: r.bern(0.3),
    care_gaps: r.weighted([0, 1, 2, 3, 4], [0.5, 0.2, 0.15, 0.1, 0.05]),
    has_dates: hasDates, days_ago_most_recent: daysAgoMostRecent,
    span_months: r.weighted([0, 1, 3, 5, 8, 14, 24, 40, 60], [0.15, 0.12, 0.13, 0.1, 0.12, 0.13, 0.12, 0.08, 0.05]),
    n_intermediate_dates: r.int(0, 3),
    consent_kind: consentKind, consent_age_days: r.weighted([r.int(0, 364), r.int(365, 729), r.int(730, 1500)], [0.5 + 0.3 * q, 0.25, 0.25 * (1 - q) + 0.05]),
    conflict: r.bern(0.4 * (1 - q) + 0.03) ? (format === "recap" && r.bern(0.5) ? "allergy_med" : "keyword") : "none",
    n_elements: nElements,
    corroboration_mean_target: Math.max(0, Math.min(4, r.uniform(-0.5, 1.0) + 3.5 * q)),
    typed_share: r.weighted([0, r.uniform(0.2, 0.9), 1], [0.3, 0.3, 0.4]),
    source_type_bias: sourceTypeBias,
    element_dates_share: r.weighted([0, r.uniform(0.2, 0.9), 1], [0.35, 0.3, 0.35]),
    element_age_spread_days: r.weighted([0, 30, 120, 400], [0.4, 0.3, 0.2, 0.1]),
    source_consent_n: sourceConsentN,
    source_consent_levels: Array.from({ length: sourceConsentN }, () => r.weighted<string>(CONSENT_LEVELS as unknown as string[], [0.15 + 0.6 * q, 0.25, 0.2, 0.4 * (1 - q) + 0.03])),
    consent_scope_n: consentScopeN,
    consent_scope_values: Array.from({ length: consentScopeN }, () => r.weighted<string>(SCOPES as unknown as string[], [0.35 * (1 - q) + 0.05, 0.25, 0.15 + 0.3 * q, 0.05 + 0.15 * q, 0.2])),
  };
}

// ─── Record text + scoring context ────────────────────────────────────────────
export interface Built { text: string; context: ScoringContext; datePool: string[] }

export function buildRecord(k: Knobs, r: RNG, recordId: string): Built {
  const L: string[] = [];
  const recap = k.format === "recap";
  const patientName = `SYN-${r.pick(FIRST)} ${r.pick(LAST)}`;
  const dob = `${String(r.int(1, 12)).padStart(2, "0")}/${String(r.int(1, 28)).padStart(2, "0")}/${r.int(1940, 1975)}`;
  const mbi = `${r.int(1, 9)}SYN${r.int(0, 9)}-TST-${String(r.int(0, 9999)).padStart(4, "0")}`;

  // Date pool: most recent + oldest + intermediates (only when has_dates)
  const dates: Date[] = [];
  if (k.has_dates) {
    const mr = daysAgo(k.days_ago_most_recent);
    dates.push(mr);
    const spanDays = Math.round(k.span_months * 30.44);
    if (spanDays > 0) {
      dates.push(daysAgo(k.days_ago_most_recent + spanDays));
      for (let i = 0; i < k.n_intermediate_dates; i++) dates.push(daysAgo(k.days_ago_most_recent + r.int(1, Math.max(1, spanDays - 1))));
    }
  }
  const dateAt = (i: number) => dates.length ? dates[Math.min(i, dates.length - 1)] : null;
  const dstr = (d: Date | null, f: (d: Date) => string) => d ? f(d) : "not recorded";

  // Header / source system
  switch (k.format) {
    case "recap":
      L.push("[recap_header]", `Record ID: ${recordId}`, "Export: MedSync RECAP flat file, consolidated across connected sources");
      for (let i = 0; i < k.facility_count; i++) L.push(`Hospital Name: SYN Facility ${String.fromCharCode(65 + i)}`);
      break;
    case "labcorp": L.push("LABCORP  Laboratory Corporation of America  Patient Report", `Report ID: ${recordId}`); break;
    case "quest":   L.push("Quest Diagnostics  Patient Report", `Report ID: ${recordId}`); break;
    case "epic":    L.push("Generated by Epic EHR (SYN Health System)", `Chart ID: ${recordId}`); break;
    case "cerner":  L.push("Cerner EHR continuity of care export", `Chart ID: ${recordId}`); break;
    case "generic": L.push("Source: SYN Community Clinic Export", `Record ID: ${recordId}`); break;
    case "none":    L.push("Faxed summary, origin not identified", `Record ID: ${recordId}`); break;
  }
  L.push("");

  // Demographics (word "patient" avoided elsewhere so name absence is real)
  L.push(recap ? "[recap_patient]" : "DEMOGRAPHICS");
  L.push(k.name_present ? `Name: ${patientName}` : "Name: [not retrieved]");
  L.push(k.dob_present ? `Date of Birth: ${dob}` : "Date of Birth: not retrieved");
  L.push(k.mbi_present ? `Medicare Beneficiary Identifier: ${mbi}` : "Medicare Beneficiary Identifier: NOT ON FILE");
  L.push(`Sex: ${r.pick(["Male", "Female"])}`);
  L.push("");

  // Consent
  switch (k.consent_kind) {
    case "signed_dated":
      L.push(recap ? "[recap_consent]" : "AUTHORIZATION", `HIPAA Authorization signed ${fmtLong(daysAgo(k.consent_age_days))}.`, "Release to treating care team. Status: ACTIVE.", "");
      break;
    case "on_file_undated":
      L.push(recap ? "[recap_consent]" : "AUTHORIZATION", "Consent: on file. Release to treating care team.", "");
      break;
    case "verbal_unsigned":
      L.push(recap ? "[recap_consent]" : "AUTHORIZATION", "Formal HIPAA Authorization: NOT ON FILE.", "Verbal agreement noted at intake. Written form requested.", "");
      break;
    case "absent": break;
  }

  // Care team
  if (k.npi_count + k.providers_without_npi > 0) {
    L.push(recap ? "[recap_care_team]" : "CARE TEAM");
    for (let i = 0; i < k.npi_count; i++) {
      L.push(`Dr. ${PROVIDER_FIRST[i % PROVIDER_FIRST.length]} ${PROVIDER_LAST[i % PROVIDER_LAST.length]}  NPI: 0000${String(100000 + r.int(0, 899999))}  ${r.pick(["Primary Care", "Cardiology", "Endocrinology", "Nephrology", "Pulmonology"])}`);
    }
    for (let i = 0; i < k.providers_without_npi; i++) {
      L.push(`Dr. ${PROVIDER_FIRST[(i + 5) % PROVIDER_FIRST.length]} ${PROVIDER_LAST[(i + 3) % PROVIDER_LAST.length]}  (identifier not on file)`);
    }
    L.push("");
  }

  // Conditions
  const condPool: Array<{ icd: string; label: string }> = [];
  for (const f of k.families) condPool.push(...CONDITIONS[f]);
  condPool.push(...CONDITIONS.filler);
  const conds = r.shuffle(condPool).slice(0, k.n_conditions);
  // guarantee each chosen family contributes at least one condition when n allows
  k.families.forEach((f, i) => { if (i < conds.length && !conds.some(c => CONDITIONS[f].includes(c))) conds[i] = CONDITIONS[f][0]; });
  if (conds.length > 0 && k.icd_style !== "none") {
    if (k.icd_style === "recap_list") {
      L.push(`[recap_conditions] (${conds.length})`, conds.map(c => c.label).join("; "), "");
    } else if (k.icd_style === "dash") {
      L.push("ACTIVE DIAGNOSES (ICD-10-CM)");
      for (const c of conds) L.push(`${c.icd} - ${c.label}`);
      L.push("");
    } else {
      L.push(`Diagnosis: ${conds.map(c => c.label).join(", ")}`, "");
    }
  }

  // Medications
  const medPool: string[] = [];
  for (const f of k.families) medPool.push(...MEDS[f]);
  medPool.push(...MEDS.filler);
  const meds = r.shuffle(medPool).slice(0, k.n_meds);
  if (meds.length > 0) {
    L.push(recap ? "[recap_medications]" : "CURRENT MEDICATIONS");
    meds.forEach((m, i) => L.push(recap ? `Medication: ${m}` : `${i + 1}. ${m}`));
    L.push("");
  }

  // Allergies (+ optional allergen/medication overlap for RECAP conflict)
  if (k.allergies || k.conflict === "allergy_med") {
    L.push(recap ? "[recap_allergies]" : "ALLERGIES");
    L.push(`Allergen: ${r.pick(["Penicillin", "Sulfonamide", "Latex", "Shellfish"])} [reaction: ${r.pick(["hives", "rash", "GI upset"])}]`);
    if (k.conflict === "allergy_med") {
      const target = meds[0]?.split(" ")[0] ?? "Metformin";
      if (!meds.length) L.push(`Medication: Metformin 500 mg PO QD`);
      L.push(`Allergen: ${target} [reaction: rash]`);
    }
    L.push("");
  }

  // Vitals
  if (k.vitals) {
    L.push(recap ? "[recap_vitals]" : "VITAL SIGNS", `Recorded: ${dstr(dateAt(0), fmtUS)}`);
    L.push(`Blood Pressure: ${r.int(110, 165)}/${r.int(65, 95)} mmHg  Heart Rate: ${r.int(58, 98)} bpm  Weight: ${r.int(120, 240)} lbs`, "");
  }

  // Labs
  if (k.panel !== "none" && k.n_labs > 0) {
    L.push(recap ? "[recap_labs]" : "LABORATORY RESULTS");
    const panel = r.shuffle(LABS[k.panel]).slice(0, k.n_labs);
    panel.forEach((lab, i) => L.push(`${lab.name}: ${lab.value}  ${dstr(dateAt(i === 0 ? 0 : r.int(0, Math.max(0, dates.length - 1))), fmtUS)}`));
    L.push("");
  }

  // Imaging / procedures / SDOH
  if (k.imaging)    L.push(recap ? "[recap_imaging]" : "DIAGNOSTIC IMAGING", `${dstr(dateAt(r.int(0, Math.max(0, dates.length - 1))), fmtISO)}  Chest X-ray  no acute process`, "");
  if (k.procedures) L.push(recap ? "[recap_procedures]" : "PROCEDURE HISTORY", `${dstr(dateAt(dates.length ? dates.length - 1 : 0), fmtISO)}  Colonoscopy, screening`, "");
  if (k.sdoh)       L.push(recap ? "[recap_sdoh]" : "SOCIAL DETERMINANTS (SDOH)", `Housing: ${r.pick(["stable", "unstable"])}  Food security: ${r.pick(["no concern", "mild concern"])}`, "");

  // Care gaps (read into dataTypes as "care gaps"; no dimension expects that type)
  if (k.care_gaps > 0) {
    L.push(recap ? "[recap_care_gaps]" : "CARE GAPS");
    const gaps = ["OVERDUE: Annual eye exam", "OVERDUE: Kidney health evaluation", "BORDERLINE: HbA1c control", "MISSING: Annual wellness visit"];
    for (let i = 0; i < k.care_gaps; i++) L.push(gaps[i]);
    L.push("");
  }

  // Encounter dates line guarantees the pool endpoints appear in the text
  if (dates.length) L.push(recap ? "[recap_encounters]" : "ENCOUNTER DATES", dates.map(fmtISO).join(", "), "");

  // Conflict keyword
  if (k.conflict === "keyword") L.push("!! CONFLICT: dosage discrepancy between connected sources. Reconciliation required. !!", "");

  L.push(recap ? "[recap_footer]" : "----", "Synthetic record for engineering test only. Not a real person.");

  // ── Scoring context (the connector-side inputs) ───────────────────────────
  const elementScores: NonNullable<ScoringContext["elementScores"]> = [];
  for (let i = 0; i < k.n_elements; i++) {
    // integer corroboration 0..4 around the target mean
    const cc = Math.max(0, Math.min(4, Math.round(k.corroboration_mean_target + r.uniform(-1.2, 1.2))));
    const el: { corroborationCount: number; sourceType?: string; collectedAt?: string; field?: string } = { corroborationCount: cc };
    if (r.bern(k.typed_share)) {
      el.sourceType = k.source_type_bias === "trusted" ? r.weighted(SOURCE_TYPES as unknown as string[], [0.45, 0.35, 0.1, 0.03, 0.03, 0.02, 0.02])
        : k.source_type_bias === "weak" ? r.weighted(SOURCE_TYPES as unknown as string[], [0.03, 0.07, 0.1, 0.25, 0.15, 0.3, 0.1])
        : r.pick(SOURCE_TYPES as unknown as string[]);
    }
    if (r.bern(k.element_dates_share)) {
      el.field = r.pick(ELEMENT_FIELDS);
      const base = k.has_dates ? k.days_ago_most_recent : r.int(0, 900);
      el.collectedAt = fmtISO(daysAgo(Math.max(0, base + r.int(0, k.element_age_spread_days))));
    }
    elementScores.push(el);
  }
  const context: ScoringContext = {};
  if (elementScores.length) context.elementScores = elementScores;
  if (k.source_consent_n > 0) {
    context.sourceConsent = {};
    k.source_consent_levels.forEach((lv, i) => { context.sourceConsent![`syn-source-${i + 1}`] = lv as any; });
  }
  if (k.consent_scope_n > 0) {
    context.consentScope = {};
    k.consent_scope_values.forEach((sc, i) => { context.consentScope![`syn-source-${i + 1}`] = sc as any; });
  }
  return { text: L.join("\n"), context, datePool: dates.map(fmtISO) };
}

// ─── Feature vector (what the engine reads, numerically encoded) ───────────────
// Built from ExtractedFields + ScoringContext only. See dti_features_spec.md.
const SOURCE_CLASSES = ["null", "recap", "labcorp", "quest", "epic", "cerner", "other_named"] as const;
const DATA_TYPES = ["demographics", "medications", "diagnoses", "labs", "care gaps", "vitals", "SDOH", "allergies", "imaging", "procedures"] as const;
const EXPECTED_TYPES = ["diagnoses", "medications", "labs", "vitals", "imaging", "procedures", "demographics", "allergies"] as const;
const WINDOWS = [30, 60, 90, 180] as const;
const SOURCE_TYPE_TRUST: Record<string, number> = { lab: 1.0, ehr: 0.9, hie: 0.8, payer: 0.7, pharmacy: 0.7, patient_reported: 0.4, other: 0.55 };

export interface FeatureDef { index: number; name: string; meaning: string; range: string; engine_ref: string }
export const FEATURE_SPEC: FeatureDef[] = [];
function def(name: string, meaning: string, range: string, engine_ref: string) { FEATURE_SPEC.push({ index: FEATURE_SPEC.length, name, meaning, range, engine_ref }); }
SOURCE_CLASSES.forEach(c => def(`source_${c}`, `one-hot: fields.sourceSystem class = ${c}`, "{0,1}", "pipeline.ts :306-314, :432, :446-448"));
def("is_recap", "fields.isRecapFormat", "{0,1}", ":168, :434, :691");
def("facility_count", "min(fields.facilityCount, 5)", "0..5 int", ":246-247, :437-439");
def("npis_found", "min(fields.npisFound, 6)", "0..6 int", ":232-233, :441-443, :675, :702");
def("provider_count", "min(fields.providerCount, 8)", "0..8 int", ":236-243, :444-445");
def("name_present", "fields.patientName != null", "{0,1}", ":171-174, :617, :317");
def("dob_present", "fields.dob != null", "{0,1}", ":177-178, :618, :317");
def("mbi_present", "fields.mbi != null", "{0,1}", ":181-184, :619, :701");
def("log1p_medication_count", "log1p(fields.medicationCount)", "0..~4.1", ":202-204, :620, :676");
def("log1p_diagnosis_count", "log1p(fields.diagnosisCount)", "0..~3", ":207-229, :621, :694");
def("icd_coded_count", "count of fields.diagnoses entries matching ^[A-Z]\\d{2}, capped 8", "0..8 int", ":207-208, :704-706");
def("log1p_lab_count", "log1p(fields.labCount)", "0..~3", ":250, :622, :319");
def("consent_found", "fields.consentFound", "{0,1}", ":256-264, :483");
def("consent_date_present", "fields.consentDate != null", "{0,1}", ":265-266, :484");
def("log1p_consent_age_days", "log1p(daysSince(consentDate)) at the frozen clock; 0 if none", "0..~7.4", ":484-489");
def("most_recent_present", "fields.mostRecentDate != null", "{0,1}", ":282-283, :543");
def("log1p_days_since_most_recent", "log1p(daysSince(mostRecentDate)); log1p(999) if none", "0..~7.6", ":370-373, :543-548");
def("log1p_date_span_months", "log1p(months between oldest and most recent date)", "0..~4.2", ":752-758");
def("has_conflict", "fields.hasConflict", "{0,1}", ":286-304, :623, :655-657, :673-675");
DATA_TYPES.forEach(t => def(`present_${t.replace(" ", "_")}`, `one-hot: '${t}' in fields.dataTypes`, "{0,1}", ":316-326, :738-741"));
EXPECTED_TYPES.forEach(t => def(`expected_${t}`, `one-hot: '${t}' in fields.expectedDataTypes`, "{0,1}", ":110-155, :738-741"));
WINDOWS.forEach(w => def(`window_${w}d`, `one-hot: fields.primaryRecencyWindowDays == ${w}`, "{0,1}", ":104-111, :544"));
def("log1p_n_elements", "log1p(len(elementScores))", "0..~3.4", ":452, :578, :652");
def("avg_corroboration", "mean corroborationCount over elementScores; 0 if none", "0..4", ":654");
def("typed_source_share", "share of elements with sourceType", "0..1", ":452");
def("avg_source_trust", "mean SOURCE_TYPE_TRUST over typed elements; 0.75 (neutral) if none", "0.4..1.0", ":403-411, :455-459");
def("dated_element_share", "share of elements with collectedAt and field", "0..1", ":578-582");
def("log1p_element_avg_ratio", "log1p(mean daysSince(collectedAt)/getModalityWindow(field)) over dated elements; 0 if none", "0..~5", ":582-591");
def("log1p_element_worst_ratio", "log1p(max ratio) over dated elements; 0 if none", "0..~5", ":589-591");
def("source_consent_n", "number of sourceConsent entries", "0..3", ":492");
CONSENT_LEVELS.forEach(l => def(`source_consent_${l}`, `count of sourceConsent values == ${l}`, "0..3 int", ":493-500"));
def("consent_scope_n", "number of consentScope entries", "0..3", ":505");
SCOPES.forEach(s => def(`consent_scope_${s}`, `count of consentScope values == ${s}`, "0..3 int", ":506-518"));
export const FEATURE_LEN = FEATURE_SPEC.length;

function daysSinceFrozen(d: Date | null) { return d ? Math.floor((FROZEN_MS - d.getTime()) / 86400000) : 999; }

export function encodeFeatures(f: ExtractedFields, ctx: ScoringContext): number[] {
  const v: number[] = [];
  const src = f.sourceSystem;
  const srcClass = src == null ? "null" : f.isRecapFormat ? "recap" : /labcorp/i.test(src) ? "labcorp" : /quest/i.test(src) ? "quest" : /epic/i.test(src) ? "epic" : /cerner/i.test(src) ? "cerner" : "other_named";
  SOURCE_CLASSES.forEach(c => v.push(c === srcClass ? 1 : 0));
  v.push(f.isRecapFormat ? 1 : 0, Math.min(f.facilityCount, 5), Math.min(f.npisFound, 6), Math.min(f.providerCount, 8));
  v.push(f.patientName ? 1 : 0, f.dob ? 1 : 0, f.mbi ? 1 : 0);
  v.push(Math.log1p(f.medicationCount), Math.log1p(f.diagnosisCount), Math.min(8, f.diagnoses.filter(d => /^[A-Z]\d{2}/.test(d)).length), Math.log1p(f.labCount));
  v.push(f.consentFound ? 1 : 0, f.consentDate ? 1 : 0);
  if (f.consentDate) { const d = new Date(f.consentDate); v.push(isNaN(d.getTime()) ? Math.log1p(999) : Math.log1p(Math.max(0, daysSinceFrozen(d)))); } else v.push(0);
  v.push(f.mostRecentDate ? 1 : 0, Math.log1p(Math.max(0, daysSinceFrozen(f.mostRecentDate))));
  const span = f.mostRecentDate && f.oldestDate ? (f.mostRecentDate.getTime() - f.oldestDate.getTime()) / (86400000 * 30) : 0;
  v.push(Math.log1p(span), f.hasConflict ? 1 : 0);
  DATA_TYPES.forEach(t => v.push(f.dataTypes.includes(t) ? 1 : 0));
  EXPECTED_TYPES.forEach(t => v.push(f.expectedDataTypes.includes(t) ? 1 : 0));
  WINDOWS.forEach(w => v.push(f.primaryRecencyWindowDays === w ? 1 : 0));
  const els = ctx.elementScores ?? [];
  v.push(Math.log1p(els.length));
  v.push(els.length ? els.reduce((s, e) => s + (e.corroborationCount ?? 0), 0) / els.length : 0);
  const typed = els.filter(e => e.sourceType);
  v.push(els.length ? typed.length / els.length : 0);
  v.push(typed.length ? typed.reduce((s, e) => s + (SOURCE_TYPE_TRUST[e.sourceType!] ?? SOURCE_TYPE_TRUST.other), 0) / typed.length : 0.75);
  const dated = els.filter(e => e.collectedAt && e.field);
  v.push(els.length ? dated.length / els.length : 0);
  if (dated.length) {
    const ratios = dated.map(e => daysSinceFrozen(new Date(e.collectedAt!)) / getModalityWindow(e.field!));
    v.push(Math.log1p(Math.max(0, ratios.reduce((a, b) => a + b, 0) / ratios.length)), Math.log1p(Math.max(0, Math.max(...ratios))));
  } else v.push(0, 0);
  const sc = Object.values(ctx.sourceConsent ?? {});
  v.push(sc.length); CONSENT_LEVELS.forEach(l => v.push(sc.filter(x => x === l).length));
  const cs = Object.values(ctx.consentScope ?? {});
  v.push(cs.length); SCOPES.forEach(s => v.push(cs.filter(x => x === s).length));
  if (v.length !== FEATURE_LEN) throw new Error(`feature length ${v.length} != spec ${FEATURE_LEN}`);
  return v.map(x => Math.round(x * 1e6) / 1e6);
}

// ─── One record end to end ────────────────────────────────────────────────────
export function makeRow(seed: number, i: number) {
  const recordId = `SYN-DTI-${String(i).padStart(6, "0")}`;
  const r = new RNG(`${seed}|${recordId}`);
  const knobs = drawKnobs(r);
  const built = buildRecord(knobs, r, recordId);
  const fields = extractFields(built.text, 1);
  const dims = scoreDTI(fields, built.context);
  const result = computeDTIResult(dims);
  const features = encodeFeatures(fields, built.context);
  const dimScores: Record<string, number> = {};
  for (const d of dims) dimScores[d.name.toLowerCase()] = d.score;
  return {
    record_id: recordId,
    seed,
    knobs,
    extracted: {
      ...fields,
      mostRecentDate: fields.mostRecentDate ? fields.mostRecentDate.toISOString() : null,
      oldestDate: fields.oldestDate ? fields.oldestDate.toISOString() : null,
    },
    element_scores: built.context.elementScores ?? [],
    source_consent: built.context.sourceConsent ?? {},
    consent_scope: built.context.consentScope ?? {},
    dimensions: dimScores,
    dimension_notes: Object.fromEntries(dims.map(d => [d.name.toLowerCase(), d.note])),
    composite: result.composite,
    tier: result.tier,
    flags: result.flags,
    features,
    text: built.text, // the exact payload string passed to extractFields (protocol section 6)
    text_sha256: crypto.createHash("sha256").update(built.text).digest("hex"),
    text_chars: built.text.length,
  };
}

// ─── Summary ──────────────────────────────────────────────────────────────────
type Row = ReturnType<typeof makeRow>;
const DIM_NAMES = ["provenance", "consent", "recency", "quality", "concordance", "validation", "breadth", "stability"];
function stats(xs: number[]) {
  const n = xs.length; const mean = xs.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1));
  return { mean: +mean.toFixed(3), sd: +sd.toFixed(3), min: Math.min(...xs), max: Math.max(...xs), n_distinct: new Set(xs).size };
}
function corr(a: number[], b: number[]) {
  const n = a.length, ma = a.reduce((x, y) => x + y, 0) / n, mb = b.reduce((x, y) => x + y, 0) / n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { sab += (a[i] - ma) * (b[i] - mb); saa += (a[i] - ma) ** 2; sbb += (b[i] - mb) ** 2; }
  return saa === 0 || sbb === 0 ? 0 : +(sab / Math.sqrt(saa * sbb)).toFixed(4);
}
export function summarize(rows: Row[], meta: Record<string, unknown>) {
  const tierHist: Record<string, number> = {};
  for (const r of rows) tierHist[r.tier] = (tierHist[r.tier] ?? 0) + 1;
  const tierShare = Object.fromEntries(Object.entries(tierHist).map(([k, v]) => [k, +(v / rows.length).toFixed(4)]));
  const dimStats = Object.fromEntries(DIM_NAMES.map(d => [d, stats(rows.map(r => r.dimensions[d]))]));
  const compHist: Record<string, number> = {};
  for (const r of rows) { const b = Math.floor(r.composite / 5) * 5; const key = `${b}-${b + 4}`; compHist[key] = (compHist[key] ?? 0) + 1; }
  const featureKeys = new Set<string>(); let dupFeatures = 0;
  for (const r of rows) { const key = r.features.join(","); if (featureKeys.has(key)) dupFeatures++; else featureKeys.add(key); }
  const textKeys = new Set<string>(); let dupText = 0;
  for (const r of rows) { if (textKeys.has(r.text_sha256)) dupText++; else textKeys.add(r.text_sha256); }
  const corrMatrix: Record<string, Record<string, number>> = {};
  for (const a of DIM_NAMES) { corrMatrix[a] = {}; for (const b of DIM_NAMES) corrMatrix[a][b] = corr(rows.map(r => r.dimensions[a]), rows.map(r => r.dimensions[b])); }
  const flagCounts: Record<string, number> = {};
  for (const r of rows) for (const f of r.flags) flagCounts[f] = (flagCounts[f] ?? 0) + 1;
  // knob distributions (final)
  const knobHist = (key: keyof Knobs) => { const h: Record<string, number> = {}; for (const r of rows) { const v = String((r.knobs as any)[key]); h[v] = (h[v] ?? 0) + 1; } return h; };
  const knobDist = {
    format: knobHist("format"), consent_kind: knobHist("consent_kind"), conflict: knobHist("conflict"), icd_style: knobHist("icd_style"),
    panel: knobHist("panel"), npi_count: knobHist("npi_count"), facility_count: knobHist("facility_count"), has_dates: knobHist("has_dates"),
    span_months: knobHist("span_months"), source_type_bias: knobHist("source_type_bias"), source_consent_n: knobHist("source_consent_n"), consent_scope_n: knobHist("consent_scope_n"),
    days_ago_most_recent: stats(rows.map(r => r.knobs.days_ago_most_recent)), n_elements: stats(rows.map(r => r.knobs.n_elements)),
    corroboration_mean_target: stats(rows.map(r => r.knobs.corroboration_mean_target)), n_meds: stats(rows.map(r => r.knobs.n_meds)), n_labs: stats(rows.map(r => r.knobs.n_labs)),
    latent_q: stats(rows.map(r => r.knobs.latent_q)),
  };
  return {
    ...meta, n: rows.length, feature_len: FEATURE_LEN,
    tier_histogram: tierHist, tier_share: tierShare,
    tier_floor_ok: Object.values(tierShare).every(s => s >= 0.08 && s <= 0.40) && Object.keys(tierHist).length === 5,
    dimension_stats: dimStats, composite_stats: stats(rows.map(r => r.composite)), composite_histogram_5pt: compHist,
    duplicate_feature_vectors: dupFeatures, duplicate_texts: dupText, flag_counts: flagCounts,
    dimension_correlation: corrMatrix, knob_distributions: knobDist,
  };
}

// ─── Features spec markdown ───────────────────────────────────────────────────
export function featuresSpecMarkdown(): string {
  const rowsMd = FEATURE_SPEC.map(f => `| ${f.index} | \`${f.name}\` | ${f.meaning} | ${f.range} | ${f.engine_ref} |`).join("\n");
  return `# DTI teacher: feature vector specification

Fixed length: **${FEATURE_LEN}** floats per record (\`features\` in \`dti_teacher.jsonl\`).
Encoded from \`ExtractedFields\` (what \`extractFields\` returns) plus the \`ScoringContext\`
(\`elementScores\`, \`sourceConsent\`, \`consentScope\`). Nothing from the label side
(dimension scores, composite, tier, flags, notes) enters the vector. The generator knobs are
stored as the structured truth but are NOT in the vector unless the engine reads them through
an extracted field. Clock frozen at ${FROZEN_CLOCK_ISO} for every day count.
Line refs are to /Users/jas/Projects/st-homepage-refresh/src/lib/pipeline.ts at the SHA in MANIFEST.md.

| idx | name | meaning | range | pipeline.ts |
|---|---|---|---|---|
${rowsMd}

## Engine inputs deliberately excluded (not read by the scorer)

- \`fields.sex\`, \`fields.pageCount\`, \`fields.characterCount\`, \`fields.medications[]\` names,
  \`fields.providers[]\` names, \`fields.patientName\` string value: extracted but never read by
  \`scoreDTI\` (only presence/counts are read).
- \`fields.careGapCount\` / the \`care gaps\` data type: read into \`dataTypes\` (:321) but no condition
  profile expects it (:110-155), so it cannot move any dimension. Kept as a present_ one-hot for
  completeness; it carries no label signal.
- \`fields.detectedConditionProfile\` string: fully determined by \`expectedDataTypes\`, which is encoded.

## Engine inputs that are NOT representable in this vector, and why

1. **\`customWeights\`**: not varied in this dataset (every record uses the default 25/20/15/10/10/10/5/5,
   :418-428). Adding weight features would be constant columns.
2. **Exact date pool composition**: the engine only reads \`mostRecentDate\` and \`oldestDate\` (:282-283),
   both encoded; intermediate dates are irrelevant to the score.
3. **Per-element recency in full**: the engine blends 0.6*mean ratio + 0.4*worst ratio over dated elements
   (:582-591). We give the mean and worst ratio (log1p), which is sufficient for that blend, but the
   element field names themselves (which pick the modality window at :390-398) are not encoded beyond
   their effect on the ratio.
4. **Per-source consent identity**: the engine reads only the multiset of levels (\`hasNone\`,
   \`hasExplicit\`, \`allInherited\`, :493-500) and scopes (:506-518); counts per level are sufficient.
5. **Consent date string format**: \`new Date(fields.consentDate)\` parsing (:484) is deterministic for the
   formats we emit; an unparseable string would read as 999 days (encoded as log1p(999)).
6. **Regex idiosyncrasies of the extractor**: the vector starts at the extracted fields, so text-level
   quirks (a lab value in mg/dL counted as a medication at :202, "patient <word> <word>" read as a
   name at :173, the consent date entering the recency date pool at :270) are already applied. The fly
   learns the scorer, not the regex layer. This is stated in the paper as the scope of the DTI task.
`;
}

// ─── CLI ──────────────────────────────────────────────────────────────────────
function arg(name: string, dflt: string): string { const i = process.argv.indexOf(`--${name}`); return i >= 0 ? process.argv[i + 1] : dflt; }
function main() {
  const seed = parseInt(arg("seed", "20260920"), 10);
  const n = parseInt(arg("n", "20000"), 10);
  const start = parseInt(arg("start", "0"), 10);
  const outDir = arg("out", "/tmp/connectome-paper/teachers");
  const rowsOnly = arg("rows-only", "");
  const t0 = Date.now(); const wall0 = process.hrtime.bigint();
  const rows: Row[] = [];
  for (let i = start; i < start + n; i++) rows.push(makeRow(seed, i));
  const lines = rows.map(r => JSON.stringify(r)).join("\n") + "\n";
  if (rowsOnly) { fs.writeFileSync(rowsOnly, lines); console.log(`wrote ${rows.length} rows -> ${rowsOnly}`); return; }
  const runtime_s = Number(process.hrtime.bigint() - wall0) / 1e9;
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "dti_teacher.jsonl"), lines);
  const summary = summarize(rows, {
    generator: "gen_dti.ts", seed, start, frozen_clock: FROZEN_CLOCK_ISO, frozen_clock_ms: t0,
    engine: "/Users/jas/Projects/st-homepage-refresh/src/lib/pipeline.ts", runtime_seconds: +runtime_s.toFixed(2),
    node: process.version,
  });
  fs.writeFileSync(path.join(outDir, "dti_teacher_summary.json"), JSON.stringify(summary, null, 2));
  fs.writeFileSync(path.join(outDir, "dti_features_spec.md"), featuresSpecMarkdown());
  console.log(JSON.stringify({ n: summary.n, tier_share: summary.tier_share, tier_floor_ok: summary.tier_floor_ok, composite: summary.composite_stats, dup_features: summary.duplicate_feature_vectors, runtime_s: summary.runtime_seconds }, null, 1));
}
main();

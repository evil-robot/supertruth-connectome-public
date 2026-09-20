# DTI teacher: feature vector specification

Fixed length: **65** floats per record (`features` in `dti_teacher.jsonl`).
Encoded from `ExtractedFields` (what `extractFields` returns) plus the `ScoringContext`
(`elementScores`, `sourceConsent`, `consentScope`). Nothing from the label side
(dimension scores, composite, tier, flags, notes) enters the vector. The generator knobs are
stored as the structured truth but are NOT in the vector unless the engine reads them through
an extracted field. Clock frozen at 2026-09-20T00:00:00.000Z for every day count.
Line refs are to /Users/jas/Projects/st-homepage-refresh/src/lib/pipeline.ts at the SHA in MANIFEST.md.

| idx | name | meaning | range | pipeline.ts |
|---|---|---|---|---|
| 0 | `source_null` | one-hot: fields.sourceSystem class = null | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 1 | `source_recap` | one-hot: fields.sourceSystem class = recap | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 2 | `source_labcorp` | one-hot: fields.sourceSystem class = labcorp | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 3 | `source_quest` | one-hot: fields.sourceSystem class = quest | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 4 | `source_epic` | one-hot: fields.sourceSystem class = epic | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 5 | `source_cerner` | one-hot: fields.sourceSystem class = cerner | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 6 | `source_other_named` | one-hot: fields.sourceSystem class = other_named | {0,1} | pipeline.ts :306-314, :432, :446-448 |
| 7 | `is_recap` | fields.isRecapFormat | {0,1} | :168, :434, :691 |
| 8 | `facility_count` | min(fields.facilityCount, 5) | 0..5 int | :246-247, :437-439 |
| 9 | `npis_found` | min(fields.npisFound, 6) | 0..6 int | :232-233, :441-443, :675, :702 |
| 10 | `provider_count` | min(fields.providerCount, 8) | 0..8 int | :236-243, :444-445 |
| 11 | `name_present` | fields.patientName != null | {0,1} | :171-174, :617, :317 |
| 12 | `dob_present` | fields.dob != null | {0,1} | :177-178, :618, :317 |
| 13 | `mbi_present` | fields.mbi != null | {0,1} | :181-184, :619, :701 |
| 14 | `log1p_medication_count` | log1p(fields.medicationCount) | 0..~4.1 | :202-204, :620, :676 |
| 15 | `log1p_diagnosis_count` | log1p(fields.diagnosisCount) | 0..~3 | :207-229, :621, :694 |
| 16 | `icd_coded_count` | count of fields.diagnoses entries matching ^[A-Z]\d{2}, capped 8 | 0..8 int | :207-208, :704-706 |
| 17 | `log1p_lab_count` | log1p(fields.labCount) | 0..~3 | :250, :622, :319 |
| 18 | `consent_found` | fields.consentFound | {0,1} | :256-264, :483 |
| 19 | `consent_date_present` | fields.consentDate != null | {0,1} | :265-266, :484 |
| 20 | `log1p_consent_age_days` | log1p(daysSince(consentDate)) at the frozen clock; 0 if none | 0..~7.4 | :484-489 |
| 21 | `most_recent_present` | fields.mostRecentDate != null | {0,1} | :282-283, :543 |
| 22 | `log1p_days_since_most_recent` | log1p(daysSince(mostRecentDate)); log1p(999) if none | 0..~7.6 | :370-373, :543-548 |
| 23 | `log1p_date_span_months` | log1p(months between oldest and most recent date) | 0..~4.2 | :752-758 |
| 24 | `has_conflict` | fields.hasConflict | {0,1} | :286-304, :623, :655-657, :673-675 |
| 25 | `present_demographics` | one-hot: 'demographics' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 26 | `present_medications` | one-hot: 'medications' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 27 | `present_diagnoses` | one-hot: 'diagnoses' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 28 | `present_labs` | one-hot: 'labs' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 29 | `present_care_gaps` | one-hot: 'care gaps' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 30 | `present_vitals` | one-hot: 'vitals' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 31 | `present_SDOH` | one-hot: 'SDOH' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 32 | `present_allergies` | one-hot: 'allergies' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 33 | `present_imaging` | one-hot: 'imaging' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 34 | `present_procedures` | one-hot: 'procedures' in fields.dataTypes | {0,1} | :316-326, :738-741 |
| 35 | `expected_diagnoses` | one-hot: 'diagnoses' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 36 | `expected_medications` | one-hot: 'medications' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 37 | `expected_labs` | one-hot: 'labs' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 38 | `expected_vitals` | one-hot: 'vitals' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 39 | `expected_imaging` | one-hot: 'imaging' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 40 | `expected_procedures` | one-hot: 'procedures' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 41 | `expected_demographics` | one-hot: 'demographics' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 42 | `expected_allergies` | one-hot: 'allergies' in fields.expectedDataTypes | {0,1} | :110-155, :738-741 |
| 43 | `window_30d` | one-hot: fields.primaryRecencyWindowDays == 30 | {0,1} | :104-111, :544 |
| 44 | `window_60d` | one-hot: fields.primaryRecencyWindowDays == 60 | {0,1} | :104-111, :544 |
| 45 | `window_90d` | one-hot: fields.primaryRecencyWindowDays == 90 | {0,1} | :104-111, :544 |
| 46 | `window_180d` | one-hot: fields.primaryRecencyWindowDays == 180 | {0,1} | :104-111, :544 |
| 47 | `log1p_n_elements` | log1p(len(elementScores)) | 0..~3.4 | :452, :578, :652 |
| 48 | `avg_corroboration` | mean corroborationCount over elementScores; 0 if none | 0..4 | :654 |
| 49 | `typed_source_share` | share of elements with sourceType | 0..1 | :452 |
| 50 | `avg_source_trust` | mean SOURCE_TYPE_TRUST over typed elements; 0.75 (neutral) if none | 0.4..1.0 | :403-411, :455-459 |
| 51 | `dated_element_share` | share of elements with collectedAt and field | 0..1 | :578-582 |
| 52 | `log1p_element_avg_ratio` | log1p(mean daysSince(collectedAt)/getModalityWindow(field)) over dated elements; 0 if none | 0..~5 | :582-591 |
| 53 | `log1p_element_worst_ratio` | log1p(max ratio) over dated elements; 0 if none | 0..~5 | :589-591 |
| 54 | `source_consent_n` | number of sourceConsent entries | 0..3 | :492 |
| 55 | `source_consent_explicit` | count of sourceConsent values == explicit | 0..3 int | :493-500 |
| 56 | `source_consent_inherited` | count of sourceConsent values == inherited | 0..3 int | :493-500 |
| 57 | `source_consent_implicit` | count of sourceConsent values == implicit | 0..3 int | :493-500 |
| 58 | `source_consent_none` | count of sourceConsent values == none | 0..3 int | :493-500 |
| 59 | `consent_scope_n` | number of consentScope entries | 0..3 | :505 |
| 60 | `consent_scope_treatment_only` | count of consentScope values == treatment_only | 0..3 int | :506-518 |
| 61 | `consent_scope_care_coordination` | count of consentScope values == care_coordination | 0..3 int | :506-518 |
| 62 | `consent_scope_research_eligible` | count of consentScope values == research_eligible | 0..3 int | :506-518 |
| 63 | `consent_scope_commercial_eligible` | count of consentScope values == commercial_eligible | 0..3 int | :506-518 |
| 64 | `consent_scope_unknown` | count of consentScope values == unknown | 0..3 int | :506-518 |

## Engine inputs deliberately excluded (not read by the scorer)

- `fields.sex`, `fields.pageCount`, `fields.characterCount`, `fields.medications[]` names,
  `fields.providers[]` names, `fields.patientName` string value: extracted but never read by
  `scoreDTI` (only presence/counts are read).
- `fields.careGapCount` / the `care gaps` data type: read into `dataTypes` (:321) but no condition
  profile expects it (:110-155), so it cannot move any dimension. Kept as a present_ one-hot for
  completeness; it carries no label signal.
- `fields.detectedConditionProfile` string: fully determined by `expectedDataTypes`, which is encoded.

## Engine inputs that are NOT representable in this vector, and why

1. **`customWeights`**: not varied in this dataset (every record uses the default 25/20/15/10/10/10/5/5,
   :418-428). Adding weight features would be constant columns.
2. **Exact date pool composition**: the engine only reads `mostRecentDate` and `oldestDate` (:282-283),
   both encoded; intermediate dates are irrelevant to the score.
3. **Per-element recency in full**: the engine blends 0.6*mean ratio + 0.4*worst ratio over dated elements
   (:582-591). We give the mean and worst ratio (log1p), which is sufficient for that blend, but the
   element field names themselves (which pick the modality window at :390-398) are not encoded beyond
   their effect on the ratio.
4. **Per-source consent identity**: the engine reads only the multiset of levels (`hasNone`,
   `hasExplicit`, `allInherited`, :493-500) and scopes (:506-518); counts per level are sufficient.
5. **Consent date string format**: `new Date(fields.consentDate)` parsing (:484) is deterministic for the
   formats we emit; an unparseable string would read as 999 days (encoded as log1p(999)).
6. **Regex idiosyncrasies of the extractor**: the vector starts at the extracted fields, so text-level
   quirks (a lab value in mg/dL counted as a medication at :202, "patient <word> <word>" read as a
   name at :173, the consent date entering the recency date pool at :270) are already applied. The fly
   learns the scorer, not the regex layer. This is stated in the paper as the scope of the DTI task.

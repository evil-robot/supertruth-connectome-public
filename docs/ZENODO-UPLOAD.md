# Zenodo upload steps (JAS; no token on file)

Order matters: the dataset first (its DOI goes into the paper), then the paper.

## 1. Dataset record
- zenodo.org → New upload → Upload type: Dataset.
- Files (from `dataset/`): dti_records.jsonl.gz, dti_labels.jsonl.gz, bii_windows.jsonl.gz, dti_weights_seed1.tar.gz,
  splits.json, README.md, MANIFEST.json (about 136 MB total).
- Metadata: copy from `dataset/zenodo-dataset.json` (title, creator Snyder with ORCID 0009-0001-6157-8100, license
  CC BY 4.0, keywords, notes with the withheld-labels statement, related identifier "cites" 10.5281/zenodo.19601616).
  Leave the paper relation for later (it needs the paper DOI) or add it from the paper side.
- Reserve the DOI (Zenodo shows it before publishing) → send it to me. I run:
  `uv run --project ~/Projects/ds-lab python scripts/splice_paper.py --dataset-doi <DOI>` then `cd paper && ./build.sh`,
  re-run `.venv/bin/python scripts/package_dataset.py --verify-weights` so MANIFEST/README carry the DOI, and hand back
  the final PDF + any refreshed dataset files. Publish the dataset record.

## 2. Paper record
- New upload → Publication → Working paper. File: `paper/paper.pdf` (the DOI-bearing build).
- Metadata from `paper/zenodo.json`: title, creator (ORCID), CC BY 4.0, publisher SuperTruth, version 1.0, keywords,
  description (the abstract), related identifiers: cites 10.5281/zenodo.19601616; cites 10.1016/j.cell.2026.08.015;
  isDerivedFrom https://male-cns.janelia.org/; isSupplementedBy https://github.com/evil-robot/supertruth-connectome-public
  and isSupplementedBy <DATASET DOI>.
- Publish → send me the paper DOI. I fill CONNECTOME_DOI on the site, the release, the dataset record's "isSupplementTo"
  (edit the dataset record's metadata; Zenodo allows metadata edits without a new version), and flip the public repo.

## 3. After both DOIs
docs/LAUNCH-CHECKLIST.md "publish-day sequence" steps 4 to 8.

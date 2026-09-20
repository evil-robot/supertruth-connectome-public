#!/bin/zsh
# Clean public export of the code: HEAD minus the BII scorer inputs (held until BII is published) and minus large data.
# Usage: scripts/export_public.sh /path/to/public-checkout
set -euo pipefail
dest="${1:?dest}"; src="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$dest"; tmp="$(mktemp -d)"
git -C "$src" archive --format=tar HEAD | tar -x -C "$tmp"
rm -f "$tmp/teachers/bii_features_spec.md" "$tmp/teachers/gen_bii.py" "$tmp/teachers/quirks_bii.json" "$tmp/teachers/bii_teacher_summary.json"
rm -rf "$tmp/llm_arm/llm_runs"   # substantiation files stay in the private working repo (kept for the FTC lookback)
rsync -a --delete --exclude .git "$tmp/" "$dest/"
rm -rf "$tmp"
cat >> "$dest/README.md" <<'NOTE'

**About this public copy.** This is a clean export of the working repository at the commit named in `dataset/MANIFEST.json`.
Held back from the export: the Behavioral Integrity Index feature specification and window generator (unpublished work) and
the raw language-model call logs (kept privately as the substantiation record). Everything else is here.
NOTE
echo "exported to $dest"

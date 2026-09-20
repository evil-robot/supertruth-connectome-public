#!/bin/zsh
# Pre-registered PILOT (PROTOCOL.md 8.3): seeds {1,2} x arms {connectome, shuffle, er, mlp, ridge} x tasks {dti, bii}.
# Sequential. Restartable: a run with metrics.json is skipped.
#   nohup zsh scripts/run_pilot.sh > runs/pilot.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
STATUS=runs/pilot_status.json
T0=$(date +%s)
SEEDS=(1 2); TASKS=(dti bii); ARMS=(connectome shuffle er mlp ridge)
TOTAL=$(( ${#SEEDS} * ${#TASKS} * ${#ARMS} ))
done_n=0; failed=()
write_status() {
  $PY - "$1" "$2" "$3" <<'PYEOF'
import json, sys, time
from pathlib import Path
status_path, last, done_n = sys.argv[1], sys.argv[2], int(sys.argv[3])
p = Path(status_path)
doc = json.loads(p.read_text()) if p.exists() else {"runs": []}
t0 = doc.get("t0") or time.time()
doc.update({"t0": t0, "elapsed_seconds": time.time() - t0, "completed": done_n, "last": last,
            "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
p.write_text(json.dumps(doc, indent=2) + "\n")
PYEOF
}
$PY - "$STATUS" "$TOTAL" <<'PYEOF'
import json, sys, time
json.dump({"t0": time.time(), "total": int(sys.argv[2]), "completed": 0, "runs": [], "failed": []}, open(sys.argv[1], "w"), indent=2)
PYEOF
for S in $SEEDS; do for TASK in $TASKS; do for ARM in $ARMS; do
  OUT=runs/$TASK/$ARM/seed$S
  if [[ -f $OUT/metrics.json ]]; then echo "skip $TASK/$ARM/seed$S (done)"; done_n=$((done_n+1)); continue; fi
  echo "=== [$(date -u +%FT%TZ)] START $TASK/$ARM/seed$S ==="
  t1=$(date +%s)
  if $PY scripts/run_arm.py --task $TASK --arm $ARM --seed $S; then rc=0; else rc=$?; fi
  t2=$(date +%s)
  if [[ $rc -eq 0 ]]; then done_n=$((done_n+1)); else failed+=("$TASK/$ARM/seed$S"); fi
  echo "=== [$(date -u +%FT%TZ)] END $TASK/$ARM/seed$S rc=$rc in $((t2-t1)) s; total elapsed $((t2-T0)) s ==="
  $PY - "$STATUS" "$TASK/$ARM/seed$S" "$rc" "$((t2-t1))" "$done_n" <<'PYEOF'
import json, sys, time
p, name, rc, secs, done_n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
doc = json.load(open(p))
doc["runs"].append({"run": name, "rc": rc, "seconds": secs, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
if rc: doc["failed"].append(name)
doc.update({"completed": done_n, "elapsed_seconds": time.time() - doc["t0"], "last": name,
            "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
json.dump(doc, open(p, "w"), indent=2)
PYEOF
done; done; done
echo "PILOT DONE: $done_n/$TOTAL ok; failed: ${failed[*]:-none}; $(( $(date +%s) - T0 )) s"

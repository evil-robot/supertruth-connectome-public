#!/bin/zsh
# Notify on the Mac when seeds 3 to 5 finish or a run fails. Polls every 5 minutes for up to 36 hours.
cd "$(dirname "$0")/.."
for i in {1..432}; do
  if grep -q "PILOT DONE" runs/pilot2.log 2>/dev/null; then
    osascript -e 'display notification "Seeds 3 to 5 finished. Check runs/pilot2.log." with title "Connectome pilot" sound name "Glass"'; exit 0; fi
  if grep -q "rc=[1-9]" runs/pilot2.log 2>/dev/null; then
    osascript -e 'display notification "A run FAILED. Check runs/pilot2.log." with title "Connectome pilot" sound name "Basso"'; exit 1; fi
  if ! pgrep -f run_seeds3to5.sh >/dev/null; then
    osascript -e 'display notification "The pilot process is no longer running and did not finish. Restart it." with title "Connectome pilot" sound name "Basso"'; exit 2; fi
  sleep 300
done

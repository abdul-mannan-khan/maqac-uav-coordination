#!/bin/bash
# Laptop-side monitor for the Vast AirSim re-fly (6 Nov 2026). Every 20 min: copy /work/maqac/runs from the box to
# results/airsim/refly_campaign/runs/. Stall rule: /work/driver.log unchanged for 90 min -> final pull, destroy box.
# Done: 'campaign finished' in driver.log -> final pull, check, destroy box. Log: cloud/vast_airsim/monitor.log
cd ~/kfupm_ws/maqac-vehcom
ID=$(cat cloud/vast_airsim/instance.txt); S=$(cat cloud/vast_airsim/ssh.txt); L=cloud/vast_airsim/monitor.log
D=results/airsim/refly_campaign; mkdir -p $D/runs
say() { echo "$(date -u +%F_%T) $*" >> $L; }
pull() { timeout 900 $S 'cd /work/maqac && tar czf - runs 2>/dev/null; true' 2>/dev/null > $D/.pull.tgz || true
         timeout 900 $S 'cat /work/driver.log' > $D/driver.log 2>/dev/null
         [ -s $D/.pull.tgz ] && tar -C $D -xzf $D/.pull.tgz 2>/dev/null; rm -f $D/.pull.tgz
         say "pulled: $(ls $D/runs/*/result.json 2>/dev/null | wc -l) results"; }
destroy() { vastai destroy instance $ID -y >> $L 2>&1; say "destroyed $ID ($1)"; kill $(cat cloud/vast_airsim/hardstop.pid) 2>/dev/null; }
while true; do
  sleep 1200
  pull
  if grep -q "campaign finished\|giving up" $D/driver.log 2>/dev/null; then pull; destroy "$(tail -1 $D/driver.log)"; exit 0; fi
  age=$(timeout 60 $S 'echo $(( $(date +%s) - $(stat -c %Y /work/driver.log) ))' 2>/dev/null)
  [ -z "$age" ] && { say "box unreachable"; continue; }
  if [ "$age" -gt 5400 ]; then say "driver log idle ${age}s: stall"; pull; destroy stall; exit 1; fi
done

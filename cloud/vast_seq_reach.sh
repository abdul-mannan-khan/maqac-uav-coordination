#!/bin/bash
# MAQAC-S hand-over reach measurement (scripts/measure_seq_reach.py) on one Vast CPU box; 10 Nov 2026.
# Copies code only (no data/), runs, pulls results with md5 check, destroys the box. Hard stop 2 h.
set -u
OFFER=$1
cd ~/kfupm_ws/maqac-vehcom
LABEL="maqac-seq-reach"; LOG=cloud/vast_seq_reach.log; export LC_ALL=C
say() { echo "$(date '+%d %H:%M') $*" >> $LOG; }
ID=$(vastai create instance $OFFER --image python:3.11-slim --disk 20 --ssh --direct --label $LABEL --onstart-cmd \
  'apt-get update -qq && apt-get install -y -qq openssh-server openssh-client rsync tmux >/dev/null; mkdir -p /run/sshd; /usr/sbin/sshd; (for k in $(seq 1 60); do sed -i "/tmux/d" /root/.bashrc 2>/dev/null; sleep 10; done) & pip install -q numpy scipy && touch /root/READY' \
  --raw 2>&1 | tee -a cloud/vast_seq_reach_create.txt | grep -o '"new_contract": *[0-9]*' | grep -o '[0-9]*$')
if [ -z "$ID" ]; then sleep 30
  for x in $(vastai show instances --raw 2>/dev/null | python3 -c "import json,sys;[print(d['id']) for d in json.load(sys.stdin) if d.get('label')=='$LABEL']"); do
    vastai destroy instance $x -y >> $LOG 2>&1; say "destroyed stray $x"; done
  say "create failed"; exit 1; fi
echo $ID > cloud/vast_seq_reach.id; say "created $ID on offer $OFFER"
T0=$(date +%s); S=""
destroy() { vastai destroy instance $ID -y >> $LOG 2>&1; say "destroyed $ID ($1)"; sleep 15; vastai show instances --raw 2>/dev/null | python3 -c "import json,sys;print('still listed:',[d['id'] for d in json.load(sys.stdin) if d['id']==$ID])" >> $LOG; }
for t in $(seq 1 90); do
  read st ip port < <(vastai show instance $ID --raw 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('actual_status'),d.get('public_ipaddr'),((d.get('ports') or {}).get('22/tcp') or [{}])[0].get('HostPort'))" 2>/dev/null)
  if [ "$st" = running ] && [ -n "$port" ] && [ "$port" != None ]; then
    S="ssh -p $port -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR root@$ip"
    $S 'test -f /root/READY' 2>/dev/null && break; fi
  sleep 20; done
$S 'test -f /root/READY' 2>/dev/null || { say "never ready (status $st ip $ip port $port)"; vastai logs $ID --tail 40 >> $LOG 2>&1; destroy "not ready"; exit 1; }
say "ready $ip:$port, $($S nproc) cores"
$S 'mkdir -p /root/m/results /root/m/scripts'
tar --exclude=__pycache__ -cf - src/netsim scripts/measure_seq_reach.py | $S 'cd /root/m && tar xf -'
L=$(find src/netsim -name '*.py' | sort | xargs md5sum | md5sum); R=$($S 'cd /root/m && find src/netsim -name "*.py" | sort | xargs md5sum | md5sum')
[ "$L" = "$R" ] || { say "md5 mismatch"; destroy md5; exit 1; }
$S 'cd /root/m && find . -name "*.npz" | grep -q .' && { say "npz on box"; destroy npz; exit 1; }
$S "cd /root/m && OMP_NUM_THREADS=1 timeout 6000 python3 scripts/measure_seq_reach.py \$(nproc) > results/seq_reach.log 2>&1; echo \$? > results/EXIT"
say "run ended, exit $($S 'cat /root/m/results/EXIT')"
for k in 1 2 3; do
  RM=$($S 'cd /root/m && tar cf /root/r.tar results && md5sum /root/r.tar' | awk '{print $1}')
  $S 'cat /root/r.tar' > cloud/seq_reach_results.tar; LM=$(md5sum cloud/seq_reach_results.tar | awk '{print $1}')
  [ -n "$RM" ] && [ "$RM" = "$LM" ] && { tar xf cloud/seq_reach_results.tar -C . && say "pulled, md5 ok"; break; }
  sleep 20; done
destroy "done after $(( ($(date +%s)-T0)/60 )) min"
say finished

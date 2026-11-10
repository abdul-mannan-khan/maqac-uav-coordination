#!/bin/bash
# Fig. 7(a) in print colours on one Vast CPU box (laptop is for HIL only). ~$0.02; 1 h hard stop; destroys itself.
# Usage: cloud/vast_snapfig.sh <offer_id>
set -u
OFFER=$1; cd ~/kfupm_ws/maqac-vehcom; LOG=cloud/vast_snapfig.log; LABEL=maqac-snapfig
say() { echo "$(date +%H:%M:%S) $*" >> $LOG; }
ID=$(vastai create instance $OFFER --image python:3.11-slim --disk 10 --ssh --direct --label $LABEL --onstart-cmd \
  'apt-get update -qq && apt-get install -y -qq openssh-server rsync >/dev/null; mkdir -p /run/sshd; /usr/sbin/sshd; (for k in $(seq 1 60); do sed -i "/tmux/d" /root/.bashrc 2>/dev/null; sleep 10; done) & pip install -q numpy scipy matplotlib pillow; touch /root/READY' \
  --raw 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['new_contract'] if d.get('success') else '')" 2>/dev/null)
if [ -z "$ID" ]; then sleep 30
  for x in $(vastai show instances --raw 2>/dev/null | python3 -c "import json,sys;[print(d['id']) for d in json.load(sys.stdin) if d.get('label')=='$LABEL']"); do vastai destroy instance $x -y >> $LOG 2>&1; say "destroyed stray $x"; done
  say "create failed"; exit 1; fi
say "created $ID"
( sleep 3600; vastai destroy instance $ID -y >> $LOG 2>&1; echo "$(date +%H:%M) 1 h hard stop" >> $LOG ) & HARD=$!
for t in $(seq 1 60); do
  read st ip port < <(vastai show instance $ID --raw 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('actual_status'),d.get('public_ipaddr'),((d.get('ports') or {}).get('22/tcp') or [{}])[0].get('HostPort'))" 2>/dev/null)
  if [ "$st" = running ] && [ -n "$port" ] && [ "$port" != None ]; then
    S="ssh -p $port -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR root@$ip"
    $S 'test -f /root/READY' 2>/dev/null && break; fi; sleep 20; done
$S 'test -f /root/READY' 2>/dev/null || { say "never ready"; vastai destroy instance $ID -y >> $LOG 2>&1; kill $HARD; exit 1; }
tar --exclude=__pycache__ -cf - src/netsim scripts/make_comparison_video.py scripts/make_snapshot_figures.py results/demo/mappo_6_s0_actor.npz | $S 'mkdir -p /root/m/paper/figures && cd /root/m && tar xf -'
say "running"
$S 'cd /root/m && python3 scripts/make_snapshot_figures.py comparison > run.log 2>&1; echo EXIT $? >> run.log'
$S 'cat /root/m/run.log' >> $LOG
$S 'cat /root/m/paper/figures/snap_comparison_c.png' > paper/figures/snap_comparison_c.png.tmp && [ -s paper/figures/snap_comparison_c.png.tmp ] && mv paper/figures/snap_comparison_c.png.tmp paper/figures/snap_comparison_c.png && say "copied"
vastai destroy instance $ID -y >> $LOG 2>&1; say "destroyed $ID"; kill $HARD 2>/dev/null

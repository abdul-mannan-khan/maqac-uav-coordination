#!/bin/bash
# Rent one Vast GPU box for the AirSim-under-Wine re-fly (6 Nov 2026). Usage: rent_box.sh <offer> <hard_stop_hours>
# Writes the instance id to cloud/vast_airsim/instance.txt, ssh command to cloud/vast_airsim/ssh.txt. Hard stop: a laptop
# process destroys the box after <hours> (its PID in cloud/vast_airsim/hardstop.pid).
set -u
cd ~/kfupm_ws/maqac-vehcom
OFFER=$1; H=$2; LABEL=maqac-airsim-wine; LOG=cloud/vast_airsim/rent.log
say() { echo "$(date -u +%F_%T) $*" >> $LOG; }
ID=$(vastai create instance $OFFER --image nvidia/cuda:12.2.2-base-ubuntu22.04 --disk 80 --ssh --direct --label $LABEL \
  --env '-e NVIDIA_DRIVER_CAPABILITIES=all -e NVIDIA_VISIBLE_DEVICES=all' \
  --onstart-cmd 'apt-get update -qq && apt-get install -y -qq openssh-server rsync >/dev/null; mkdir -p /run/sshd; /usr/sbin/sshd; touch /root/READY' \
  --raw 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['new_contract'] if d.get('success') else '')" 2>/dev/null)
if [ -z "$ID" ]; then sleep 30
  for x in $(vastai show instances --raw 2>/dev/null | python3 -c "import json,sys;[print(d['id']) for d in json.load(sys.stdin) if d.get('label')=='$LABEL']"); do
    vastai destroy instance $x -y >> $LOG 2>&1; say "destroyed stray $x"; done
  say "create failed for $OFFER"; exit 1; fi
echo $ID > cloud/vast_airsim/instance.txt; say "created $ID on offer $OFFER, hard stop ${H} h"
nohup bash -c "sleep $((H*3600)); vastai destroy instance $ID -y; echo \"\$(date -u +%F_%T) hard stop destroyed $ID\" >> $LOG" >/dev/null 2>&1 &
echo $! > cloud/vast_airsim/hardstop.pid
for t in $(seq 1 60); do
  read st ip port < <(vastai show instance $ID --raw 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('actual_status'),d.get('public_ipaddr'),((d.get('ports') or {}).get('22/tcp') or [{}])[0].get('HostPort'))" 2>/dev/null)
  if [ "$st" = running ] && [ -n "$port" ] && [ "$port" != None ]; then
    S="ssh -p $port -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR -o ServerAliveInterval=30 root@$ip"
    $S 'test -f /root/READY' 2>/dev/null && { echo "$S" > cloud/vast_airsim/ssh.txt; say "ready $ip:$port"; exit 0; }
  fi; sleep 20; done
say "box never ready (status $st)"; vastai destroy instance $ID -y >> $LOG 2>&1; kill $(cat cloud/vast_airsim/hardstop.pid); exit 1

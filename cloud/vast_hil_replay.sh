#!/bin/bash
# HIL-in-AirSim replay video on one Vast GPU box.
# Prebuilt image abdulmannan617/airsim-city-wine (AirSim 1.8.1 CityEnviron under Wine). Copies only the replay script,
# one HIL run's logs and the AirSim survey height map (no restricted city files). Tries offers in turn; every box is
# destroyed after its attempt; 3 h hard stop per box. Usage: cloud/vast_hil_replay.sh <offer> [<offer> ...]
set -u
cd ~/kfupm_ws/maqac-vehcom
RUN=results/hil_airsim_city/maqac_seq_s20000; HM=results/airsim/v3_campaign/survey/heightmap.npz
LABEL=maqac-hil-replay; LOG=cloud/vast_hil_replay.log; OUT=results/hil_video; mkdir -p $OUT
say() { echo "$(date '+%d %H:%M') $*" >> $LOG; }
attempt() {
  local OFFER=$1 ID S st ip port
  ID=$(vastai create instance $OFFER --image abdulmannan617/airsim-city-wine:1.8.1-wine11-dxvk3.1.1 --disk 60 --ssh --direct --label $LABEL \
    --env '-e NVIDIA_DRIVER_CAPABILITIES=all -e NVIDIA_VISIBLE_DEVICES=all' \
    --onstart-cmd 'ssh-keygen -A; mkdir -p /run/sshd; /usr/sbin/sshd; touch /root/READY' --raw 2>&1 \
    | tee -a cloud/vast_hil_replay_create.txt | grep -o '"new_contract": *[0-9]*' | grep -o '[0-9]*$')
  if [ -z "$ID" ]; then sleep 20
    for x in $(vastai show instances --raw 2>/dev/null | python3 -c "import json,sys;[print(d['id']) for d in json.load(sys.stdin) if d.get('label')=='$LABEL']"); do
      vastai destroy instance $x -y >> $LOG 2>&1; say "destroyed stray $x"; done
    say "create failed on $OFFER"; return 1; fi
  echo $ID > cloud/vast_hil_replay.id; say "created $ID on offer $OFFER"
  ( sleep 10800; vastai destroy instance $ID -y >/dev/null 2>&1; echo "$(date '+%d %H:%M') hard stop destroyed $ID" >> $LOG ) & local HARD=$!
  for t in $(seq 1 90); do
    read st ip port < <(vastai show instance $ID --raw 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('actual_status'),d.get('public_ipaddr'),((d.get('ports') or {}).get('22/tcp') or [{}])[0].get('HostPort'))" 2>/dev/null)
    if [ "$st" = running ] && [ -n "$port" ] && [ "$port" != None ]; then
      S="ssh -p $port -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR -o ServerAliveInterval=30 root@$ip"
      $S 'test -f /root/READY' 2>/dev/null && break; fi
    sleep 20; done
  if ! $S 'test -f /root/READY' 2>/dev/null; then say "never ready (status $st port $port)"; vastai logs $ID --tail 30 >> $LOG 2>&1
    vastai destroy instance $ID -y >> $LOG 2>&1; kill $HARD 2>/dev/null; say "destroyed $ID"; return 1; fi
  say "ready $ip:$port $($S 'nvidia-smi --query-gpu=name,driver_version --format=csv,noheader' 2>/dev/null)"
  $S 'mkdir -p /work/rp/run /work/rp/out'
  tar -cf - sim/hil/replay_hil_airsim.py $RUN/rounds.jsonl $RUN/result.json $HM | $S 'cd /work/rp && tar xf -'
  $S 'cd /work/rp && find . -name "*lidar*" -o -name "*manhattan_nyc*" | grep -q . && echo BAD' | grep -q BAD && { say "restricted file on box"; vastai destroy instance $ID -y >> $LOG 2>&1; kill $HARD; return 1; }
  $S "cd /work/rp && (command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null)); python3 -c 'import matplotlib' 2>/dev/null || pip install -q matplotlib pillow; \
      city-settings --mode simpleflight --n 3 --overview > /work/s.json && python3 -c \"import json;f='/work/s.json';d=json.load(open(f));d['PhysicsEngineName']='ExternalPhysicsEngine';json.dump(d,open(f,'w'),indent=1)\" && city-start /work/s.json > /work/rp/start.log 2>&1; echo START_EXIT \$?" >> $LOG 2>&1
  if [ "${KEEP:-0}" = 1 ]; then echo "$S" > cloud/vast_hil_replay.ssh; say "KEEP: box $ID up, ssh in cloud/vast_hil_replay.ssh (hard stop 3 h)"; return 0; fi
  $S "cd /work/rp && timeout 5400 python3 sim/hil/replay_hil_airsim.py render --run $RUN --hm $HM --out out > render.log 2>&1; echo RENDER_EXIT \$?; tail -3 render.log" >> $LOG 2>&1
  $S "cd /work/rp && timeout 3600 python3 sim/hil/replay_hil_airsim.py compose --run $RUN --hm $HM --out out > compose.log 2>&1; echo COMPOSE_EXIT \$?; tail -3 compose.log" >> $LOG 2>&1
  local ok=1
  for k in 1 2 3; do
    RM=$($S 'md5sum /work/rp/out/hil_airsim_replay.mp4' 2>/dev/null | awk '{print $1}')
    [ -z "$RM" ] && break
    $S 'cat /work/rp/out/hil_airsim_replay.mp4' > $OUT/maqac_hil_airsim_replay.mp4
    [ "$RM" = "$(md5sum $OUT/maqac_hil_airsim_replay.mp4 | awk '{print $1}')" ] && { ok=0; say "pulled video, md5 ok"; break; }
  done
  $S 'cd /work/rp/out && tar cf - airsim/00000.jpg airsim/00600.jpg airsim/01200.jpg 2>/dev/null' | tar xf - -C $OUT 2>/dev/null
  $S 'cat /work/rp/start.log /work/rp/render.log' > cloud/vast_hil_replay_box.log 2>/dev/null
  $S 'city-stop' >/dev/null 2>&1
  vastai destroy instance $ID -y >> $LOG 2>&1; kill $HARD 2>/dev/null; say "destroyed $ID"
  return $ok
}
for OFFER in "$@"; do attempt $OFFER && { say SUCCESS; [ "${KEEP:-0}" = 1 ] && disown -a; exit 0; }; done
say "all offers failed"; exit 1

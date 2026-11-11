#!/bin/bash
# Render the demo, the comparison video and the narrated presentation on one Vast.ai box (user rule 5 Nov 2026: non-HIL
# jobs off the laptop). ~$0.05-0.10; 3 h hard stop. Copies only what the videos need: no data/cities files.
# Usage: cloud/vast_talk.sh <offer_id>
set -u
OFFER=$1
cd ~/kfupm_ws/maqac-vehcom
LOG=cloud/vast_talk.log
export LC_ALL=C
say() { echo "$(date +%H:%M:%S) $*" >> $LOG; }
destroy() { vastai destroy instance $ID -y >> $LOG 2>&1; say "destroyed $ID ($1)"; }
ID=$(vastai create instance $OFFER --image python:3.11-slim --disk 20 --ssh --direct --label maqac-talk --onstart-cmd \
  'apt-get update -qq && apt-get install -y -qq openssh-server openssh-client rsync ffmpeg curl fonts-dejavu-core >/dev/null; mkdir -p /run/sshd; /usr/sbin/sshd; (for k in $(seq 1 60); do sed -i "/tmux/d" /root/.bashrc 2>/dev/null; sleep 10; done) & pip install -q numpy scipy matplotlib playwright piper-tts==1.2.0 && python3 -m playwright install --with-deps chromium >/root/pw.log 2>&1; mkdir -p /root/voices && cd /root/voices && curl -sL -o en_US-lessac-high.onnx https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx && curl -sL -o en_US-lessac-high.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json; touch /root/READY' \
  --raw 2>&1 | grep -o '"new_contract": *[0-9]*' | grep -o '[0-9]*$')
if [ -z "$ID" ]; then sleep 30   # a failed create can still leave an instance (6 Nov 2026)
  for x in $(vastai show instances --raw 2>/dev/null | python3 -c "import json,sys;[print(d['id']) for d in json.load(sys.stdin) if d.get('label')=='maqac-talk']"); do vastai destroy instance $x -y >> $LOG 2>&1; say "destroyed stray $x"; done
  say "create failed for offer $OFFER"; exit 1; fi
say "created $ID on offer $OFFER"
( sleep 10800; vastai destroy instance $ID -y >> $LOG 2>&1; echo "$(date +%H:%M) 3 h hard stop fired" >> $LOG ) &
HARD=$!
S=""
for t in $(seq 1 90); do
  read st ip port < <(vastai show instance $ID --raw 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('actual_status'),d.get('public_ipaddr'),((d.get('ports') or {}).get('22/tcp') or [{}])[0].get('HostPort'))" 2>/dev/null)
  if [ "$st" = running ] && [ "$port" != None ] && [ -n "$port" ]; then
    S="ssh -p $port -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR root@$ip"
    $S 'test -f /root/READY' 2>/dev/null && break
  fi
  sleep 20
done
$S 'test -f /root/READY' 2>/dev/null || { say "box never ready"; destroy "not ready"; kill $HARD; exit 1; }
say "ready $ip:$port"
FILES="src/netsim scripts/make_demo_video.py scripts/make_comparison_video.py scripts/make_presentation_video.py presentation
 sim/airsim/maqac_px4/heightmap.py results/airsim/v3_campaign/survey/heightmap.npz
 results/airsim/refly_campaign/runs/ko_city_n6_maqac_seq_onboard_20000/rounds.jsonl results/hil_airsim_city/maqac_seq_s20000/rounds.jsonl
 results/demo/mappo_6_s0_actor.npz results/demo/mappo_6_s0_actor_v4.npz
 results/hil_video/maqac_hil_airsim_replay.mp4"
tar --exclude=__pycache__ -cf - $FILES | $S 'mkdir -p /root/m && cd /root/m && tar xf -'
$S 'cd /root/m && find . -name "*lidar*" -o -name "*nyc*"' | grep -q . && { say "restricted file on box"; destroy "restricted"; kill $HARD; exit 1; }
$S "cd /root/m && (setsid nohup bash -c 'python3 scripts/make_demo_video.py --out demo && python3 scripts/make_comparison_video.py --out cmp && python3 scripts/make_presentation_video.py --voice-dir /root/voices --out talk --work . ; echo EXIT \$?' > run.log 2>&1 < /dev/null &)"
say "render started"
for t in $(seq 1 150); do
  sleep 40
  $S 'grep -q "^EXIT" /root/m/run.log' 2>/dev/null && break
  $S 'pgrep -f "make_.*_video" >/dev/null' 2>/dev/null || { say "render process gone"; break; }
done
mkdir -p results/talk results/talk/slides
$S 'cat /root/m/run.log' > results/talk/run.log 2>/dev/null
$S 'cd /root/m && tar cf - talk/*.mp4 talk/slides/*.png talk/narration/*_track.wav demo/maqac_demo.mp4 demo/demo_info.json cmp/maqac_comparison.mp4 cmp/comparison_info.json 2>/dev/null' | tar xf - -C results/talk 2>>$LOG
ls -la results/talk/talk results/talk/demo results/talk/cmp >> $LOG 2>&1
if [ -s results/talk/talk/maqac_presentation_narrated.mp4 ]; then say "copied outputs"; destroy "done"; else say "presentation missing, see results/talk/run.log"; destroy "incomplete"; fi
kill $HARD 2>/dev/null
vastai show instances --raw 2>/dev/null | python3 -c "import json,sys; print('still listed:', [i['id'] for i in json.load(sys.stdin) if i['id']==$ID])" >> $LOG

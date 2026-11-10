#!/bin/bash
# Runs ON the Vast box: AirSim 1.8.1 CityEnviron under Wine 11.0 + DXVK (off-screen) and PX4 v1.14.3 SITL on one machine.
# Same per-mission steps as cloud/airsim_driver.sh (GCP): API check / map restart with N vehicles, PX4 stop, scene reset,
# PX4 start, mission with a time limit, up to 3 tries; resumable (skips missions with result.json).
#   bash box_campaign.sh plan1.txt [plan2.txt ...]       log: /work/driver.log
set -u
export WINEPREFIX=/root/wine_city WINEDEBUG=-all DXVK_LOG_LEVEL=none DISPLAY=:99
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json XDG_RUNTIME_DIR=/tmp
CLOCK=${CLOCK:-0.7}; LOG=/work/driver.log; EXE=$(cat /root/city_exe.txt)
M=/work/maqac/sim/airsim/maqac_px4; RUNS=/work/maqac/runs; mkdir -p $RUNS
export PX4_DIR=/opt/PX4-Autopilot RUN=/work/px4_run WIN_IP=127.0.0.1
log() { echo "$(date -u +%F_%T) $*" | tee -a $LOG; }
alive() { timeout 25 python3 -c "import airsim; c=airsim.MultirotorClient(ip='127.0.0.1',timeout_value=15); c.confirmConnection(); c.getMultirotorState(vehicle_name='UAV0')" >/dev/null 2>&1; }
xup() { pgrep -x Xvfb >/dev/null || { Xvfb :99 -screen 0 1280x720x24 >/dev/null 2>&1 & sleep 2; }; }
map_stop() { [ -f /work/map.pgid ] && kill -- -$(cat /work/map.pgid) 2>/dev/null; sleep 3; wineserver -k 2>/dev/null; sleep 3; bash /root/wclean.sh >/dev/null; rm -f /work/map.pgid; }
map_start() {  # N vehicles
  local N=$1; map_stop; xup
  python3 /work/maqac/sim/airsim/make_settings_city.py --n $N --win-ip 127.0.0.1 --px4-ip 127.0.0.1 --clock-speed $CLOCK > /work/settings_$N.json
  setsid wine "$EXE" -dx11 -RenderOffScreen -nosound -nosplash -ResX=640 -ResY=360 -log -settings="Z:\\work\\settings_$N.json" \
     > /work/airsim_$N.log 2>&1 < /dev/null &
  echo $! > /work/map.pgid
  for w in $(seq 1 45); do alive && return 0; sleep 10; done; return 1; }
N_MAP=0; FAILS=0
for PLAN in "$@"; do
  log "plan $PLAN"
  grep -v '^#' "$PLAN" | while read -r NAME N ARGS; do
    [ -z "${NAME:-}" ] && continue
    [ -f $RUNS/$NAME/result.json ] && { log "skip $NAME"; continue; }
    T=$(echo "$ARGS" | grep -o -- '--T [0-9]*' | awk '{print $2}'); LIM=$(python3 -c "print(int(2*${T:-300}/$CLOCK+900))")
    for try in 1 2 3; do
      if [ "$N_MAP" != "$N" ] || ! alive; then
        log "starting map with $N vehicles (clock $CLOCK)"; bash $M/px4_stack.sh stop >/dev/null
        if ! map_start $N; then log "AirSim did not come up"; FAILS=$((FAILS+1)); N_MAP=0
          [ $FAILS -ge 4 ] && { log "4 map failures in a row, giving up"; exit 3; }; continue; fi
        FAILS=0; N_MAP=$N
      fi
      bash $M/px4_stack.sh stop >/dev/null; python3 $M/airsim_reset.py --ip 127.0.0.1 >/dev/null 2>&1 && bash $M/px4_stack.sh start $N > /work/px4_start.log 2>&1 < /dev/null; tail -1 /work/px4_start.log   # no pipe: PX4 children keep it open
      log "$NAME try $try (limit ${LIM}s)"
      rm -rf $RUNS/$NAME; mkdir -p $RUNS/$NAME
      (cd $M && timeout $LIM python3 run_maqac_airsim.py --ip 127.0.0.1 --n $N --free-run --out $RUNS/$NAME $ARGS > $RUNS/$NAME/stdout.log 2>&1)
      if [ -f $RUNS/$NAME/result.json ]; then log "$NAME done"; break; fi
      log "$NAME failed: $(tail -1 $RUNS/$NAME/stdout.log)"; N_MAP=0
    done
  done
  log "plan $PLAN finished"
done
bash $M/px4_stack.sh stop >/dev/null; map_stop
log "campaign finished"

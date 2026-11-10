#!/bin/bash
# MAQAC HIL campaign on the Jetson (~/maqac_hil): parameter backup, HITL set-up, shakedown, the 15 fixed missions,
# restore and read-back. Protocol copied from Paper A (~/paperA_hil_v4h/hil_proposed_v2.sh): back up ALL parameters,
# set, reboot, run, restore the backup, reboot, read back and fix differences, then mark the board idle.
# Start (holds the shared lock for the whole campaign):
#   ONLY through robotq (~/robot_schedule, run maqac-x500-hil), which holds ~/vlm_research/.x500.lock; the command also
#   takes ~/.pixhawk.lock: flock -n ~/.pixhawk.lock bash hil_campaign.sh
# After the shakedown it waits for ~/maqac_hil/CONTROL: "GO" (run the missions), "REDO" (shakedown again with the
# code now in ~/maqac_hil), "ABORT" (restore and stop). No answer within 3 h: restore and stop.
cd ~/maqac_hil || exit 1
mkdir -p params results/hil ${OUTDIR:-results/hil}
L=~/maqac_hil/campaign.log
log(){ echo "$(date -u +%F_%T) $*" | tee -a $L; }
TAG="MAQAC HIL"
B=params/params_before_maqac_hil_$(date -u +%m%d_%H%M).params   # new file per run; the 3 Nov 17:29 baseline stays untouched
REF=params/reference_paperA_2026-11-02.params          # names/types for a by-name backup if the full list fails
SEEDS=${SEEDS:-"20000 20001 20002 20003 20004"}
METHODS="maqac_seq maqac rag"
# City scenario (4 Nov, robotq run maqac-x500-hil-city): EXTRA="--L 600 --city survey/heightmap.npz" OUTDIR=results/hil_city
EXTRA=${EXTRA:-}
OUTDIR=${OUTDIR:-results/hil}
# Resume (robotq run maqac-x500-hil, 3 Nov): SKIP_SHAKEDOWN=1 (passed 17:33); FIRST_METHODS = methods still missing for the
# first seed (maqac_seq s20000 finished before the 17:46 collision).
FIRST_METHODS=${FIRST_METHODS:-$METHODS}
RESTORED=0

for f in ~/.pixhawk.owner ~/vlm_research/.x500.owner; do
  if grep -qi '^busy' $f 2>/dev/null; then log "owner file $f says busy: $(cat $f); not starting"; exit 2; fi
done
if fuser /dev/ttyACM0 >/dev/null 2>&1; then log "serial port in use; not starting"; exit 2; fi
busy="busy: $TAG $(date -u)"; echo "$busy" > ~/.pixhawk.owner; echo "$busy" > ~/vlm_research/.x500.owner
log "start; owner files set busy"

restore(){
  [ $RESTORED = 1 ] && return; RESTORED=1
  pkill -f run_maqac_hil.py; sleep 2
  if [ "${HAVE_BACKUP:-0}" = 1 ]; then
    log "restore"; timeout 60 python3 param_set.py --reboot >> $L 2>&1; sleep 40
    timeout 900 python3 param_set.py --restore $B >> $L 2>&1
    timeout 60 python3 param_set.py --reboot >> $L 2>&1; sleep 60
    for pass in 1 2 3 4; do
      A=params/params_after_maqac_hil_$pass.params
      timeout 1500 python3 backup_by_name.py $B $A >> $L 2>&1
      fix=$(python3 - "$B" "$A" <<'PY'
import sys
def rd(f):
    d = {}
    for l in open(f):
        p = l.split()
        if len(p) >= 4 and not l.startswith('#'):
            d[p[2]] = p[3]
    return d
a, b = rd(sys.argv[1]), rd(sys.argv[2])
def eq(x, y):
    try: return abs(float(x) - float(y)) < 1e-6 * max(1, abs(float(x)))
    except ValueError: return x == y
miss = [k for k in a if k != '_HASH_CHECK' and k not in b]
dif = [f'{k}={a[k]}' for k in a if k != '_HASH_CHECK' and k in b and not eq(a[k], b[k])]
open(sys.argv[2] + '.diff', 'w').write(f'differing {len(dif)}: {" ".join(dif)}\nmissing {len(miss)}: {" ".join(miss)}\n')
print(' '.join(dif))
PY
)
      log "read-back pass $pass: $(head -c 400 $A.diff | tr '\n' ' ')"
      [ -z "$fix" ] && { log "read-back pass $pass: 0 differing parameters"; break; }
      timeout 300 python3 param_set.py $fix >> $L 2>&1; timeout 60 python3 param_set.py --reboot >> $L 2>&1; sleep 60
    done
  else
    log "no backup was taken; nothing was changed"
  fi
  idle="idle (last: MAQAC HIL $(date -u))"; echo "$idle" > ~/.pixhawk.owner; echo "$idle" > ~/vlm_research/.x500.owner
  log "done; owner files idle"
}
trap restore EXIT
trap 'log "signal: stopping"; exit 1' INT TERM HUP

# ---- backup
timeout 300 python3 param_dump.py $B >> $L 2>&1
n=$(grep -c "^1" $B 2>/dev/null); log "backup lines $n"
if [ "${n:-0}" -le 1000 ]; then
  log "full list failed: backup by name"; timeout 1500 python3 backup_by_name.py $REF $B >> $L 2>&1
  n=$(grep -c "^1" $B 2>/dev/null); log "backup lines $n"
fi
[ "${n:-0}" -gt 1000 ] || { log "NO BACKUP: stopping before any change"; exit 1; }
HAVE_BACKUP=1
# diff the fresh backup against Paper A's reference before any change (hand-over protocol, 3 Nov)
python3 - "$REF" "$B" >> $L 2>&1 <<'PY'
import sys
def rd(f):
    d = {}
    for l in open(f):
        p = l.split()
        if len(p) >= 4 and not l.startswith('#'):
            d[p[2]] = p[3]
    return d
a, b = rd(sys.argv[1]), rd(sys.argv[2])
def eq(x, y):
    try: return abs(float(x) - float(y)) < 1e-6 * max(1, abs(float(x)))
    except ValueError: return x == y
dif = [f'{k}: ref {a[k]} now {b[k]}' for k in a if k != '_HASH_CHECK' and k in b and not eq(a[k], b[k])]
print(f'pre-run diff vs {sys.argv[1]}: {len(dif)} differing; ' + '; '.join(dif[:30]))
PY
cp $B params/params_before_maqac_hil_$(date -u +%F_%H%M).params
# ---- HITL set-up (same changes as Paper A)
timeout 120 python3 param_set.py SYS_AUTOSTART=1001 SYS_HITL=1 MPC_XY_VEL_MAX=20 MPC_Z_VEL_MAX_DN=2.0 MPC_Z_VEL_MAX_UP=3.0 GF_ACTION=0 >> $L 2>&1

fly(){   # fly(args...) with a reboot first; one retry if the HIL link was not ready
  for try in 1 2; do
    log "reboot before: $*"; timeout 60 python3 param_set.py --reboot >> $L 2>&1; sleep 40
    python3 run_maqac_hil.py "$@" $EXTRA --out $OUTDIR >> ~/maqac_hil/hil_run.log 2>&1; rc=$?
    log "run exit $rc: $*"
    [ $rc = 0 ] && return 0
    grep -q "HIL not ready" <(tail -5 ~/maqac_hil/hil_run.log) || return $rc
  done
}

# ---- shakedown (60 s, seed outside the design), then wait for the decision
dec=GO
while [ "${SKIP_SHAKEDOWN:-0}" != 1 ]; do
  rm -f CONTROL
  fly --T 60 --methods maqac_seq --seeds 19999 --tag shakedown_
  log "shakedown finished; waiting for CONTROL (GO / REDO / ABORT)"
  dec=""
  for i in $(seq 1 1080); do [ -f CONTROL ] && { dec=$(cat CONTROL); break; }; sleep 10; done
  log "CONTROL: ${dec:-timeout}"
  [ "$dec" = "REDO" ] && continue
  break
done
[ "$dec" = "GO" ] || exit 0

# ---- the fixed design: urban, 3 UAVs, L = 1000 m, T = 300 s, seeds 20000-20004 x (maqac_seq, maqac, rag)
first=1
for s in $SEEDS; do
  [ -f STOP ] && { log "STOP file: ending after complete seeds"; break; }
  if [ $first = 1 ]; then fly --T 300 --methods $FIRST_METHODS --seeds $s; first=0
  else fly --T 300 --methods $METHODS --seeds $s; fi
done
log "missions finished: $(grep -c RESULT ~/maqac_hil/hil_run.log) RESULT lines in hil_run.log"
exit 0

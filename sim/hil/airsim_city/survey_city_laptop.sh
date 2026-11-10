#!/bin/bash
# Geometry check (4 Nov 2026): does the laptop's Wine CityEnviron have the same buildings as the cloud VM's?
# Re-runs the campaign survey (sim/airsim/maqac_px4/survey_heightmap.py, same arguments as results/airsim/v3_campaign/survey:
# origin 0 0, L 1000, alt 400, 9 tiles, marker orientation check) on the laptop and writes a new height map for comparison.
# Default render quality here (as on the VM), so view-distance culling cannot drop far buildings from the depth images.
#   resman run -m 4.5G -g 4G -n maqac-city-survey -- bash sim/hil/airsim_city/survey_city_laptop.sh OUTDIR
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../.." && pwd)
O=${1:?OUTDIR}; mkdir -p "$O"
export WINEPREFIX=~/sim_bins/wine_city WINEDEBUG=-all DXVK_HUD=0 DXVK_FRAME_RATE=20 DXVK_FILTER_DEVICE_NAME="NVIDIA"
export __NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia
EXE=~/sim_bins/airsim181_win/CityEnviron/WindowsNoEditor/CityEnviron/Binaries/Win64/CityEnviron.exe
WSET=$(winepath -w "$HERE/settings_survey_city.json" 2>/dev/null)
PY=~/sim_bins/airsim_venv/bin/python
setsid wine "$EXE" -dx11 -windowed -ResX=480 -ResY=270 -nosound -nosplash -log -stdout -settings="$WSET" > "$O/airsim.log" 2>&1 &
AP=$!
stop(){ kill -- -$AP 2>/dev/null; sleep 5; kill -9 -- -$AP 2>/dev/null; wineserver -k 2>/dev/null; }
trap stop EXIT
( sleep 2400; echo "hard timeout 2400 s" >> "$O/airsim.log"; kill -- -$AP 2>/dev/null; wineserver -k 2>/dev/null ) & WD=$!
trap 'stop; kill $WD 2>/dev/null' EXIT
for i in $(seq 1 60); do
  fr=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo); [ "$fr" -lt 1536 ] && { echo "free RAM $fr MB: stop"; exit 1; }
  $PY -c "import airsim; c=airsim.MultirotorClient(timeout_value=3); c.confirmConnection()" >/dev/null 2>&1 && break; sleep 3
done
echo "API up after ~$((i*3)) s"; sleep 10
cd "$REPO/sim/airsim/maqac_px4" && timeout 1200 $PY survey_heightmap.py --ip 127.0.0.1 --out "$O" --origin-ne 0 0 --L 1000 --alt 400 > "$O/survey.log" 2>&1
echo "survey exit $?"
# Second pass in the same AirSim session (5 Nov, for Paper A, which shares the raster instead of running its own survey):
# window N -140..500, E -700..-60 (centre 180 -380, L 640, + 60 m margin), same method and 1 m cells. Skip: PAPERA_PASS=0.
if [ "${PAPERA_PASS:-0}" != 0 ]; then   # off by default since 5 Nov 09:50: Paper A maps its window itself
  mkdir -p "$O/paperA_window"
  timeout 1200 $PY survey_heightmap.py --ip 127.0.0.1 --out "$O/paperA_window" --origin-ne 180 -380 --L 640 --alt 400 \
      > "$O/paperA_window/survey.log" 2>&1
  echo "paperA window survey exit $?"
fi
# ---- Hand-off (4 Nov ~19:45 UTC): queue #437 was stuck at 4.5 GB behind idle sessions while the X500 came free, so the
# city HIL AirSim runs inside the same reservation right after the survey (re-queuing would land behind 5 jobs).
# Only if CHAIN_HIL is not 0 and the rig's owner files on the Jetson are not busy. Stop it early: touch HIL_OUT/STOP.
[ "${CHAIN_HIL:-1}" = 0 ] && exit 0
stop; kill $WD 2>/dev/null; trap - EXIT; sleep 15
HIL_OUT=$REPO/results/airsim/hil_city_1104
if ssh -o ConnectTimeout=10 orin 'grep -qi "^busy" ~/.pixhawk.owner ~/vlm_research/.x500.owner' 2>/dev/null; then
  echo "rig busy on the Jetson: not starting the HIL AirSim"; exit 0
fi
echo "HIL AIRSIM START $(date -u +%T) -> $HIL_OUT"
exec bash "$HERE/run_city_hitl.sh" "$HIL_OUT" 14400

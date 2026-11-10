# MAQAC hardware-in-the-loop (PX4 HITL on a Pixhawk 6C + Jetson Orin Nano)

One UAV of the MAQAC fleet is flown by the real PX4 firmware (1.15.1, EKF2 + position/attitude/rate controllers)
on a Pixhawk 6C in HITL mode. The network simulator (`src/netsim`, v3 model `sim.realistic()`, `takeoff=False` as
in the AirSim bridge) and the decisions of the whole fleet run on the Jetson Orin Nano's ARM CPU, in real time
(one 1 s decision round = 1 s of wall time). The other UAVs stay on the network model's kinematic flight model.

## Files
| file | what |
|---|---|
| `run_maqac_hil.py` | mission runner: `run_episode(..., move=HilMover)`; times every `decide()` call; kinematic twin after each mission; writes `result.json` + `rounds.jsonl` |
| `hil_link.py` | HIL server process: 6-DOF quadrotor physics + HIL_SENSOR (250 Hz) / HIL_GPS (10 Hz), HIL_ACTUATOR_CONTROLS in, OFFBOARD setpoints out (50 Hz), TIMESYNC round trip, mode-drop/failsafe counters; `fake` backend = first-order autopilot for dry runs |
| `hil_campaign.sh` | protocol on the Jetson: lock + owner files, full parameter backup, HITL set-up, reboot, shakedown, wait for GO, 15 missions, restore, reboot, read-back loop until 0 differences, owner files idle |
| `param_dump.py`, `param_set.py`, `backup_by_name.py`, `fc_state.py` | parameter tools, copied unchanged from Paper A's HIL |
| `summarize_hil.py` | per-method table (mean over seeds, min–max) |

Sources: the `Sim`/`Link` classes and the 250 Hz loop come from Paper A's HIL (wind-aware-delivery `hil/hil_run.py`,
Jetson `~/paperA_hil_v4h/hil/`, 2 Nov 2026) with the wind, gusts, payload drop and city logic removed. The
quadrotor model is `src/netsim/third_party/wad_quadrotor.py` (vendored unchanged from the same repository).
Paper A's files were not changed.

## How the loop closes
Each round: the network step and all decisions run (timed); `W.move_uavs()` gives the kinematic reference; UAV 0's
reference for the next second is sent to the HIL server as a cubic Hermite segment (start = current setpoint and its
velocity, end = reference position at 100 m and the model's velocity); the server evaluates it at 50 Hz and sends
position + velocity + acceleration (clipped at 4 m/s²) setpoints to PX4; at the end of the second the true position
from the HIL physics replaces the reference in `W.upos[0]`, `W.ualt[0]`; energy and distance of UAV 0 are corrected
for the distance actually flown (same rule as the AirSim bridge). UAVs 1..n−1 keep the kinematic positions.

## Usage
    python3 run_maqac_hil.py --dry-run --T 30 --methods maqac_seq --seeds 20000 --out /tmp/hil_dry   # no hardware
    cd ~/maqac_hil && setsid nohup flock -w 3600 ~/.pixhawk.lock bash hil_campaign.sh > campaign.out 2>&1 &
    echo GO > ~/maqac_hil/CONTROL          # after checking the shakedown
    python3 sim/hil/summarize_hil.py results/hil --json results/hil/hil_summary.json

## Design (fixed before the first real mission)
Urban scenario, 3 UAVs, L = 1000 m, T = 300 s, 200 users + 0.1 arrivals/s, methods `maqac_seq`, `maqac`, `rag`,
paired seeds 20000–20004 (15 missions), complete seeds first; one 60 s shakedown (`maqac_seq`, seed 19999) before.
PX4 parameters changed for the campaign (same set as Paper A): SYS_AUTOSTART=1001, SYS_HITL=1, MPC_XY_VEL_MAX=20,
MPC_Z_VEL_MAX_DN=2, MPC_Z_VEL_MAX_UP=3, GF_ACTION=0; everything restored and read back afterwards.

## Caveats (state these with any HIL result)
- **Airframe.** The HIL vehicle is a ~2.2 kg X500-class quadrotor (Paper A's 6-DOF model, 4 × 12 N rotors) under
  PX4's HITL quadrotor airframe (1001), not the 6 kg UAV-BS of the network model's energy model. The reference speed
  (14 m/s, 4 m/s²) is within what PX4 tracks on this airframe (MPC_XY_VEL_MAX = 20 m/s); see the tracking errors.
- **One UAV in hardware.** Only UAV 0 is flown by PX4; the others are kinematic. Separation is measured between
  UAV 0's true 3-D position and the others' model positions at 1 Hz.
- **Sensors simulated.** IMU, magnetometer, barometer and GPS are simulated (noise models of Paper A); no wind;
  props off, no battery. The firmware, estimator, controllers and the MAVLink link are real; the radio channels and
  users are the network model's.
- **Compute.** Decision times are measured on the Jetson's ARM CPU (Python/NumPy, one core per process), while a
  separate process runs the 250 Hz HIL loop; another session's LLM server was resident on the same board.

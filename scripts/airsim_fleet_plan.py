#!/usr/bin/env python3
"""Mission lists for the approved AirSim/PX4 fleet study (docs/AIRSIM_FLEET_PLAN.md, approved 1 Nov 2026; user "Do it" 3 Nov).
3 Nov: realistic model v3 (run_maqac_airsim.py --model v3, the default), MAQAC-S (maqac_seq) replaces IAD (same mission
count and cost), mountains dropped, mission names tagged v3 so the old-model run is not skipped.
City (CityEnviron high-rise core, 600 m, 72 users, T = 300 s): n in {3, 6} x {maqac, rag, iad, central} x 5 paired
seeds (on-board perception) + MAQAC offloaded and oracle at n = 6 + 2 repeats of MAQAC n = 6 seed 20000 (run-to-run
spread). Mountains (LandscapeMountains, held-out environment): n = 3 x {maqac, rag} x 5 seeds.
Writes sim/airsim/maqac_px4/plans/plan_<map>_n<N>.txt ("NAME N ARGS")."""
from pathlib import Path

D = Path(__file__).resolve().parents[1] / 'sim' / 'airsim' / 'maqac_px4' / 'plans'
D.mkdir(parents=True, exist_ok=True)
SEEDS = range(20000, 20005)
CITY = '--scenario urban --T 300 --L 600 --origin-ne 40 -10 --heightmap /work/maqac/survey/heightmap.npz --layer 3 --no-users'
# --no-users (3 Nov 19:50): the pedestrian models are visual only; their spawn call hung AirSim's RPC server twice
MOUNT = '--scenario urban --T 300 --L 600 --origin-ne 0 0 --heightmap /work/maqac/survey_mountains/heightmap.npz --layer 3'
plans = {}
for n in (3, 6):
    L = [f'v3_city_n{n}_{m}_onboard_{s} {n} --method {m} --perception onboard --seed {s} {CITY}'
         for s in SEEDS for m in ('maqac_seq', 'maqac', 'rag', 'central')]
    if n == 6:
        L += [f'v3_city_n6_maqac_{p}_{s} 6 --method maqac --perception {p} --seed {s} {CITY}' for p in ('offload', 'oracle') for s in SEEDS]
        L += [f'v3_city_n6_maqac_onboard_20000_rep{r} 6 --method maqac --perception onboard --seed 20000 {CITY}' for r in (1, 2)]
    plans[f'city_n{n}'] = L
for k, L in plans.items():
    (D / f'plan_{k}.txt').write_text('# origin of the mountains area is set after the height survey\n' * k.startswith('mount')
                                     + '\n'.join(L) + '\n')
    print(k, len(L), 'missions')
print('total', sum(map(len, plans.values())))

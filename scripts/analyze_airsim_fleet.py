#!/usr/bin/env python3
"""Summary of the AirSim/PX4 fleet missions (results/airsim/<batch>/runs/*/result.json).
Per (map, n, method, perception): missions, J (mean, 95 % CI), J relative to the kinematic twin, min UAV separation,
min building clearance, near-contact rate (missions with a < 5 m approach during the mission phase) with a
Clopper-Pearson 95 % interval, near-contact events per pair-hour, tracking error, climb energy, pacing overruns.
Paired by seed: MAQAC vs each method (mean relative difference with a paired t 95 % CI; no significance claim at 5 seeds).
    python3 scripts/analyze_airsim_fleet.py results/airsim/fleet_1101 [more dirs] -> results/airsim_fleet_summary.json"""
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import beta as B, t as T

ROOT = Path(__file__).resolve().parents[1]


def cp(k, n):
    return [float(B.ppf(0.025, k, n - k + 1)) if k else 0.0, float(B.ppf(0.975, k + 1, n - k)) if k < n else 1.0]


def ci(x):
    x = np.asarray(x, float)
    return [float(x.mean()), float(T.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else None]


def main():
    R = []
    for d in sys.argv[1:]:
        for f in Path(d).rglob('result.json'):
            r = json.load(open(f)); r['_name'] = f.parent.name
            r['_map'] = 'mountains' if f.parent.name.startswith('mount') else 'city'
            r['_perc'] = next((p for p in ('offload', 'oracle', 'onboard') if f'_{p}_' in f.parent.name), 'onboard')
            r['_rep'] = '_rep' in f.parent.name
            R.append(r)
    G = defaultdict(list)
    for r in R:
        if not r['_rep']:
            G[(r['_map'], r['n_uav'], r['method'], r['_perc'])].append(r)
    out = {}
    for k, E in sorted(G.items()):
        mis = [e['safety'].get('mission', {}) for e in E]
        near = sum(bool(m.get('near_contact')) for m in mis)
        pair_h = sum(m.get('pair_s', 0) for m in mis) / 3600
        out['|'.join(map(str, k))] = dict(
            missions=len(E), J=ci([e['px4']['qos_score'] for e in E]),
            dJ_vs_kinematic_pct=ci([e['delta_qos_pct'] for e in E]),
            min_sep_m=min((m.get('min_sep_m') or np.inf) for m in mis), min_clear_m=min((m.get('min_clear_m') or np.inf) for m in mis),
            near_contact_missions=near, near_contact_rate=near / len(E), near_contact_cp95=cp(near, len(E)),
            near_events_per_pair_h=sum(m.get('near_events', 0) for m in mis) / pair_h if pair_h else None,
            track_err_mean_m=ci([e['flight']['track_err_mean_m'] for e in E]),
            climb_energy_wh=ci([e['flight']['climb_energy_wh'] for e in E]),
            pacing_overrun_frac=ci([(e.get('pacing') or {}).get('overrun_frac', np.nan) for e in E]),
            collisions_in_flight=sum(bool(e.get('collisions_in_flight')) for e in E))
    paired = {}
    for (mp, n, m, p), E in G.items():
        if m == 'maqac' or p != 'onboard':
            continue
        A = {e['seed']: e['px4']['qos_score'] for e in G.get((mp, n, 'maqac', 'onboard'), [])}
        d = [100 * (A[e['seed']] - e['px4']['qos_score']) / e['px4']['qos_score'] for e in E if e['seed'] in A]
        if d:
            paired[f'{mp}|{n}|maqac_vs_{m}'] = dict(seeds=len(d), rel_diff_pct=ci(d))
    reps = [r['px4']['qos_score'] for r in R if r['_rep'] or (r['_name'] == 'city_n6_maqac_onboard_20000')]
    allnear = sum(bool(r['safety'].get('mission', {}).get('near_contact')) for r in R if not r['_rep'])
    nall = sum(1 for r in R if not r['_rep'])
    res = dict(groups=out, paired=paired, repeat_spread_J=ci(reps) if len(reps) > 1 else None,
               near_contact_all=dict(missions=nall, with_near_contact=allnear, cp95=cp(allnear, nall) if nall else None))
    (ROOT / 'results' / 'airsim_fleet_summary.json').write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()

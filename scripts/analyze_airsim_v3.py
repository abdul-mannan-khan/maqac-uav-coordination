#!/usr/bin/env python3
"""AirSim/PX4 CityEnviron campaign on the realistic model v3 (cloud/airsim_v3_campaign.sh, plans from
scripts/airsim_fleet_plan.py) -> results/airsim_v3_summary.json and a printed summary.
Per method and fleet size (5 paired seeds): J_session flown with PX4, J_session of the kinematic twin (same seed, same
code, no flight stack), the paired difference flown - twin, tracking error, minimum UAV separation and building
clearance during the mission (AirSim ground truth, 5 Hz), near-contacts (< 5 m) with a Clopper-Pearson 95 % interval,
and the paired difference of each method to RAG (flown). The kinematic twin of the first mission
(v3_city_n3_maqac_seq_onboard_20000) was not saved by the bridge then; it is recomputed here with the same code and
config (the recomputation reproduces the saved twins exactly, checked on v3_city_n3_rag_onboard_20001)."""
import glob, json, os, sys
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'results' / 'airsim' / 'v3_campaign' / 'runs'
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))


def twin(d, method):
    from sim import realistic
    from episode import run_episode
    L = d['L']; s = (L / 1000) ** 2
    cfg = realistic(name=f"{d['scenario']}_{d['n_uav']}uav", scenario=d['scenario'], n_uav=d['n_uav'], T=d['T'],
                    perception='onboard', altitude=d['alt'], world=L, gateway=(L / 2, L / 2), n_users=int(round(200 * s)),
                    arrival_rate=0.1 * s, takeoff=False)
    return run_episode(cfg, method, d['seed'], log_rounds=False)['J_session']


def cp(k, n):
    lo = 0.0 if k == 0 else stats.beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(0.975, k + 1, n - k)
    return float(lo), float(hi)


rows = []
for f in sorted(glob.glob(str(D / 'v3_city_*' / 'result.json'))):
    name = os.path.basename(os.path.dirname(f)); d = json.load(open(f))
    Jk = d['kinematic'].get('J_session')
    if Jk is None:
        Jk = twin(d, d['method'])
    mis = d['safety']['mission']
    rows.append(dict(name=name, method=d['method'], n=d['n_uav'], seed=d['seed'],
                     perception=name.split('_')[-2] if 'rep' not in name else 'onboard', repeat='rep' in name,
                     J=d['px4']['J_session'], Jk=Jk, dJ=100 * (d['px4']['J_session'] / Jk - 1),
                     trk=d['flight']['track_err_mean_m'], trk95=d['flight']['track_err_p95_m'],
                     sep=mis['min_sep_m'], clr=mis['min_clear_m'], near=bool(mis['near_contact']),
                     pad_near=bool(d['safety'].get('startup', {}).get('near_contact') or d['safety'].get('takeoff', {}).get('near_contact')),
                     dist=d['px4']['distance_m'], wall=d['wall_s'], overrun=(d.get('pacing') or {}).get('overrun_frac')))
out = dict(n_missions=len(rows), rows=rows, cells={})
main = [r for r in rows if r['perception'] == 'onboard' and not r['repeat']]
for n in (3, 6):
    J = {m: {r['seed']: r for r in main if r['n'] == n and r['method'] == m} for m in ('maqac_seq', 'maqac', 'rag', 'central')}
    for m, S in J.items():
        x = list(S.values())
        if not x:
            continue
        c = dict(missions=len(x), J=float(np.mean([r['J'] for r in x])), dJ_mean=float(np.mean([r['dJ'] for r in x])),
                 dJ_min=float(min(r['dJ'] for r in x)), dJ_max=float(max(r['dJ'] for r in x)),
                 trk=float(np.mean([r['trk'] for r in x])), trk95=float(np.mean([r['trk95'] for r in x])),
                 sep_min=float(min(r['sep'] for r in x)), clr_min=float(min(r['clr'] for r in x)),
                 near=int(sum(r['near'] for r in x)))
        k = sorted(set(S) & set(J['rag']))
        if m != 'rag' and len(k) >= 3:
            dd = np.array([100 * (S[s]['J'] / J['rag'][s]['J'] - 1) for s in k])
            c['vs_rag'] = dict(mean=float(dd.mean()), p=float(stats.ttest_1samp(dd, 0).pvalue), n=len(k))
        out['cells'][f'{n}_{m}'] = c
nm = [r for r in rows]
k = sum(r['near'] for r in nm)
out['near_all'] = dict(k=int(k), n=len(nm), cp95=cp(k, len(nm)))
rep = [r for r in rows if r['n'] == 6 and r['method'] == 'maqac' and r['seed'] == 20000 and r['perception'] == 'onboard']
out['repeat_spread'] = dict(J=[r['J'] for r in rep], spread_pct=float(100 * (max(r['J'] for r in rep) / min(r['J'] for r in rep) - 1)) if len(rep) > 1 else None)
per = {p: [r for r in rows if r['n'] == 6 and r['method'] == 'maqac' and r['perception'] == p and not r['repeat']] for p in ('onboard', 'offload', 'oracle')}
out['perception'] = {p: dict(n=len(x), J=float(np.mean([r['J'] for r in x])) if x else None) for p, x in per.items()}
json.dump(out, open(ROOT / 'results' / 'airsim_v3_summary.json', 'w'), indent=1)
for k_, c in out['cells'].items():
    print(k_, {a: (round(b, 2) if isinstance(b, float) else b) for a, b in c.items()})
print('near-contacts (mission phase):', out['near_all'])
print('repeat spread:', out['repeat_spread'])
print('perception (6 UAVs, MAQAC):', out['perception'])

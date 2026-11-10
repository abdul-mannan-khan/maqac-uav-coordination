#!/usr/bin/env python3
"""AirSim/PX4 CityEnviron results as reported after the re-fly.
The six-UAV missions of the v3 campaign touched a hidden collision volume above Building_C_Mid_CornerIn_C264 (15 of 42
reported missions, scripts/analyze_airsim_contacts.py). They were flown again with a planner-only keep-out over that
block (results/airsim/refly_campaign/, ko_city_n6_*, AirSim under Wine on Vast). Reported set = three-UAV missions of
the v3 campaign (no contact) + the 27 re-flown six-UAV missions; Central excluded.
Per method and fleet size: flown J_session, kinematic twin, paired difference, tracking error, min separation and
visible-building clearance in the mission phase, near-contacts (< 5 m) and AirSim in-flight contacts, each with a
Clopper-Pearson 95 % interval; paired difference to RAG. -> results/airsim_refly_summary.json"""
import glob, json, os
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'results' / 'airsim' / 'v3_campaign' / 'runs'
NEW = ROOT / 'results' / 'airsim' / 'refly_campaign' / 'runs'


def cp(k, n):
    lo = 0.0 if k == 0 else stats.beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(0.975, k + 1, n - k)
    return [float(lo), float(hi)]


def row(f, src):
    name = os.path.basename(os.path.dirname(f)); d = json.load(open(f)); mis = d['safety']['mission']
    Jk = d['kinematic'].get('J_session')
    if Jk is None:   # first v3 mission: twin recomputed by analyze_airsim_v3.py (same code), read from its summary
        Jk = next(r['Jk'] for r in json.load(open(ROOT / 'results' / 'airsim_v3_summary.json'))['rows'] if r['name'] == name)
    return dict(name=name, src=src, method=d['method'], n=d['n_uav'], seed=d['seed'],
                perception=('onboard' if 'rep' in name else name.split('_')[-2]), repeat='rep' in name,
                J=d['px4']['J_session'], Jk=Jk, dJ=100 * (d['px4']['J_session'] / Jk - 1),
                trk=d['flight']['track_err_mean_m'], trk95=d['flight']['track_err_p95_m'],
                sep=mis['min_sep_m'], clr=mis['min_clear_m'], near=bool(mis['near_contact']),
                contact=bool(d.get('collisions_in_flight')), wall=d['wall_s'])


rows = [row(f, 'v3') for f in sorted(glob.glob(str(OLD / 'v3_city_n3_*' / 'result.json')))]
rows = [r for r in rows if r['method'] != 'central']
rows += [row(f, 'refly') for f in sorted(glob.glob(str(NEW / 'ko_city_n6_*' / 'result.json')))]
out = dict(n_missions=len(rows), n3=sum(r['n'] == 3 for r in rows), n6=sum(r['n'] == 6 for r in rows), rows=rows, cells={})
main = [r for r in rows if r['perception'] == 'onboard' and not r['repeat']]
for n in (3, 6):
    J = {m: {r['seed']: r for r in main if r['n'] == n and r['method'] == m} for m in ('maqac_seq', 'maqac', 'rag')}
    for m, S in J.items():
        x = list(S.values())
        if not x:
            continue
        c = dict(missions=len(x), J=float(np.mean([r['J'] for r in x])), dJ_mean=float(np.mean([r['dJ'] for r in x])),
                 dJ_min=float(min(r['dJ'] for r in x)), dJ_max=float(max(r['dJ'] for r in x)),
                 trk=float(np.mean([r['trk'] for r in x])), trk95=float(np.mean([r['trk95'] for r in x])),
                 sep_min=float(min(r['sep'] for r in x)), clr_min=float(min(r['clr'] for r in x)))
        k = sorted(set(S) & set(J['rag']))
        if m != 'rag' and len(k) >= 3:
            dd = np.array([100 * (S[s]['J'] / J['rag'][s]['J'] - 1) for s in k])
            c['vs_rag'] = dict(mean=float(dd.mean()), min=float(dd.min()), max=float(dd.max()),
                               p=float(stats.ttest_1samp(dd, 0).pvalue), n=len(k))
        out['cells'][f'{n}_{m}'] = c
for key in ('near', 'contact'):
    k = sum(r[key] for r in rows); out[key + '_all'] = dict(k=int(k), n=len(rows), cp95=cp(k, len(rows)))
for n in (3, 6):
    x = [r for r in rows if r['n'] == n]
    out[f'range_{n}'] = dict(dJ=[min(r['dJ'] for r in x), max(r['dJ'] for r in x)], sep_min=min(r['sep'] for r in x),
                             clr_min=min(r['clr'] for r in x), trk95_max=max(r['trk95'] for r in x), missions=len(x))
per = {p: [r for r in rows if r['n'] == 6 and r['method'] == 'maqac' and r['perception'] == p and not r['repeat']] for p in ('onboard', 'offload', 'oracle')}
out['perception'] = {p: dict(n=len(x), J=float(np.mean([r['J'] for r in x])) if x else None) for p, x in per.items()}
rep = [r for r in rows if r['n'] == 6 and r['method'] == 'maqac' and r['seed'] == 20000 and r['perception'] == 'onboard']
out['repeat_spread_pct'] = float(100 * (max(r['J'] for r in rep) / min(r['J'] for r in rep) - 1)) if len(rep) > 1 else None
json.dump(out, open(ROOT / 'results' / 'airsim_refly_summary.json', 'w'), indent=1)
print('missions', out['n_missions'], '(3 UAVs', out['n3'], ', 6 UAVs', out['n6'], ')')
for k_, c in out['cells'].items():
    print(k_, {a: (round(b, 2) if isinstance(b, float) else b) for a, b in c.items()})
for k_ in ('near_all', 'contact_all', 'range_3', 'range_6', 'perception', 'repeat_spread_pct'):
    print(k_, out[k_])

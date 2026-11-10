#!/usr/bin/env python3
"""The paper's main comparison re-run on the realistic model v3 (sim.realistic()); pre-registered 1 Nov 2026, 23:00 GMT.

Question: do the paper's findings (MAQAC ahead of RAG, IAD and the potential game; close to Central) hold when the
service footprint is link-limited, users need whole sessions, and flight, energy and backhaul are physical?
Design (fixed before running):
  model     sim.realistic() defaults (A2G urban/suburban channel, link-limited admission, sessions, take-off, 6 kg
            energy model, staggered swaps, GNSS, 3 km backhaul), planning radius r_s = 150 m, lambda_hold = 0.2
            (from the tuning scan on seeds 900-904, results/v3_scan/scale2.jsonl; no further tuning)
  areas     1 km x 1 km (the paper's area) and 3 km x 3 km, users per km^2 fixed (200 + 0.1/s), gateway at the centre;
            real cities (added 1 Nov 23:20, before any city result): City of London (EA LiDAR heights) and Midtown
            Manhattan (NYC Open Data heights), 640 m x 640 m, from wind-aware-delivery commit 871d003, ray-march LOS,
            6-DOF flight (sixdof.py), tower-climb rule, urban users on open ground
  scenarios urban, suburban, disaster; fleets 4, 6, 8
  methods   maqac, rag, iad, potgame, central, greedy_info, systematic, static_pad, static_grid (MAPPO is not
            included: it would need retraining on v3)
  seeds     20000-20019 (paired; disjoint from the tuning seeds)
  metric    J_session (primary), qos_score (first contact), session_frac_mean, users_served, blocked
  tests     paired relative difference MAQAC vs each method, paired t-test, Holm within each (area, scenario, n) cell
Output: results/netsim_v3_study.jsonl (per mission, resumable) and results/netsim_v3_study_summary.json.
    python3 scripts/netsim_v3_study.py [workers] [--out FILE] [--part all|iad3k|rest|area_rest|cities]
Rerun of 2 Nov 2026 (deviation from the pre-registration, decided before any result of the rerun): every block is run
again with the 6-DOF controller fix (sixdof.Controller6kg) and the v3 separation rule sep_model='sum', both found
after the first run (21/1,080 city missions diverged; the 'first' separation rule pushed UAVs across each other).
Design, seeds and tests unchanged. --part splits the work between machines (iad3k = IAD on 3 km areas).
"""
import json, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402

METHODS = ('maqac', 'rag', 'iad', 'potgame', 'central', 'greedy_info', 'systematic', 'static_pad', 'static_grid',
           'maqac_seq', 'maqac_rag', 'maqac_hyb')   # last three added 2 Nov 2026 before the rerun started
AREAS, SCEN, FLEETS, SEEDS = (1000.0, 3000.0), ('urban', 'suburban', 'disaster'), (4, 6, 8), range(20000, 20020)
CITIES = ('london_lidar', 'manhattan_nyc')          # real cities, measured heights, ray-march LOS, 6-DOF flight (urban users)
OUT = ROOT / 'results' / 'netsim_v3_study.jsonl'
KEYS = ('J_session', 'qos_score', 'session_frac_mean', 'users_served', 'users_total', 'blocked', 'continuity',
        'mean_hops', 'disconnected_uav_s', 'collisions', 'energy_wh', 'episode_time_s')


def job(a):
    W, sc, n, m, s = a
    if isinstance(W, str):                          # real city block
        cfg = realistic(scenario='urban', n_uav=n, city_file=str(ROOT / 'data' / 'cities' / f'{W}.npz'), flight='sixdof',
                        name=f'v3_{W}_{n}')
    else:
        f = (W / 1000.0) ** 2
        cfg = realistic(scenario=sc, n_uav=n, world=W, n_users=int(200 * f), arrival_rate=0.1 * f, gateway=(W / 2, W / 2),
                        name=f'v3_{int(W)}_{sc}_{n}')
    try:
        r = run_episode(cfg, m, s, log_rounds=False)
        out = {k: r.get(k) for k in KEYS + ('track_err_mean', 'track_err_p95', 'tilt_sat_share', 'tower_climb_s')}
    except Exception as e:
        out = dict(error=repr(e))
    return dict(W=W, scenario=sc, n=n, method=m, seed=s, **out)


def holm(p):
    o = np.argsort(p); adj = np.empty(len(p)); run = 0.0
    for r, i in enumerate(o):
        run = max(run, (len(p) - r) * p[i]); adj[i] = min(1.0, run)
    return adj


def summarise(done):
    S = {}
    for W in AREAS + CITIES:
        for sc in (SCEN if not isinstance(W, str) else ('urban',)):
            for n in FLEETS:
                cell = [d for d in done if d['W'] == W and d['scenario'] == sc and d['n'] == n and 'error' not in d]
                J = {m: {d['seed']: d['J_session'] for d in cell if d['method'] == m} for m in METHODS}
                if not J['maqac']:
                    continue
                rows, ps = {}, []
                for m in METHODS:
                    if m == 'maqac' or not J[m]:
                        continue
                    s = sorted(set(J['maqac']) & set(J[m]))
                    a, b = np.array([J['maqac'][k] for k in s]), np.array([J[m][k] for k in s])
                    p = float(stats.ttest_rel(a, b).pvalue) if len(s) > 1 and not np.allclose(a, b) else 1.0
                    rows[m] = dict(rel=float(a.mean() / b.mean() - 1), n=len(s), p=p)
                    ps.append(p)
                for (m, r), pa in zip(rows.items(), holm(np.array(ps)) if ps else []):
                    r['p_holm'] = float(pa)
                S[f'{W if isinstance(W, str) else int(W)}_{sc}_{n}'] = dict(
                    mean={m: float(np.mean(list(J[m].values()))) for m in METHODS if J[m]},
                    maqac_vs=rows)
    return S


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--out' in args:
        OUT = Path(args[args.index('--out') + 1])
    part = args[args.index('--part') + 1] if '--part' in args else 'all'
    workers = int(args[0]) if args and args[0].isdigit() else 8
    done = [json.loads(l) for l in open(OUT)] if OUT.exists() else []
    have = {(d['W'], d['scenario'], d['n'], d['method'], d['seed']) for d in done}
    todo = [(W, sc, n, m, s) for W in AREAS for sc in SCEN for n in FLEETS for m in METHODS for s in SEEDS
            if (W, sc, n, m, s) not in have]
    todo += [(C, 'urban', n, m, s) for C in CITIES for n in FLEETS for m in METHODS for s in SEEDS
             if (C, 'urban', n, m, s) not in have]
    is_iad3k = lambda a: a[0] == 3000.0 and a[3] == 'iad'
    if part == 'iad3k':
        todo = [a for a in todo if is_iad3k(a)]
    elif part == 'rest':
        todo = [a for a in todo if not is_iad3k(a)]
    elif part == 'area_rest':                       # areas only, no real-city files needed (e.g. on a rented machine)
        todo = [a for a in todo if not is_iad3k(a) and not isinstance(a[0], str)]
    elif part == 'cities':
        todo = [a for a in todo if isinstance(a[0], str)]
    slow = {'iad': 0, 'central': 1, 'rag': 2}
    todo.sort(key=lambda a: (0 if isinstance(a[0], str) else 1, -(a[0] if not isinstance(a[0], str) else 0),
                             slow.get(a[3], 9), -a[2]))                 # longest first (6-DOF cities, then 3 km)
    print(f'{len(todo)} missions to run', flush=True)
    with Pool(workers) as p, open(OUT, 'a') as f:
        for i, r in enumerate(p.imap_unordered(job, todo)):
            f.write(json.dumps(r, default=float) + '\n'); f.flush(); done.append(r)
            if (i + 1) % 100 == 0:
                print(f'{i + 1}/{len(todo)}', flush=True)
    if part == 'all':
        json.dump(summarise(done), open(OUT.with_name(OUT.stem + '_summary.json'), 'w'), indent=1)
    print('v3 study finished', flush=True)

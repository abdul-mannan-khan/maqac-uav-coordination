"""Coordination cost per decision round: sequential message iterations, coordination messages beyond record flooding,
and decision compute (slowest UAV; UAVs compute in parallel). MAQAC vs RAG (Xu, Garimella, Tzoumas, T-RO 2025) vs
sequential MAQAC. Urban scenario, fleets 2-10, 10 seeds, T = 900 s, single worker per episode (compute times are wall
clock on a shared laptop CPU: relative, not absolute).   -> results/netsim_coord_cost.json"""
import sys, json
sys.path.insert(0, 'src/netsim')
from dataclasses import replace
from multiprocessing import Pool
import numpy as np
from sim import NetConfig
from episode import run_episode
KEYS = ('coord_iters', 'coord_iters_max', 'coord_msgs', 'decide_ms', 'decide_ms_p95', 'qos_score')
def f(a):
    m, n, s = a
    r = run_episode(replace(NetConfig(), n_uav=n), m, 40000 + s, log_rounds=False)
    return dict(method=m, n_uav=n, seed=s, **{k: r[k] for k in KEYS})
if __name__ == '__main__':
    J = [(m, n, s) for n in (2, 4, 6, 8, 10) for m in ('maqac', 'rag', 'maqac_seq') for s in range(10)]
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 6) as p:
        R = p.map(f, J)
    out = dict(rows=R, summary={})
    for n in (2, 4, 6, 8, 10):
        for m in ('maqac', 'rag', 'maqac_seq'):
            X = [r for r in R if r['method'] == m and r['n_uav'] == n]
            out['summary'][f'{m}_{n}'] = {k: float(np.mean([x[k] for x in X])) for k in KEYS}
            print(n, m, {k: round(out['summary'][f'{m}_{n}'][k], 2) for k in KEYS}, flush=True)
    json.dump(out, open('results/netsim_coord_cost.json', 'w'), indent=1)

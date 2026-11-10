#!/usr/bin/env python3
"""Per-round diagnostics of MAQAC at full scale (Sec. 7.9): the overlap multiplicity m(G) of Theorem 4 and the
online certificate of Proposition 6, evaluated with the true users in every logged round.

For each logged round (every cfg.cert_every = 5 s) the simulator returns, with ground truth:
  g    = round gain g_k(G) of the simultaneous choice,
  ub   = g + sum_i max_e Delta(e | X u G)   (Proposition 6 upper bound on g_k(O)),
  m    = overlap multiplicity m(G),
for three user scopes: 'full' (all unserved users present), 'obs' (users seen in the last 90 s), 'view'
(users inside a camera view this round). rho = g / ub is the certified per-round ratio.

Urban scenario, 4/6/8 UAVs, 20 seeds each (30000-30019, disjoint from the grid and the certificate study), T = 900 s.
Output: results/netsim_round_diagnostics.json.   Light: ~1 min on 6 cores, < 2 GB.
"""
import json
import sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import NetConfig          # noqa: E402
from episode import run_episode    # noqa: E402

FLEETS, SEEDS = (4, 6, 8), range(30000, 30020)


def job(a):
    n, s = a
    r = run_episode(replace(NetConfig(), scenario='urban', n_uav=n), 'maqac', s, log_rounds=True)
    keep = ('g_full', 'ub_full', 'm_full', 'g_obs', 'ub_obs', 'm_obs', 'g_view', 'ub_view', 'm_view', 'n')
    return dict(n=n, seed=s, J=r['qos_score'], rounds=[{k: x[k] for k in keep if k in x} for x in r['rounds']])


def summarize(R, scope):
    out = {}
    for n in FLEETS:
        rr = [x for e in R if e['n'] == n for x in e['rounds'] if x.get(f'ub_{scope}', 0) > 0]
        m = np.array([x[f'm_{scope}'] for x in rr])
        rho = np.array([x[f'g_{scope}'] / x[f'ub_{scope}'] for x in rr])
        # mission-level version of Proposition 6: sum of gains over sum of upper bounds
        mis = [sum(x[f'g_{scope}'] for x in e['rounds']) / max(1e-9, sum(x[f'ub_{scope}'] for x in e['rounds']))
               for e in R if e['n'] == n]
        hist = {str(k): float(np.mean(m == k)) for k in range(0, int(m.max()) + 1)} if len(m) else {}
        bound = 0.5 / (0.5 + np.maximum(m, 1))
        out[str(n)] = dict(rounds=int(len(rr)), m_hist=hist, m_mean=float(m.mean()), m_le1=float(np.mean(m <= 1)),
                           rho_mean=float(rho.mean()), rho_median=float(np.median(rho)),
                           rho_p10=float(np.percentile(rho, 10)), rho_min=float(rho.min()),
                           theorem4_bound_mean=float(bound.mean()),
                           mission_rho_mean=float(np.mean(mis)), mission_rho_min=float(np.min(mis)),
                           J_mean=float(np.mean([e['J'] for e in R if e['n'] == n])))
    return out


def main():
    jobs = [(n, s) for n in FLEETS for s in SEEDS]
    with Pool(6) as p:
        R = p.map(job, jobs)
    res = dict(note=__doc__.strip().splitlines()[0], fleets=FLEETS, seeds=[SEEDS.start, SEEDS.stop - 1],
               **{scope: summarize(R, scope) for scope in ('full', 'obs', 'view')})
    out = ROOT / 'results' / 'netsim_round_diagnostics.json'
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res['full'], indent=1))


if __name__ == '__main__':
    main()

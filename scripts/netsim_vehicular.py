#!/usr/bin/env python3
"""Vehicular users (pre-registered 1 Nov 2026): a share of the users drive on a Manhattan road grid (roads every
200 m, 8-15 m/s, random turn at each intersection, no stops); the rest are the urban scenario's pedestrians.
Urban, veh_frac in {0.3, 0.6}, n in {4, 6, 8}, methods maqac, rag, iad, potgame, central, greedy_info, systematic
(+ he2025 when implemented); 20 paired seeds 20000-20019 -> 840 missions (+120 per added method).
Reported like Table 2: mean J (95 % CI) and paired relative difference with Holm-adjusted paired t-tests per block.
Output: results/netsim_vehicular.jsonl (+ .json summary)."""
import json, sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from scipy.stats import ttest_rel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import NetConfig          # noqa: E402
from episode import run_episode, METHODS as REG    # noqa: E402

METHODS = [m for m in ('maqac', 'rag', 'iad', 'potgame', 'central', 'greedy_info', 'systematic', 'he2025')
           if m in REG or m == 'central']
FR, FLEETS, SEEDS = (0.3, 0.6), (4, 6, 8), range(20000, 20020)
OUT = ROOT / 'results' / 'netsim_vehicular.jsonl'


def job(a):
    f, n, m, s = a
    r = run_episode(replace(NetConfig(), scenario='urban', n_uav=n, veh_frac=f), m, s, log_rounds=False)
    return dict(veh_frac=f, n=n, method=m, seed=s, J=r['qos_score'], served=r['users_served'], wait=r['mean_wait_s'],
                interf_outage=r['interf_outage'])


def holm(p):
    o = np.argsort(p); adj = np.empty(len(p)); run = 0.0
    for r, i in enumerate(o):
        run = max(run, (len(p) - r) * p[i]); adj[i] = min(1.0, run)
    return adj


def main():
    done = [json.loads(l) for l in open(OUT)] if OUT.exists() else []
    have = {(d['veh_frac'], d['n'], d['method'], d['seed']) for d in done}
    todo = [(f, n, m, s) for f in FR for n in FLEETS for m in METHODS for s in SEEDS if (f, n, m, s) not in have]
    with Pool(8) as p, open(OUT, 'a') as fo:
        for r in p.imap_unordered(job, todo, chunksize=2):
            fo.write(json.dumps(r) + '\n'); fo.flush(); done.append(r)
    summ = {}
    for f in FR:
        for n in FLEETS:
            J = {m: np.array([d['J'] for d in sorted([d for d in done if d['veh_frac'] == f and d['n'] == n and
                                                      d['method'] == m], key=lambda d: d['seed'])]) for m in METHODS}
            J = {m: v for m, v in J.items() if len(v)}
            others = [m for m in J if m != 'maqac']
            adj = holm(np.array([ttest_rel(J['maqac'], J[m]).pvalue for m in others]))
            row = dict(J={m: [round(float(v.mean()), 1), round(float(1.96 * v.std(ddof=1) / np.sqrt(len(v))), 1)] for m, v in J.items()})
            for m, pa in zip(others, adj):
                row[f'vs_{m}_pct'] = round(100 * float((J['maqac'].mean() - J[m].mean()) / J[m].mean()), 1)
                row[f'vs_{m}_p_holm'] = float(pa)
            summ[f'veh{f:g}_n{n}'] = row
    (ROOT / 'results' / 'netsim_vehicular.json').write_text(json.dumps(dict(note=__doc__.strip(), blocks=summ), indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == '__main__':
    main()

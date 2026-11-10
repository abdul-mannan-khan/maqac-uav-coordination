#!/usr/bin/env python3
"""Channel sensitivity of the main comparison (pre-registered 1 Nov 2026).

Question: do the single-channel result (+55 % vs RAG at K = 1) and the value of the co-channel exclusion rule survive a
harsher channel than the main grid's (fixed per-link shadowing, no fading)?
Variants: 'fade'  = shadowing evolving with link displacement (decorrelation distance 50 m) + per-round block fading
                    (Rician K = 10 dB on LOS links, Rayleigh on NLOS);
          'worst' = 'fade' + every interfering link LOS (worst-case interference).
Urban, n in {4, 6, 8}, K in {1, 3}, methods maqac, maqac_nocc (no exclusion), rag, iad, potgame; 20 paired seeds
(20000-20019, the grid's first 20 test seeds) -> 2 x 3 x 2 x 5 x 20 = 1,200 missions.
Reported: mean J with 95 % CI, paired relative difference MAQAC vs each method with Holm-adjusted paired t-test per
(variant, K, n) block. Output: results/netsim_channel_sensitivity.jsonl (+ .json summary).
"""
import json, sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from scipy.stats import ttest_rel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import NetConfig          # noqa: E402
from episode import run_episode    # noqa: E402

VAR = {'fade': dict(shadow_corr_m=50.0, fading=True), 'worst': dict(shadow_corr_m=50.0, fading=True, interf_los=True)}
METHODS, FLEETS, KS, SEEDS = ('maqac', 'maqac_nocc', 'rag', 'iad', 'potgame'), (4, 6, 8), (1, 3), range(20000, 20020)
OUT = ROOT / 'results' / 'netsim_channel_sensitivity.jsonl'


def job(a):
    v, k, n, m, s = a
    r = run_episode(replace(NetConfig(), scenario='urban', n_uav=n, n_channels=k, **VAR[v]), m, s, log_rounds=False)
    return dict(variant=v, K=k, n=n, method=m, seed=s, J=r['qos_score'], interf_outage=r['interf_outage'],
                served=r['users_served'])


def holm(p):
    o = np.argsort(p); adj = np.empty(len(p)); run = 0.0
    for r, i in enumerate(o):
        run = max(run, (len(p) - r) * p[i]); adj[i] = min(1.0, run)
    return adj


def main():
    done = [json.loads(l) for l in open(OUT)] if OUT.exists() else []
    have = {(d['variant'], d['K'], d['n'], d['method'], d['seed']) for d in done}
    todo = [(v, k, n, m, s) for v in VAR for k in KS for n in FLEETS for m in METHODS for s in SEEDS
            if (v, k, n, m, s) not in have]
    with Pool(8) as p, open(OUT, 'a') as f:
        for r in p.imap_unordered(job, todo, chunksize=2):
            f.write(json.dumps(r) + '\n'); f.flush(); done.append(r)
    summ = {}
    for v in VAR:
        for k in KS:
            for n in FLEETS:
                J = {m: np.array([d['J'] for d in sorted([d for d in done if d['variant'] == v and d['K'] == k and
                                                          d['n'] == n and d['method'] == m], key=lambda d: d['seed'])])
                     for m in METHODS}
                others = [m for m in METHODS if m != 'maqac']
                ps = np.array([ttest_rel(J['maqac'], J[m]).pvalue for m in others])
                adj = holm(ps)
                row = dict(J={m: [round(float(J[m].mean()), 1), round(float(1.96 * J[m].std(ddof=1) / np.sqrt(len(J[m]))), 1)]
                              for m in METHODS})
                for m, pa in zip(others, adj):
                    row[f'vs_{m}_pct'] = round(100 * float((J['maqac'].mean() - J[m].mean()) / J[m].mean()), 1)
                    row[f'vs_{m}_p_holm'] = float(pa)
                summ[f'{v}_K{k}_n{n}'] = row
    (ROOT / 'results' / 'netsim_channel_sensitivity.json').write_text(json.dumps(dict(note=__doc__.strip(), blocks=summ), indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == '__main__':
    main()

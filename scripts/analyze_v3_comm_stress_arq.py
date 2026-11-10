#!/usr/bin/env python3
"""Analysis of scripts/v3_comm_stress_arq.py as pre-registered there (same test as analyze_v3_comm_stress.py):
paired relative difference of J_session for maqac and maqac_seq vs rag in every condition x cell, 95 % t-interval,
Holm over all comparisons of each pair. Also link transmissions per mission (every attempt counted).
Output: results/v3_comm_stress_arq_summary.json and a printed table."""
import json, glob, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
rows = []
for f in sorted(glob.glob(str(ROOT / 'results' / 'v3_comm_stress_arq_shard*.jsonl'))):
    rows += [json.loads(l) for l in open(f)]
# Bursty-loss fix (6 Nov 2026): Gilbert-Elliott state advances once per round; corrected ge20_arq2 rows replace the old.
GEFIX = ROOT / 'results' / 'v3_comm_stress_arq_gefix.jsonl'
if GEFIX.exists() and '--old-ge' not in sys.argv:
    rows = [r for r in rows if r.get('cond') != 'ge20_arq2'] + [json.loads(l) for l in open(GEFIX)]
err = [r for r in rows if 'error' in r]
rows = [r for r in rows if 'error' not in r]
J, TX, AT = defaultdict(dict), defaultdict(list), defaultdict(list)
for r in rows:
    J[(r['cond'], r['W'], r['scenario'], r['n'], r['method'])][r['seed']] = r['J_session']
    TX[(r['cond'], r['W'], r['method'])].append(r['tx_attempts'])
    if r.get('tx_msgs'):
        AT[(r['cond'], r['method'])].append(r['tx_attempts'] / r['tx_msgs'])
CONDS = ('loss40_arq2', 'ge20_arq2', 'node20', 'node40')
cells = sorted({(r['W'], r['scenario'], r['n']) for r in rows})
out = {}
for m in ('maqac', 'maqac_seq'):
    res, ps = [], []
    for c in CONDS:
        for (W, sc, n) in cells:
            a, b = J.get((c, W, sc, n, m), {}), J.get((c, W, sc, n, 'rag'), {})
            s = sorted(set(a) & set(b))
            if len(s) < 5:
                continue
            d = np.array([100 * (a[k] / b[k] - 1) for k in s])
            t = stats.ttest_1samp(d, 0.0)
            hw = stats.t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
            res.append(dict(cond=c, W=W, scenario=sc, n=n, seeds=len(d), mean=float(d.mean()), lo=float(d.mean() - hw),
                            hi=float(d.mean() + hw), p=float(t.pvalue)))
            ps.append(t.pvalue)
    ps = np.array(ps); o = np.argsort(ps); adj = np.empty(len(ps)); run = 0.0
    for r_, i in enumerate(o):
        run = max(run, (len(ps) - r_) * ps[i]); adj[i] = min(1.0, run)
    for x, pa in zip(res, adj):
        x['p_holm'] = float(pa)
        x['verdict'] = ('WIN' if x['mean'] >= 3 else 'win') if pa < 0.05 and x['mean'] > 0 else ('LOSS' if pa < 0.05 else 'level')
    out[m] = res
summ = {m: {c: {f'{int(W)}': {v: sum(1 for x in out[m] if x['cond'] == c and x['W'] == W and x['verdict'] == v)
                              for v in ('WIN', 'win', 'level', 'LOSS')} for W in (1000.0, 3000.0)} for c in CONDS} for m in out}
rng = {m: {c: {f'{int(W)}': [min(x['mean'] for x in out[m] if x['cond'] == c and x['W'] == W),
                             max(x['mean'] for x in out[m] if x['cond'] == c and x['W'] == W)] for W in (1000.0, 3000.0)}
           for c in CONDS} for m in out}
tx = {f'{c}|{int(W)}|{m}': float(np.mean(v)) for (c, W, m), v in TX.items()}
att = {f'{c}|{m}': float(np.mean(v)) for (c, m), v in AT.items()}
json.dump(dict(cells=out, counts=summ, ranges=rng, tx_attempts_per_mission=tx, attempts_per_msg=att, errors=len(err),
               missions=len(rows)), open(ROOT / 'results' / 'v3_comm_stress_arq_summary.json', 'w'), indent=1)
print(f'missions {len(rows)}, errors {len(err)}')
for m in out:
    print(f'\n{m} vs rag  (WIN = Holm-significant and >= 3 %, win = significant < 3 %), per area')
    for c in CONDS:
        for W in ('1000', '3000'):
            print(f'  {c:12s} {W} m  {summ[m][c][W]}  range {rng[m][c][W][0]:+.1f} .. {rng[m][c][W][1]:+.1f} %')
print('\nlink transmissions per mission (all attempts), ratio rag / method')
for c in CONDS:
    for W in (1000, 3000):
        r = tx[f'{c}|{W}|rag']
        print(f'  {c:12s} {W} m  rag {r:9.0f}  maqac x{r / tx[f"{c}|{W}|maqac"]:.1f}  maqac_seq x{r / tx[f"{c}|{W}|maqac_seq"]:.1f}')
print('attempts per message', {k: round(v, 2) for k, v in att.items()})
if '-v' in sys.argv:
    for m in out:
        for x in out[m]:
            print(m, x['cond'], int(x['W']), x['scenario'], x['n'], f"{x['mean']:+.1f} [{x['lo']:+.1f},{x['hi']:+.1f}]", x['verdict'])

# LaTeX table for Supplementary Section S7: clear wins / small wins / level / losses vs RAG and range, per area
NAME = {'loss40_arq2': '40\\% independent, 2 retransm.', 'ge20_arq2': None,
        'node20': '20\\% correlated per UAV', 'node40': '40\\% correlated per UAV'}
L = ['\\begin{tabular}{@{}llcccc@{}}', '\\toprule',
     'Loss condition & Rule & 1~km W/w/l/L & range (\\%) & 3~km W/w/l/L & range (\\%) \\\\', '\\midrule']
for c in CONDS:
    if not NAME[c]:
        continue
    for m, lab in (('maqac', 'MAQAC'), ('maqac_seq', 'MAQAC-S')):
        row = [NAME[c] if m == 'maqac' else '', lab]
        for W in ('1000', '3000'):
            k = summ[m][c][W]; r = rng[m][c][W]
            row += [f"{k['WIN']}/{k['win']}/{k['level']}/{k['LOSS']}", f'${r[0]:+.1f}$ to ${r[1]:+.1f}$']
        L.append(' & '.join(row) + ' \\\\')
L += ['\\bottomrule', '\\end{tabular}']
open(ROOT / 'paper' / 'tables' / 'netsim_arq_counts.tex', 'w').write('\n'.join(L) + '\n')

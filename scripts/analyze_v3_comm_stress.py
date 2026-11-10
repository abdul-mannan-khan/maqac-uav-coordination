#!/usr/bin/env python3
"""Analysis of scripts/v3_comm_stress.py as pre-registered there: paired relative difference of J_session for maqac and
maqac_seq (and maqac_rag) vs rag in every condition x cell, 95 % t-interval, Holm over all comparisons of each pair.
The no-stress reference ('none') comes from results/v3_area_rest/netsim_v3_area_rest.jsonl (same seeds).
Output: results/v3_comm_stress_summary.json and a printed table."""
import json, glob, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
rows = []
for f in sorted(glob.glob(str(ROOT / 'results' / 'v3_comm_stress_shard*.jsonl'))):
    rows += [json.loads(l) for l in open(f)]
# Bursty-loss fix (6 Nov 2026): the Gilbert-Elliott state now advances once per round, not once per message, so
# bursts last ~5 s for every method. The corrected ge20 rows replace the old ones.
GEFIX = ROOT / 'results' / 'v3_comm_stress_gefix.jsonl'
if GEFIX.exists() and '--old-ge' not in sys.argv:
    rows = [r for r in rows if r.get('cond') != 'ge20'] + [json.loads(l) for l in open(GEFIX)]
for l in open(ROOT / 'results' / 'v3_area_rest' / 'netsim_v3_area_rest.jsonl'):
    d = json.loads(l)
    if d['method'] in ('rag', 'maqac', 'maqac_seq', 'maqac_rag'):
        rows.append({**d, 'cond': 'none'})
err = [r for r in rows if 'error' in r]
rows = [r for r in rows if 'error' not in r]
J = defaultdict(dict)
msgs = defaultdict(list)
for r in rows:
    J[(r['cond'], r['W'], r['scenario'], r['n'], r['method'])][r['seed']] = r['J_session']
    if r.get('coord_msgs') is not None:
        msgs[(r['cond'], r['W'], r['method'])].append(r['coord_msgs'])
CONDS = ('none', 'loss20', 'ge20', 'loss40', 'k1')
cells = sorted({(r['W'], r['scenario'], r['n']) for r in rows})
out = {}
for m in ('maqac', 'maqac_seq', 'maqac_rag'):
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
summ = {m: {c: {v: sum(1 for x in out[m] if x['cond'] == c and x['verdict'] == v) for v in ('WIN', 'win', 'level', 'LOSS')}
            for c in CONDS} for m in out}
msg = {f'{c}|{int(W)}|{m}': float(np.mean(v)) for (c, W, m), v in msgs.items()}
json.dump(dict(cells=out, counts=summ, msgs_per_round=msg, errors=len(err), missions=len(rows)),
          open(ROOT / 'results' / 'v3_comm_stress_summary.json', 'w'), indent=1)
print(f'missions {len(rows)}, errors {len(err)}')
for m in out:
    print(f'\n{m} vs rag  (WIN = Holm-significant and >= 3 %, win = significant < 3 %)')
    for c in CONDS:
        xs = [x for x in out[m] if x['cond'] == c]
        if xs:
            print(f'  {c:7s} {summ[m][c]}  range {min(x["mean"] for x in xs):+.1f} .. {max(x["mean"] for x in xs):+.1f} %')
if '-v' in sys.argv:
    for m in out:
        for x in out[m]:
            print(m, x['cond'], int(x['W']), x['scenario'], x['n'], f"{x['mean']:+.1f} [{x['lo']:+.1f},{x['hi']:+.1f}]", x['verdict'])

"""Analyse results/netsim_grid.jsonl -> results/netsim_grid_summary.json (+ printed tables).

Per cell: mean, 95 % CI (t), and paired comparisons against MAQAC on identical seeds:
mean relative difference (MAQAC - other)/other, so + means MAQAC is better; paired t-test, Wilcoxon signed-rank, Cohen's d_z, Holm correction within each block.
"""
import json, sys
from collections import defaultdict
import numpy as np
from scipy import stats

IN, OUT = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ('results/netsim_grid.jsonl', 'results/netsim_grid_summary.json')
METRICS = ['qos_score', 'users_served', 'emergency_score', 'mean_wait_s', 'continuity', 'blocked', 'interf_outage',
           'disconnected_uav_s', 'energy_wh', 'score_per_wh', 'collisions', 'near_misses', 'mean_hops',
           'mean_offload_lat_s', 'record_age_s', 'record_coverage']


def ci(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 2:
        return dict(mean=float(x.mean()) if len(x) else None, ci95=None, n=len(x))
    h = stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))
    return dict(mean=float(x.mean()), ci95=float(h), sd=float(x.std(ddof=1)), n=len(x))


def paired(a, b):
    """a = MAQAC, b = other, aligned by seed."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    out = dict(rel_diff=float(d.mean() / b.mean()) if b.mean() else None, mean_diff=float(d.mean()))
    if np.allclose(d, 0):
        return {**out, 'p_t': 1.0, 'p_w': 1.0, 'd_z': 0.0}
    out['p_t'] = float(stats.ttest_rel(a, b).pvalue)
    out['p_w'] = float(stats.wilcoxon(a, b).pvalue)
    out['d_z'] = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else None
    return out


def holm(ps):
    idx = np.argsort(ps); m = len(ps); adj = np.empty(m); run = 0.0
    for r, i in enumerate(idx):
        run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run
    return adj


def main():
    rows = [json.loads(l) for l in open(IN)]
    err = [r for r in rows if 'error' in r]
    rows = [r for r in rows if 'error' not in r]
    cells = defaultdict(lambda: defaultdict(dict))      # cell -> method -> seed -> row
    for r in rows:
        c = (r['block'], r['scenario'], r['n_uav'], r['param'], str(r['value']))
        cells[c][r['method']][r['seed']] = r
    summary = dict(n_episodes=len(rows), n_errors=len(err), errors=[(e['method'], e['error']) for e in err[:20]], cells=[])
    for c in sorted(cells, key=str):
        M = cells[c]
        ent = dict(block=c[0], scenario=c[1], n_uav=c[2], param=c[3], value=c[4], methods={}, vs_maqac={})
        for m, S in M.items():
            ent['methods'][m] = {k: ci([S[s].get(k) if S[s].get(k) is not None else np.nan for s in S]) for k in METRICS}
        if 'maqac' in M:
            for m, S in M.items():
                if m == 'maqac':
                    continue
                seeds = sorted(set(S) & set(M['maqac']))
                if len(seeds) >= 5:
                    ent['vs_maqac'][m] = dict(n=len(seeds), **paired([M['maqac'][s]['qos_score'] for s in seeds],
                                                                    [S[s]['qos_score'] for s in seeds]))
        summary['cells'].append(ent)
    for blk in ('main', 'ablation', 'stress'):                # Holm within block, on the paired t-test
        refs = [(e, m) for e in summary['cells'] if e['block'] == blk for m in e['vs_maqac']]
        if refs:
            adj = holm(np.array([e['vs_maqac'][m]['p_t'] for e, m in refs]))
            for (e, m), p in zip(refs, adj):
                e['vs_maqac'][m]['p_holm'] = float(p)
    json.dump(summary, open(OUT, 'w'), indent=1)
    # printed tables
    print(f"{len(rows)} episodes, {len(err)} errors")
    for blk in ('main', 'ablation', 'stress'):
        print(f'\n== {blk}')
        for e in summary['cells']:
            if e['block'] != blk:
                continue
            tag = f"{e['scenario']:9s} n={e['n_uav']:2d}" + (f" {e['param']}={e['value']}" if e['param'] else '')
            parts = []
            for m, st in e['methods'].items():
                q = st['qos_score']
                v = e['vs_maqac'].get(m)
                sig = '' if v is None else f" ({100 * v['rel_diff']:+.0f}%{'*' if v.get('p_holm', 1) < 0.05 else ''})"
                parts.append(f"{m}={q['mean']:.0f}±{q['ci95'] or 0:.0f}{sig}")
            print(tag, ' | '.join(parts))


if __name__ == '__main__':
    main()

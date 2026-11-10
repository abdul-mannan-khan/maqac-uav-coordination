#!/usr/bin/env python3
"""Table and summary of the realistic-model (v3) study -> paper/tables/netsim_v3.tex, results/netsim_v3_study_summary.json.
Rerun of 2 Nov 2026 (6-DOF and separation fixes): area blocks from results/v3_area_rest/netsim_v3_area_rest.jsonl
plus the 3 km IAD block results/netsim_v3_rerun_iad3k.jsonl; real cities from results/netsim_v3_rerun_cities.jsonl.
The first run (results/netsim_v3_study.jsonl) is not used. Column "MAQAC-S vs RAG" is maqac_seq against rag. Relative differences
(MAQAC - other)/other of J_session, paired over seeds; * = Holm-adjusted paired t-test p < .05 within each cell."""
import json
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
M = ('maqac', 'maqac_seq', 'rag', 'iad', 'potgame', 'he2025', 'central', 'greedy_info', 'systematic', 'static_pad', 'static_grid')
COLS = M[2:]
SHOW = tuple(c for c in COLS if c != 'central')   # Central (full information) is computed, not shown
area = [d for f in ('results/v3_area_rest/netsim_v3_area_rest.jsonl', 'results/netsim_v3_rerun_iad3k.jsonl')
        for d in map(json.loads, open(ROOT / f)) if not isinstance(d['W'], str)]
# He, Liu & Xie (TNSM 2025) baseline: scripts/he2025_runs.py, same seeds, areas only
area += [d for d in map(json.loads, open(ROOT / 'results/he2025_v3_shard0.jsonl')) if d['cond'] == 'none' and 'error' not in d]
cf = ROOT / 'results/netsim_v3_rerun_cities.jsonl'
city = [d for d in map(json.loads, open(cf))] if cf.exists() else []
full_city = len([d for d in city if "error" not in d]) >= 1440      # 12 methods x 2 cities x 3 fleets x 20 seeds
D = area + (city if full_city else [])


def holm(p):
    o = np.argsort(p); adj = np.empty(len(p)); run = 0.0
    for r, i in enumerate(o):
        run = max(run, (len(p) - r) * p[i]); adj[i] = min(1.0, run)
    return adj


def cellstats(rows, key='J_session'):
    J = {m: {d['seed']: d[key] for d in rows if d['method'] == m and 'error' not in d} for m in M}
    a0 = np.array(list(J['maqac'].values()))
    out = dict(maqac_mean=float(a0.mean()), maqac_ci=float(1.96 * a0.std(ddof=1) / np.sqrt(len(a0))), n=len(a0), vs={})
    ps = []
    for m in COLS:
        s = sorted(set(J['maqac']) & set(J[m])); a = np.array([J['maqac'][k] for k in s]); b = np.array([J[m][k] for k in s])
        if len(s) < 2:                              # method not run on this block (He et al. on the real cities)
            out['vs'][m] = dict(rel=float('nan'), p=1.0); ps.append(1.0); continue
        p = float(stats.ttest_rel(a, b).pvalue) if not np.allclose(a, b) else 1.0
        out['vs'][m] = dict(rel=float(a.mean() / b.mean() - 1), p=p); ps.append(p)
    for m, pa in zip(COLS, holm(np.array(ps))):
        out['vs'][m]['p_holm'] = float(pa)
    s = sorted(set(J['maqac_seq']) & set(J['rag']))
    if s:
        a = np.array([J['maqac_seq'][k] for k in s]); b = np.array([J['rag'][k] for k in s])
        out['seq_vs_rag'] = dict(rel=float(a.mean() / b.mean() - 1), p=float(stats.ttest_rel(a, b).pvalue))
    out['contacts'] = {m: float(np.mean([d['collisions'] for d in rows if d['method'] == m])) for m in M
                       if any(d['method'] == m for d in rows)}
    out['qos_vs'] = {m: v['rel'] for m, v in cellstats_q(rows).items()}
    return out


def cellstats_q(rows):
    J = {m: {d['seed']: d['qos_score'] for d in rows if d['method'] == m} for m in M}
    r = {}
    for m in COLS:
        s = sorted(set(J['maqac']) & set(J[m]))
        if not s:
            r[m] = dict(rel=float('nan')); continue
        r[m] = dict(rel=float(np.mean([J['maqac'][k] for k in s]) / np.mean([J[m][k] for k in s]) - 1))
    return r


SC = {'urban': 'Urban', 'suburban': 'Suburban', 'disaster': 'Disaster'}
CITY = {'london_lidar': 'City of London', 'manhattan_nyc': 'Midtown Manhattan'}
blocks = [(1000.0, '1 km $\\times$ 1 km'), (3000.0, '3 km $\\times$ 3 km')]
S = {}


def fmt(v):
    if v['rel'] != v['rel']:
        return '--'
    s = f"{100 * v['rel']:+.0f}".replace('-0', '0').replace('+0', '0').replace('-', '$-$')
    return s + ('$^{*}$' if v['p_holm'] < 0.05 else '')


L = [r'\begin{tabular}{@{}lllrr' + 'r' * len(SHOW) + '@{}}', r'\toprule',
     r'& & & \multicolumn{1}{c}{\textbf{MAQAC}} & \multicolumn{1}{c}{\textbf{MAQAC-S}} & \multicolumn{' + str(len(SHOW)) + r'}{c}{\textbf{MAQAC vs.\ baseline [\%]}} \\ \cmidrule(l){6-' + str(5 + len(SHOW)) + '}',
     r'\textbf{Area} & \textbf{Users} & $n$ & $J_{\mathrm{s}}$ (95\% CI) & vs.\ RAG [\%] & RAG & IAD & Pot.\ game & He et al. & Greedy-info & Systematic & Static pads & Static grid \\', r'\midrule']
for W, lab in blocks:
    first = True
    for sc in ('urban', 'suburban', 'disaster'):
        for k, n in enumerate((4, 6, 8)):
            c = cellstats([d for d in D if d['W'] == W and d['scenario'] == sc and d['n'] == n])
            S[f'{int(W)}_{sc}_{n}'] = c
            L.append((lab if first else '') + ' & ' + (SC[sc] if k == 0 else '') + f" & {n} & ${c['maqac_mean']:.0f}\\pm{c['maqac_ci']:.0f}$ & SEQ{len(S)-1} & "
                     + ' & '.join(fmt(c['vs'][m]) for m in SHOW) + r' \\')
            first = False
    L.append(r'\midrule')
for C, lab in CITY.items():
    for k, n in enumerate((4, 6, 8)):
        rows = [d for d in D if d['W'] == C and d['n'] == n]
        if not rows:
            L.append((lab if k == 0 else '') + f' & Urban & {n} & ' + ' & '.join(['\\tbd{rerun}'] + ['']*(len(SHOW) + 1)) + r' \\'); continue
        c = cellstats(rows); S[f'{C}_urban_{n}'] = c
        L.append((lab if k == 0 else '') + ' & ' + ('Urban' if k == 0 else '') + f" & {n} & ${c['maqac_mean']:.0f}\\pm{c['maqac_ci']:.0f}$ & SEQ{len(S)-1} & "
                 + ' & '.join(fmt(c['vs'][m]) for m in SHOW) + r' \\')
    L.append(r'\midrule' if C == 'london_lidar' else r'\bottomrule')
L.append(r'\end{tabular}')
keys = list(S)                                     # Holm for MAQAC-S vs RAG over all reported cells
pa = holm(np.array([S[k]['seq_vs_rag']['p'] for k in keys]))
for k, x in zip(keys, pa):
    S[k]['seq_vs_rag']['p_holm'] = float(x)
for i in reversed(range(len(keys))):
    L = [l.replace(f'SEQ{i} ', fmt(S[keys[i]]['seq_vs_rag']) + ' ') for l in L]
(ROOT / 'paper/tables/netsim_v3.tex').write_text('\n'.join(L) + '\n')
# Compact main-text version: same cells and marks, only the major columns
# (Area, Users, n, MAQAC J_s, MAQAC-S vs RAG, MAQAC vs RAG, IAD, Pot. game, He et al.); the full table goes to the supplement.
KEEP = 5 + 4                                       # first 5 columns + RAG, IAD, Pot. game, He et al.
C = [r'\setlength{\tabcolsep}{3.5pt}', r'\begin{tabular}{@{}lllrrrrrr@{}}', r'\toprule',
     r'& & & \multicolumn{1}{c}{\textbf{MAQAC}} & \multicolumn{1}{c}{\textbf{MAQAC-S}} & \multicolumn{4}{c}{\textbf{MAQAC vs.\ baseline [\%]}} \\ \cmidrule(l){6-9}',
     r'\textbf{Area} & \textbf{Users} & $n$ & $J_{\mathrm{s}}\pm$CI & vs.\ RAG [\%] & RAG & IAD & Pot.\ game & He et al. \\', r'\midrule']
for l in L[5:]:  # L[0:5] = tabular, toprule, group header, header, midrule
    if '&' in l:
        cells = l.rstrip()[:-2].rstrip().split(' & ') if l.rstrip().endswith(r'\\') else l.split(' & ')
        cells = cells[:KEEP]
        cells[0] = (cells[0].replace('1 km $\\times$ 1 km', '1 km').replace('3 km $\\times$ 3 km', '3 km')
                    .replace('City of London', 'London').replace('Midtown Manhattan', 'Manhattan'))
        C.append(' & '.join(cells) + r' \\')
    else:
        C.append(l)
C[-1] = r'\end{tabular}'
(ROOT / 'paper/tables/netsim_v3_compact.tex').write_text('\n'.join(C) + '\n')
json.dump(dict(n_area=len(area), n_city=len(city), city_from='netsim_v3_study_cities_fix.jsonl', cells=S),
          open(ROOT / 'results/netsim_v3_study_summary.json', 'w'), indent=1)
print('v3 table written; city rows', 'included' if full_city else f'pending ({len(city)}/1440)')

#!/usr/bin/env python3
"""Table of the communication-stress study (scripts/v3_comm_stress.py, analysed by scripts/analyze_v3_comm_stress.py)
-> paper/tables/netsim_commstress.tex. One row per condition x area: RAG's mean J_s over the 9 scenario x fleet cells,
and for MAQAC and MAQAC-S (maqac_seq) the range of the paired difference to RAG over the 9 cells, the number of clear
wins (Holm-significant and >= 3 %) and of significant losses. Run analyze_v3_comm_stress.py first."""
import json, glob
from collections import defaultdict
from pathlib import Path
import numpy as np
from stress_rows import stress_rows, he_rows

ROOT = Path(__file__).resolve().parents[1]
S = json.load(open(ROOT / 'results' / 'v3_comm_stress_summary.json'))
J = defaultdict(list)
for d in stress_rows():
        if d['method'] == 'rag' and 'error' not in d:
            J[(d['cond'], d['W'])].append(d['J_session'])
for l in open(ROOT / 'results' / 'v3_area_rest' / 'netsim_v3_area_rest.jsonl'):
    d = json.loads(l)
    if d['method'] == 'rag':
        J[('none', d['W'])].append(d['J_session'])
# He, Liu & Xie (TNSM 2025): scripts/he2025_runs.py, same seeds; analysed here as in
# analyze_v3_comm_stress.py (paired relative difference vs rag, 95 % t-test, Holm over its 90 comparisons)
from scipy import stats
JJ = defaultdict(dict)
for d in stress_rows() + he_rows():
        if d['method'] in ('rag', 'he2025') and 'error' not in d:
            JJ[(d['cond'], d['W'], d['scenario'], d['n'], d['method'])][d['seed']] = d['J_session']
for l in open(ROOT / 'results' / 'v3_area_rest' / 'netsim_v3_area_rest.jsonl'):
    d = json.loads(l)
    if d['method'] == 'rag':
        JJ[('none', d['W'], d['scenario'], d['n'], 'rag')][d['seed']] = d['J_session']
HE = []
for c in ('none', 'loss20', 'ge20', 'loss40', 'k1'):
    for W in (1000.0, 3000.0):
        for sc in ('urban', 'suburban', 'disaster'):
            for n in (4, 6, 8):
                a, b = JJ[(c, W, sc, n, 'he2025')], JJ[(c, W, sc, n, 'rag')]
                k = sorted(set(a) & set(b))
                x = np.array([100 * (a[q] / b[q] - 1) for q in k])
                HE.append(dict(cond=c, W=W, scenario=sc, n=n, mean=float(x.mean()), p=float(stats.ttest_1samp(x, 0).pvalue)))
ps = np.array([x['p'] for x in HE]); o = np.argsort(ps); adj = np.empty(len(ps)); run = 0.0
for r_, i in enumerate(o):
    run = max(run, (len(ps) - r_) * ps[i]); adj[i] = min(1.0, run)
for x, pa in zip(HE, adj):
    x['p_holm'] = float(pa)
    x['verdict'] = ('WIN' if x['mean'] >= 3 else 'win') if pa < 0.05 and x['mean'] > 0 else ('LOSS' if pa < 0.05 else 'level')
S['cells']['he2025'] = HE
json.dump(HE, open(ROOT / 'results' / 'he2025_v3_vs_rag.json', 'w'), indent=1)
LAB = {'none': 'No stress', 'loss20': 'Loss 20\\%', 'ge20': 'Bursty 20\\%', 'loss40': 'Loss 40\\%',
       'k1': 'One channel'}


def m(x):
    return f'{x:+.1f}'.replace('-', '$-$')


def part(meth, c, W):
    xs = [x for x in S['cells'][meth] if x['cond'] == c and x['W'] == W]
    w = sum(x['verdict'] == 'WIN' for x in xs); lo = sum(x['verdict'] == 'LOSS' for x in xs)
    return f"{m(min(x['mean'] for x in xs))} to {m(max(x['mean'] for x in xs))} & {w} & {lo}"


L = [r'\begin{tabular}{@{}llrrrrrrrrrr@{}}', r'\toprule',
     r'& & \multicolumn{1}{c}{\textbf{RAG}} & \multicolumn{3}{c}{\textbf{MAQAC vs.\ RAG}} & \multicolumn{3}{c}{\textbf{MAQAC-S vs.\ RAG}} & \multicolumn{3}{c}{\textbf{He et al.\ vs.\ RAG}} \\'
     r' \cmidrule(lr){4-6} \cmidrule(lr){7-9} \cmidrule(l){10-12}',
     r'\textbf{Condition} & \textbf{Area} & mean $J_{\mathrm{s}}$ & range [\%] & wins & losses & range [\%] & wins & losses & range [\%] & wins & losses \\',
     r'\midrule']
for c in ('none', 'loss20', 'ge20', 'loss40', 'k1'):
    for k, W in enumerate((1000.0, 3000.0)):
        L.append((LAB[c] if k == 0 else '') + f" & {int(W) // 1000} km & {np.mean(J[(c, W)]):.0f} & "
                 + part('maqac', c, W) + ' & ' + part('maqac_seq', c, W) + ' & ' + part('he2025', c, W) + r' \\')
    L.append(r'\midrule' if c != 'k1' else r'\bottomrule')
L.append(r'\end{tabular}')
(ROOT / 'paper' / 'tables' / 'netsim_commstress.tex').write_text('\n'.join(L) + '\n')
print('\n'.join(L))

# ---- Main-text version: mean J_s of each method per condition and
# area (nine configurations x 20 seeds), best in bold. (User, 9 Nov 2026: count of clear wins dropped from the table.)
JM = defaultdict(list)
for d in stress_rows() + he_rows():
        if 'error' not in d and d['method'] in ('rag', 'maqac', 'maqac_seq', 'he2025'):
            JM[(d['cond'], d['W'], d['method'])].append(d['J_session'])
for l in open(ROOT / 'results' / 'v3_area_rest' / 'netsim_v3_area_rest.jsonl'):
    d = json.loads(l)
    if d['method'] in ('rag', 'maqac', 'maqac_seq'):
        JM[('none', d['W'], d['method'])].append(d['J_session'])
COLS = (('he2025', 'He et al.'), ('rag', 'RAG'), ('maqac', 'MAQAC'), ('maqac_seq', 'MAQAC-S'))
# Coordination messages per round, counted per link (rule of 3 Nov 2026, scripts/make_netsim_tables.py): RAG's log is
# per link; MAQAC-S is logged as broadcasts, so its per-link count is d(d-1)/2 for d UAVs deciding in turn. The
# no-stress reference run did not log messages; results/v3_nostress_msgs.jsonl reruns it.
MSG = defaultdict(list)
_src = stress_rows() + [json.loads(l) for l in open(ROOT / 'results' / 'v3_nostress_msgs.jsonl')]
for d in _src:
    if 'error' in d or d.get('coord_msgs') is None:
        continue
    if d['method'] == 'rag':
        MSG[(d['cond'], d['W'], 'rag', d['n'])].append(d['coord_msgs'])
    elif d['method'] == 'maqac_seq':
        MSG[(d['cond'], d['W'], 'maqac_seq', d['n'])].append(d['coord_iters'] * (d['coord_iters'] - 1) / 2)
def msg_range(c, W, m):
    v = [float(np.mean(MSG[(c, W, m, n)])) for n in (4, 6, 8) if MSG[(c, W, m, n)]]
    return f'{min(v):.0f}--{max(v):.0f}' if len(v) == 3 else '--'
L = [r'\begin{tabular}{@{}llrrrrrr@{}}', r'\toprule',
     r'& & \multicolumn{4}{c}{\textbf{Mean session score $J_{\mathrm{s}}$ }} & \multicolumn{2}{c}{\textbf{Messages per round}} \\ \cmidrule(lr){3-6}\cmidrule(l){7-8}',
     r'\textbf{Condition} & \textbf{Area} & ' + ' & '.join(f'\\textbf{{{n}}}' for _, n in COLS) + r' & \textbf{RAG} & \textbf{MAQAC-S} \\',
     r'\midrule']
for c in ('none', 'loss20', 'ge20', 'loss40', 'k1'):
    for k, W in enumerate((1000.0, 3000.0)):
        v = {m: float(np.mean(JM[(c, W, m)])) for m, _ in COLS if JM[(c, W, m)]}
        best = max(v.values())
        cell = lambda m: ('--' if m not in v else (f'\\textbf{{{v[m]:.0f}}}' if abs(v[m] - best) < 0.5 else f'{v[m]:.0f}'))
        L.append((LAB[c] if k == 0 else '') + f" & {int(W) // 1000} km & " + ' & '.join(cell(m) for m, _ in COLS)
                 + f" & {msg_range(c, W, 'rag')} & {msg_range(c, W, 'maqac_seq')}" + " \\\\")
    L.append(r'\midrule' if c != 'k1' else r'\bottomrule')
L.append(r'\end{tabular}')
(ROOT / 'paper' / 'tables' / 'netsim_commstress_means.tex').write_text('\n'.join(L) + '\n')
print('\n'.join(L))

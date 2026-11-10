#!/usr/bin/env python3
"""Summary of Table 2: per baseline, in how many configurations MAQAC scored significantly
higher, by how much, and how many were level or worse. Reads paper/tables/netsim_main.tex (made by
make_netsim_tables.py) so the two tables always agree. Output: paper/tables/netsim_main_summary.tex"""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'paper', 'tables', 'netsim_main.tex')).read()
names = ['RAG', 'IAD', 'Potential game', 'MAPPO', 'Greedy-info', 'Greedy', 'Systematic']
cells = {k: [] for k in names}
for line in src.splitlines():
    parts = [p.strip() for p in line.rstrip('\\ ').split('&')]
    if len(parts) != 10 or not re.match(r'^\d+$', parts[1]):
        continue
    for k, v in zip(names, parts[3:]):
        if v == '--':
            continue
        sig = '^{*}' in v
        x = float(re.sub(r'\$\^\{\*\}\$|\^\{\*\}|\$', '', v))
        cells[k].append((x, sig))
fmt = lambda x: '0' if x == 0 else f'{x:+.0f}'
rng = lambda xs: '--' if not xs else (fmt(min(xs)) if min(xs) == max(xs) else f'{fmt(min(xs))} to {fmt(max(xs))}')
rows = []
for k in names:
    c = cells[k]
    win = [x for x, s in c if s and x > 0]
    lev = [x for x, s in c if not s]
    worse = [x for x, s in c if s and x < 0]
    rows.append(f'{k} & {len(c)} & {len(win)} & {rng(win)} & {len(lev)} & {rng(lev)} & {len(worse)} \\\\')
out = ['\\begin{tabular}{@{}lrrrrrr@{}}', '\\toprule',
       '& & \\multicolumn{2}{c}{\\textbf{MAQAC significantly better}} & \\multicolumn{2}{c}{\\textbf{Level (n.s.)}} & \\textbf{MAQAC} \\\\',
       '\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}',
       '\\textbf{Baseline} & \\textbf{Configs} & \\textbf{Count} & \\textbf{Difference [\\%]} & \\textbf{Count} & \\textbf{Difference [\\%]} & \\textbf{worse} \\\\',
       '\\midrule'] + rows[:4] + ['\\midrule'] + rows[4:] + ['\\bottomrule', '\\end{tabular}']
p = os.path.join(ROOT, 'paper', 'tables', 'netsim_main_summary.tex')
open(p, 'w').write('\n'.join(out) + '\n')
print('\n'.join(rows)); print('wrote', p)

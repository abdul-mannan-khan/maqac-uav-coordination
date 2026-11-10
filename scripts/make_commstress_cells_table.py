#!/usr/bin/env python3
"""Per-configuration table of the communication-stress study for the Supplementary Material (Section S7):
MAQAC-S vs RAG, mean paired difference of J_s in % for every scenario x fleet (rows) and condition x area (columns),
from results/v3_comm_stress_summary.json (scripts/analyze_v3_comm_stress.py). Bold: clear win (Holm-adjusted
p < 0.05 over the 90 comparisons and at least 3 %). -> paper/tables/netsim_commstress_cells.tex"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = json.load(open(ROOT / 'results' / 'v3_comm_stress_summary.json'))['cells']['maqac_seq']
idx = {(c['cond'], c['W'], c['scenario'], c['n']): c for c in C}
conds = [('loss20', '20\\% loss'), ('ge20', 'bursty 20\\%'), ('loss40', '40\\% loss'), ('k1', 'one channel')]
areas = [(1000.0, '1 km'), (3000.0, '3 km')]
L = ['\\begin{tabular}{@{}ll' + 'r' * 8 + '@{}}', '\\toprule',
     ' & & ' + ' & '.join(f'\\multicolumn{{2}}{{c}}{{{n}}}' for _, n in conds) + ' \\\\',
     ' '.join(f'\\cmidrule(l){{{3 + 2 * i}-{4 + 2 * i}}}' for i in range(4)),
     'Scenario & UAVs & ' + ' & '.join(a for _ in conds for _, a in areas) + ' \\\\', '\\midrule']
for sc in ('urban', 'suburban', 'disaster'):
    for k, n in enumerate((4, 6, 8)):
        row = [sc.capitalize() if k == 0 else '', str(n)]
        for c, _ in conds:
            for W, _ in areas:
                x = idx[(c, W, sc, n)]
                v = f"{x['mean']:+.1f}".replace('-', '$-$')
                row.append(f'\\textbf{{{v}}}' if x['verdict'] == 'WIN' else v)
        L.append(' & '.join(row) + ' \\\\')
    L.append('\\midrule' if sc != 'disaster' else '\\bottomrule')
L.append('\\end{tabular}')
out = ROOT / 'paper' / 'tables' / 'netsim_commstress_cells.tex'
out.write_text('\n'.join(L) + '\n')
print('wrote', out)

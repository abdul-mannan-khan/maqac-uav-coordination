"""Learning curves of the MAPPO baseline (default v4, results/mappo_v4: 5 seeds per fleet size, 3,000 iterations each;
`--v3` draws the old 1,500-iteration runs), validation
every 10 iterations on 32 fixed missions) -> paper/figures/fig_mappo_curves.pdf/png.
Per fleet size: each seed's validation score (thin grey), the mean over the seeds (black) and their min-max band (grey).
The pre-registered saturation rule (scripts/mappo_saturation.py) found no saturation iteration k* for any fleet size,
so no k* line is drawn; the caption states this."""
import json
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

V, CAP = ('v3', 1500) if '--v3' in sys.argv else ('v4', 3000)
plt.rcParams.update({'font.size': 8, 'font.family': 'serif', 'axes.linewidth': 0.6})
fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.2), sharey=False)
for ax, n in zip(axes, (4, 6, 8)):
    runs = []
    for s in range(5):
        cur = [json.loads(l) for l in open(f'results/mappo_{V}/mappo_{n}_s{s}_curve.jsonl')]
        cur = [c for c in cur if c.get('J_val') is not None]
        it = np.array([c['it'] + 1 for c in cur]); v = np.array([c['J_val'] for c in cur])
        runs.append((it, v))
        ax.plot(it, v, lw=0.5, color='0.55', alpha=0.8, label='single seed' if s == 0 else None)
    L = min(len(r[0]) for r in runs)
    grid = runs[0][0][:L]
    M = np.stack([r[1][:L] for r in runs])
    ax.fill_between(grid, M.min(0), M.max(0), color='0.5', alpha=0.25, lw=0, label='range over 5 seeds')
    ax.plot(grid, M.mean(0), color='k', lw=1.0, label='mean over 5 seeds')
    ax.set_title(f'{n} UAVs'); ax.set_xlabel('training iteration'); ax.set_xlim(0, CAP)
    if CAP > 1500:
        ax.axvline(1500, color='0.3', ls=':', lw=0.7, label='first cap (1,500)')
    ax.grid(alpha=0.25, lw=0.4)
    ax.legend(fontsize=6, frameon=False, loc='lower right')
axes[0].set_ylabel('validation score $J$')
fig.tight_layout(pad=0.4)
fig.savefig('paper/figures/fig_mappo_curves.pdf'); fig.savefig('paper/figures/fig_mappo_curves.png', dpi=200)
print('ok')

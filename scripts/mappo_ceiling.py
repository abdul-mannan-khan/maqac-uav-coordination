"""Ceiling estimate for MAPPO v4 (added 10 Nov 2026, user request): fit each seed's validation curve J(k), k >= 500,
with two saturating models, (a) J = A - B*exp(-k/T) and (b) J = A - B*k^(-c), and report the asymptote A relative to
the seed's best validation score. Offline analysis of results/mappo_v4/*_curve.jsonl -> results/mappo_v4_ceiling.json.
An extrapolation, not a measurement. Both models fit equally well (RMSE ~2 at noise level; neither predicts
iterations 2,000-3,000 better from 500-2,000), so the asymptote is not identified; the predicted gain from 3,000 to 6,000
iterations (`*_6000`) is the quantity reported in Supplement S4."""
import json, numpy as np
from scipy.optimize import curve_fit
def fexp(k, A, B, T): return A - B * np.exp(-k / T)
def fpow(k, A, B, c): return A - B * np.power(k, -c)
out = {}
for n in (4, 6, 8):
    for s in range(5):
        cur = [json.loads(l) for l in open(f'results/mappo_v4/mappo_{n}_s{s}_curve.jsonl')]
        cur = [c for c in cur if c.get('J_val') is not None]
        k = np.array([c['it'] + 1 for c in cur], float); v = np.array([c['J_val'] for c in cur])
        m = k >= 500; k, v = k[m], v[m]; best = v.max()
        r = {'best': float(best)}
        try:
            p, _ = curve_fit(fexp, k, v, p0=(best, best * 0.3, 800), bounds=([0, 0, 50], [5 * best, 5 * best, 1e5]), maxfev=20000)
            r['exp'] = 100 * (p[0] / best - 1); r['exp_6000'] = 100 * (fexp(6000, *p) / fexp(3000, *p) - 1)
        except Exception as e: r['exp'] = None
        try:
            p, _ = curve_fit(fpow, k, v, p0=(best * 1.05, best, 0.5), bounds=([0, 0, 0.05], [5 * best, 1e6, 3]), maxfev=20000)
            r['pow'] = 100 * (p[0] / best - 1); r['pow_6000'] = 100 * (fpow(6000, *p) / fpow(3000, *p) - 1); r['pow_c'] = float(p[2])
        except Exception as e: r['pow'] = None
        out[f'{n}_s{s}'] = r
json.dump(out, open('results/mappo_v4_ceiling.json', 'w'), indent=1)
for n in (4, 6, 8):
    for mdl in ('exp', 'pow', 'exp_6000', 'pow_6000'):
        x = [out[f'{n}_s{s}'][mdl] for s in range(5)]
        print(n, mdl, [None if a is None else round(a, 1) for a in x])

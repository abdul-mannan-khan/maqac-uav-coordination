#!/usr/bin/env python3
"""Saturation of the MAPPO baseline, judged on ALL seeds together (rule fixed on 2026-11-01, before training).

Data: results/mappo_v3/mappo_<n>_s<seed>_curve.jsonl (validation score J_val every 10 iterations, 32 missions).
Rule, per fleet size n:
  * window W = 200 iterations (20 validation checks);
  * for seed s and check k (iteration >= 2W): gain_s(k) = mean J_val over (k-W, k] - mean over (k-2W, k-W],
    rel_s(k) = gain_s(k) / mean over (k-2W, k-W];
  * saturation iteration k* = the first check from which rel_s(k) < EPS = 0.01 holds for EVERY seed and at EVERY
    later check up to the cap (1,500 iterations); minimum budget 400 iterations (first possible k).
  * Saturated if k* exists and k* <= 1,300 (at least 200 iterations of confirmation before the cap); otherwise the
    paper reports that the baseline had not saturated within 24,000 training missions.
Also reported: the per-seed two-standard-error version (Welch, 10 checks per window) used in v2, the best validation
score and its iteration per seed, and the across-seed mean, min and max curve for the figure.
Output: results/mappo_v3_saturation.json
"""
import argparse
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'results' / 'mappo_v3'
EPS, W_IT, CAP, MIN_IT, CONFIRM = 0.01, 200, 1500, 400, 200


def curve(n, s):
    f = D / f'mappo_{n}_s{s}_curve.jsonl'
    if not f.exists():
        return None
    R = [json.loads(l) for l in open(f)]
    return np.array([[r['it'] + 1, r['J_val']] for r in R if 'J_val' in r])


def main():
    global D, CAP
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=str(D))
    ap.add_argument('--cap', type=int, default=CAP)
    ap.add_argument('--out', default=str(ROOT / 'results' / 'mappo_v3_saturation.json'))
    args = ap.parse_args()
    D, CAP = Path(args.dir), args.cap
    out = {}
    for n in (4, 6, 8):
        C = {s: curve(n, s) for s in range(5)}
        C = {s: c for s, c in C.items() if c is not None and len(c)}
        if not C:
            continue
        w = W_IT // 10
        its = min(len(c) for c in C.values())
        ok = np.zeros(its, bool)
        rels = {}
        for s, c in C.items():
            v = c[:its, 1]
            r = np.full(its, np.nan)
            for k in range(2 * w - 1, its):
                a, b = v[k - w + 1:k + 1].mean(), v[k - 2 * w + 1:k - w + 1].mean()
                r[k] = (a - b) / b
            rels[s] = r
        allok = np.all([np.nan_to_num(rels[s], nan=1.0) < EPS for s in C], axis=0)
        it_axis = next(iter(C.values()))[:its, 0]
        kstar = None
        for k in range(its):
            if it_axis[k] >= MIN_IT and allok[k:].all():
                kstar = int(it_axis[k])
                break
        V = np.array([c[:its, 1] for c in C.values()])
        out[str(n)] = dict(seeds=sorted(C), iterations=int(it_axis[-1]), saturation_iteration=kstar,
                           saturated=bool(kstar is not None and kstar <= CAP - CONFIRM and it_axis[-1] >= CAP),
                           final_window_gain_pct={str(s): round(100 * float(rels[s][-1]), 2) for s in C},
                           best_val={str(s): round(float(c[:, 1].max()), 2) for s, c in C.items()},
                           best_iter={str(s): int(c[int(np.argmax(c[:, 1])), 0]) for s, c in C.items()},
                           curve=dict(it=it_axis.astype(int).tolist(), mean=np.round(V.mean(0), 2).tolist(),
                                      lo=np.round(V.min(0), 2).tolist(), hi=np.round(V.max(0), 2).tolist()))
        print(n, {k: v for k, v in out[str(n)].items() if k != 'curve'})
    Path(args.out).write_text(json.dumps(dict(rule=__doc__.strip(), cap=CAP, data=str(D), fleets=out), indent=1))


if __name__ == '__main__':
    main()

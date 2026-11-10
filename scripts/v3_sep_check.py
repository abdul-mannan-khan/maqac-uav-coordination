#!/usr/bin/env python3
"""Separation rule of the v3 model: 'first' (first v3 study) vs 'sum' (fix of 2 Nov 2026). Tuning seeds 900-904.
Reports <5 m 3-D contacts and J_session per method. Output results/v3_sep_check.jsonl."""
import json, sys
from multiprocessing import Pool
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402
OUT = ROOT / 'results' / 'v3_sep_check.jsonl'


def job(a):
    W, sc, n, m, s, sep = a
    f = (W / 1000.0) ** 2
    cfg = realistic(scenario=sc, n_uav=n, world=W, n_users=int(200 * f), arrival_rate=0.1 * f, gateway=(W / 2, W / 2),
                    sep_model=sep, name='sep')
    r = run_episode(cfg, m, s, log_rounds=False)
    return dict(W=W, scenario=sc, n=n, method=m, seed=s, sep=sep, **{k: r.get(k) for k in ('J_session', 'qos_score', 'collisions', 'near', 'energy_wh')})


if __name__ == '__main__':
    J = [(1000.0, sc, n, m, s, sep) for sc in ('urban', 'disaster') for n in (6, 8) for m in ('maqac', 'rag', 'central', 'static_pad')
         for s in range(900, 905) for sep in ('first', 'sum')]
    J += [(3000.0, sc, 8, m, s, sep) for sc in ('urban', 'disaster') for m in ('maqac', 'rag') for s in range(900, 903) for sep in ('first', 'sum')]
    J.sort(key=lambda a: -a[0])
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 8) as p, open(OUT, 'w') as f:
        for r in p.imap_unordered(job, J):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
    print('sep check done', flush=True)

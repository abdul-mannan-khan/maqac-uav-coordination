#!/usr/bin/env python3
"""Screen of MAQAC-swap and the stay bonus on TUNING seeds 900-904 only.
Settings fixed before this run: swap threshold eps = 0.01, stay bonus 0.1; nothing is tuned here. rag_stay gives RAG
the same stay bonus (like-for-like). Same cells and config as scripts/v3_hyb_screen.py, so its rag / maqac_seq rows
are the reference. Output results/v3_swap_screen.jsonl."""
import json, sys
from multiprocessing import Pool
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402
OUT = ROOT / 'results' / 'v3_swap_screen.jsonl'
METHODS = ('maqac_swap', 'maqac_seq_stay', 'maqac_swap_stay', 'rag_stay')


def job(a):
    sc, n, m, s = a
    cfg = realistic(scenario=sc, n_uav=n, world=3000.0, n_users=1800, arrival_rate=0.9, gateway=(1500.0, 1500.0), name='hyb')
    r = run_episode(cfg, m, s, log_rounds=False)
    return dict(scenario=sc, n=n, method=m, seed=s, **{k: r.get(k) for k in ('J_session', 'coord_msgs', 'coord_iters', 'swaps_per_round',
                                                                          'collisions', 'episode_time_s')})


if __name__ == '__main__':
    J = [(sc, n, m, s) for sc in ('disaster', 'urban') for n in (4, 6) for m in METHODS for s in range(900, 905)]
    J.sort(key=lambda a: -a[1])
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 8) as p, open(OUT, 'w') as f:
        for r in p.imap_unordered(job, J):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
    print('swap screen done', flush=True)

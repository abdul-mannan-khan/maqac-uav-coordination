#!/usr/bin/env python3
"""Screen of MAQAC-hyb (conflict-triggered RAG re-decision, eps = 0.01 fixed in advance) on TUNING seeds 900-904 only:
does it work as intended on the 3 km cells where simultaneous MAQAC lost to RAG? No parameter is tuned here.
v3 model as in the rerun (sep_model 'sum'). Output results/v3_hyb_screen.jsonl."""
import json, sys
from multiprocessing import Pool
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402
OUT = ROOT / 'results' / 'v3_hyb_screen.jsonl'


def job(a):
    sc, n, m, s = a
    cfg = realistic(scenario=sc, n_uav=n, world=3000.0, n_users=1800, arrival_rate=0.9, gateway=(1500.0, 1500.0), name='hyb')
    r = run_episode(cfg, m, s, log_rounds=False)
    return dict(scenario=sc, n=n, method=m, seed=s, **{k: r.get(k) for k in ('J_session', 'coord_msgs', 'coord_iters', 'conflict_round_share',
                                                                          'conflicted_per_round', 'collisions', 'episode_time_s')})


if __name__ == '__main__':
    J = [(sc, n, m, s) for sc in ('disaster', 'urban') for n in (4, 6) for m in ('rag', 'maqac', 'maqac_seq', 'maqac_hyb') for s in range(900, 905)]
    J.sort(key=lambda a: (a[2] != 'rag', -a[1]))
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 8) as p, open(OUT, 'w') as f:
        for r in p.imap_unordered(job, J):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
    print('hyb screen done', flush=True)

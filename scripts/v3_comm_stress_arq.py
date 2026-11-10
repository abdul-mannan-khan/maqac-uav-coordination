#!/usr/bin/env python3
"""Follow-up to the communication-stress study (scripts/v3_comm_stress.py), removing two limitations of its loss model
: no link-layer retransmissions, and loss independent across links. Fixed before running:
  conditions loss40_arq2  iid loss 0.4 per attempt, up to 2 retransmissions per message
             ge20_arq2    Gilbert-Elliott bursts (mean loss 0.2, mean burst 5 s), up to 2 retransmissions
             node20       loss correlated across links: per-UAV Gilbert-Elliott state (mean burst 5 s), a link is down
                          when either end is bad; average per-link loss 0.2
             node40       the same with average per-link loss 0.4
  methods    rag, maqac, maqac_seq; areas 1 and 3 km; urban, suburban, disaster; 4, 6, 8 UAVs; seeds 20000-20019
  model      link-limited model of Section 6.7 (sim.realistic), identical to v3_comm_stress.py otherwise
  test       paired relative difference of J_session vs rag, Holm over each pair's comparisons (analysis script)
Every attempt is counted (tx_attempts, tx_msgs). Nothing is tuned.
    python3 scripts/v3_comm_stress_arq.py WORKERS [--out results/v3_comm_stress_arq.jsonl] [--shard i/k]
"""
import json, sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402

CONDS = {'loss40_arq2': dict(p_loss=0.4, arq_retx=2),
         'ge20_arq2': dict(p_loss=0.2, loss_model='ge', ge_burst_s=5.0, arq_retx=2),
         'node20': dict(p_loss=0.2, loss_model='node', ge_burst_s=5.0),
         'node40': dict(p_loss=0.4, loss_model='node', ge_burst_s=5.0)}
METHODS = ('rag', 'maqac', 'maqac_seq')
AREAS, SCEN, FLEETS, SEEDS = (1000.0, 3000.0), ('urban', 'suburban', 'disaster'), (4, 6, 8), range(20000, 20020)
KEYS = ('J_session', 'qos_score', 'session_frac_mean', 'users_served', 'continuity', 'coord_msgs', 'coord_iters',
        'record_age_s', 'record_coverage', 'collisions', 'episode_time_s', 'tx_msgs', 'tx_attempts')


def job(a):
    cond, W, sc, n, m, s = a
    f = (W / 1000.0) ** 2
    cfg = realistic(scenario=sc, n_uav=n, world=W, n_users=int(200 * f), arrival_rate=0.1 * f, gateway=(W / 2, W / 2),
                    name=f'v3a_{cond}_{int(W)}_{sc}_{n}', **CONDS[cond])
    try:
        r = run_episode(cfg, m, s, log_rounds=False)
        out = {k: r.get(k) for k in KEYS}
    except Exception as e:
        out = dict(error=repr(e))
    return dict(cond=cond, W=W, scenario=sc, n=n, method=m, seed=s, **out)


if __name__ == '__main__':
    args = sys.argv[1:]
    out = Path(args[args.index('--out') + 1]) if '--out' in args else ROOT / 'results' / 'v3_comm_stress_arq.jsonl'
    workers = int(args[0]) if args and args[0].isdigit() else 8
    done = set()
    if out.exists():
        for l in open(out):
            d = json.loads(l)
            if 'error' not in d:
                done.add((d['cond'], d['W'], d['scenario'], d['n'], d['method'], d['seed']))
    J = [(c, W, sc, n, m, s) for c in CONDS for W in AREAS for sc in SCEN for n in FLEETS for m in METHODS for s in SEEDS]
    if '--cond' in args:                          # e.g. --cond ge20_arq2 (bursty-loss fix rerun, 6 Nov 2026)
        J = [a for a in J if a[0] == args[args.index('--cond') + 1]]
    if '--shard' in args:
        i, k = map(int, args[args.index('--shard') + 1].split('/'))
        J = J[i::k]
    J = [a for a in J if a not in done]
    J.sort(key=lambda a: (-a[1], -a[3]))
    print(f'{len(J)} missions to run', flush=True)
    with Pool(workers) as p, open(out, 'a') as f:
        for r in p.imap_unordered(job, J, chunksize=1):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
    print('comm stress arq done', flush=True)

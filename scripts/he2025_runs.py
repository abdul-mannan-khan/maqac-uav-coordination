#!/usr/bin/env python3
"""He, Liu & Xie (TNSM 2025) baseline on the realistic model v3. Fixed before any run:
the evaluation design of Table 6 (areas 1 and 3 km x urban/suburban/disaster x fleets 4/6/8 x seeds 20000-20019, same
code path as scripts/netsim_v3_study.py --part area_rest) and of Table 7 (conditions loss20, loss40, ge20, k1 as in
scripts/v3_comm_stress.py), method he2025 only; the other methods' rows already exist with the same seeds (paired).
No tuning: src/netsim/baseline_he2025.py fixes every constant from the paper or states the choice. Cities are not
included (their files cannot leave the laptop). Tests: as the existing tables (paired relative difference of
J_session vs rag, 95 % t-interval, Holm over the reported comparisons).
    python3 scripts/he2025_runs.py [workers] [--out FILE] [--shard i/k]
"""
import json, sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402

CONDS = {'none': {}, 'loss20': dict(p_loss=0.2), 'loss40': dict(p_loss=0.4),
         'ge20': dict(p_loss=0.2, loss_model='ge', ge_burst_s=5.0), 'k1': dict(n_channels=1)}
AREAS, SCEN, FLEETS, SEEDS = (1000.0, 3000.0), ('urban', 'suburban', 'disaster'), (4, 6, 8), range(20000, 20020)
KEYS = ('J_session', 'qos_score', 'session_frac_mean', 'users_served', 'users_total', 'continuity', 'coord_msgs',
        'coord_iters', 'record_age_s', 'record_coverage', 'collisions', 'energy_wh', 'episode_time_s')


def job(a):
    cond, W, sc, n, s = a
    f = (W / 1000.0) ** 2
    name = f'v3_{int(W)}_{sc}_{n}' if cond == 'none' else f'v3s_{cond}_{int(W)}_{sc}_{n}'
    cfg = realistic(scenario=sc, n_uav=n, world=W, n_users=int(200 * f), arrival_rate=0.1 * f, gateway=(W / 2, W / 2),
                    name=name, **CONDS[cond])
    try:
        r = run_episode(cfg, 'he2025', s, log_rounds=False)
        out = {k: r.get(k) for k in KEYS}
    except Exception as e:
        out = dict(error=repr(e))
    return dict(cond=cond, W=W, scenario=sc, n=n, method='he2025', seed=s, **out)


if __name__ == '__main__':
    args = sys.argv[1:]
    out = Path(args[args.index('--out') + 1]) if '--out' in args else ROOT / 'results' / 'he2025_v3.jsonl'
    workers = int(args[0]) if args and args[0].isdigit() else 8
    done = set()
    if out.exists():
        for l in open(out):
            d = json.loads(l)
            if 'error' not in d:
                done.add((d['cond'], d['W'], d['scenario'], d['n'], d['seed']))
    J = [(c, W, sc, n, s) for c in CONDS for W in AREAS for sc in SCEN for n in FLEETS for s in SEEDS]
    if '--cond' in args:                              # rerun one condition only (6 Nov: bursty-loss fix)
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
    print('he2025 done', flush=True)

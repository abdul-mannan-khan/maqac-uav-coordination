#!/usr/bin/env python3
"""Communication-stress study on the realistic model v3. Pre-registered 2 Nov 2026, ~22:00 GMT, before any run.

Question: under which operating conditions does MAQAC beat RAG? Hypothesis fixed in advance: RAG needs
every neighbour to hear every in-round choice, so it should degrade under message loss; RAG has no co-channel
exclusion, so it should degrade when spectrum is scarce. MAQAC's simultaneous rule sends no in-round messages.
Design (fixed before running; every cell is reported, wins and losses alike):
  conditions loss20 (iid message loss 0.2 per link and message), loss40 (0.4), ge20 (Gilbert-Elliott bursts, mean
             loss 0.2, mean burst 5 s), k1 (one shared radio channel instead of 3, no loss). The no-stress
             reference is the evaluation run results/v3_area_rest/netsim_v3_area_rest.jsonl (same seeds, same code
             path at p_loss = 0).
  model      sim.realistic() defaults, as in scripts/netsim_v3_study.py; areas 1 km and 3 km; urban, suburban,
             disaster; fleets 4, 6, 8; real cities not included (they cannot leave the laptop)
  methods    rag, maqac, maqac_seq, maqac_rag. Fairness fix made before this run: under loss, maqac_seq's in-turn
             hand-overs face the same per-message loss as RAG's (episode.py), so no method gets lossless messages.
  seeds      20000-20019 (evaluation seeds, paired); no tuning step, nothing is tuned
  test       paired relative difference of J_session, maqac / maqac_seq vs rag; 95 % t-interval; Holm over all
             condition x cell comparisons of each pair. "Beats RAG" = Holm-significant positive difference; >= 3 % is
             called a clear win (the rule used for the area_rest analysis).
Added 9 Nov 2026 (user: show coordination messages in the main-text table): condition 'none' (no loss, 3 channels)
  is run only with --cond none, to log the per-round message counts that the no-stress reference run did not record.
  Its scores must reproduce results/v3_area_rest/netsim_v3_area_rest.jsonl for the same seeds (check, not a new result).
  --methods a,b limits the methods.
Output: results/v3_comm_stress.jsonl (per mission, resumable).
    python3 scripts/v3_comm_stress.py [workers] [--out FILE] [--shard i/k]   (shard: every k-th mission from i)
"""
import json, sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic          # noqa: E402
from episode import run_episode    # noqa: E402

CONDS = {'loss20': dict(p_loss=0.2), 'loss40': dict(p_loss=0.4),
         'ge20': dict(p_loss=0.2, loss_model='ge', ge_burst_s=5.0), 'k1': dict(n_channels=1), 'none': dict()}
METHODS = ('rag', 'maqac', 'maqac_seq', 'maqac_rag')
AREAS, SCEN, FLEETS, SEEDS = (1000.0, 3000.0), ('urban', 'suburban', 'disaster'), (4, 6, 8), range(20000, 20020)
KEYS = ('J_session', 'qos_score', 'session_frac_mean', 'users_served', 'continuity', 'coord_msgs', 'coord_iters',
        'record_age_s', 'record_coverage', 'collisions', 'episode_time_s')


def job(a):
    cond, W, sc, n, m, s = a
    f = (W / 1000.0) ** 2
    cfg = realistic(scenario=sc, n_uav=n, world=W, n_users=int(200 * f), arrival_rate=0.1 * f, gateway=(W / 2, W / 2),
                    name=f'v3s_{cond}_{int(W)}_{sc}_{n}', **CONDS[cond])
    try:
        r = run_episode(cfg, m, s, log_rounds=False)
        out = {k: r.get(k) for k in KEYS}
    except Exception as e:
        out = dict(error=repr(e))
    return dict(cond=cond, W=W, scenario=sc, n=n, method=m, seed=s, **out)


if __name__ == '__main__':
    args = sys.argv[1:]
    out = Path(args[args.index('--out') + 1]) if '--out' in args else ROOT / 'results' / 'v3_comm_stress.jsonl'
    workers = int(args[0]) if args and args[0].isdigit() else 8
    done = set()
    if out.exists():
        for l in open(out):
            d = json.loads(l)
            if 'error' not in d:
                done.add((d['cond'], d['W'], d['scenario'], d['n'], d['method'], d['seed']))
    J = [(c, W, sc, n, m, s) for c in CONDS for W in AREAS for sc in SCEN for n in FLEETS for m in METHODS for s in SEEDS]
    if '--cond' in args:                              # rerun one condition only (6 Nov: bursty-loss fix)
        J = [a for a in J if a[0] == args[args.index('--cond') + 1]]
    else:
        J = [a for a in J if a[0] != 'none']
    if '--methods' in args:
        J = [a for a in J if a[4] in args[args.index('--methods') + 1].split(',')]
    if '--shard' in args:
        i, k = map(int, args[args.index('--shard') + 1].split('/'))
        J = J[i::k]
    J = [a for a in J if a not in done]
    J.sort(key=lambda a: (-a[1], -a[3]))             # long 3 km / large-fleet missions first
    print(f'{len(J)} missions to run', flush=True)
    with Pool(workers) as p, open(out, 'a') as f:
        for r in p.imap_unordered(job, J, chunksize=1):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
    print('comm stress done', flush=True)

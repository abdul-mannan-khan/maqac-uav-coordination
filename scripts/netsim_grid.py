"""Full experiment grid of the network-level simulator (src/netsim).

Blocks (paired seeds: every method in a cell sees the same worlds):
  main     methods x scenario {urban, suburban, disaster} x fleet {2,4,6,8,10}, 30 seeds
  ablation MAQAC variants, urban, fleets {4, 8}, 30 seeds
  stress   one network parameter varied at a time around the urban 6-UAV default, 20 seeds

Each finished episode is appended to results/netsim_grid.jsonl, so an interrupted run resumes where it stopped.
    python3 scripts/netsim_grid.py [--workers 12] [--block main|ablation|stress] [--dry]
"""
import sys, os, json, argparse
sys.path.insert(0, 'src/netsim')
from dataclasses import replace
from multiprocessing import Pool
from sim import NetConfig
from episode import run_episode

OUT = 'results/netsim_grid_fix.jsonl'     # grid with the perception-delay fix (1 Nov 2026); netsim_grid.jsonl = old
MAIN_METHODS = ['maqac', 'maqac_nocc', 'central', 'greedy', 'greedy_info', 'systematic', 'rag', 'iad', 'potgame']
ABL_METHODS = ['maqac', 'maqac_nocc', 'maqac_seq', 'maqac_share', 'maqac_nocons', 'maqac_hard', 'maqac_noconn',
               'maqac_noqos', 'maqac_noprior']
STRESS_METHODS = ['maqac', 'maqac_nocc', 'central', 'greedy', 'greedy_info', 'rag', 'iad', 'potgame']
STRESS = {   # parameter: values (the default is included so each sweep is self-contained)
    'bh_range': [250.0, 350.0, 500.0, 700.0],
    'p_loss': [0.0, 0.1, 0.3, 0.5],
    'n_channels': [1, 2, 3, 4],
    'mobile_frac': [0.0, 0.5, 1.0],
    'p_fail': [0.0, 0.25, 0.5],
    'survival': ['exp', 'weibull', 'deadline'],
    'battery_wh': [20.0, 40.0, 80.0],
    'perception': ['oracle', 'onboard', 'offload'],
    'arrival_rate': [0.05, 0.1, 0.2],
    'bg_load': [0.0, 0.5, 0.9],
    'r_s': [50.0, 100.0, 150.0],          # service radius (modelling choice, sensitivity added 1 Nov 2026)
}


def jobs():
    J = []
    for sc in ('urban', 'suburban', 'disaster'):
        for n in (2, 4, 6, 8, 10):
            for m in MAIN_METHODS:
                for s in range(30):
                    J.append(dict(block='main', scenario=sc, n_uav=n, method=m, seed=20000 + s, param=None, value=None))
    for n in (4, 8):
        for m in ABL_METHODS:
            for s in range(30):
                J.append(dict(block='ablation', scenario='urban', n_uav=n, method=m, seed=20000 + s, param=None, value=None))
    for p, vals in STRESS.items():
        for v in vals:
            for m in STRESS_METHODS:
                for s in range(20):
                    J.append(dict(block='stress', scenario='urban', n_uav=6, method=m, seed=30000 + s, param=p, value=v))
    return J


def key(j):
    return (j['block'], j['scenario'], j['n_uav'], j['method'], j['seed'], j['param'], str(j['value']))


def run(j):
    kw = dict(scenario=j['scenario'], n_uav=j['n_uav'], name=f"{j['block']}_{j['scenario']}_{j['n_uav']}")
    if j['param'] is not None:
        kw[j['param']] = j['value']
    if j['param'] == 'bg_load':                  # background traffic only matters when frames are offloaded
        kw['perception'] = 'offload'
    cfg = replace(NetConfig(), **kw)
    try:
        r = run_episode(cfg, j['method'], j['seed'], log_rounds=False)
    except Exception as e:                       # record and continue; failures are reported by the analysis
        r = dict(error=repr(e))
    r.update(j)
    return r


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--block', default=None)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--methods', default=None)        # comma-separated subset
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args()
    OUT = a.out
    J = [j for j in jobs() if (a.block is None or j['block'] == a.block) and (a.methods is None or j['method'] in a.methods.split(','))]
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            done.add(key(json.loads(line)))
    todo = [j for j in J if key(j) not in done]
    # slow jobs (large fleets) first for better load balance
    todo.sort(key=lambda j: -j['n_uav'])
    print(f'{len(J)} episodes in grid, {len(J) - len(todo)} done, {len(todo)} to run', flush=True)
    if a.dry:
        sys.exit()
    with Pool(a.workers) as p, open(OUT, 'a') as f:
        for i, r in enumerate(p.imap_unordered(run, todo, chunksize=2)):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
            if (i + 1) % 100 == 0:
                print(f'{i + 1}/{len(todo)}', flush=True)
    print('grid finished', flush=True)

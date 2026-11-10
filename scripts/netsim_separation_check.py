#!/usr/bin/env python3
"""When do close approaches between UAVs happen in the network-level simulator?

The simulator counts, every second, UAV pairs closer than 5 m ('collisions') and 5-15 m ('near_misses'). In the
grid these counts were almost identical across methods (about 1, 5 and 10 per mission at 6, 8 and 10 UAVs), which
suggests the take-off from the common 30 m ring around the gateway. This script splits the counts into the first
10 s after take-off and the rest of the mission.

Urban, 6/8/10 UAVs, 5 seeds (30100-30104), T = 900 s. Output: results/netsim_separation_check.json. Light: < 10 min.
"""
import json
import sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import NetConfig          # noqa: E402
from episode import run_episode    # noqa: E402

METHODS = ('maqac', 'rag', 'iad', 'potgame', 'central', 'greedy_info', 'systematic')
FLEETS, SEEDS, T_TAKEOFF = (6, 8, 10), range(30100, 30105), 10


def job(a):
    meth, n, s = a
    snap = {}

    def hook(W, agents, step):
        if step == T_TAKEOFF - 1:
            snap.update(c=W.m['collisions'], nm=W.m['near'])
    r = run_episode(replace(NetConfig(), scenario='urban', n_uav=n), meth, s, log_rounds=False, step_hook=hook)
    return dict(method=meth, n=n, seed=s, coll_takeoff=int(snap['c']), coll_after=int(r['collisions'] - snap['c']),
                near_takeoff=int(snap['nm']), near_after=int(r['near_misses'] - snap['nm']))


def main():
    jobs = [(m, n, s) for m in METHODS for n in FLEETS for s in SEEDS]
    with Pool(6) as p:
        R = p.map(job, jobs)
    summ = {}
    for m in METHODS:
        for n in FLEETS:
            E = [e for e in R if e['method'] == m and e['n'] == n]
            summ[f'{m}_{n}'] = {k: sum(e[k] for e in E) for k in ('coll_takeoff', 'coll_after', 'near_takeoff', 'near_after')}
            summ[f'{m}_{n}']['missions'] = len(E)
            summ[f'{m}_{n}']['missions_with_contact_after_takeoff'] = sum(e['coll_after'] > 0 for e in E)
    out = ROOT / 'results' / 'netsim_separation_check.json'
    out.write_text(json.dumps(dict(note=__doc__.strip().splitlines()[0], summary=summ, rows=R), indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == '__main__':
    main()

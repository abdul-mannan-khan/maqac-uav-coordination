#!/usr/bin/env python3
"""
Empirical check of Theorem 3 on instances small enough to compute OPT exactly.

Setting (matches the theorem's hypotheses):
  * n agents, each owning a partition P_i of candidate cells (partition matroid,
    capacity T cells per agent over the horizon);
  * users with priority weight w and decay mu; a user is served by the first cell
    (in an agent's visiting order) whose footprint contains it;
  * f(S) = sum over served users of w * exp(-mu * t_service), with t_service the
    arrival time of the serving agent (cruise speed, cells visited in order);
  * consensus converged (agents share the served set) and footprints of cells in
    different partitions are disjoint (partitions are separated by > 2R).
  * MAQAC = per-round greedy: each agent adds the cell of its own partition with
    the largest marginal gain against the shared served set.
  * OPT   = exhaustive search over all feasible ordered selections.

Outputs results/bound_verification.json and prints the distribution of
f(MAQAC)/f(OPT); Theorem 3 predicts every ratio >= 0.5.

    python3 scripts/verify_bound_small_instances.py --instances 200
"""
import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
W = {'emergency': 3.0, 'realtime': 2.0, 'besteffort': 1.0}
MU = {'emergency': 0.028, 'realtime': 0.010, 'besteffort': 0.003}
CLASSES = list(W)


def make_instance(rng, n_agents=3, cells_per_agent=4, users_per_agent=8, R=50.0, T=2):
    """Each agent's partition is a separate 300 m strip so footprints never overlap."""
    cells, users, part = [], [], []
    for i in range(n_agents):
        ox = i * 400.0                       # strips 400 m apart > 2R
        cx = rng.uniform(ox + 60, ox + 240, cells_per_agent)
        cy = rng.uniform(60, 240, cells_per_agent)
        start = np.array([ox + 150.0, 0.0])
        for k in range(cells_per_agent):
            cells.append({'agent': i, 'xy': np.array([cx[k], cy[k]]), 'start': start})
            part.append(i)
        for _ in range(users_per_agent):
            k = rng.integers(cells_per_agent)
            ang, rad = rng.uniform(0, 2 * math.pi), rng.uniform(0, R * 0.9)
            c = rng.choice(CLASSES, p=[0.25, 0.30, 0.45])
            users.append({'xy': np.array([cx[k] + rad * math.cos(ang), cy[k] + rad * math.sin(ang)]),
                          'w': W[c], 'mu': MU[c]})
    return cells, users, np.array(part), R, T


def value_of_orders(orders, cells, users, R, v=14.0):
    """orders: dict agent -> list of cell indices in visiting order. Users are served by the
    earliest arrival among all agents' cells that cover them."""
    t_serve = {}
    for i, seq in orders.items():
        t, pos = 0.0, None
        for c in seq:
            xy = cells[c]['xy']
            pos = cells[c]['start'] if pos is None else pos
            t += np.linalg.norm(xy - pos) / v
            pos = xy
            for u, usr in enumerate(users):
                if np.linalg.norm(usr['xy'] - xy) <= R:
                    t_serve[u] = min(t_serve.get(u, math.inf), t)
    return sum(users[u]['w'] * math.exp(-users[u]['mu'] * t) for u, t in t_serve.items())


def maqac_greedy(cells, users, part, R, T):
    n = part.max() + 1
    orders = {i: [] for i in range(n)}
    for _ in range(T):
        base = value_of_orders(orders, cells, users, R)
        for i in range(n):                                  # simultaneous per-round choices
            best, best_c = -1.0, None
            for c in np.where(part == i)[0]:
                if c in orders[i]:
                    continue
                trial = {k: list(v) for k, v in orders.items()}
                trial[i].append(int(c))
                gain = value_of_orders(trial, cells, users, R) - base
                if gain > best:
                    best, best_c = gain, int(c)
            if best_c is not None:
                orders[i].append(best_c)
    return value_of_orders(orders, cells, users, R), orders


def optimum(cells, users, part, R, T):
    n = part.max() + 1
    per_agent = []
    for i in range(n):
        own = [int(c) for c in np.where(part == i)[0]]
        seqs = [list(p) for k in range(1, T + 1) for p in itertools.permutations(own, k)]
        per_agent.append(seqs)
    best = -1.0
    for combo in itertools.product(*per_agent):
        val = value_of_orders({i: combo[i] for i in range(n)}, cells, users, R)
        best = max(best, val)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--instances', type=int, default=200)
    ap.add_argument('--agents', type=int, default=3)
    ap.add_argument('--cells', type=int, default=4)
    ap.add_argument('--horizon', type=int, default=2)
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    ratios = []
    for k in range(a.instances):
        cells, users, part, R, T = make_instance(rng, a.agents, a.cells, T=a.horizon)
        g, _ = maqac_greedy(cells, users, part, R, T)
        o = optimum(cells, users, part, R, T)
        ratios.append(g / o if o > 0 else 1.0)
        if (k + 1) % 25 == 0:
            print(f'  {k + 1}/{a.instances}  min ratio so far {min(ratios):.3f}', flush=True)
    ratios = np.array(ratios)
    out = {'instances': a.instances, 'agents': a.agents, 'cells_per_agent': a.cells, 'horizon': a.horizon,
           'feasible_orders_per_instance': int(sum(math.perm(a.cells, k) for k in range(1, a.horizon + 1)) ** a.agents),
           'ratio_min': float(ratios.min()), 'ratio_mean': float(ratios.mean()), 'ratio_median': float(np.median(ratios)),
           'share_optimal': float((ratios > 0.999).mean()), 'share_below_half': float((ratios < 0.5).mean()),
           'ratios': ratios.round(4).tolist()}
    (ROOT / 'results' / 'bound_verification.json').write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != 'ratios'}, indent=1))


if __name__ == '__main__':
    main()

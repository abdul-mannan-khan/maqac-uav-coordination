#!/usr/bin/env python3
"""
Brute-force checks of the revised MAQAC theory (time-indexed coverage formulation).

Ground set: service events e = (UAV i, target cell c, arrival time tau_e). Event e covers the users inside the
service footprint of c. With b_u = best survival value already secured for user u (0 if never served),
    f(X) = sum_u w_u * max(b_u, max_{e in X, u in F(e)} S_u(tau_e)).
Checks (all on random instances, exact enumeration where an optimum is needed):
  T1  f is monotone submodular for arbitrary event sets (any agents, any times, overlapping footprints).
  T2  per-round guarantee for SIMULTANEOUS selection with soft partition weight alpha in [beta, 1]:
        gain(G) >= beta / (beta + m) * gain(OPT),  m = max number of chosen footprints that cover one user
                                                       and improve it (observable after the round).
  T3  with estimated gains (|est - true| <= eps per event):
        gain(G) >= (beta * gain(OPT) - n (1 + beta) eps) / (beta + m).
  T4  a-posteriori certificate: gain(OPT) <= gain(G) + sum_i max_e Delta(e | X u G).
  T5  hard partition (alpha = 0 outside own Voronoi cell): gain(G) >= 1/(1+m) * gain(OPT restricted to partitions).
  T6  capacity-limited objective (each event serves at most K users, max-weight assignment) is monotone submodular.
  T7  co-channel interference (SINR threshold) can break monotonicity/submodularity (counterexample search).
Run: python3 scripts/verify_theory_v2.py [--instances 300]   (light: < 1 min, < 500 MB)
"""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

W = np.array([3.0, 2.0, 1.0])            # emergency, real-time, best-effort
MU = np.array([0.028, 0.010, 0.003])
V_CRUISE, R_S = 14.0, 50.0
ROOT = Path(__file__).resolve().parents[1]


def make_instance(rng, n_agents, n_cand, n_users=40, area=400.0):
    hot = rng.uniform(50, area - 50, (3, 2))
    k = rng.integers(0, 3, n_users)
    users = np.where(rng.random((n_users, 1)) < 0.6, hot[k] + rng.normal(0, 35, (n_users, 2)),
                     rng.uniform(0, area, (n_users, 2)))
    cls = rng.choice(3, n_users, p=[0.2, 0.3, 0.5])
    w, mu = W[cls], MU[cls]
    t0 = rng.uniform(0, 120)
    b = np.where(rng.random(n_users) < 0.25, np.exp(-mu * rng.uniform(0, t0 + 1e-9, n_users)), 0.0)
    pos = rng.uniform(0, area, (n_agents, 2))
    cand = rng.uniform(0, area, (n_agents, n_cand, 2))
    cand[:, 0] = pos                                           # hovering in place is always a candidate
    tau = t0 + np.linalg.norm(cand - pos[:, None], axis=-1) / V_CRUISE           # (n, C)
    cover = np.linalg.norm(cand[:, :, None] - users[None, None], axis=-1) <= R_S   # (n, C, U)
    val = np.where(cover, np.exp(-mu[None, None] * tau[..., None]), 0.0)           # survival if served by e
    # soft Voronoi weight w.r.t. current positions
    d_all = np.linalg.norm(cand[:, :, None] - pos[None, None], axis=-1)            # (n, C, n)
    own = np.array([[d_all[i, c, i] <= d_all[i, c].min() + 1e-9 for c in range(n_cand)] for i in range(n_agents)])
    return dict(w=w, b=b, val=val, own=own, users=users, cand=cand)


def f_vec(inst, chosen_vals):
    """chosen_vals: (..., U) max survival secured by the chosen events (0 where uncovered)."""
    return (inst['w'] * np.maximum(inst['b'], chosen_vals)).sum(-1)


def gain(inst, picks):
    v = np.max([inst['val'][i, c] for i, c in enumerate(picks)], axis=0)
    return f_vec(inst, v) - f_vec(inst, np.zeros_like(inst['b']))


def marginal(inst, i, base_vals):
    """Delta(e | base) for every candidate of agent i; base_vals (U,) max survival already secured."""
    cur = np.maximum(inst['b'], base_vals)
    return (inst['w'] * np.maximum(0.0, inst['val'][i] - cur)).sum(-1)


def opt_gain(inst, restrict=None):
    n, C, U = inst['val'].shape
    best, arg = -1.0, None
    sets = [np.where(restrict[i])[0] if restrict is not None else np.arange(C) for i in range(n)]
    for combo in itertools.product(*sets):
        g = gain(inst, combo)
        if g > best:
            best, arg = g, combo
    return best, arg


def multiplicity(inst, picks):
    """max over users of #chosen events that cover the user AND improve on b_u."""
    imp = np.array([(inst['val'][i, c] > inst['b']) for i, c in enumerate(picks)])
    return int(max(1, imp.sum(0).max()))


def simultaneous_greedy(inst, alpha_out, est=None):
    n = inst['val'].shape[0]
    picks = []
    zero = np.zeros_like(inst['b'])
    for i in range(n):
        d = marginal(inst, i, zero) if est is None else est[i]
        a = np.where(inst['own'][i], 1.0, alpha_out)
        score = a * d
        if alpha_out == 0.0:
            score = np.where(inst['own'][i], d, -np.inf)
        picks.append(int(np.argmax(score)))
    return picks


def check_rounds(rng, n_inst):
    rec = dict(T2=[], T3=[], T4=[], T5=[])
    viol = dict(T2=0, T3=0, T4=0, T5=0)
    for k in range(n_inst):
        n, C = (3, 20) if k % 2 == 0 else (4, 10)
        inst = make_instance(rng, n, C)
        go, _ = opt_gain(inst)
        if go <= 1e-9:
            continue
        # T2 soft partition, beta = 0.5
        beta = 0.5
        g = simultaneous_greedy(inst, beta)
        gg, m = gain(inst, g), multiplicity(inst, g)
        bound = beta / (beta + m) * go
        rec['T2'].append(dict(ratio=gg / go, bound=beta / (beta + m), m=m))
        viol['T2'] += gg < bound - 1e-9
        # T4 certificate
        vG = np.max([inst['val'][i, c] for i, c in enumerate(g)], axis=0)
        ub = gg + sum(marginal(inst, i, vG).max() for i in range(n))
        rec['T4'].append(dict(ub_over_opt=ub / go))
        viol['T4'] += ub < go - 1e-9
        # T3 noisy estimates
        eps = 0.05 * max(marginal(inst, i, np.zeros_like(inst['b'])).max() for i in range(n))
        zero = np.zeros_like(inst['b'])
        est = [np.maximum(0, marginal(inst, i, zero) + rng.uniform(-eps, eps, C)) for i in range(n)]
        eps_eff = max(np.abs(est[i] - marginal(inst, i, zero)).max() for i in range(n))
        g3 = simultaneous_greedy(inst, beta, est)
        g3g, m3 = gain(inst, g3), multiplicity(inst, g3)
        b3 = (beta * go - n * (1 + beta) * eps_eff) / (beta + m3)
        rec['T3'].append(dict(ratio=g3g / go, bound_ratio=b3 / go))
        viol['T3'] += g3g < b3 - 1e-9
        # T5 hard partition vs partition-restricted optimum
        goh, _ = opt_gain(inst, restrict=inst['own'])
        gh = simultaneous_greedy(inst, 0.0)
        ghg, mh = gain(inst, gh), multiplicity(inst, gh)
        if goh > 1e-9:
            rec['T5'].append(dict(ratio=ghg / goh, bound=1 / (1 + mh), m=mh))
            viol['T5'] += ghg < goh / (1 + mh) - 1e-9
    return rec, viol


def check_stress(rng, n_trials):
    """Tiny adversarial instances (few users, heavy overlap, random alpha in [beta,1]): worst bound slack."""
    worst, viol = np.inf, 0
    for _ in range(n_trials):
        n, C, U = rng.integers(2, 4), rng.integers(2, 5), rng.integers(1, 6)
        w = rng.uniform(0.1, 3, U)
        b = np.where(rng.random(U) < 0.3, rng.uniform(0, 1, U), 0.0)
        val = np.where(rng.random((n, C, U)) < 0.6, rng.uniform(0, 1, (n, C, U)), 0.0)
        beta = rng.uniform(0.1, 1.0)
        alpha = rng.uniform(beta, 1.0, (n, C))
        inst = dict(w=w, b=b, val=val)
        go, _ = opt_gain(inst)
        if go <= 1e-9:
            continue
        zero = np.zeros(U)
        g = [int(np.argmax(alpha[i] * marginal(inst, i, zero))) for i in range(n)]
        gg, m = gain(inst, g), multiplicity(inst, g)
        slack = gg / go - beta / (beta + m)
        worst = min(worst, slack)
        viol += slack < -1e-9
    return int(viol), float(worst)


def check_submodular(rng, n_trials):
    viol_mono = viol_sub = 0
    for _ in range(n_trials):
        inst = make_instance(rng, 4, 15)
        n, C, U = inst['val'].shape
        events = [(i, c) for i in range(n) for c in range(C)]          # any agent, any time, any overlap
        idx = rng.permutation(len(events))
        B = [events[j] for j in idx[: rng.integers(1, 12)]]
        A = [e for e in B if rng.random() < 0.5]
        e = events[idx[-1]]

        def F(S):
            v = np.max([inst['val'][i, c] for i, c in S], axis=0) if S else np.zeros(U)
            return f_vec(inst, v)
        dA, dB = F(A + [e]) - F(A), F(B + [e]) - F(B)
        viol_mono += dA < -1e-12
        viol_sub += dA < dB - 1e-9
    return viol_mono, viol_sub


def check_capacity(rng, n_trials, K=4):
    viol = 0
    for _ in range(n_trials):
        inst = make_instance(rng, 3, 8, n_users=25)
        inst['b'][:] = 0.0
        n, C, U = inst['val'].shape
        events = [(i, c) for i in range(n) for c in range(C)]

        def F(S):
            if not S:
                return 0.0
            cols = np.repeat(np.array([inst['val'][i, c] for i, c in S]), K, axis=0)   # (|S|K, U)
            M = inst['w'][None] * cols
            r, cidx = linear_sum_assignment(-M.T)
            return float(M.T[r, cidx].sum())
        idx = rng.permutation(len(events))
        B = [events[j] for j in idx[: rng.integers(1, 8)]]
        A = [x for x in B if rng.random() < 0.5]
        e = events[idx[-1]]
        viol += (F(A + [e]) - F(A)) < (F(B + [e]) - F(B)) - 1e-9
    return viol


def check_interference(rng, n_trials):
    """Users served iff SINR > threshold from the nearest selected UAV; other UAVs interfere (co-channel)."""
    found_mono = found_sub = 0
    for _ in range(n_trials):
        U, C = 20, 12
        users = rng.uniform(0, 300, (U, 2))
        sites = rng.uniform(0, 300, (C, 2))
        w = rng.choice(W, U)
        d = np.sqrt(np.linalg.norm(sites[:, None] - users[None], axis=-1) ** 2 + 100.0 ** 2)
        p = d ** -2.2

        def F(S):
            if not S:
                return 0.0
            S = list(S)
            P = p[S]
            best = P.max(0)
            sinr = best / (P.sum(0) - best + 1e-13)       # interference-limited regime
            return float((w * (sinr > 1.0)).sum())
        A = list(rng.choice(C, rng.integers(0, 3), replace=False))
        B = list(set(A) | set(rng.choice(C, rng.integers(1, 4), replace=False)))
        e = int(rng.integers(C))
        if e in B:
            continue
        found_mono += F(B + [e]) < F(B) - 1e-9
        found_sub += (F(A + [e]) - F(A)) < (F(B + [e]) - F(B)) - 1e-9
    return found_mono, found_sub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--instances', type=int, default=300)
    ap.add_argument('--seed', type=int, default=2026)
    ap.add_argument('--out', default=str(ROOT / 'results' / 'theory_v2_checks.json'))
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    rec, viol = check_rounds(rng, a.instances)
    vm, vs = check_submodular(rng, 20000)
    vc = check_capacity(rng, 3000)
    im, is_ = check_interference(rng, 5000)
    sv, sw = check_stress(rng, 100000)
    summ = {
        'T1_submodular': dict(trials=20000, monotonicity_violations=int(vm), submodularity_violations=int(vs)),
        'T2_soft_simultaneous': dict(n=len(rec['T2']), violations=int(viol['T2']),
                                     min_ratio=min(r['ratio'] for r in rec['T2']),
                                     mean_ratio=float(np.mean([r['ratio'] for r in rec['T2']])),
                                     m_hist={str(k): sum(r['m'] == k for r in rec['T2']) for k in range(1, 5)}),
        'T3_noisy': dict(n=len(rec['T3']), violations=int(viol['T3']),
                         min_ratio=min(r['ratio'] for r in rec['T3'])),
        'T4_certificate': dict(n=len(rec['T4']), violations=int(viol['T4']),
                               mean_ub_over_opt=float(np.mean([r['ub_over_opt'] for r in rec['T4']])),
                               max_ub_over_opt=max(r['ub_over_opt'] for r in rec['T4'])),
        'T5_hard_partition': dict(n=len(rec['T5']), violations=int(viol['T5']),
                                  min_ratio=min(r['ratio'] for r in rec['T5'])),
        'T2_stress_tiny_adversarial': dict(trials=100000, violations=sv, min_slack_ratio_minus_bound=sw),
        'T6_capacity_submodular': dict(trials=3000, violations=int(vc)),
        'T7_interference_counterexamples': dict(trials=5000, monotonicity=int(im), submodularity=int(is_)),
    }
    print(json.dumps(summ, indent=1))
    Path(a.out).write_text(json.dumps(dict(summary=summ, seed=a.seed), indent=1))


if __name__ == '__main__':
    main()

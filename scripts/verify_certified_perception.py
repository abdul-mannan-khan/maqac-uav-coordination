#!/usr/bin/env python3
"""
Brute-force check of the probabilistic, network-aware guarantee (Theorem "certified coordination").

Per round, UAV i estimates the marginal value of each candidate event from
  * perception: estimated counts yhat[c,k] of class-k users in cell c (a learned model; here a noisy predictor),
  * service records received over the backhaul: users served by another UAV within the last d rounds may be
    missing (stale), so they are still counted as unserved.
True marginal (unserved users only, see paper):  Delta(e) = sum_{c in F(e)} sum_k w_k S_k(tau_e) y[c,k].
Perception score per round (computable on calibration data with ground truth):
  s = max_{i,e} sum_{c in F(e)} sum_k w_k |yhat[c,k] - y[c,k]|.
Split conformal: qhat = ceil((n_cal+1)(1-delta))-th smallest calibration score  =>  P(s_test <= qhat) >= 1-delta.
Network term: eps_N = max_{i,e} sum_{stale users j in F(e)} w_j  (<= w_max * U_F(d)).
Claim:  g(G) >= beta/(beta+m) g(O) - n(1+beta)(qhat+eps_N)/(beta+m)   with probability >= 1-delta.
Also checks the offloading corollary numerically: the bound term with (q_on, d_on) vs (q_off, d_off).
Light: < 2 min, < 300 MB.
"""
import itertools, json, math
from pathlib import Path
import numpy as np

W = np.array([3.0, 2.0, 1.0]); MU = np.array([0.028, 0.010, 0.003])
CELL, R_S, V = 20.0, 50.0, 14.0
G = 15                                                    # 15x15 cells = 300 m x 300 m
ROOT = Path(__file__).resolve().parents[1]
centres = np.stack(np.meshgrid((np.arange(G) + .5) * CELL, (np.arange(G) + .5) * CELL, indexing='ij'), -1).reshape(-1, 2)


def scenario(rng, noise, stale_frac, n=3, C=12):
    hot = rng.uniform(40, 260, (3, 2))
    lam = np.zeros((G * G, 3))
    for h in hot:
        d = np.linalg.norm(centres - h, axis=1)
        lam += np.exp(-(d / 40) ** 2)[:, None] * rng.uniform(0.3, 1.2, 3)
    lam += 0.02
    y = rng.poisson(lam).astype(float)                     # true unserved counts per cell and class
    # learned perception: misses, false positives and a heavy tail
    yhat = np.maximum(0, y + rng.normal(0, noise, y.shape) * (1 + y) + (rng.random(y.shape) < 0.02) * rng.integers(1, 4, y.shape))
    yhat = np.round(yhat)
    # stale records: users actually served but not yet known (counted as unserved by the estimator)
    stale = rng.binomial(rng.poisson(lam * stale_frac).astype(int), 1.0).astype(float)
    pos = rng.uniform(0, G * CELL, (n, 2))
    cand = rng.uniform(0, G * CELL, (n, C, 2)); cand[:, 0] = pos
    t0 = rng.uniform(0, 100)
    tau = t0 + np.linalg.norm(cand - pos[:, None], axis=-1) / V
    F = np.linalg.norm(cand[:, :, None] - centres[None, None], axis=-1) <= R_S       # (n,C,cells)
    S = np.exp(-MU[None, None] * tau[..., None])                                      # (n,C,3)
    return dict(y=y, yhat=yhat, stale=stale, F=F, S=S, n=n, C=C)


def values(sc, counts):
    """per-event value of serving `counts` (cells x classes) -> (n, C, cells, classes) contributions"""
    return sc['F'][..., None] * (W * sc['S'])[:, :, None, :] * counts[None, None]


def gain(sc, picks):
    """joint gain with exact counts: each (cell,class) user served at the earliest covering arrival."""
    best = np.zeros_like(sc['y'])
    for i, c in enumerate(picks):
        best = np.maximum(best, sc['F'][i, c][:, None] * sc['S'][i, c][None, :])
    return float((W * best * sc['y']).sum())


def run(seed=7, n_cal=300, n_test=400, delta=0.1, beta=0.5, noise=0.25, stale_frac=0.05):
    rng = np.random.default_rng(seed)
    def score(sc):
        return float((sc['F'][..., None] * W * np.abs(sc['yhat'] - sc['y'])[None, None]).sum((-1, -2)).max())
    cal = [score(scenario(rng, noise, stale_frac)) for _ in range(n_cal)]
    qhat = float(np.sort(cal)[min(n_cal - 1, math.ceil((n_cal + 1) * (1 - delta)) - 1)])
    cover = viol = viol_given_cover = 0
    ratios, bound_ratios, ms = [], [], []
    for _ in range(n_test):
        sc = scenario(rng, noise, stale_frac)
        s = score(sc)
        cover += s <= qhat
        # estimator used by the UAVs: perceived counts + stale users still believed unserved
        est_counts = sc['yhat'] + sc['stale']
        D_true = values(sc, sc['y']).sum((-1, -2))                                   # (n,C)
        D_hat = values(sc, est_counts).sum((-1, -2))
        eps_N = float((sc['F'][..., None] * W * sc['stale'][None, None]).sum((-1, -2)).max())
        own = np.zeros_like(D_hat, dtype=bool)                                       # soft partition: own half
        for i in range(sc['n']):
            own[i] = np.linalg.norm(np.ones(1)) > 0                                  # placeholder all-own
        alpha = np.where(rng.random(D_hat.shape) < 0.5, 1.0, beta)                   # arbitrary weights in [beta,1]
        picks = [int(np.argmax(alpha[i] * D_hat[i])) for i in range(sc['n'])]
        gG = gain(sc, picks)
        gO = max(gain(sc, p) for p in itertools.product(range(sc['C']), repeat=sc['n']))
        improv = np.array([sc['F'][i, c] for i, c in enumerate(picks)]) & (sc['y'].sum(1) > 0)[None]
        m = int(max(1, improv.sum(0).max()))
        eps_total = qhat + eps_N
        bound = beta / (beta + m) * gO - sc['n'] * (1 + beta) * eps_total / (beta + m)
        ok = gG >= bound - 1e-9
        viol += not ok
        if s <= qhat:
            viol_given_cover += not ok
        ratios.append(gG / gO if gO > 0 else 1.0); bound_ratios.append(bound / gO if gO > 0 else 0); ms.append(m)
    return dict(delta=delta, qhat=qhat, coverage=cover / n_test, violations=viol, violations_when_covered=viol_given_cover,
                n_test=n_test, mean_ratio=float(np.mean(ratios)), min_ratio=float(np.min(ratios)),
                mean_bound_ratio=float(np.mean(bound_ratios)), m_mean=float(np.mean(ms)))


def gain_counts(sc, picks, counts):
    best = np.zeros_like(counts)
    for i, c in enumerate(picks):
        best = np.maximum(best, sc['F'][i, c][:, None] * sc['S'][i, c][None, :])
    return float((W * best * counts).sum()), best


def certificate(sc, picks, counts):
    """rho = g(G) / (g(G) + sum_i max_e Delta(e | G)), all evaluated with `counts`; rho <= g(G)/g(O)."""
    gG, best = gain_counts(sc, picks, counts)
    tot = gG
    for i in range(sc['n']):
        inc = np.maximum(0.0, sc['F'][i][..., None] * sc['S'][i][:, None, :] - best[None]) * W * counts[None]
        tot += float(inc.sum((-1, -2)).max())
    return gG / tot if tot > 0 else 1.0


def conformal_certificate(seed=21, n_cal=300, n_test=300, delta=0.1, beta=0.5, noise=0.25, stale_frac=0.05):
    """Calibrate s = rho_hat - rho_true; then P(true ratio >= rho_hat - qhat) >= 1 - delta."""
    rng = np.random.default_rng(seed)
    def one():
        sc = scenario(rng, noise, stale_frac)
        est = sc['yhat'] + sc['stale']
        D_hat = values(sc, est).sum((-1, -2))
        alpha = np.where(rng.random(D_hat.shape) < 0.5, 1.0, beta)
        picks = [int(np.argmax(alpha[i] * D_hat[i])) for i in range(sc['n'])]
        return sc, picks, certificate(sc, picks, est), certificate(sc, picks, sc['y'])
    cal = []
    for _ in range(n_cal):
        _, _, rh, rt = one(); cal.append(rh - rt)
    qhat = float(np.sort(cal)[min(n_cal - 1, math.ceil((n_cal + 1) * (1 - delta)) - 1)])
    hits, cert, true_r = 0, [], []
    for _ in range(n_test):
        sc, picks, rh, rt = one()
        gG = gain(sc, picks)
        gO = max(gain(sc, p) for p in itertools.product(range(sc['C']), repeat=sc['n']))
        r = gG / gO if gO > 0 else 1.0
        hits += r >= rh - qhat - 1e-12
        cert.append(rh - qhat); true_r.append(r)
    return dict(delta=delta, noise=noise, stale_frac=stale_frac, qhat=qhat, coverage=hits / n_test,
                mean_certified_ratio=float(np.mean(cert)), mean_true_ratio=float(np.mean(true_r)),
                p10_certified=float(np.percentile(cert, 10)))


def offload_rule():
    """Corollary: bound penalty n(1+beta)(q + w_max*U_F(d))/(beta+m); compare on-board vs offload."""
    rng = np.random.default_rng(3)
    out = {}
    for name, noise, stale in (('onboard_small_model', 0.40, 0.03), ('offload_large_model', 0.15, 0.12)):
        r = run(seed=11, n_cal=200, n_test=150, noise=noise, stale_frac=stale)
        out[name] = dict(qhat=r['qhat'], mean_bound_ratio=r['mean_bound_ratio'], mean_ratio=r['mean_ratio'],
                         coverage=r['coverage'], violations=r['violations'])
    return out


if __name__ == '__main__':
    res = {f'delta={d}': run(delta=d) for d in (0.1, 0.05)}
    res['offload_vs_onboard'] = offload_rule()
    res['conformal_certificate'] = {
        'delta=0.1': conformal_certificate(delta=0.1),
        'delta=0.05': conformal_certificate(delta=0.05),
        'onboard_small_model(noise .40, stale .03)': conformal_certificate(noise=0.40, stale_frac=0.03),
        'offload_large_model(noise .15, stale .12)': conformal_certificate(noise=0.15, stale_frac=0.12),
        'offload_congested(noise .15, stale .30)': conformal_certificate(noise=0.15, stale_frac=0.30),
    }
    print(json.dumps(res, indent=1))
    (ROOT / 'results' / 'certified_perception_checks.json').write_text(json.dumps(res, indent=1))

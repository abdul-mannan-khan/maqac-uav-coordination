"""PAC (calibration-conditional) version (allowed miss rate eps here = eta in the manuscript) of the mission-level certificate, by Learn-then-Test
(Angelopoulos et al., Ann. Appl. Stat. 2025), as in the companion wind-dispatch paper.
Margin q is certified if the exact binomial test rejects H0: P(R < rho_hat - q) > eps at level delta.
Candidate margins are tested from the largest (safest) down; the miscoverage is monotone in q, so fixed-sequence
testing needs no multiplicity correction. Choosing on-board vs offload after calibration: each at delta/2 (Bonferroni).
Re-analyses results/netsim_mission_certificate.pkl; no new simulation."""
import pickle, json
import numpy as np
from scipy.stats import binom
R = pickle.load(open('results/netsim_mission_certificate.pkl', 'rb'))
EPS, DELTA, NCAL, REPS = 0.10, 0.10, 40, 200
rng = np.random.default_rng(0)

def ltt_margin(rh, Re, eps, delta):
    s = rh - Re
    prev = np.inf                     # no margin certified (too few missions: N < log(delta)/log(1-eps)) -> vacuous
    for q in np.sort(np.unique(np.r_[s, s.max() + 1e-9]))[::-1]:     # largest margin first
        k = int(np.sum(Re < rh - q))
        if binom.cdf(k, len(s), eps) > delta:                       # not certified -> stop
            return prev
        prev = q
    return prev

out = {}
for k in ('oracle', 'onboard', 'offload', 'offload_congested'):
    E = [r for r in R if r['k'] == k]
    rh = np.array([e['gh'] / e['ubh'] for e in E]); Re = np.array([e['g'] / e['ubh'] for e in E])
    res = {}
    for name, d in (('ltt', DELTA), ('ltt_bonf', DELTA / 2)):
        miss, cert, qs = [], [], []
        for _ in range(REPS):
            idx = rng.permutation(len(E)); c, t = idx[:NCAL], idx[NCAL:]
            q = ltt_margin(rh[c], Re[c], EPS, d)
            miss.append(np.mean(Re[t] < rh[t] - q)); cert.append(np.mean(np.maximum(rh[t] - q, 0))); qs.append(q)
        miss = np.array(miss)
        res[name] = dict(delta=d, q=float(np.mean(qs)), certified=float(np.mean(cert)),
                         test_miscoverage=float(miss.mean()), frac_splits_miscov_gt_eps=float(np.mean(miss > EPS)))
    out[k] = res
    print(k, {n: {a: round(b, 3) for a, b in v.items()} for n, v in res.items()})
json.dump(dict(eps=EPS, delta=DELTA, n_cal=NCAL, reps=REPS, results=out), open('results/netsim_certificate_ltt.json', 'w'), indent=1)

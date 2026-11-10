#!/usr/bin/env python3
"""Certificate transfer test on PX4-flown missions (limitation E, user 5 Nov 2026). Learn-then-Test margin q at
eta = delta = 0.1 (scripts/netsim_certificate_ltt.py: ltt_margin) calibrated on the 80 kinematic calibration missions
(scripts/airsim_cert_calibrate.py, seeds 31000-31079), then applied unchanged to the flown test missions
(results/airsim/cert_campaign/runs/cert_*; PX4 run and its kinematic twin, seeds 20000-20019). A miss is a mission whose
realised fraction R = g / UB_hat falls below rho_hat - q. Miss rate with a one-sided Clopper-Pearson 95 % upper bound.
Output: results/airsim_cert_summary.json
Re-fly (6-7 Nov 2026): --refly uses results/airsim/refly_campaign/runs/ko_cert_* (planner keep-out over C264, AirSim
under Wine on Vast) -> results/airsim_cert_refly_summary.json. Same calibration missions and margin."""
import json, glob, sys
from pathlib import Path
import numpy as np
from scipy.stats import binom, beta
ROOT = Path(__file__).resolve().parents[1]
EPS = DELTA = 0.10


def ltt_margin(rh, Re, eps, delta):
    s = rh - Re; prev = np.inf
    for q in np.sort(np.unique(np.r_[s, s.max() + 1e-9]))[::-1]:
        k = int(np.sum(Re < rh - q))
        if binom.cdf(k, len(s), eps) > delta:
            return prev
        prev = q
    return prev


def cp_upper(k, n, a=0.05):
    return 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))


cal = [json.loads(l) for l in open(ROOT / 'results/airsim/cert_campaign/runs/cert_calibration.jsonl')]
rh_c = np.array([c['gh'] / c['ubh'] for c in cal]); R_c = np.array([c['g'] / c['ubh'] for c in cal])
q = ltt_margin(rh_c, R_c, EPS, DELTA)
out = dict(eta=EPS, delta=DELTA, n_cal=len(cal), q=float(q), cal_rho_hat=float(rh_c.mean()), cal_R=float(R_c.mean()))
REFLY = '--refly' in sys.argv
runs = sorted(glob.glob(str(ROOT / ('results/airsim/refly_campaign/runs/ko_cert_*/result.json' if REFLY else 'results/airsim/cert_campaign/runs/cert_*/result.json'))))
for kind in ('px4', 'kinematic'):
    rh, R, contact = [], [], []
    for f in runs:
        r = json.load(open(f)); c = r['cert'][kind]
        rh.append(c['gh'] / c['ubh']); R.append(c['g'] / c['ubh']); contact.append(bool(r.get('collisions_in_flight')))
    rh, R = np.array(rh), np.array(R); miss = R < rh - q; k = int(miss.sum())
    out[kind] = dict(missions=len(R), rho_hat=float(rh.mean()), R=float(R.mean()), certified=float(np.maximum(rh - q, 0).mean()),
                     misses=k, miss_rate=k / len(R), cp95_upper=cp_upper(k, len(R)),
                     slack_min=float((R - (rh - q)).min()), building_contact_missions=int(sum(contact)) if kind == 'px4' else None)
json.dump(out, open(ROOT / ('results/airsim_cert_refly_summary.json' if REFLY else 'results/airsim_cert_summary.json'), 'w'), indent=1)
print(json.dumps(out, indent=1))

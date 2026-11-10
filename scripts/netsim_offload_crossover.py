#!/usr/bin/env python3
"""Certified offload crossover and held-out calibration (Sec. 7.7), pre-registered 1 Nov 2026.

Part A, crossover: where does offloading perception stop paying, judged by the certificate of Cor. 10?
  MAQAC, urban, 4 UAVs, T = 600 s, 80 missions per configuration (seeds 6000-6079, disjoint from all other studies).
  Backhaul regimes: bandwidth bh_bw_mhz in {40, 10, 4, 2} x background load bg_load in {0, 0.9} (8 regimes).
  Perception: 'onboard' (pd 0.80), 'onboard_good' (pd 0.90, sigma 3 m, class acc. 0.85, 0.3 FP; a better on-board
  detector) and 'offload' (frames over the backhaul). 3 x 8 x 80 = 1,920 missions.
  Per regime and mode: Learn-then-Test margin at eta = 0.1, delta/2 = 0.05 on 40 calibration missions, evaluated on the
  other 40, over 200 random splits; the certified fraction is rho_hat - q_hat. Cor. 10 chooses the mode with the larger
  certified fraction (offload vs the on-board detector of the same row).
Part B, held-out calibration: calibrate on the 80 urban missions of the existing certificate study
  (results/netsim_mission_certificate.pkl, seeds 5000-5079) and test on suburban and disaster missions
  (80 each per perception mode, seeds 7000-7079): miss rate of the urban-calibrated margin on the new scenario, with a
  Clopper-Pearson 95 % interval, against the allowed eta = 0.1. 2 x 3 x 80 = 480 missions.
Output: results/netsim_offload_crossover.pkl (per mission) and .json (summary).
"""
import json, pickle, sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from scipy.stats import binom, beta as betad

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
import sim                                   # noqa: E402
from sim import NetConfig                    # noqa: E402
from episode import run_episode              # noqa: E402

sim.PERCEPTION['onboard_good'] = dict(pd=0.90, sigma=3.0, pcls=0.85, fp=0.3, lat=0.5)
EPS, DELTA, NCAL, REPS = 0.10, 0.10, 40, 200
BW, LOAD, MODES = (40.0, 10.0, 4.0, 2.0), (0.0, 0.9), ('onboard', 'onboard_good', 'offload')


def job(a):
    part, scen, mode, bw, load, s = a
    cfg = replace(NetConfig(T=600), scenario=scen, perception=mode, bh_bw_mhz=bw, bg_load=load)
    r = run_episode(cfg, 'maqac', s)
    rr = [x for x in r['rounds'] if 'g_hat_full' in x]
    return dict(part=part, scen=scen, mode=mode, bw=bw, load=load, seed=s, J=r['qos_score'],
                gh=sum(x['g_hat_full'] for x in rr), ubh=sum(x['ub_hat_full'] for x in rr),
                g=sum(x['g_full'] for x in rr), lat=r['mean_offload_lat_s'], disc=r['disconnected_uav_s'])


def ltt_margin(rh, Re, eps, delta):
    s = rh - Re
    prev = np.inf
    for q in np.sort(np.unique(np.r_[s, s.max() + 1e-9]))[::-1]:
        if binom.cdf(int(np.sum(Re < rh - q)), len(s), eps) > delta:
            return prev
        prev = q
    return prev


def fr(E):
    return np.array([e['gh'] / e['ubh'] for e in E]), np.array([e['g'] / e['ubh'] for e in E])


def cp(k, n):
    return [float(betad.ppf(0.025, k, n - k + 1)) if k else 0.0, float(betad.ppf(0.975, k + 1, n - k)) if k < n else 1.0]


def main():
    jobs = [('A', 'urban', m, bw, ld, 6000 + s) for m in MODES for bw in BW for ld in LOAD for s in range(80)]
    jobs += [('B', sc, m, 40.0, 0.0, 7000 + s) for sc in ('suburban', 'disaster') for m in ('oracle', 'onboard', 'offload')
             for s in range(80)]
    out_pkl = ROOT / 'results' / 'netsim_offload_crossover.pkl'
    done = pickle.load(open(out_pkl, 'rb')) if out_pkl.exists() else []
    key = lambda r: (r['part'], r['scen'], r['mode'], r['bw'], r['load'], r['seed'])
    have = {key(r) for r in done}
    todo = [j for j in jobs if j not in have]
    with Pool(8) as p:
        for k, r in enumerate(p.imap_unordered(job, todo, chunksize=2)):
            done.append(r)
            if k % 40 == 0:
                pickle.dump(done, open(out_pkl, 'wb'))
    pickle.dump(done, open(out_pkl, 'wb'))
    rng = np.random.default_rng(0)
    summ = dict(A={}, B={})
    for bw in BW:
        for ld in LOAD:
            row = {}
            for m in MODES:
                E = [r for r in done if r['part'] == 'A' and r['mode'] == m and r['bw'] == bw and r['load'] == ld]
                rh, Re = fr(E)
                cert, miss = [], []
                for _ in range(REPS):
                    idx = rng.permutation(len(E)); c, t = idx[:NCAL], idx[NCAL:]
                    q = ltt_margin(rh[c], Re[c], EPS, DELTA / 2)
                    cert.append(np.mean(np.maximum(rh[t] - q, 0))); miss.append(np.mean(Re[t] < rh[t] - q))
                row[m] = dict(J=float(np.mean([e['J'] for e in E])), rho_hat=float(rh.mean()), R=float(Re.mean()),
                              certified=float(np.mean(cert)), miss=float(np.mean(miss)),
                              frac_splits_miss_gt_eta=float(np.mean(np.array(miss) > EPS)),
                              lat_s=float(np.nanmean([e['lat'] if e['lat'] is not None else np.nan for e in E]))
                              if m == 'offload' else None)
            row['choice_vs_onboard'] = 'offload' if row['offload']['certified'] > row['onboard']['certified'] else 'onboard'
            row['choice_vs_onboard_good'] = 'offload' if row['offload']['certified'] > row['onboard_good']['certified'] else 'onboard_good'
            summ['A'][f'bw{bw:g}_load{ld:g}'] = row
    U = pickle.load(open(ROOT / 'results' / 'netsim_mission_certificate.pkl', 'rb'))
    for m in ('oracle', 'onboard', 'offload'):
        Eu = [r for r in U if r['k'] == m]
        rhu, Reu = fr(Eu)
        q = ltt_margin(rhu, Reu, EPS, DELTA / 2)
        for sc in ('suburban', 'disaster'):
            E = [r for r in done if r['part'] == 'B' and r['scen'] == sc and r['mode'] == m]
            rh, Re = fr(E)
            k = int(np.sum(Re < rh - q))
            summ['B'][f'{sc}_{m}'] = dict(q_urban=float(q), miss=k / len(E), miss_cp95=cp(k, len(E)), n=len(E),
                                          certified=float(np.mean(np.maximum(rh - q, 0))), R=float(Re.mean()),
                                          J=float(np.mean([e['J'] for e in E])))
    (ROOT / 'results' / 'netsim_offload_crossover.json').write_text(json.dumps(dict(note=__doc__.strip(), **summ), indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == '__main__':
    main()

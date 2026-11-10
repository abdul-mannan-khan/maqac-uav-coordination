"""Mission-level (episode) conformal certificate: score s = rho_hat_ep - R_ep,
rho_hat_ep = sum_k g_hat_k / sum_k UB_hat_k (belief), R_ep = sum_k g_true_k / sum_k UB_hat_k (realised)."""
import sys, json, pickle
sys.path.insert(0, 'src/netsim')
from dataclasses import replace
import numpy as np
from multiprocessing import Pool
from sim import NetConfig
from episode import run_episode
CF = {'oracle': dict(perception='oracle'), 'onboard': dict(perception='onboard'),
      'offload': dict(perception='offload'), 'offload_congested': dict(perception='offload', bg_load=0.9)}
def job(a):
    k, s = a
    r = run_episode(replace(NetConfig(T=600), **CF[k]), 'maqac', s)
    rr = [x for x in r['rounds'] if 'g_hat_full' in x]
    return dict(k=k, seed=s, J=r['qos_score'], gh=sum(x['g_hat_full'] for x in rr), ubh=sum(x['ub_hat_full'] for x in rr),
                g=sum(x['g_full'] for x in rr), ub=sum(x['ub_full'] for x in rr), lat=r['mean_offload_lat_s'])
jobs = [(k, 5000 + s) for k in CF for s in range(80)]
with Pool(12) as p: R = p.map(job, jobs)
pickle.dump(R, open('results/netsim_mission_certificate.pkl', 'wb'))
rng = np.random.default_rng(0)
for k in CF:
    E = [r for r in R if r['k'] == k]
    rh = np.array([e['gh'] / e['ubh'] for e in E]); Re = np.array([e['g'] / e['ubh'] for e in E])
    covs, certs, qs = [], [], []
    for rep in range(200):                    # random calibration/test splits
        idx = rng.permutation(len(E)); c, t = idx[:40], idx[40:]
        sc = np.sort(rh[c] - Re[c]); q = sc[int(np.ceil(41 * 0.9)) - 1]
        covs.append(np.mean(Re[t] >= rh[t] - q)); certs.append(np.mean(rh[t] - q)); qs.append(q)
    print(f"{k:18s} J={np.mean([e['J'] for e in E]):6.1f} rho_hat_ep={rh.mean():.3f} realised={Re.mean():.3f}±{Re.std():.3f} "
          f"q90={np.mean(qs):.3f} certified={np.mean(certs):.3f} coverage={np.mean(covs):.3f} lat={np.nanmean([e['lat'] or np.nan for e in E]):.2f}s")

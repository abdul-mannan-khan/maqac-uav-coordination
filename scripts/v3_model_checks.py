#!/usr/bin/env python3
"""Component checks of the realistic (v3) network-simulator model, sim.realistic(). Each check compares the model with
the value its parameters imply. Output: results/v3_model_checks.json.

    python3 scripts/v3_model_checks.py
"""
import json, math, sys
from dataclasses import replace
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
from sim import realistic, World, propulsion_power, plos_a2g, pathloss_a2g, A2G_ENV, City   # noqa: E402
from episode import run_episode   # noqa: E402

OUT = ROOT / 'results' / 'v3_model_checks.json'


def coverage_radius():
    """Distance at which the mean SNR (P_LOS-weighted path loss) falls to the 5 dB admission threshold, UAV at 100 m."""
    c = realistic()
    noise = -174 + 10 * math.log10(c.bw_mhz * 1e6) + c.nf_db
    d = np.arange(10.0, 5000.0, 5.0)
    d3 = np.hypot(d, c.altitude - 1.5)
    out = {}
    for env in A2G_ENV:
        p = plos_a2g(d, c.altitude, env)
        pl = p * pathloss_a2g(d3, True, c.f_ghz, env) + (1 - p) * pathloss_a2g(d3, False, c.f_ghz, env)
        snr = c.tx_dbm - pl - noise
        out[env] = float(d[np.where(snr >= c.gamma_db)[0][-1]])
    return out


def energy():
    c = realistic()
    ph = float(propulsion_power(0.0, c.weight_n, c.rotor_area))
    pc = float(propulsion_power(c.speed, c.weight_n, c.rotor_area))
    return dict(hover_w=round(ph, 1), cruise_w_at_14ms=round(pc, 1),
                hover_endurance_min=round(c.battery_wh / (ph + c.p_comm_w) * 60, 1),
                old_model_hover_w=round(float(propulsion_power(0.0)), 1))


def kinematics():
    """Take-off time, acceleration and staggering, from a 120 s mission of 4 UAVs that only hover over their pads."""
    c = realistic(n_uav=4, T=120)
    alt, t_mission = [], {}

    def hook(W, agents, step):
        alt.append(W.ualt.copy())
        for i in range(c.n_uav):
            if W.mode[i] == 0 and i not in t_mission:
                t_mission[i] = step
    run_episode(c, 'static_pad', 900, log_rounds=False, step_hook=hook)
    # acceleration: a UAV starting at rest towards a target 500 m away
    W = World(replace(c, takeoff=False, gnss_sigma=0.0), 900)
    W.upos[:] = [[0.0, 500.0], [0.0, 800.0], [0.0, 200.0], [0.0, 950.0]]
    v = []
    for t in range(10):
        p0 = W.upos[0].copy()
        W.move_uavs([np.array([500.0, 500.0])] + [W.upos[k].copy() for k in range(1, 4)], [False] * 4, float(t))
        v.append(float(np.hypot(*(W.upos[0] - p0))))
    return dict(climb_s_expected=round(c.altitude / c.v_climb, 1), mission_mode_at_s=t_mission,
                takeoff_gap_s=c.takeoff_gap, speed_per_s_first_10s=[round(x, 2) for x in v],
                a_max=c.a_max, v_max=c.speed)


def backhaul():
    c = realistic(n_uav=2)
    W = World(c, 900)
    W.upos[:] = [W.gw + [1000.0, 0.0], W.gw + [2000.0, 0.0]]
    W.ualt[:] = c.altitude
    W.mode[:] = 0
    bh = W.backhaul(False)
    return dict(range_m=round(c.bh_range, 1), hops=bh['hops'][:2].tolist(), budget_mbps=np.round(bh['budget'], 1).tolist())


def latency():
    """Perceived position = true position at t - lat (linear between rounds) for a user walking at constant speed."""
    c = realistic(n_uav=1, n_users=1, arrival_rate=0.0, T=10, mobile_frac=1.0)
    W = World(c, 900)
    W.mobile[:] = True
    W.vel[:] = 1.0
    W.wp[:] = W.pos + [500.0, 0.0]
    W.pause[:] = 0
    for t in range(6):
        W.move_users(float(t))
    hp = []
    pre = dict(pd=1.0, sigma=0.0, pcls=1.0, fp=0.0, lat=0.5)
    W.upos[0] = W.pos[0]
    xy, _ = W.perceive(0, 5.0, pre, 0.5)
    return dict(true_x=round(float(W.pos[0, 0]), 3), perceived_x=round(float(xy[0, 0]), 3) if len(xy) else None,
                expected_lag_m=0.5)


def loss_ge():
    c = realistic(p_loss=0.2, loss_model='ge', ge_burst_s=5.0)
    W = World(c, 900)
    x = np.array([W.msg_lost(0, 1) for _ in range(200000)], float)
    runs, k = [], 0
    for b in x:
        if b:
            k += 1
        elif k:
            runs.append(k); k = 0
    return dict(loss_rate=round(float(x.mean()), 4), target=0.2, mean_burst=round(float(np.mean(runs)), 2), target_burst=5.0)


def city_los():
    """Share of LOS street-level links by horizontal distance in the procedural city, next to the A2G urban curve."""
    c = realistic(city='manhattan', chan='geom')
    rng = np.random.default_rng(5)
    city = City(c.world, c.city_block, c.city_street, c.city_h_median, c.city_h_sigma, c.city_open, rng, c.city_h_dist)
    P = city.snap(rng.uniform(0, c.world, (4000, 2)))
    Q = rng.uniform(0, c.world, (8, 2))
    L = city.los(P, 1.5, Q, np.full(8, c.altitude), c.los_samples)
    d = np.hypot(P[:, None, 0] - Q[None, :, 0], P[:, None, 1] - Q[None, :, 1])
    out = []
    for lo, hi in ((0, 50), (50, 100), (100, 200), (200, 300), (300, 400), (400, 600), (600, 800)):
        m = (d >= lo) & (d < hi)
        if m.any():
            out.append(dict(d_m=f'{lo}-{hi}', los_city=round(float(L[m].mean()), 3),
                            los_a2g_urban=round(float(plos_a2g(np.array([(lo + hi) / 2]), c.altitude, 'urban')[0]), 3)))
    return dict(building_h_median=round(float(np.median(city.H[city.H > 0])), 1), by_distance=out)


def session_score():
    """A UAV hovering over a static user serves its whole session: session fraction close to 1."""
    c = realistic(n_uav=1, n_users=1, arrival_rate=0.0, T=300, mobile_frac=0.0, takeoff=False, world=200.0, gateway=(100.0, 100.0))
    W = World(c, 901)
    r = run_episode(replace(c), 'static_pad', 901, log_rounds=False)
    return dict(session_frac_mean=round(r['session_frac_mean'], 3), users_served=r['users_served'])


def swaps():
    """Staggered initial charge and 2 swap slots: swap starts are spread and at most 2 UAVs swap at once."""
    c = realistic(n_uav=6, T=3600, battery_wh=120.0)
    starts, conc = [], []

    def hook(W, agents, step):
        conc.append(int((W.mode == 2).sum()))
        for i in range(c.n_uav):
            if W.mode[i] == 2 and W.swap_until[i] == step + c.swap_s:
                starts.append(step)
    r = run_episode(c, 'maqac', 902, log_rounds=False, step_hook=hook)
    return dict(swap_starts_s=starts[:12], max_concurrent_swaps=max(conc), slots=c.swap_slots, rtb=r['rtb'],
                swap_wait_s=r.get('swap_wait_s'))


if __name__ == '__main__':
    R = {}
    for f in (coverage_radius, energy, kinematics, backhaul, latency, loss_ge, city_los, session_score, swaps):
        R[f.__name__] = f()
        print(f.__name__, json.dumps(R[f.__name__], default=float), flush=True)
    json.dump(R, open(OUT, 'w'), indent=1, default=float)
    print('->', OUT)

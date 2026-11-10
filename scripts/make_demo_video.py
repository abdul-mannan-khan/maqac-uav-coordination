#!/usr/bin/env python3
"""Demo video of MAQAC (about 90 s, 1280x720, 15 fps) from the paper's own code and logs.

Segments (each an mp4 in --out/seg, then joined to --out/maqac_demo.mp4):
  0 title card
  1 replay: one urban mission with six UAVs (main-grid configuration, seed 20000), MAQAC and RAG side by side on the
    same users, re-simulated with the network-level simulator; users fade with their session survival and turn green
    when first served; the running score is the paper's QoS-weighted score J
  2 AirSim/PX4: six UAVs, each flown by PX4 SITL, over the surveyed CityEnviron height map (logged positions of
    results/airsim/refly_campaign/runs/ko_city_n6_maqac_seq_onboard_20000, re-flown 7 Nov 2026)
  3 hardware in the loop: the Pixhawk-flown UAV in the city HIL (results/hil_airsim_city/maqac_seq_s20000): track
    and altitude while climbing over towers
  4 AirSim chase camera of a PX4 UAV in CityEnviron (results/airsim/one_drone_core_1031/chase.mp4)
  5 closing card with the paper's results
Numbers on the cards are copied from the manuscript (Sections 6.3, 6.8 and 6.10).

    python3 scripts/make_demo_video.py --out demo/          [--quick: few frames per segment, for a test]
Needs numpy, scipy, matplotlib and ffmpeg.
"""
import argparse, glob, json, os, subprocess, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src', 'netsim'))
sys.path.insert(0, os.path.join(ROOT, 'sim', 'airsim', 'maqac_px4'))
W_PX, H_PX, DPI, FPS = 1280, 720, 100, 15
BG, FG, MUTED = '#0f1420', '#e8ecf3', '#9aa4b5'
CLS_COL = ['#ff5a5f', '#ffb020', '#4da3ff']           # emergency, real-time, best-effort classes
UAV_COL = ['#7ee081', '#c792ea', '#ffd166', '#5ec8e5', '#f78c6c', '#ff9ecd']
SERVED = '#3ddc84'


def fig_new():
    f = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI, facecolor=BG)
    return f


class Writer:
    """Pipes RGB frames to ffmpeg."""
    def __init__(self, path):
        self.p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                                   '-s', f'{W_PX}x{H_PX}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264',
                                   '-pix_fmt', 'yuv420p', '-crf', '20', path], stdin=subprocess.PIPE)
        self.n = 0

    def add(self, fig):
        fig.canvas.draw()
        a = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        self.p.stdin.write(np.ascontiguousarray(a).tobytes())
        self.n += 1

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def card(path, title, lines, secs, quick, sub=None):
    w = Writer(path)
    f = fig_new()
    f.text(0.07, 0.80, title, color=FG, fontsize=30, weight='bold', va='top')
    if sub:
        f.text(0.07, 0.69, sub, color=MUTED, fontsize=16, va='top')
    y = 0.58
    for ln in lines:
        f.text(0.09, y, '•  ' + ln, color=FG, fontsize=16, va='top')
        y -= 0.075
    for _ in range(2 if quick else int(secs * FPS)):
        w.add(f)
    plt.close(f)
    w.close()


# ---------------------------------------------------------------------------------------------------- 1 replay
def simulate(method, seed=20000, n=6):
    from dataclasses import replace
    from sim import NetConfig
    from episode import run_episode
    cfg = replace(NetConfig(), scenario='urban', n_uav=n, name='main_urban_6')
    frames = []

    def hook(W, agents, step):
        frames.append(dict(t=step, pos=W.pos.copy(), pres=W.present(float(step)).copy(), first=W.first_t.copy(),
                           upos=W.upos.copy(), alive=W.alive.copy()))
    r = run_episode(cfg, method, seed, log_rounds=False, step_hook=hook)
    W0 = dict(arr=None)
    return cfg, frames, r


def survival(cfg, mu, dt):
    return np.exp(-mu * np.maximum(dt, 0.0))


def seg_replay(path, quick):
    from sim import World
    cfg, fa, ra = simulate('maqac')
    _, fb, rb = simulate('rag')
    Wd = World(cfg, 20000)                      # static user attributes (same seed: same users for both methods)
    arr, w, mu, cls = Wd.arr, Wd.w, Wd.mu, Wd.cls
    L = cfg.world

    def J_at(fr, t):
        s = fr['first']
        ok = np.isfinite(s) & (s <= t)
        return float((w[ok] * survival(cfg, mu[ok], s[ok] - arr[ok])).sum())
    JA = [J_at(fr, fr['t']) for fr in fa]
    JB = [J_at(fr, fr['t']) for fr in fb]
    T = len(fa)
    w_ = Writer(path)
    f = fig_new()
    axA = f.add_axes([0.03, 0.17, 0.44, 0.65])
    axB = f.add_axes([0.53, 0.17, 0.44, 0.65])
    axJ = f.add_axes([0.08, 0.04, 0.86, 0.09])
    steps = range(0, T, 2) if not quick else range(0, T, T // 4)
    for k in steps:
        for ax, fr, name, J in ((axA, fa[k], 'MAQAC (no in-round messages)', JA), (axB, fb[k], 'RAG (T-RO 2025)', JB)):
            ax.cla()
            ax.set_facecolor('#151c2c'); ax.set_xlim(0, L); ax.set_ylim(0, L); ax.set_aspect('equal')
            ax.set_xticks([]); ax.set_yticks([])
            for s_ in ax.spines.values():
                s_.set_color('#2a3448')
            t = fr['t']
            pres = fr['pres']
            served = np.isfinite(fr['first']) & (fr['first'] <= t)
            wait = pres & ~served
            sv = survival(cfg, mu[wait], t - arr[wait])
            cols = np.array([matplotlib.colors.to_rgba(CLS_COL[c]) for c in cls[wait]]).reshape(-1, 4)
            if len(cols):
                cols[:, 3] = 0.15 + 0.85 * sv
            ax.scatter(fr['pos'][wait, 0], fr['pos'][wait, 1], s=9, c=cols, lw=0)
            ax.scatter(fr['pos'][served & pres, 0], fr['pos'][served & pres, 1], s=7, c=SERVED, alpha=0.35, lw=0)
            up = fr['upos']
            for i in range(len(up)):
                for j in range(i + 1, len(up)):
                    if np.hypot(*(up[i] - up[j])) <= cfg.bh_range:
                        ax.plot([up[i, 0], up[j, 0]], [up[i, 1], up[j, 1]], color='#56627a', lw=0.6, alpha=0.6)
            for i, p in enumerate(up):
                ax.add_patch(Circle(p, cfg.r_s, fc=UAV_COL[i], alpha=0.18, ec=UAV_COL[i], lw=1.0))
                ax.plot(*p, marker='^', ms=8, color=UAV_COL[i], mec='black', mew=0.5)
            ax.plot(*cfg.gateway, marker='s', ms=7, color='white')
            ax.set_title(f'{name}    J = {J[k]:.0f}', color=FG, fontsize=13, loc='left')
        axJ.cla(); axJ.set_facecolor(BG)
        axJ.plot(range(k + 1), JA[:k + 1], color=UAV_COL[0], lw=2, label='MAQAC')
        axJ.plot(range(k + 1), JB[:k + 1], color=UAV_COL[1], lw=2, label='RAG')
        axJ.set_xlim(0, T); axJ.set_ylim(0, max(JA[-1], JB[-1]) * 1.05)
        axJ.tick_params(colors=MUTED, labelsize=8)
        for s_ in axJ.spines.values():
            s_.set_color('#2a3448')
        axJ.legend(loc='upper left', fontsize=8, facecolor=BG, labelcolor=FG, frameon=False)
        f.texts.clear()
        f.text(0.03, 0.955, f'One urban mission (seed 20000), six UAVs, 1 km × 1 km, same users for both    t = {fa[k]["t"]:3d} s / {T} s   (×30)',
               color=FG, fontsize=14, va='top')
        f.text(0.03, 0.905, 'users: red emergency, amber real-time, blue best-effort traffic; they fade as sessions expire, '
               'green once served.  ▲ UAV with its 50 m footprint;  grey lines: backhaul links;  ■ gateway',
               color=MUTED, fontsize=9.5, va='top')
        f.text(0.94, 0.135, 'this mission: +8%; mean of 30 missions: +5%', color=MUTED, fontsize=8.5, ha='right')
        w_.add(f)
    plt.close(f)
    w_.close()
    return dict(J_maqac=JA[-1], J_rag=JB[-1], J_maqac_sim=ra.get('qos_score'), J_rag_sim=rb.get('qos_score'))


# ---------------------------------------------------------------------------------------------------- 2 AirSim fleet
def heightmap():
    from heightmap import HeightMap
    return HeightMap.load(os.path.join(ROOT, 'results', 'airsim', 'v3_campaign', 'survey', 'heightmap.npz'))


def hm_extent(hm, ax, lo=-330, hi=330):
    """Draw the height map (world N up, E right) clipped to [lo, hi] m."""
    n0, e0, res = hm.n0, hm.e0, hm.res
    i0, i1 = int((lo - n0) / res), int((hi - n0) / res)
    j0, j1 = int((lo - e0) / res), int((hi - e0) / res)
    h = np.clip(hm.h[i0:i1, j0:j1], 0, 200)
    ax.imshow(h, origin='lower', extent=[lo, hi, lo, hi], cmap='bone', vmin=-20, vmax=220)


def seg_airsim(path, quick):
    # re-flown mission with the no-fly box over C264 (7 Nov 2026); the v3 flight touched its hidden collision volume
    run = os.path.join(ROOT, 'results', 'airsim', 'refly_campaign', 'runs', 'ko_city_n6_maqac_seq_onboard_20000')
    R = [json.loads(l) for l in open(os.path.join(run, 'rounds.jsonl'))]
    hm = heightmap()
    w_ = Writer(path)
    f = fig_new()
    ax = f.add_axes([0.03, 0.05, 0.50, 0.84])
    axh = f.add_axes([0.60, 0.12, 0.36, 0.62])
    P = np.array([r['gt_world'] for r in R])           # rounds x UAV x (N, E, D)
    steps = range(0, len(R), 2) if not quick else range(0, len(R), len(R) // 4)
    for k in steps:
        ax.cla(); hm_extent(hm, ax); ax.set_xticks([]); ax.set_yticks([])
        for i in range(P.shape[1]):
            tr = P[max(0, k - 40):k + 1, i]
            ax.plot(tr[:, 1], tr[:, 0], color=UAV_COL[i], lw=1.4, alpha=0.9)
            ax.plot(P[k, i, 1], P[k, i, 0], marker='^', ms=9, color=UAV_COL[i], mec='black', mew=0.6)
        axh.cla(); axh.set_facecolor(BG)
        up = [r for r in R[k]['up']]
        axh.bar(range(len(up)), up, color=UAV_COL[:len(up)])
        axh.set_ylim(0, 300); axh.set_ylabel('altitude above start [m]', color=MUTED)
        axh.set_xticks(range(len(up))); axh.set_xticklabels([f'UAV {i}' for i in range(len(up))], color=MUTED, fontsize=8)
        axh.tick_params(colors=MUTED)
        for s_ in axh.spines.values():
            s_.set_color('#2a3448')
        f.texts.clear()
        f.text(0.03, 0.955, f'AirSim CityEnviron: six UAVs, each flown by its own PX4 flight stack (MAQAC-S)    t = {R[k]["t"]} s',
               color=FG, fontsize=14, va='top')
        f.text(0.60, 0.86, 'Map: building heights from the AirSim survey\n(white = tall, towers up to 237 m).\n'
               'UAVs climb over towers in flight.', color=MUTED, fontsize=10, va='top')
        f.text(0.60, 0.07, f'min. separation {R[k]["min_sep"]:.0f} m    clearance to buildings {R[k]["clearance"]:.0f} m',
               color=FG, fontsize=11)
        w_.add(f)
    plt.close(f)
    w_.close()


# ---------------------------------------------------------------------------------------------------- 3 HIL
def seg_hil(path, quick):
    run = os.path.join(ROOT, 'results', 'hil_airsim_city', 'maqac_seq_s20000')
    R = [json.loads(l) for l in open(os.path.join(run, 'rounds.jsonl'))]
    hm = heightmap()
    from heightmap import AreaFrame
    fr = AreaFrame(600.0, (40.0, -10.0))
    U = np.array([[fr.to_world(np.array(p)) for p in r['upos']] for r in R])      # rounds x 3 x (N, E)
    Z = np.array([[r['act0'][2]] + r['z_cmd'][1:] for r in R])
    ms = np.array([r['fleet_decide_ms'] for r in R])
    w_ = Writer(path)
    f = fig_new()
    ax = f.add_axes([0.03, 0.05, 0.50, 0.84])
    axz = f.add_axes([0.60, 0.47, 0.36, 0.36])
    axm = f.add_axes([0.60, 0.10, 0.36, 0.24])
    steps = range(0, len(R), 2) if not quick else range(0, len(R), len(R) // 4)
    for k in steps:
        ax.cla(); hm_extent(hm, ax); ax.set_xticks([]); ax.set_yticks([])
        for i in range(3):
            tr = U[max(0, k - 60):k + 1, i]
            ax.plot(tr[:, 1], tr[:, 0], color=UAV_COL[i], lw=1.6 if i == 0 else 1.0, alpha=0.95 if i == 0 else 0.6)
            ax.plot(U[k, i, 1], U[k, i, 0], marker='^', ms=11 if i == 0 else 7, color=UAV_COL[i], mec='black', mew=0.6)
        for a_ in (axz, axm):
            a_.cla(); a_.set_facecolor(BG); a_.tick_params(colors=MUTED, labelsize=8)
            for s_ in a_.spines.values():
                s_.set_color('#2a3448')
        axz.plot(range(k + 1), Z[:k + 1, 0], color=UAV_COL[0], lw=2, label='UAV 0 (Pixhawk 6C)')
        axz.set_xlim(0, len(R)); axz.set_ylim(0, 380); axz.set_ylabel('altitude [m]', color=MUTED, fontsize=9)
        axz.legend(loc='upper left', fontsize=8, frameon=False, labelcolor=FG)
        axm.plot(range(k + 1), ms[:k + 1], color='#ffd166', lw=1.2)
        axm.set_xlim(0, len(R)); axm.set_ylim(0, 40)
        axm.set_ylabel('decision [ms]', color=MUTED, fontsize=9); axm.set_xlabel('mission time [s]', color=MUTED, fontsize=9)
        f.texts.clear()
        f.text(0.03, 0.955, f'Hardware in the loop: UAV 0 flown by PX4 on a Pixhawk 6C, fleet decisions on a Jetson Orin Nano    t = {R[k]["t"]} s',
               color=FG, fontsize=13, va='top')
        f.text(0.60, 0.88, 'AirSim supplies physics and sensors; the Pixhawk flies.\nThe UAV holds position while it climbs over towers.',
               color=MUTED, fontsize=10, va='top')
        w_.add(f)
    plt.close(f)
    w_.close()


def seg_chase(path, quick):
    src = os.path.join(ROOT, 'results', 'airsim', 'one_drone_core_1031', 'chase.mp4')
    t = ['-t', '1'] if quick else []
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, *t, '-vf',
                    f'scale={W_PX}:{H_PX}:force_original_aspect_ratio=decrease,pad={W_PX}:{H_PX}:(ow-iw)/2:(oh-ih)/2,fps={FPS}',
                    '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', path], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='demo')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--only', default='0,1,2,3,4,5')
    a = ap.parse_args()
    seg = os.path.join(a.out, 'seg'); os.makedirs(seg, exist_ok=True)
    only = set(a.only.split(','))
    P = lambda k: os.path.join(seg, f'{k}.mp4')
    info = {}
    if '0' in only:
        card(P(0), 'MAQAC', ['Distributed coordination of UAV aerial base stations after a disaster',
                             'Urgent users first: the score counts sessions still alive when first served',
                             'A per-round guarantee and a calibrated mission-level certificate',
                             'Evaluated in a network simulator, in AirSim with PX4, and on a Pixhawk'],
             5, a.quick, sub='Certified coordination under imperfect perception and backhaul delay')
    if '1' in only:
        info['replay'] = seg_replay(P(1), a.quick)
        print('replay', info['replay'], flush=True)
    if '2' in only:
        card(P('2a'), 'Real flight control in a city', ['42 missions in AirSim CityEnviron, one PX4 flight stack per UAV',
             'Flown score within 4% of the kinematic model', 'No two UAVs closer than 11.9 m; none closer than 19 m to a building'],
             3, a.quick)
        seg_airsim(P(2), a.quick)
    if '3' in only:
        seg_hil(P(3), a.quick)
    if '4' in only:
        card(P('4a'), 'AirSim chase camera', ['A PX4-flown UAV crossing the CityEnviron downtown map (first test flight, 31 Oct 2026)'],
             2, a.quick)
        seg_chase(P(4), a.quick)
    if '5' in only:
        card(P(5), 'Results', ['Main grid (9,180 missions): 4-7% higher score than RAG in 8 of 15 settings',
                               'Ahead of interference-aware (7-13%), potential-game and MAPPO (6-23%) deployments',
                               'At 40% message loss MAQAC-S beats RAG by 5-22% (8 of 9 settings, 3 km areas)',
                               'With one shared channel: +4-9%; and 5-8x fewer messages than RAG',
                               'Pixhawk in the loop: 30 missions, decisions in 17-33 ms per round, no failsafe',
                               'Code and data: see the paper\'s Data Availability statement'], 7, a.quick)
    order = [k for k in ['0', '1', '2a', '2', '3', '4a', '4', '5'] if os.path.exists(P(k))]
    lst = os.path.join(seg, 'list.txt')
    with open(lst, 'w') as fh:
        for k in order:
            fh.write(f"file '{os.path.abspath(P(k))}'\n")
    out = os.path.join(a.out, 'maqac_demo.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out], check=True)
    json.dump(info, open(os.path.join(a.out, 'demo_info.json'), 'w'), indent=1)
    print('wrote', out)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Comparison video (1920x1080, 15 fps, about 45 s): one urban mission with six UAVs (main-grid configuration,
seed 20000) flown by six methods on the same users, side by side, with each method's running QoS-weighted score J.

Methods: MAQAC, MAQAC-S, RAG (Xu, Garimella & Tzoumas, IEEE T-RO 2025), interference-aware deployment (IAD, after Lai
et al. 2023), potential game (after Furuta et al. 2024) and MAPPO (one of its five trained policies, seed 0, best
validation checkpoint of the 3,000-iteration v4 runs, iteration 2,919; weights exported to
results/demo/mappo_6_s0_actor_v4.npz; the v3 export mappo_6_s0_actor.npz is kept). Re-simulated with the network-level
simulator; the final scores equal the grid's for this mission (results/netsim_grid_fix.jsonl).

    python3 scripts/make_comparison_video.py --out demo/ [--quick]
Needs numpy, scipy, matplotlib and ffmpeg.
"""
import argparse, json, os, subprocess, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src', 'netsim'))
W_PX, H_PX, DPI, FPS = 1920, 1080, 100, 15
BG, FG, MUTED = '#0f1420', '#e8ecf3', '#9aa4b5'
CLS_COL = ['#ff5a5f', '#ffb020', '#4da3ff']
SERVED = '#3ddc84'
METH = [('maqac', 'MAQAC', '#7ee081'), ('maqac_seq', 'MAQAC-S', '#5ec8e5'), ('rag', 'RAG (T-RO 2025)', '#c792ea'),
        ('iad', 'Interference-aware', '#ffd166'), ('potgame', 'Potential game', '#f78c6c'), ('mappo', 'MAPPO (learned)', '#ff9ecd')]


class Writer:
    def __init__(self, path):
        self.p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                                   '-s', f'{W_PX}x{H_PX}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264',
                                   '-pix_fmt', 'yuv420p', '-crf', '23', path], stdin=subprocess.PIPE)

    def add(self, fig):
        fig.canvas.draw()
        self.p.stdin.write(np.ascontiguousarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3]).tobytes())

    def close(self):
        self.p.stdin.close(); self.p.wait()


def simulate(method, seed=20000, n=6):
    from dataclasses import replace
    from sim import NetConfig
    from episode import run_episode
    flags = None
    if method == 'mappo':
        import mappo                                                   # registers METHODS['mappo']
        z = np.load(os.path.join(ROOT, 'results', 'demo', 'mappo_6_s0_actor_v4.npz'))
        Wt = [z[f'arr_{i}'] for i in range(len(z.files))]
        flags = dict(policy=mappo.np_actor(Wt, greedy=True))
    cfg = replace(NetConfig(), scenario='urban', n_uav=n, name='main_urban_6')
    fr = []

    def hook(W, agents, step):
        fr.append(dict(t=step, pos=W.pos.copy(), pres=W.present(float(step)).copy(), first=W.first_t.copy(),
                       upos=W.upos.copy()))
    r = run_episode(cfg, method, seed, log_rounds=False, step_hook=hook, agent_flags=flags)
    return cfg, fr, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='demo')
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from sim import World
    runs = {}
    for m, _, _ in METH:
        cfg, fr, r = simulate(m)
        runs[m] = (fr, r.get('qos_score'))
        print(m, 'J', r.get('qos_score'), flush=True)
    Wd = World(cfg, 20000)
    arr, w, mu, cls = Wd.arr, Wd.w, Wd.mu, Wd.cls
    L = cfg.world

    def J_at(f):
        s = f['first']; ok = np.isfinite(s) & (s <= f['t'])
        return float((w[ok] * np.exp(-mu[ok] * np.maximum(s[ok] - arr[ok], 0))).sum())
    J = {m: [J_at(f) for f in runs[m][0]] for m, _, _ in METH}
    T = len(runs['maqac'][0])
    f = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI, facecolor=BG)
    axes = []
    for k in range(6):
        r_, c_ = divmod(k, 3)
        axes.append(f.add_axes([0.02 + c_ * 0.215, 0.495 - r_ * 0.40, 0.20, 0.345]))
    axJ = f.add_axes([0.685, 0.13, 0.295, 0.66])
    wr = Writer(os.path.join(a.out, 'maqac_comparison.mp4'))
    steps = list(range(0, T, 2)) if not a.quick else list(range(0, T, T // 3))
    hold = [steps[-1]] * (0 if a.quick else 4 * FPS)                    # hold the final frame 4 s
    for k in steps + hold:
        for ax, (m, name, col) in zip(axes, METH):
            fr = runs[m][0][k]; t = fr['t']
            ax.cla(); ax.set_facecolor('#151c2c'); ax.set_xlim(0, L); ax.set_ylim(0, L); ax.set_aspect('equal')
            ax.set_xticks([]); ax.set_yticks([])
            for s_ in ax.spines.values():
                s_.set_color(col); s_.set_linewidth(1.5)
            served = np.isfinite(fr['first']) & (fr['first'] <= t)
            wait = fr['pres'] & ~served
            sv = np.exp(-mu[wait] * np.maximum(t - arr[wait], 0))
            cols = np.array([matplotlib.colors.to_rgba(CLS_COL[c]) for c in cls[wait]]).reshape(-1, 4)
            if len(cols):
                cols[:, 3] = 0.15 + 0.85 * sv
            ax.scatter(fr['pos'][wait, 0], fr['pos'][wait, 1], s=5, c=cols, lw=0)
            ax.scatter(fr['pos'][served & fr['pres'], 0], fr['pos'][served & fr['pres'], 1], s=4, c=SERVED, alpha=0.3, lw=0)
            for p in fr['upos']:
                ax.add_patch(Circle(p, cfg.r_s, fc=col, alpha=0.25, ec=col, lw=1.0))
                ax.plot(*p, marker='^', ms=6, color=col, mec='black', mew=0.4)
            ax.plot(*cfg.gateway, marker='s', ms=5, color='white')
            ax.set_title(f'{name}   J = {J[m][k]:.0f}', color=FG, fontsize=14, loc='left')
        axJ.cla(); axJ.set_facecolor(BG)
        for m, name, col in METH:
            axJ.plot(range(k + 1), J[m][:k + 1], color=col, lw=2.4 if m == 'maqac' else 1.6, label=name)
        axJ.set_xlim(0, T); axJ.set_ylim(0, max(J[m][-1] for m, _, _ in METH) * 1.08)
        axJ.set_xlabel('mission time [s]', color=MUTED, fontsize=12); axJ.set_ylabel('score J (higher is better)', color=MUTED, fontsize=12)
        axJ.tick_params(colors=MUTED, labelsize=11)
        for s_ in axJ.spines.values():
            s_.set_color('#2a3448')
        axJ.legend(loc='lower right', fontsize=12, frameon=False, labelcolor=FG)
        f.texts.clear()
        f.text(0.02, 0.965, 'Same mission, same users, six methods: urban area 1 km × 1 km, six UAVs (seed 20000)', color=FG, fontsize=22, va='top')
        f.text(0.02, 0.915, f't = {runs["maqac"][0][k]["t"]:3d} s / {T} s (×30)    users: red emergency, amber real-time, blue best-effort '
               '(fading as sessions expire), green once served;  ▲ UAV with its 50 m footprint;  ■ gateway',
               color=MUTED, fontsize=13, va='top')
        f.text(0.685, 0.835, 'Running score of each method', color=FG, fontsize=16)
        f.text(0.02, 0.04, 'Score J: priority-weighted sessions still alive when first served. One mission shown; the paper '
               'reports 30 paired missions per configuration. MAPPO: one of its five trained policies.', color=MUTED, fontsize=12)
        wr.add(f)
    wr.close()
    json.dump({m: dict(J_end=J[m][-1], J_sim=runs[m][1]) for m, _, _ in METH},
              open(os.path.join(a.out, 'comparison_info.json'), 'w'), indent=1)
    print('wrote', os.path.join(a.out, 'maqac_comparison.mp4'))


if __name__ == '__main__':
    main()

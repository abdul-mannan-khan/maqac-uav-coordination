#!/usr/bin/env python3
"""Fig. 7 (snapshots) panels (a)-(c) for print: white background. Reuses the drawing code of make_comparison_video.py and make_demo_video.py with a light
theme (colours swapped in the source before it is executed) and saves one frame of each segment as a 250-dpi image,
with the video titles replaced by keys (legend, building-height colour bar, 100 m scale bar, plot titles).

    python3 scripts/make_snapshot_figures.py airsim hil      # replay logged flights only (seconds)
    python3 scripts/make_snapshot_figures.py comparison      # re-simulates six methods (run on Vast)
Outputs: paper/figures/snap_{comparison,airsim,hil}_c.png
"""
import os, sys, types
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'paper', 'figures')
DPI_OUT = 250

# dark video theme -> print theme (same order everywhere so each entity keeps its colour)
SWAP = [("'#0f1420'", "'white'"), ("'#e8ecf3'", "'#1b1f27'"), ("'#9aa4b5'", "'#4b5563'"),
        ("'#151c2c'", "'#fbfcfd'"), ("'#2a3448'", "'#9aa4b5'"), ("'#56627a'", "'#9aa4b5'"),
        ("color='white'", "color='black'"),
        ("'#7ee081'", "'#2a9d3f'"), ("'#c792ea'", "'#8e44ad'"), ("'#ffd166'", "'#c99700'"),
        ("'#5ec8e5'", "'#1f77b4'"), ("'#f78c6c'", "'#e4572e'"), ("'#ff9ecd'", "'#d63384'"),
        ("'#3ddc84'", "'#1e9e55'"),
        ("cmap='bone', vmin=-20, vmax=220", "cmap='Greys', vmin=-60, vmax=260"),
        ("(white = tall, towers up to 237 m)", "(darker = taller, towers up to 237 m)"),
        # AirSim panel: last 20 s instead of 40 s, dot where the track starts
        ("tr = P[max(0, k - 40):k + 1, i]", "tr = P[max(0, k - 20):k + 1, i]"),
        # user, 9 Nov 2026: fewer UAVs -> the three-UAV MAQAC-S mission of the same seed (v3 campaign, part of the 42)
        ("'refly_campaign', 'runs', 'ko_city_n6_maqac_seq_onboard_20000'", "'v3_campaign', 'runs', 'v3_city_n3_maqac_seq_onboard_20000'"),
        ("ax.plot(tr[:, 1], tr[:, 0], color=UAV_COL[i], lw=1.4, alpha=0.9)",
         "ax.plot(tr[:, 1], tr[:, 0], color=UAV_COL[i], lw=1.4, alpha=0.9); "
         "ax.plot(tr[0, 1], tr[0, 0], marker='o', ms=4, color=UAV_COL[i], mec='black', mew=0.4, ls='none')")]


class Grab:
    """Stands in for the ffmpeg Writer: keeps frame number `want` as a high-resolution image."""
    want, name = 0, ''

    def __init__(self, path):
        self.n = 0

    decorate = None
    fontscale = 1.0

    def add(self, fig):
        if self.n == Grab.want:
            p = os.path.join(OUT, Grab.name)
            if Grab.decorate:
                Grab.decorate(fig)
            if Grab.fontscale != 1:          # video layout -> print: text readable at the printed panel width
                import matplotlib.text as mt
                fig.canvas.draw()
                for t in fig.findobj(mt.Text):
                    t.set_fontsize(t.get_fontsize() * Grab.fontscale)
            fig.savefig(p, dpi=DPI_OUT, facecolor='white', bbox_inches='tight', pad_inches=0.08)
            print('wrote', p)
        self.n += 1

    def close(self):
        pass


from matplotlib.lines import Line2D


def _drop_texts(fig, keys):
    for t in list(fig.texts):
        if any(k in t.get_text() for k in keys):
            t.remove()


def _map_keys(fig, ax, items, ncol=1, loc='upper left'):
    """Colour bar for building height, a 100 m scale bar and a legend on a top-view map."""
    ax.set_position([0.01, 0.07, 0.42, 0.83])
    cax = fig.add_axes([0.445, 0.17, 0.012, 0.62])
    cb = fig.colorbar(ax.images[0], cax=cax)
    cb.set_label('building height [m]', fontsize=11); cb.ax.set_ylim(0, 200); cb.set_ticks([0, 50, 100, 150, 200])
    cb.ax.tick_params(labelsize=9)
    ax.plot([-315, -215], [-312, -312], color='black', lw=3, solid_capstyle='butt')
    ax.text(-265, -300, '100 m', ha='center', va='bottom', fontsize=10, color='black')
    ax.legend(handles=items, loc=loc, fontsize=9.5, framealpha=0.92, edgecolor='#9aa4b5', ncol=ncol)
    ax.set_title('Top view: building heights and UAV tracks', loc='left', fontsize=12)


def deco_airsim(D):
    def f(fig):
        ax, axh = fig.axes[0], fig.axes[1]
        _drop_texts(fig, ('AirSim CityEnviron:', 'Map: building heights'))
        items = [Line2D([], [], color='#4b5563', marker='^', ms=9, mec='black', mew=0.6, ls='-', lw=1.4,
                        label='UAV now and its track over the last 20 s;\ncolour = UAV, as in the bar chart'),
                 Line2D([], [], color='#4b5563', marker='o', ms=4, mec='black', mew=0.4, ls='none',
                        label='position 20 s earlier')]
        _map_keys(fig, ax, items, loc='lower right')
        ax.legend(handles=items, loc='upper left', bbox_to_anchor=(0.0, -0.01), fontsize=9.5, frameon=False, ncol=2)
        axh.set_position([0.64, 0.17, 0.34, 0.62])
        axh.set_title('UAV altitude above start (t = 224 s)', loc='left', fontsize=12)
        for t in fig.texts:
            if 'min. separation' in t.get_text():
                t.set_position((0.55, 0.0)); t.set_text('At t = 224 s: ' + t.get_text().replace('    ', '; '))
    return f


def deco_hil(D):
    def f(fig):
        ax, axz, axm = fig.axes[0], fig.axes[1], fig.axes[2]
        _drop_texts(fig, ('Hardware in the loop:', 'AirSim supplies physics'))
        c = D.UAV_COL
        items = [Line2D([], [], color=c[0], marker='^', ms=10, mec='black', mew=0.6, lw=1.8, label='UAV 0: Pixhawk 6C (hardware)'),
                 Line2D([], [], color=c[1], marker='^', ms=7, mec='black', mew=0.6, lw=1.0, label='UAV 1: simulated'),
                 Line2D([], [], color=c[2], marker='^', ms=7, mec='black', mew=0.6, lw=1.0, label='UAV 2: simulated'),
                 Line2D([], [], color='#4b5563', lw=1.2, label='line: track, last 60 s')]
        _map_keys(fig, ax, items)
        axz.set_position([0.64, 0.58, 0.34, 0.30]); axm.set_position([0.64, 0.12, 0.34, 0.28])
        if axz.get_legend():
            axz.get_legend().remove()
        axz.set_title('Altitude of UAV 0 (Pixhawk-flown)', loc='left', fontsize=12)
        axm.set_title('Fleet decision time per round (Jetson)', loc='left', fontsize=12)
        for ln in axm.lines:
            ln.set_color('#374151')     # not the gold of UAV 2
        axz.set_xlabel('mission time [s]', color='#4b5563', fontsize=9)
    return f


def deco_comparison(C):
    def f(fig):
        _drop_texts(fig, ('Same mission, same users', 'users: red emergency'))
        for ax in fig.axes[:6]:                 # map titles: one short line that fits its panel after scaling
            t = ax.title if ax.title.get_text() else ax._left_title
            t.set_text(t.get_text().replace('   J', ', J').replace('RAG (T-RO 2025)', 'RAG')); t.set_fontsize(11)
        fig.axes[6].set_position([0.715, 0.13, 0.27, 0.66])
        dot = lambda col, lab, a=1.0: Line2D([], [], marker='o', ls='', ms=6, color=col, alpha=a, label=lab)
        items = [dot(C.CLS_COL[0], 'emergency user (waiting)'), dot(C.CLS_COL[1], 'real-time user (waiting)'),
                 dot(C.CLS_COL[2], 'best-effort user (waiting)'), dot(C.SERVED, 'user already served', 0.6),
                 Line2D([], [], marker='^', ls='', ms=9, color='#6b7280', mec='black', mew=0.5, label='UAV (colour = method)'),
                 Line2D([], [], marker='o', ls='', ms=16, mfc=(0.42, 0.45, 0.5, 0.25), mec='#6b7280', label='UAV footprint (50 m radius)'),
                 Line2D([], [], marker='s', ls='', ms=7, color='black', label='gateway')]
        fig.legend(handles=items, loc='lower left', bbox_to_anchor=(0.015, 0.975), ncol=4, fontsize=12.5, frameon=False,
                   handletextpad=0.3, columnspacing=1.4)
        fig.text(0.02, 0.965, 'Each map: the same 1 km x 1 km urban area, six UAVs, t = 660 s. Faded dots: sessions close to expiry.',
                 fontsize=12, color='#4b5563', va='top')
        _drop_texts(fig, ('Score J: priority-weighted',))
        fig.text(0.02, 0.03, 'Score J: priority-weighted sessions still alive when first served.', fontsize=12, color='#4b5563')
    return f


def load(script):
    src = open(os.path.join(ROOT, 'scripts', script)).read()
    for a, b in SWAP:
        src = src.replace(a, b)
    mod = types.ModuleType(script[:-3]); mod.__file__ = os.path.join(ROOT, 'scripts', script)
    sys.argv = [script]
    exec(compile(src.replace("if __name__ == '__main__':", "if False:"), script, 'exec'), mod.__dict__)
    mod.Writer = Grab
    return mod


def main():
    what = sys.argv[1:] or ['airsim', 'hil', 'comparison']
    if 'airsim' in what or 'hil' in what:
        D = load('make_demo_video.py')
        if 'airsim' in what:   # frame k = 2n; n = 112 -> round k = 224, t = 224 s
            Grab.want, Grab.name, Grab.decorate, Grab.fontscale = 112, 'snap_airsim_c.png', deco_airsim(D), 1.7
            D.seg_airsim('/dev/null', False)
        if 'hil' in what:
            Grab.want, Grab.name, Grab.decorate, Grab.fontscale = 112, 'snap_hil_c.png', deco_hil(D), 1.7
            D.seg_hil('/dev/null', False)
    if 'comparison' in what:   # frame n = 330 -> t = 660 s, as in the earlier panel
        C = load('make_comparison_video.py')
        Grab.want, Grab.name, Grab.decorate, Grab.fontscale = 330, 'snap_comparison_c.png', deco_comparison(C), 1.6
        sys.argv = ['make_comparison_video.py', '--out', '/tmp/cmp_snap']
        os.makedirs('/tmp/cmp_snap', exist_ok=True)
        C.main()


if __name__ == '__main__':
    main()

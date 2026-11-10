"""LaTeX tables for Section 7 from results/netsim_grid_fix_summary.json (or the summary given as argument) -> paper/tables/*.tex
Relative differences are (MAQAC - other)/other, so + means MAQAC is better; * = Holm-adjusted paired t-test p < .05."""
import json
import sys
S = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'results/netsim_grid_fix_summary.json'))
OUT = 'paper/tables/'
SC = {'urban': 'Urban', 'suburban': 'Suburban', 'disaster': 'Disaster'}


def cell(block, sc='urban', n=6, param=None, value=None):
    for e in S['cells']:
        if e['block'] == block and e['scenario'] == sc and e['n_uav'] == n and e['param'] == param and (value is None or e['value'] == str(value)):
            return e


def mq(e, m='maqac'):
    q = e['methods'][m]['qos_score']
    return f"${q['mean']:.0f}\\pm{q['ci95']:.0f}$"


def rel(e, m):
    v = e['vs_maqac'][m]
    s = f"{100 * v['rel_diff']:+.0f}".replace('-0', '0').replace('+0', '0').replace('-', '$-$')
    return s + ('$^{*}$' if v['p_holm'] < 0.05 else '')


def raw(e, m):
    return f"{e['methods'][m]['qos_score']['mean']:.0f}"


# main grid
L = [r'\begin{tabular}{@{}llrrrrrrrr@{}}', r'\toprule',
     r'& & \multicolumn{1}{c}{\textbf{MAQAC}} & \multicolumn{7}{c}{\textbf{MAQAC vs.\ baseline [\%]}} \\ \cmidrule(l){4-10}',
     r'\textbf{Scenario} & $n$ & \multicolumn{1}{c}{$J$ (95\% CI)} & RAG & IAD & Pot.\ game & MAPPO & Greedy-info & Greedy & Systematic \\', r'\midrule']
for sc in ('urban', 'suburban', 'disaster'):
    for k, n in enumerate((2, 4, 6, 8, 10)):
        e = cell('main', sc, n)
        L.append((SC[sc] if k == 0 else '') + f" & {n} & {mq(e)} & " + ' & '.join(rel(e, m) if m in e['vs_maqac'] else '--' for m in ('rag', 'iad', 'potgame', 'mappo', 'greedy_info', 'greedy', 'systematic')) + r' \\')
    L.append(r'\midrule' if sc != 'disaster' else r'\bottomrule')
L.append(r'\end{tabular}')
open(OUT + 'netsim_main.tex', 'w').write('\n'.join(L) + '\n')

# ablation
names = [('maqac', 'MAQAC (full)'), ('maqac_nocons', 'w/o record sharing (no consensus)'), ('maqac_share', 'with sharing of raw detections'),
         ('maqac_noprior', 'w/o density prior'), ('maqac_noqos', 'w/o QoS weighting (user count)'), ('maqac_nocc', 'w/o co-channel exclusion'),
         ('maqac_noconn', 'w/o backhaul-connectivity filter'), ('maqac_hard', r'hard partition ($\beta=0$)'), ('maqac_seq', 'sequential choice ($n$ hand-overs)')]
E4, E8 = cell('ablation', n=4), cell('ablation', n=8)


def var(e, m):
    if m == 'maqac':
        return mq(e) + ' & ---'
    v = e['vs_maqac'][m]; q = e['methods'][m]['qos_score']['mean']; base = e['methods']['maqac']['qos_score']['mean']
    s = f"{100 * (q / base - 1):+.0f}".replace('-0', '0').replace('+0', '0').replace('-', '$-$')
    return mq(e, m) + ' & ' + s + ('$^{*}$' if v['p_holm'] < 0.05 else '')


L = [r'\begin{tabular}{@{}lrrrr@{}}', r'\toprule', r'& \multicolumn{2}{c}{\textbf{4 UAVs}} & \multicolumn{2}{c}{\textbf{8 UAVs}} \\ \cmidrule(lr){2-3}\cmidrule(l){4-5}',
     r'\textbf{Variant} & $J$ & $\Delta$ [\%] & $J$ & $\Delta$ [\%] \\', r'\midrule']
for m, lab in names:
    L.append(f"{lab} & {var(E4, m)} & {var(E8, m)} " + r'\\')
L += [r'\bottomrule', r'\end{tabular}']
open(OUT + 'netsim_ablation.tex', 'w').write('\n'.join(L) + '\n')

# stress
P = [('n_channels', 'Channels $K$', [1, 2, 3, 4], None), ('p_loss', 'Message loss $p$', [0.0, 0.1, 0.3, 0.5], None),
     ('bh_range', 'Backhaul range [m]', [250.0, 350.0, 500.0, 700.0], None), ('p_fail', 'UAV failure prob.', [0.0, 0.25, 0.5], None),
     ('mobile_frac', 'Mobile users', [0.0, 0.5, 1.0], None), ('arrival_rate', r'Arrivals [s$^{-1}$]', [0.05, 0.1, 0.2], None),
     ('battery_wh', 'Battery [Wh]', [20.0, 40.0, 80.0], None), ('survival', 'Survival function', ['exp', 'weibull', 'deadline'], None),
     ('perception', 'Perception', ['oracle', 'onboard', 'offload'], None), ('bg_load', 'Backhaul load (offload)', [0.0, 0.5, 0.9], None),
     ('r_s', r'Service radius $r_s$ [m]', [50.0, 100.0, 150.0], None)]
L = [r'\begin{tabular}{@{}llrrrrrr@{}}', r'\toprule',
     r'\textbf{Parameter} & \textbf{Value} & \textbf{MAQAC} & \textbf{RAG} & \textbf{IAD} & \textbf{Pot.\ game} & \textbf{w/o excl.} & \textbf{vs.\ RAG [\%]} \\', r'\midrule']
for p, lab, vals, _ in P:
    for k, v in enumerate(vals):
        e = cell('stress', param=p, value=v)
        vs = str(v).replace('_', ' ')
        L.append((lab if k == 0 else '') + f" & {vs} & {mq(e)} & {raw(e, 'rag')} & {raw(e, 'iad')} & {raw(e, 'potgame')} & {raw(e, 'maqac_nocc')} & {rel(e, 'rag')} " + r'\\')
    L.append(r'\midrule' if p != 'r_s' else r'\bottomrule')
L.append(r'\end{tabular}')
open(OUT + 'netsim_stress.tex', 'w').write('\n'.join(L) + '\n')
print('tables written')

# coordination cost (results/netsim_coord_cost.json, scripts/netsim_coord_cost.py)
C = json.load(open('results/netsim_coord_cost.json'))['rows']
L = [r'\begin{tabular}{@{}rlrrrr@{}}', r'\toprule',
     r'$n$ & \textbf{Method} & \textbf{Iterations} & \textbf{Messages} & \textbf{Time [ms]} & $J$ \\', r'\midrule']
LAB = {'maqac': 'MAQAC', 'rag': 'RAG', 'maqac_seq': 'MAQAC-S'}
# Messages are counted per link for every method (3 Nov 2026). RAG's count is per link already; the simulator logs
# MAQAC-S as n-1 broadcasts, so its per-link count is d(d-1)/2 for d deciding UAVs (each choice to every later UAV),
# computed here from the mean number of sequential iterations d of each mission.
for n in (2, 4, 6, 8, 10):
    for k, m in enumerate(('maqac', 'rag', 'maqac_seq')):
        X = [r for r in C if r['method'] == m and r['n_uav'] == n]
        mean = lambda key: sum(x[key] for x in X) / len(X)
        L.append((f'{n}' if k == 0 else '') + f" & {LAB[m]} & {mean('coord_iters'):.1f} / {max(x['coord_iters_max'] for x in X):.0f} & "
                 f"{(sum(x['coord_iters'] * (x['coord_iters'] - 1) / 2 for x in X) / len(X) if m == 'maqac_seq' else mean('coord_msgs')):.0f} & {mean('decide_ms'):.1f} & {mean('qos_score'):.0f} " + r'\\')
    L.append(r'\midrule' if n != 10 else r'\bottomrule')
L.append(r'\end{tabular}')
open(OUT + 'netsim_coordcost.tex', 'w').write('\n'.join(L) + '\n')
print('coordination-cost table written')

# mission-level certificate (results/netsim_certificate_ltt.json + results/netsim_mission_certificate.pkl)
import pickle
import numpy as np
LT = json.load(open('results/netsim_certificate_ltt.json'))
R = pickle.load(open('results/netsim_mission_certificate.pkl', 'rb'))
LAB = {'oracle': 'Oracle (exact detections)', 'onboard': 'On board', 'offload': 'Offloaded', 'offload_congested': r'Offloaded, 90\% backhaul load'}
L = [r'\begin{tabular}{@{}lrrrrrr@{}}', r'\toprule',
     r'\textbf{Perception} & $J$ & $\hat\rho$ & $R$ & $\hat q$ & \textbf{Certified} & \textbf{Miss rate} \\', r'\midrule']
for k in ('oracle', 'onboard', 'offload', 'offload_congested'):
    E = [r for r in R if r['k'] == k]
    J = np.mean([e['J'] for e in E]); rh = np.mean([e['gh'] / e['ubh'] for e in E]); Re = np.mean([e['g'] / e['ubh'] for e in E])
    b = LT['results'][k]['ltt_bonf']
    L.append(f"{LAB[k]} & {J:.0f} & {rh:.2f} & {Re:.2f} & {b['q']:.2f} & {b['certified']:.2f} & {100 * b['test_miscoverage']:.1f}\\% " + r'\\')
L += [r'\bottomrule', r'\end{tabular}']
open(OUT + 'netsim_certificate.tex', 'w').write('\n'.join(L) + '\n')
print('certificate table written')

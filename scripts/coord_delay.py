#!/usr/bin/env python3
"""In-round coordination time per decision round (removes the limitation "coordination cost is counted in messages,
not in delays", user 5 Nov 2026). For each mission of the communication-stress studies the simulator logged the mean
number of sequential in-round stages (coord_iters) and of link messages (coord_msgs) per round. A stage must finish
before the next starts, so the in-round time is

    T = stages * t_stage + messages * L / R

t_stage = channel access, processing and propagation per stage; L = message size; R = effective backhaul rate.
MAQAC decides simultaneously and sends no in-round message (T = 0); its record exchange is common to all methods and
happens between rounds. Base values: t_stage = 2 ms, L = 1 kbit, R = 20 Mbit/s; t_stage = 1 and 5 ms as sensitivity.
With retransmissions (v3_comm_stress_arq.jsonl) the message term is scaled by the measured attempts per message.

    python3 scripts/coord_delay.py  ->  results/coord_delay.json (and a printed table)
"""
import json, glob
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
L_BITS, R_BPS = 1000.0, 20e6
T_STAGE = {'base': 2e-3, 'fast': 1e-3, 'slow': 5e-3}


def rows():
    from stress_rows import stress_rows  # ge20 rows with the bursty-loss fix (6 Nov 2026)
    arq = [json.loads(l) for f in sorted(glob.glob(str(ROOT / 'results' / 'v3_comm_stress_arq*.jsonl'))) for l in open(f)]
    for d in stress_rows() + arq:
        if 'error' not in d and d.get('coord_iters') is not None:
            yield d


def main():
    acc = defaultdict(list)
    for d in rows():
        if d['method'] not in ('rag', 'maqac', 'maqac_seq'):
            continue
        att = (d['tx_attempts'] / d['tx_msgs']) if d.get('tx_msgs') else 1.0
        stages = 0.0 if d['method'] == 'maqac' else d['coord_iters']
        msgs = 0.0 if d['method'] == 'maqac' else d['coord_msgs']
        for k, ts in T_STAGE.items():
            acc[(d['cond'], d['method'], d['n'], k)].append(1e3 * (stages * ts + msgs * att * L_BITS / R_BPS))
    out = {}
    for (c, m, n, k), v in sorted(acc.items()):
        out[f'{c}|{m}|{n}|{k}'] = dict(mean_ms=float(np.mean(v)), p95_ms=float(np.percentile(v, 95)), missions=len(v))
    json.dump(dict(model=dict(L_bits=L_BITS, R_bps=R_BPS, t_stage_s=T_STAGE), cells=out),
              open(ROOT / 'results' / 'coord_delay.json', 'w'), indent=1)
    for c in sorted({k.split('|')[0] for k in out}):
        print(c)
        for m in ('maqac', 'maqac_seq', 'rag'):
            print('  ', m.ljust(10), '  '.join(f"n={n}: {out.get(f'{c}|{m}|{n}|base', {}).get('mean_ms', float('nan')):5.1f} ms"
                                                for n in (4, 6, 8)))


if __name__ == '__main__':
    main()

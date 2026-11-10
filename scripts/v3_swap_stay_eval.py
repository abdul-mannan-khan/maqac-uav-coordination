#!/usr/bin/env python3
"""Full evaluation of the swap and stay variants on the v3 areas.

Settings fixed before this run, on tuning seeds 900-904 only (maqac-vehcom scripts/v3_swap_screen.py):
swap threshold eps = 0.01, stay bonus 0.1. Nothing is tuned here.
Methods: maqac_swap, maqac_seq_stay, maqac_swap_stay, rag_stay (RAG with the same stay bonus).
Cells, config and seeds as maqac-vehcom scripts/netsim_v3_study.py ('area_rest' areas: 1 km and 3 km; urban, suburban,
disaster; 4/6/8 UAVs; seeds 20000-20019). Reference rows (maqac, maqac_seq, rag, ...) come from
results/v3_area_rest/netsim_v3_area_rest.jsonl.
Rules (as scripts/analyze_v3_area_rest.py): a variant beats X in a cell if the mean paired gain in J_session is >= 3 %,
the 95 % CI is above 0 and the Holm p (18 cells) is < 0.05; reported vs rag and vs maqac_seq.

Runs from the bundle root next to the VehCom copy of scripts/netsim_v3_study.py (its job() is reused unchanged):
    python3 scripts/v3_swap_stay_eval.py check          # 6 area_rest rows must reproduce exactly
    python3 scripts/v3_swap_stay_eval.py run [workers]  # 1,440 missions, resumable
"""
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import netsim_v3_study as S   # noqa: E402

NEW = ('maqac_swap', 'maqac_seq_stay', 'maqac_swap_stay', 'rag_stay')
OUT = ROOT / 'results' / 'netsim_v3_swap_stay.jsonl'
CHECK = [(1000.0, 'urban', 4, 'maqac', 20000), (1000.0, 'disaster', 6, 'maqac_seq', 20001),
         (1000.0, 'suburban', 8, 'rag', 20002), (1000.0, 'urban', 6, 'maqac_hyb', 20003),
         (1000.0, 'disaster', 4, 'rag', 20004), (1000.0, 'suburban', 4, 'maqac_seq', 20005)]

if __name__ == '__main__':
    if sys.argv[1] == 'check':
        ref = {}
        for l in open(ROOT / 'results' / 'netsim_v3_area_rest.jsonl'):
            r = json.loads(l); ref[(r['W'], r['scenario'], r['n'], r['method'], r['seed'])] = r['J_session']
        with Pool(len(CHECK)) as p:
            res = p.map(S.job, CHECK)
        ok = all(r.get('J_session') == ref[a] for r, a in zip(res, CHECK))
        for r, a in zip(res, CHECK):
            print(a, r.get('J_session'), ref[a], 'MATCH' if r.get('J_session') == ref[a] else 'DIFF', r.get('error', ''))
        print('CHECK PASS' if ok else 'CHECK FAIL', flush=True)
        sys.exit(0 if ok else 1)
    done = [json.loads(l) for l in open(OUT)] if OUT.exists() else []
    have = {(d['W'], d['scenario'], d['n'], d['method'], d['seed']) for d in done if 'error' not in d}
    todo = [(W, sc, n, m, s) for W in S.AREAS for sc in S.SCEN for n in S.FLEETS for m in NEW for s in S.SEEDS
            if (W, sc, n, m, s) not in have]
    todo.sort(key=lambda a: (-a[0], a[3] != 'rag_stay', -a[2]))          # longest first
    print(f'{len(todo)} missions to run', flush=True)
    with Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 8) as p, open(OUT, 'a') as f:
        for i, r in enumerate(p.imap_unordered(S.job, todo)):
            f.write(json.dumps(r, default=float) + '\n'); f.flush()
            if (i + 1) % 100 == 0:
                print(f'{i + 1}/{len(todo)}', flush=True)
    print('swap/stay eval finished', flush=True)

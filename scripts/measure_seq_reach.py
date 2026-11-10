"""How often does netsim's MAQAC-S use an announcement it could not have received? (10 Nov 2026), checking that episode.py line 230 hands every earlier MAQAC-S choice to every
later UAV with only a per-pair loss draw, ignoring whether the two UAVs share a backhaul link.)

For every in-round hand-over j -> i of maqac_seq it records whether j and i were one-hop backhaul neighbours, connected
only through relays (hop count), or not connected at all, in the backhaul graph of that round. Measurement only: the
'none' condition uses p_loss = 1e-12 so that the hand-over code path (which calls msg_lost) is taken.
Usage: python3 scripts/measure_seq_reach.py <workers> [--seeds 3] -> results/seq_reach.jsonl + printed summary."""
import json, sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'netsim'))
import sim                          # noqa: E402
from sim import realistic           # noqa: E402
from episode import run_episode     # noqa: E402

HANDOVER_LINE = 230                 # episode.py: known = [... if not W.msg_lost(j, i)] (checked below)
src = open(ROOT / 'src' / 'netsim' / 'episode.py').read().split('\n')[HANDOVER_LINE - 1]
assert 'W.msg_lost(j, i)' in src and 'known' in src, src


def job(a):
    cond, W, sc, n, s = a
    f = (W / 1000.0) ** 2
    extra = dict(p_loss=0.4) if cond == 'loss40' else dict(p_loss=1e-12)
    cfg = realistic(scenario=sc, n_uav=n, world=W, n_users=int(200 * f), arrival_rate=0.1 * f, gateway=(W / 2, W / 2),
                    name=f'reach_{cond}_{int(W)}_{sc}_{n}', **extra)
    cnt = Counter()
    hopsum = defaultdict(int)
    orig = sim.World.msg_lost

    def patched(self, u, v):
        fr = sys._getframe(1)
        if fr.f_lineno == HANDOVER_LINE and fr.f_code.co_filename.endswith('episode.py'):
            A = np.zeros((n + 1, n + 1), bool)
            for (p, q) in self.bh['edges']:
                A[p, q] = True
            if A[u, v]:
                cnt['direct'] += 1
            else:                                   # BFS from u over the backhaul graph (incl. gateway)
                d = {u: 0}; fr_ = [u]
                while fr_:
                    nx = []
                    for x in fr_:
                        for y in np.where(A[x])[0]:
                            if y not in d:
                                d[y] = d[x] + 1; nx.append(y)
                    fr_ = nx
                if v in d:
                    cnt['relay'] += 1; hopsum['relay_hops'] += d[v]
                else:
                    cnt['none'] += 1
        return orig(self, u, v)

    sim.World.msg_lost = patched
    try:
        r = run_episode(cfg, 'maqac_seq', s, log_rounds=False)
        err = None
    except Exception as e:
        r, err = {}, repr(e)
    sim.World.msg_lost = orig
    return dict(cond=cond, W=W, scenario=sc, n=n, seed=s, error=err, qos_score=r.get('qos_score'), **cnt, **hopsum)


if __name__ == '__main__':
    args = sys.argv[1:]
    workers = int(args[0]) if args and args[0].isdigit() else 8
    ns = int(args[args.index('--seeds') + 1]) if '--seeds' in args else 3
    J = [(c, W, sc, n, s) for c in ('none', 'loss40') for W in (1000.0, 3000.0) for sc in ('urban', 'suburban', 'disaster')
         for n in (4, 6, 8) for s in range(20000, 20000 + ns)]
    J.sort(key=lambda a: (-a[1], -a[3]))
    out = ROOT / 'results' / 'seq_reach.jsonl'
    rows = []
    with Pool(workers) as p, open(out, 'w') as f:
        for r in p.imap_unordered(job, J, chunksize=1):
            rows.append(r); f.write(json.dumps(r, default=float) + '\n'); f.flush()
    agg = defaultdict(Counter)
    for r in rows:
        k = (r['cond'], int(r['W']), r['n'])
        for x in ('direct', 'relay', 'none', 'relay_hops'):
            agg[k][x] += r.get(x, 0)
    print('cond area n | direct relay none (share of hand-overs) | mean relay hops | errors')
    for k in sorted(agg):
        a = agg[k]; t = a['direct'] + a['relay'] + a['none']
        print(k, f"{a['direct']/t:.3f} {a['relay']/t:.3f} {a['none']/t:.3f}",
              f"{a['relay_hops']/max(1,a['relay']):.2f}", sum(1 for r in rows if r['error'] and (r['cond'], int(r['W']), r['n']) == k))

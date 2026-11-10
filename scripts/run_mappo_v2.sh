#!/bin/bash
# MAPPO baseline, protocol of 2026-10-30 (src/netsim/mappo.py train2):
#   urban training scenario, fleets {4, 6, 8} x training seeds {0, 1, 2}, 16 missions per iteration, 4 PPO epochs,
#   lr 3e-4 decayed linearly over the 1500-iteration cap, value normalisation;
#   validation every 10 iterations on 16 fixed missions (seeds 90000-90015, greedy policy);
#   stop when the mean validation score of the last 10 checks (100 iterations) is not above that of the previous 10 by
#   more than two standard errors, after at least 300 iterations; checkpoint = best validation score.
#   Test: each checkpoint on the grid's 30 test seeds (20000-20029) in all three scenarios -> results/mappo_v2_eval.jsonl
#   (method mappo_s<seed>).
# Usage on a 64-core host: bash scripts/run_mappo_v2.sh [PY] [WORKERS_PER_RUN]
set -u
PY=${1:-python3}
WK=${2:-7}
mkdir -p results/mappo_v2
for n in 4 6 8; do
  for s in 0 1 2; do
    $PY src/netsim/mappo.py train2 --n $n --train-seed $s --episodes 16 --workers $WK \
        --out results/mappo_v2/mappo_${n}_s${s}.pt > results/mappo_v2/train_${n}_s${s}.log 2>&1 &
  done
done
wait
for n in 4 6 8; do
  for s in 0 1 2; do
    $PY src/netsim/mappo.py eval --n $n --ckpt results/mappo_v2/mappo_${n}_s${s}.pt --scenarios urban,suburban,disaster \
        --workers 21 --method-name mappo_s${s} --results results/mappo_v2_eval.jsonl > results/mappo_v2/eval_${n}_s${s}.log 2>&1 &
  done
  wait
done
echo ALL_DONE > results/mappo_v2/DONE

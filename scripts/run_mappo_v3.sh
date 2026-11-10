#!/bin/bash
# MAPPO baseline, saturation protocol of 2026-11-01 (pre-registered; replaces v2's per-seed early stop):
#   urban training scenario, fleets {4, 6, 8} x training seeds {0..4}, 16 missions per iteration, 4 PPO epochs,
#   lr 3e-4 decayed linearly over the 1,500-iteration cap; EVERY run trains to the cap (no early stop), i.e.
#   24,000 training missions per seed; validation every 10 iterations on 32 fixed missions (seeds 90000-90031).
#   Saturation is judged afterwards on all seeds together by scripts/mappo_saturation.py (rule in its docstring).
#   Checkpoint = best validation score of each seed; test on the grid's 30 test seeds (20000-20029) in all three
#   scenarios -> results/mappo_v3_eval.jsonl (method mappo_s<seed>).
# Usage on a many-core host: bash scripts/run_mappo_v3.sh [PY] [WORKERS_PER_RUN] [PARALLEL_RUNS]
set -u
PY=${1:-python3}
WK=${2:-7}
PAR=${3:-9}
OUT=results/mappo_v3
mkdir -p $OUT
jobs_list=()
for n in 4 6 8; do for s in 0 1 2 3 4; do jobs_list+=("$n $s"); done; done
run_one() {
  set -- $1
  [ -f $OUT/mappo_${1}_s${2}_summary.json ] && return 0          # resume: skip finished runs
  $PY src/netsim/mappo.py train2 --n $1 --train-seed $2 --episodes 16 --workers $WK --max-iters 1500 \
      --no-stop --resume --n-val 32 --out $OUT/mappo_${1}_s${2}.pt > $OUT/train_${1}_s${2}.log 2>&1
}
export -f run_one; export PY WK OUT
printf '%s\n' "${jobs_list[@]}" | xargs -P $PAR -I{} bash -c 'run_one "{}"'
for n in 4 6 8; do
  for s in 0 1 2 3 4; do
    grep -q "\"method\": \"mappo_s${s}\".*\"n_uav\": ${n}" results/mappo_v3_eval.jsonl 2>/dev/null && continue
    $PY src/netsim/mappo.py eval --n $n --ckpt $OUT/mappo_${n}_s${s}.pt --scenarios urban,suburban,disaster \
        --workers 21 --method-name mappo_s${s} --results results/mappo_v3_eval.jsonl > $OUT/eval_${n}_s${s}.log 2>&1
  done
done
python3 scripts/mappo_saturation.py
echo ALL_DONE > $OUT/DONE

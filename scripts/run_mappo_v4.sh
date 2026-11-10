#!/bin/bash
# MAPPO v4 (pre-registered 2026-11-09, docs/MAPPO_V4_PREREG.md): as v3 but cap 3,000 iterations, lr decayed over 3,000.
#   urban training, fleets {4,6,8} x seeds {0..4}, 16 missions per iteration, validation every 10 iterations on 32
#   fixed missions (seeds 90000-90031), no early stop; best-validation checkpoint tested on the 30 grid test seeds.
# Usage: bash scripts/run_mappo_v4.sh [PY] [WORKERS_PER_RUN] [PARALLEL_RUNS] [EVAL_WORKERS]
set -u
PY=${1:-python3}
WK=${2:-15}
PAR=${3:-15}
EW=${4:-90}
OUT=results/mappo_v4
EVAL=results/mappo_v4_eval.jsonl
mkdir -p $OUT
jobs_list=()
for n in 4 6 8; do for s in 0 1 2 3 4; do jobs_list+=("$n $s"); done; done
run_one() {
  set -- $1
  [ -f $OUT/mappo_${1}_s${2}_summary.json ] && return 0
  $PY src/netsim/mappo.py train2 --n $1 --train-seed $2 --episodes 16 --workers $WK --max-iters 3000 \
      --no-stop --resume --n-val 32 --out $OUT/mappo_${1}_s${2}.pt > $OUT/train_${1}_s${2}.log 2>&1
}
export -f run_one; export PY WK OUT
printf '%s\n' "${jobs_list[@]}" | xargs -P $PAR -I{} bash -c 'run_one "{}"'
echo TRAIN_DONE > $OUT/TRAIN_DONE
for n in 4 6 8; do
  for s in 0 1 2 3 4; do
    grep -q "\"method\": \"mappo_s${s}\".*\"n_uav\": ${n}" $EVAL 2>/dev/null && continue
    $PY src/netsim/mappo.py eval --n $n --ckpt $OUT/mappo_${n}_s${s}.pt --scenarios urban,suburban,disaster \
        --workers $EW --method-name mappo_s${s} --results $EVAL > $OUT/eval_${n}_s${s}.log 2>&1
  done
done
$PY scripts/mappo_saturation.py --dir $OUT --cap 3000 --out results/mappo_v4_saturation.json > $OUT/saturation.log 2>&1
echo ALL_DONE > $OUT/DONE

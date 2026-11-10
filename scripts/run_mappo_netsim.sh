#!/bin/bash
# MAPPO baseline in the network-level simulator: train on urban (300 iterations x 16 missions), evaluate on the grid seeds.
set -e
PY=~/.venvs/maqac/bin/python
for n in 4 6 8; do
  $PY src/netsim/mappo.py train --n $n --iters 300 --episodes 16 --workers 8 --out results/mappo_netsim_${n}.pt
  $PY src/netsim/mappo.py eval --n $n --ckpt results/mappo_netsim_${n}.pt --scenarios urban,suburban,disaster --workers 8
done

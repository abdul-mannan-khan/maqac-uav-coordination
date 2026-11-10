#!/bin/bash
# Rerun the bursty-loss condition (ge20) after the Gilbert-Elliott fix (6 Nov 2026: burst state now advances once per
# round, not per message). 1,440 missions of v3_comm_stress.py (rag, maqac, maqac_seq, maqac_rag) + 360 of he2025_runs.py.
#   bash scripts/ge_fix_rerun.sh <workers>
W=${1:-8}
cd "$(dirname "$0")/.."
python3 scripts/v3_comm_stress.py $W --cond ge20 --out results/v3_comm_stress_gefix.jsonl && \
python3 scripts/he2025_runs.py $W --cond ge20 --out results/he2025_v3_gefix.jsonl && echo "ge fix rerun done"

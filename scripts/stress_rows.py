"""Rows of the communication-stress study with the bursty-loss fix applied (6 Nov 2026).

The Gilbert-Elliott chain used to advance once per message, so methods that send more messages per second (RAG, He
et al.) saw shorter bursts. It now advances once per round (bursts ~5 s for every method). The ge20 rows were rerun
(results/v3_comm_stress_gefix.jsonl, results/he2025_v3_gefix.jsonl) and replace the old ge20 rows here."""
import json, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / 'results'


def _read(files, fix):
    rows = [json.loads(l) for f in files for l in open(f)]
    if fix.exists():
        rows = [d for d in rows if d.get('cond') != 'ge20'] + [json.loads(l) for l in open(fix)]
    return rows


def stress_rows():
    """Four-method stress rows (rag, maqac, maqac_seq, maqac_rag)."""
    return _read(sorted(glob.glob(str(R / 'v3_comm_stress_shard*.jsonl'))), R / 'v3_comm_stress_gefix.jsonl')


def he_rows():
    """He et al. (TNSM 2025) rows, all conditions."""
    return _read([R / 'he2025_v3_shard0.jsonl'], R / 'he2025_v3_gefix.jsonl')

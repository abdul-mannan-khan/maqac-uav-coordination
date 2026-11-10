# v3_nostress_msgs.jsonl (9 Nov 2026)

Purpose: per-round coordination-message counts for the no-stress condition of the link-limited model, which the
original reference run (results/v3_area_rest/netsim_v3_area_rest.jsonl, 1-2 Nov) did not log. User asked for message
columns in the main-text table (Table 5). Run: `scripts/v3_comm_stress.py 100 --cond none --methods rag,maqac_seq`
on the MAPPO v4 Vast box's idle cores (no extra cost); 720 missions, 0 errors; md5 cc6aa918c13be1f4b66e0d2bde92390f.

Reproduction check: 708 of 720 missions reproduce the original J_session exactly. 12 differ (11 RAG, 1 MAQAC-S;
-2.4 % to +2.9 %, three at rounding level) because src/netsim changed after 2 Nov (bursty-loss fix, loss-fairness fix,
message logging). Means per method and area change by < 0.3 points (RAG 3 km 1782.8 -> 1783.0, MAQAC-S 1783.0 ->
1782.7). The paper keeps the ORIGINAL scores; only the message counts are taken from this run.

Result: RAG 32 / 98 / 217 link messages per round with 4 / 6 / 8 UAVs (matches the one-channel condition and the
numbers already in the text); MAQAC-S 6 / 15 / 27 per link (d(d-1)/2 rule of 3 Nov); MAQAC 0.

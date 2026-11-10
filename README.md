# MAQAC: certified coordination of UAV aerial base stations — code and data

Companion deposit of the article "Certified coordination of UAV aerial base stations under imperfect perception and
backhaul delay" (Vehicular Communications, submitted). Authors: Abdul-Manan Khan (University of West London), Rabia Nazir (University of Engineering and Technology Lahore),
Vishwanath Bijalwan (Amity University Punjab), Venkatesan Vellaiyan (BITS Pilani Dubai Campus).

| Folder | Content |
|---|---|
| `src/netsim/` | network-level simulator (A2G channel, SINR admission, lossy multi-hop backhaul, batteries, mobility), MAQAC, MAQAC-S and all baselines |
| `sim/airsim/` | AirSim CityEnviron + PX4 SITL bridge |
| `scripts/` | experiment runners, analysis and table scripts (one per table of the paper) |
| `results/` | per-mission results (JSON lines) and the summaries behind every table and figure |
| `data/cities/` | OpenStreetMap height maps (ODbL) |
| `media/` | videos: `maqac_hil_airsim_replay.mp4` (60 s: a logged hardware-in-the-loop city mission replayed in AirSim with a chase camera, next to map, altitude and decision-time panels; made by `sim/hil/replay_hil_airsim.py`); `maqac_demo.mp4` / `demo_narrated.mp4` (about 100 s: MAQAC and RAG side by side, PX4 flights in AirSim's city, the HIL replay, a chase camera); `maqac_comparison.mp4` / `comparison_narrated.mp4` (six methods on the same mission); `maqac_presentation_narrated.mp4` (narrated presentation, about 9 min) |
| `sim/hil/` | hardware-in-the-loop runner (Pixhawk 6C + Jetson Orin Nano), MAVLink router, and `replay_hil_airsim.py` (AirSim replay video of a logged HIL mission) |

Requirements: Python 3.11, numpy, scipy (PyTorch for the MAPPO baseline). Every runner prints its usage in its
docstring; for example `python3 scripts/v3_comm_stress.py 8` reruns the message-loss study, and
`python3 scripts/make_commstress_table.py` rebuilds Table 5 from `results/`.

Licences: code MIT; results CC BY 4.0; city height maps ODbL.

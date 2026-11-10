# AirSim (Windows build) + PX4 SITL on one Vast.ai GPU box, under Wine

> **Scope: ONLY for AirSim environments that exist only as Windows builds**, i.e. in AirSim 1.8.1
> **CityEnviron** and **Coastline** (city/urban and coastal maps). Every other AirSim environment has a native Linux
> build (LandscapeMountains, Blocks, AirSimNH (Neighborhood), AbandonedPark, Africa_Savannah, Building_99, MSBuild2018,
> TrapCamera, ZhangJiajie): run those natively on Linux, with no Wine and without this container. Projects that do not
> use AirSim (e.g. MuJoCo, Gazebo, plain Python on CPU Vast boxes) are not affected at all.

Standard set-up for AirSim/PX4 simulation runs. Validated 6-7 Nov 2026 on 47 MAQAC re-fly missions (6 and 4 UAVs, CityEnviron, clock 0.7, ~9.5 min per
300 s mission, 0 failures).

## Container
- Image: `nvidia/cuda:12.2.2-base-ubuntu22.04`
- Docker options: `-e NVIDIA_DRIVER_CAPABILITIES=all -e NVIDIA_VISIBLE_DEVICES=all` (mounts the NVIDIA Vulkan/GLX/EGL libraries)
- Disk 80 GB; any NVIDIA GPU with >= 8 GB (tested: RTX A4000, driver 595); >= 16 cores for 6 PX4 instances.

## Files
| File | What it does |
|---|---|
| `rent_box.sh <offer> <hours>` | rents the box with the image/options above, waits for ssh, starts a laptop-side hard stop; writes `instance.txt`, `ssh.txt` |
| `box_setup.sh` | ON the box (~40 min): WineHQ 11.0 (pinned 11.0.0.0~jammy-1) + DXVK 3.1.1, AirSim 1.8.1 CityEnviron from the official GitHub release (v1.8.1-windows), PX4 v1.14.3 SITL, Python deps |
| `box_campaign.sh plan.txt ...` | ON the box: per mission, AirSim map (off-screen) with N vehicles, PX4 start, scene reset, mission, up to 3 tries; resumable |
| `monitor.sh` | laptop: pulls results every 20 min, 90-min stall rule, destroys the box when the campaign finishes |

## Fixes that were needed (do not undo)
1. DXVK **3.1.1** (2.3.1 hangs 60 s in vkCreateDevice on NVIDIA 595, then Unreal "Fatal error").
2. Vulkan ICD = `libEGL_nvidia.so.0` with `VK_ICD_FILENAMES` pointing only at it (the GLX ICD needs an NVIDIA X server).
3. `WINEDLLOVERRIDES='mscoree,mshtml='` when creating the prefix (Mono/Gecko dialogs hang on a headless display).
4. Launch the real `.../Binaries/Win64/CityEnviron.exe` with `-dx11 -RenderOffScreen` under Xvfb; settings `ViewMode: NoDisplay`.
5. PX4 1.14 build: `pip install empy==3.3.4`; placeholder tag in `platforms/nuttx/NuttX/nuttx` (shallow clone).
6. Do not pipe a script that spawns PX4 into `tail` (children keep the pipe open). Do not `pkill -f` over ssh (kills your own shell).

## Prebuilt image and GPU driver rule
- Image: `abdulmannan617/airsim-city-wine:1.8.1-wine11-dxvk3.1.1`
  (digest `sha256:8ad0d8cec214974a8b8150efe610fdddb43c227f71beb46e38613a723ebb482f`, 5.5 GB; built from this recipe).
  Self-test 8/8 pass in container mode (RTX 3080 Ti, driver 595.91), incl. a down-camera Scene image under
  `-RenderOffScreen`. Commands: city-start/stop/status, city-settings, px4-sitl, city-selftest, city-flytest.
- **NVIDIA driver >= 595 only.** Driver 575 (RTX 3060) froze the renderer ("GameThread timed out waiting for
  RenderThread" / simGetImages timeouts) in 3 of 4 tests; 576-594 untested. Filter Vast offers by driver (the CLI's
  driver_version>= query fails; the image README has a Python filter). Validated here: RTX A4000 driver 595.99.

## Rules that still apply
State the cost first; auto-teardown; stall and hard-stop rules; never copy restricted data (e.g. london_lidar.npz,
manhattan_nyc.npz) to Vast. Other maps: download the official AirSim release on the box; do not upload from the laptop.

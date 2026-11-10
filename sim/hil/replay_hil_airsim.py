"""Replay of a logged hardware-in-the-loop city mission in AirSim CityEnviron, as a video (10 Nov 2026).

The 4 Nov city HIL campaign logged, every 1 s round, the Pixhawk-flown UAV 0's position (act0, from PX4's own estimate
in AirSim), the other UAVs' positions (upos) and commanded altitudes (z_cmd), and the Jetson's decision time. No camera
footage was recorded then. This script places the three UAVs at the logged positions (linear interpolation between
rounds; poses set just before each capture), films UAV 0 with a chase camera, and composes each AirSim frame with the logged
map, altitude and decision-time panels. It is a replay of logged data, labelled as such in every frame.

Stages (run on a Vast GPU box with abdulmannan617/airsim-city-wine, after `city-settings --mode simpleflight --n 3
--overview > s.json; city-start s.json`):
  python3 replay_hil_airsim.py render  --run RUN_DIR --hm heightmap.npz --out OUT   # AirSim frames -> OUT/airsim/
  python3 replay_hil_airsim.py compose --run RUN_DIR --hm heightmap.npz --out OUT   # OUT/frames/ + OUT/hil_airsim_replay.mp4
Frames: 5 per logged second (1,500 for 300 s); video 25 fps = 5x real time."""
import argparse, json, os, subprocess, sys, time
import numpy as np

L, ORIGIN = 600.0, (40.0, -10.0)          # HIL city area frame (sim/hil/city.py): 600 m, origin N 40, E -10
FPS_SAMPLE, FPS_VIDEO = 5, 25
BG, FG, MUTED = '#0f1420', '#e8ecf3', '#9aa4b5'
UAV_COL = ['#7ee081', '#c792ea', '#ffd166']


def to_world(xy):                          # area (x, y) -> AirSim world (N, E); same as heightmap.AreaFrame.to_world
    xy = np.asarray(xy, float)
    return np.stack([ORIGIN[0] + xy[..., 1] - L / 2, ORIGIN[1] + xy[..., 0] - L / 2], -1)


def load(run):
    R = [json.loads(l) for l in open(os.path.join(run, 'rounds.jsonl'))]
    t = np.array([r['t'] for r in R], float)
    P = np.zeros((len(R), 3, 3))                                     # rounds x UAV x (N, E, up)
    for k, r in enumerate(R):
        ne = to_world(np.array(r['upos']))
        ne[0] = to_world(np.array(r['act0'][:2]))
        P[k, :, :2] = ne
        P[k, 0, 2] = r['act0'][2]
        P[k, 1:, 2] = r['z_cmd'][1:]
    ms = np.array([r['fleet_decide_ms'] for r in R])
    return R, t, P, ms


def interp(t, P, T, smooth_s=1.0):
    """Linear interpolation of the 1 s log, then a moving average over smooth_s (removes the kink at every logged
    second, which made the replay jerk; changes positions by well under the 2-4 m PX4 tracking error)."""
    out = np.empty((len(T),) + P.shape[1:])
    w = max(1, int(round(smooth_s * FPS_SAMPLE)))
    k = np.ones(w) / w
    for i in range(P.shape[1]):
        for d in range(3):
            x = np.interp(T, t, P[:, i, d])
            out[:, i, d] = np.convolve(np.pad(x, (w // 2, w - 1 - w // 2), mode='edge'), k, mode='valid') if w > 1 else x
    return out


def headings(Q, max_rate_deg_s=8.0):
    """Camera (and UAV 0) heading: direction of UAV 0's horizontal motion over the last ~5 s, kept while it hovers,
    then rate-limited to max_rate_deg_s of mission time and smoothed, so the chase view turns slowly (an unlimited
    heading swung the camera within a few frames and the replay appeared to jump, 10 Nov 2026)."""
    lag = 5 * FPS_SAMPLE
    v = Q[:, 0, :2] - Q[np.maximum(np.arange(len(Q)) - lag, 0), 0, :2]
    yaw = np.zeros(len(Q)); last = float(np.arctan2(*(Q[min(len(Q) - 1, lag), 0, :2] - Q[0, 0, :2])[::-1]))
    for i, (dn, de) in enumerate(v):
        if np.hypot(dn, de) > 5.0:                      # moved > 5 m in 5 s: follow the direction of travel
            last = np.arctan2(de, dn)
        yaw[i] = last
    step = np.radians(max_rate_deg_s) / FPS_SAMPLE
    out = np.empty_like(yaw); out[0] = yaw[0]
    for i in range(1, len(yaw)):
        d = (yaw[i] - out[i - 1] + np.pi) % (2 * np.pi) - np.pi
        out[i] = out[i - 1] + np.clip(d, -step, step)
    k = np.ones(3 * FPS_SAMPLE) / (3 * FPS_SAMPLE)
    return np.convolve(np.pad(out, (len(k) // 2, len(k) - 1 - len(k) // 2), mode='edge'), k, mode='valid')


def render(a):
    import airsim
    from PIL import Image
    R, t, P, ms = load(a.run)
    T = np.arange(0, t[-1] + 1e-9, 1.0 / FPS_SAMPLE)
    Q = interp(t, P, T)
    yaw = headings(Q)
    c = airsim.MultirotorClient('127.0.0.1', timeout_value=60)
    c.confirmConnection()
    names = ['UAV0', 'UAV1', 'UAV2']
    od = os.path.join(a.out, 'airsim'); os.makedirs(od, exist_ok=True)

    def place(k):
        """Vehicles first; then the camera relative to UAV 0's pose as AirSim reports it. The vehicle and camera updates
        reach the renderer in different frames, so placing both at once made the drone jitter by 20-30 px between
        frames (10 Nov 2026); waiting and reading the pose back keeps them in step."""
        for i, nm in enumerate(names):
            n, e, up = Q[k, i]
            ya = yaw[k] if i == 0 else 0.0
            c.simSetVehiclePose(airsim.Pose(airsim.Vector3r(float(n), float(e), float(-up)),
                                            airsim.to_quaternion(0, 0, float(ya))), True, vehicle_name=nm)
        time.sleep(0.06)
        q = c.simGetVehiclePose(vehicle_name='UAV0').position
        n, e, d = q.x_val, q.y_val, q.z_val
        back, high = 20.0, 6.0
        cam = airsim.Pose(airsim.Vector3r(float(n - back * np.cos(yaw[k])), float(e - back * np.sin(yaw[k])), float(d - high)),
                          airsim.to_quaternion(-0.29, 0, float(yaw[k])))
        c.simSetCameraPose('overview', cam, external=True)
        time.sleep(0.06)
        return np.array([n, e, -d])

    def grab():
        for _ in range(2):                                  # keep the second image: the first may predate the last pose
            r = c.simGetImages([airsim.ImageRequest('overview', airsim.ImageType.Scene, False, False)], external=True)[0]
        return np.frombuffer(r.image_data_uint8, np.uint8).reshape(r.height, r.width, 3)[:, :, ::-1]

    # Settings use PhysicsEngineName = ExternalPhysicsEngine: no gravity or controller acts on the vehicles, so they stay
    # exactly at the poses set here (with the default physics they fell and tumbled between set and capture, which made
    # the drone wobble in the first renders, 10 Nov 2026; while paused, AirSim ignores simSetVehiclePose).
    start = len([f for f in os.listdir(od) if f.endswith('.jpg')])          # resumable
    for k in range(start, len(T)):
        got = place(k)
        err = float(np.linalg.norm(got - Q[k, 0]))
        if err > 0.5:
            print(f'frame {k}: UAV0 readback off by {err:.2f} m', flush=True)
        if k % 100 == 0:
            print(f'frame {k}/{len(T)}  UAV0 set {Q[k, 0].round(1).tolist()} readback {got.round(1).tolist()}', flush=True)
        Image.fromarray(grab()).save(os.path.join(od, f'{k:05d}.jpg'), quality=90)
    print('render done', flush=True)


def compose(a):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    R, t, P, ms = load(a.run)
    T = np.arange(0, t[-1] + 1e-9, 1.0 / FPS_SAMPLE)
    Q = interp(t, P, T)
    z = np.load(a.hm)
    n0, e0, res, H = float(z['n0']), float(z['e0']), float(z['res']), z['h']
    lo, hi = -330, 330
    i0, i1 = int((lo - n0) / res), int((hi - n0) / res); j0, j1 = int((lo - e0) / res), int((hi - e0) / res)
    hmap = np.clip(H[i0:i1, j0:j1], 0, 200)
    res_ = json.load(open(os.path.join(a.run, 'result.json')))
    method = {'maqac_seq': 'MAQAC-S', 'maqac': 'MAQAC', 'rag': 'RAG'}.get(res_.get('method'), res_.get('method'))
    fd = os.path.join(a.out, 'frames'); os.makedirs(fd, exist_ok=True)
    f = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=BG)
    axi = f.add_axes([0.012, 0.215, 0.655, 0.655]); axi.axis('off')
    axm = f.add_axes([0.685, 0.42, 0.30, 0.45])
    axz = f.add_axes([0.71, 0.235, 0.275, 0.13])
    axd = f.add_axes([0.71, 0.075, 0.275, 0.10])
    for k in range(len(T)):
        src = os.path.join(a.out, 'airsim', f'{k:05d}.jpg')
        if not os.path.exists(src):
            break
        for ax in (axi, axm, axz, axd):
            ax.cla()
        axi.imshow(Image.open(src)); axi.axis('off')
        axm.imshow(hmap, origin='lower', extent=[lo, hi, lo, hi], cmap='bone', vmin=-20, vmax=220)
        axm.set_xticks([]); axm.set_yticks([])
        kk = int(T[k])
        for i in range(3):
            tr = Q[max(0, k - 300):k + 1, i]
            axm.plot(tr[:, 1], tr[:, 0], color=UAV_COL[i], lw=1.8 if i == 0 else 1.0, alpha=0.95 if i == 0 else 0.65)
            axm.plot(Q[k, i, 1], Q[k, i, 0], marker='^', ms=11 if i == 0 else 7, color=UAV_COL[i], mec='black', mew=0.6)
        for ax_ in (axz, axd):
            ax_.set_facecolor(BG); ax_.tick_params(colors=MUTED, labelsize=9)
            for s_ in ax_.spines.values():
                s_.set_color('#2a3448')
        axz.plot(T[:k + 1], Q[:k + 1, 0, 2], color=UAV_COL[0], lw=2)
        axz.set_xlim(0, T[-1]); axz.set_ylim(0, 380); axz.set_ylabel('altitude [m]', color=MUTED, fontsize=10)
        axd.plot(t[:kk + 1], ms[:kk + 1], color='#ffd166', lw=1.2)
        axd.set_xlim(0, T[-1]); axd.set_ylim(0, 40); axd.set_ylabel('decision [ms]', color=MUTED, fontsize=10)
        axd.set_xlabel('mission time [s]', color=MUTED, fontsize=10)
        f.texts.clear()
        f.text(0.012, 0.965, f'Hardware in the loop in AirSim CityEnviron ({method}, three UAVs)    t = {T[k]:5.1f} s',
               color=FG, fontsize=20, va='top', weight='bold')
        f.text(0.012, 0.915, 'UAV 0 (green) flown by PX4 on a Pixhawk 6C; fleet decisions on a Jetson Orin Nano; '
               'AirSim supplied physics and sensors.', color=MUTED, fontsize=13, va='top')
        f.text(0.012, 0.185, 'Chase camera behind UAV 0. Replay of the logged flight (4 Nov 2026): positions logged every 1 s, '
               'interpolated and smoothed over 1 s; video at 5x real time.', color=MUTED, fontsize=12, va='top')
        f.text(0.685, 0.895, 'Map: building heights (AirSim survey); tracks of the last 60 s', color=MUTED, fontsize=11, va='top')
        f.savefig(os.path.join(fd, f'{k:05d}.png'), facecolor=BG)
        if k % 100 == 0:
            print(f'composed {k}/{len(T)}', flush=True)
    plt.close(f)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS_VIDEO), '-i', os.path.join(fd, '%05d.png'),
                    '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', os.path.join(a.out, 'hil_airsim_replay.mp4')],
                   check=True)
    print('video done', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('render', 'compose'))
    ap.add_argument('--run', required=True)
    ap.add_argument('--hm', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    render(a) if a.stage == 'render' else compose(a)

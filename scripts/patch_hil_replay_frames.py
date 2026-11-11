"""Repair render-glitch frames in the AirSim HIL replay video (11 Nov 2026).

AirSim occasionally drew a frame with the UAV at a wrong height (or a stale background). For each listed run of bad
frames, the camera panel is rebuilt by optical-flow interpolation between the good frames on either side; the map and
plot panels stay as rendered. Input: results/hil_video/maqac_hil_airsim_replay_unpatched.mp4.
    python3 scripts/patch_hil_replay_frames.py
"""
import os, subprocess
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'results', 'hil_video', 'maqac_hil_airsim_replay_unpatched.mp4')
OUT = os.path.join(ROOT, 'results', 'hil_video', 'maqac_hil_airsim_replay.mp4')
W, H, FPS = 1920, 1080, 25
BAD = [(31, 31)]                                   # stale background, UAV drawn too high: flow interpolation
HOLD = [(595, 597), (1158, 1159)]                  # UAV drawn at a wrong height: hold the previous good frame
# (flow interpolation ghosts the UAV here because the camera moves fast; the held frames were checked on 10 Nov)
X0, X1, Y0, Y1 = 18, 1286, 135, 852               # camera panel (axes [0.012, 0.215, 0.655, 0.655])


def interp(a, b, t):
    """Frame between a (t=0) and b (t=1) by warping both along DIS optical flow and blending."""
    ga, gb = (cv2.cvtColor(x, cv2.COLOR_RGB2GRAY) for x in (a, b))
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    fab, fba = dis.calc(ga, gb, None), dis.calc(gb, ga, None)
    h, w = ga.shape
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    wa = cv2.remap(a, gx - t * fab[..., 0], gy - t * fab[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    wb = cv2.remap(b, gx - (1 - t) * fba[..., 0], gy - (1 - t) * fba[..., 1], cv2.INTER_LINEAR,
                   borderMode=cv2.BORDER_REPLICATE)
    return ((1 - t) * wa.astype(np.float32) + t * wb.astype(np.float32)).round().astype(np.uint8)


def main():
    need = {n for s, e in BAD + HOLD for n in (s - 1, e + 1)}
    bad = {n for s, e in BAD + HOLD for n in range(s, e + 1)}
    dec = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-i', SRC, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                           stdout=subprocess.PIPE)
    frames, keep = [], {}
    n = 0
    while True:
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        if n in need or n in bad:
            keep[n] = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        n += 1
    dec.wait()
    total = n
    fixed = {}
    for s, e in BAD:
        a, b = keep[s - 1][Y0:Y1, X0:X1], keep[e + 1][Y0:Y1, X0:X1]
        for k in range(s, e + 1):
            f = keep[k].copy()
            f[Y0:Y1, X0:X1] = interp(a, b, (k - s + 1) / (e - s + 2))
            fixed[k] = f
    for s, e in HOLD:
        for k in range(s, e + 1):
            fixed[k] = keep[s - 1]
    dec = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-i', SRC, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                            '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
                            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', OUT], stdin=subprocess.PIPE)
    for k in range(total):
        buf = dec.stdout.read(W * H * 3)
        enc.stdin.write(fixed[k].tobytes() if k in fixed else buf)
    enc.stdin.close(); enc.wait(); dec.wait()
    print('wrote', OUT, total, 'frames; rebuilt', sorted(fixed))


if __name__ == '__main__':
    main()

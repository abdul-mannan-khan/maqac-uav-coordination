#!/usr/bin/env python3
"""Narrated presentation video of the MAQAC talk (1920x1080, 30 fps), with the comparison and demo videos inside it.

Inputs (all in this repository):
  presentation/narration.json   spoken text per slide and per video clip (order of the talk)
  presentation/slides/*.html    the deck's slides (one <section> each, the Slides format), images in presentation/assets/
  demo/maqac_demo.mp4 + demo/seg/*.mp4 and cmp/maqac_comparison.mp4  (scripts/make_demo_video.py, make_comparison_video.py)
Steps: render every slide with headless Chromium (Playwright), synthesise each narration with Piper TTS, put a slide's
narration over its picture, and the clip narrations over the clips (a clip's last frame is held if its narration is
longer), then join everything. Outputs in --out: maqac_presentation_narrated.mp4, comparison_narrated.mp4,
demo_narrated.mp4, slides/*.png, narration/*.wav.

    python3 scripts/make_presentation_video.py --voice-dir voices --out talk
Needs ffmpeg, playwright (chromium) and piper-tts.
"""
import argparse, json, os, re, subprocess, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS, W, H = 30, 1920, 1080
ICONS = {  # Feather icons (MIT), stroke = currentColor
    'Check': '<polyline points="20 6 9 17 4 12"/>',
    'Clock': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    'Link': '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    'Search': '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'}
CSS = """*{margin:0;box-sizing:border-box} html,body{margin:0;background:#000}
section{position:relative;width:1920px;height:1080px;overflow:hidden} div:not([style*="display"]){display:flex;flex-direction:column}
section > :not([style*="position:absolute"]){position:relative;z-index:1}
h1{font-size:96px;font-weight:600;line-height:1.1} h2{font-size:64px;font-weight:600;line-height:1.15}
h3{font-size:44px;font-weight:600;line-height:1.2} p{font-size:32px;line-height:1.4} aside{display:none} img{display:block}
li{line-height:inherit}"""
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400..700&display=swap">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">')


def sh(*a):
    subprocess.run(a, check=True)


def prep_slide(html, assets):
    def icon(m):
        name = m.group(1); st = m.group(2)
        return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
                f'stroke-linejoin="round" style="{st};flex:none">{ICONS.get(name, "")}</svg>')
    html = re.sub(r'<x-icon name="(\w+)" style="([^"]*)"></x-icon>', icon, html)

    def arrow(m):
        st = m.group(1)
        col = re.search(r'background:\s*([#\w]+)', st).group(1)
        w = int(re.search(r'width:\s*(\d+)px', st).group(1)); h = int(re.search(r'height:\s*(\d+)px', st).group(1))
        return (f'<svg width="{w}" height="{h}" viewBox="0 0 56 32" preserveAspectRatio="none" style="flex:none">'
                f'<polygon points="0,10 34,10 34,0 56,16 34,32 34,22 0,22" fill="{col}"/></svg>')
    html = re.sub(r'<x-shape kind="arrow-right" style="([^"]*)"></x-shape>', arrow, html)
    for blob, f in assets.items():
        html = html.replace(f'/_blob/{blob}', 'file://' + f)
    return f'<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{html}</body></html>'


def render_slides(ids, src, assets, out):
    from playwright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport=dict(width=W, height=H))
        for i in ids:
            html = prep_slide(open(os.path.join(src, f'{i}.html')).read(), assets)
            fn = os.path.join(out, f'{i}.html'); open(fn, 'w').write(html)
            pg.goto('file://' + os.path.abspath(fn), wait_until='networkidle')
            pg.evaluate('document.fonts.ready'); pg.wait_for_timeout(400)
            pg.screenshot(path=os.path.join(out, f'{i}.png'), clip=dict(x=0, y=0, width=W, height=H))
        b.close()


def tts(text, model, path):
    subprocess.run(['piper', '--model', model, '--output_file', path, '--sentence_silence', '0.35', '--length_scale', '1.05'],
                   input=text.encode(), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16), w.getframerate()


def write_wav(path, x, sr):
    with wave.open(path, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(x.astype(np.int16).tobytes())


def dur(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True).stdout)


ENC = ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-crf', '23', '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-b:a', '128k']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='talk')
    ap.add_argument('--voice-dir', default='voices')
    ap.add_argument('--work', default='.')
    a = ap.parse_args()
    N = json.load(open(os.path.join(ROOT, 'presentation', 'narration.json')))
    model = os.path.join(a.voice_dir, N['voice'] + '.onnx')
    out = a.out; os.makedirs(os.path.join(out, 'narration'), exist_ok=True); os.makedirs(os.path.join(out, 'seg'), exist_ok=True)
    assets = {k: os.path.abspath(os.path.join(ROOT, 'presentation', 'assets', v))
              for k, v in json.load(open(os.path.join(ROOT, 'presentation', 'assets', 'map.json'))).items()}
    slides = [k for k in N['order'] if not k.startswith('clip:')]
    render_slides(slides, os.path.join(ROOT, 'presentation', 'slides'), assets, os.path.join(out, 'slides'))
    segs = []
    for k in N['order']:
        if not k.startswith('clip:'):
            wv = os.path.join(out, 'narration', f'{k}.wav'); tts(N['slides'][k], model, wv)
            x, sr = read_wav(wv)
            x = np.concatenate([np.zeros(int(0.6 * sr)), x, np.zeros(int(0.9 * sr))])
            write_wav(wv, x, sr)
            d = len(x) / sr
            s = os.path.join(out, 'seg', f'{len(segs):02d}_{k}.mp4')
            sh('ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-framerate', str(FPS), '-t', f'{d:.3f}',
               '-i', os.path.join(out, 'slides', f'{k}.png'), '-i', wv, '-map', '0:v', '-map', '1:a',
               '-t', f'{d:.3f}', '-tune', 'stillimage', *ENC, s)
            segs.append(s); print('slide', k, round(d, 1), flush=True)
            continue
        c = N['clips'][k[5:]]
        vid = os.path.join(a.work, c['video'])
        vd = dur(vid)
        starts = {}
        if any(str(t).startswith('seg:') for t, _ in c['parts']):          # demo: part offsets = segment starts
            seg_dir = os.path.join(os.path.dirname(vid), 'seg')
            order = [l.split("'")[1] for l in open(os.path.join(seg_dir, 'list.txt'))]
            t0 = 0.0
            for f in order:
                starts['seg:' + os.path.basename(f)[:-4]] = t0; t0 += dur(f)
        sr = None; track = None; t_end = 0.0
        for t, text in c['parts']:
            wv = os.path.join(out, 'narration', f'{k[5:]}_{len(starts)}_{abs(hash(text)) % 10**6}.wav')
            tts(text, model, wv)
            x, sr = read_wav(wv)
            t0 = starts.get(t, t) if isinstance(t, str) else float(t)
            t0 = max(float(t0) + 0.4, t_end + 0.3)
            if track is None:
                track = np.zeros(int((vd + 60) * sr))
            i0 = int(t0 * sr); track[i0:i0 + len(x)] = x; t_end = t0 + len(x) / sr
        total = max(vd, t_end + 1.0)
        track = track[:int(total * sr)]
        wv = os.path.join(out, 'narration', f'{k[5:]}_track.wav'); write_wav(wv, track, sr)
        s = os.path.join(out, 'seg', f'{len(segs):02d}_{k[5:]}.mp4')
        sh('ffmpeg', '-y', '-loglevel', 'error', '-i', vid, '-i', wv, '-filter_complex',
           f'[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},'
           f'tpad=stop_mode=clone:stop_duration={max(0.0, total - vd) + 0.5:.2f}[v]',
           '-map', '[v]', '-map', '1:a', '-t', f'{total:.3f}', *ENC, s)
        segs.append(s); print('clip', k, round(vd, 1), '->', round(total, 1), flush=True)
        sh('ffmpeg', '-y', '-loglevel', 'error', '-i', s, '-c:v', 'libx264', '-crf', '27', '-c:a', 'copy',
           os.path.join(out, f'{k[5:]}_narrated.mp4'))
    lst = os.path.join(out, 'seg', 'list.txt')
    open(lst, 'w').write(''.join(f"file '{os.path.abspath(s)}'\n" for s in segs))
    final = os.path.join(out, 'maqac_presentation_narrated.mp4')
    sh('ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', final)
    print('wrote', final, round(dur(final), 1), 's')


if __name__ == '__main__':
    main()

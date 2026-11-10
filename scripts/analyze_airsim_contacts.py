#!/usr/bin/env python3
"""AirSim in-flight contacts vs the visible-geometry height map (6 Nov 2026). Usage: analyze_airsim_contacts.py results/airsim_contacts.json"""
import json, glob, numpy as np, collections, sys
R='results/airsim/'
z=np.load(R+'v3_campaign/survey/heightmap.npz'); H=z['h']; n0,e0,res=float(z['n0']),float(z['e0']),float(z['res'])
N=n0+(np.arange(H.shape[0])+.5)*res; E=e0+(np.arange(H.shape[1])+.5)*res
NN,EE=np.meshgrid(N,E,indexing='ij')
rows=[]
for camp in ('v3_campaign','cert_campaign'):
  for f in sorted(glob.glob(R+camp+'/runs/*/result.json')):
    d=json.load(open(f)); run=f.split('/')[-2]
    if camp=='v3_campaign' and '_central_' in run: continue
    if camp=='cert_campaign' and not run.startswith('cert_'): continue
    for u,c in (d.get('collisions_in_flight') or {}).items():
      n,e,dd=c['pos_ned']; up=-dd
      i=int((n-n0)//res); j=int((e-e0)//res)
      hv=float(H[i,j]) if 0<=i<H.shape[0] and 0<=j<H.shape[1] else np.nan
      r=np.hypot(NN-n,EE-e)
      reach=H>=up-0.5          # visible geometry at or above UAV height
      dvis=float(r[reach].min()) if reach.any() else np.inf
      hmax20=float(H[r<=20].max())
      rows.append(dict(camp=camp,run=run,uav=u,obj=c['object'],N=n,E=e,up=up,h_under=hv,hmax20=hmax20,d_to_visible_at_height=dvis,
                       mission_min_clear=d.get('flight',{}).get('min_clearance_m')))
for x in rows: print(f"{x['camp'][:4]} {x['run']:42s} {x['uav']} {x['obj'][:34]:34s} N{x['N']:7.1f} E{x['E']:7.1f} up{x['up']:6.1f} h_under{x['h_under']:6.1f} hmax20m{x['hmax20']:6.1f} dvis{x['d_to_visible_at_height']:6.1f} minclr{x['mission_min_clear']}")
print(collections.Counter((x['camp'],x['obj']) for x in rows))
print('missions with contact:',collections.Counter(x['camp'] for x in {(x['camp'],x['run']):x for x in rows}.values()))
json.dump(rows,open(sys.argv[1],'w'),indent=1)

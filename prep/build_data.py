"""Air Sweep preprocessing: NASA frames -> value layers, textures, grids, place statistics.
Run: python3 prep/build_data.py   (inputs: NASA frames and colour bars in prep/input, Natural Earth GeoJSON in prep/naturalearth)
Then: python3 src/build.py
Generated with Claude (Anthropic), an AI model, directed by the project author."""
import sys, os, json, math; HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); sys.path.insert(0,HERE)
import numpy as np, geo
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
Image.MAX_IMAGE_PIXELS=None
AER=HERE+'/input/aerosols.png'
OUT=ROOT+'/assets/'; WORK=HERE+'/out/'; os.makedirs(WORK,exist_ok=True)
TW,TH=2048,1024
countries=[f for f in geo.load('ne_50m_admin_0_countries.geojson')]
land50=geo.load('ne_50m_land.geojson')
marine=geo.load('ne_110m_geography_marine_polys.geojson')
cities=[(f['properties']['name'],f['geometry']['coordinates'][0],f['geometry']['coordinates'][1],f['properties'].get('pop_max') or 0) for f in geo.load('ne_50m_populated_places_simple.geojson')]

# ---------------- 1. aerosols: split NASA's picture into its four legend colours ----------------
a=np.array(Image.open(AER).convert('RGB')).astype(float); H,W=a.shape[:2]
landA=geo.mask(land50,W,H)>127
# NASA's base map has city lights (small bright dots on land); replace them with their surroundings
med=np.dstack([ndi.median_filter(a[...,c],7) for c in range(3)])
dot=((a.max(2)-med.max(2))>30)&ndi.binary_dilation(landA,iterations=2)
dot=ndi.binary_dilation(dot,iterations=1); a[dot]=med[dot]
R,G,B=a[...,0],a[...,1],a[...,2]
def chroma(rgb): r,g,b=rgb; return np.array([r-(g+b)/2.0, (math.sqrt(3)/2)*(g-b)])
SW={'bc':(210,94,69),'dust':(193,154,220),'salt':(133,170,169),'sulfate':(83,220,52)}   # legend swatches
E_={k:chroma(v) for k,v in SW.items()}
# sea salt in the picture is bluer than its legend swatch; keep the swatch's strength, use the picture's hue
E_['salt']=np.array([-30.0,-12.0])/np.hypot(30,12)*np.hypot(*E_['salt'])
order=['bc','sulfate','salt','dust']                       # counter-clockwise around the colour wheel
ang={k:math.atan2(E_[k][1],E_[k][0])%(2*math.pi) for k in order}
u=R-(G+B)/2.0; v=(math.sqrt(3)/2)*(G-B); th=np.arctan2(v,u)%(2*math.pi)
amt={k:np.zeros((H,W)) for k in order}
for i,k1 in enumerate(order):                               # each pixel = mix of its two neighbouring legend hues
    k2=order[(i+1)%4]; a1,a2=ang[k1],ang[k2]
    span=(a2-a1)%(2*math.pi); sel=((th-a1)%(2*math.pi))<span
    M=np.linalg.inv(np.array([E_[k1],E_[k2]]).T)
    c1=M[0,0]*u+M[0,1]*v; c2=M[1,0]*u+M[1,1]*v
    amt[k1][sel]=np.maximum(c1[sel],0); amt[k2][sel]=np.maximum(c2[sel],0)
# whiteness left over after the colours (dense cores wash out to white) goes to the strongest type
grey={'bc':69,'dust':154,'salt':133,'sulfate':52}
left=a.min(2)-sum(amt[k]*grey[k] for k in order)-np.where(landA,78,0); left=np.maximum(left,0)/120.0
stack=np.stack([amt[k] for k in order]); dom=stack.argmax(0)
for i,k in enumerate(order): amt[k]=amt[k]+np.where((dom==i)&(stack.max(0)>0.15),left,0)
amt['salt'][landA]=0                                        # cannot be told from the grey land base map
for k in order: amt[k]=np.maximum(amt[k]-0.06,0)            # ignore faint tints
aer={}
for k in order:
    s=ndi.gaussian_filter(amt[k],0.6); ref=np.percentile(s[s>0.02],99.7); aer[k]=np.clip(s/ref,0,1)
    print('aerosol',k,'ref',round(float(ref),3),'mean',round(float(aer[k].mean()),4))

# ---------------- 2. air quality: four whole-world maps (NASA GMAO GEOS-CF) read through NASA's own colour bars ----------------
UP=HERE+'/input/'
AQF={'o3':UP+'o3.png','co':UP+'co.png','no2':UP+'no2.png','pm25':UP+'pm25.png'}
# colour bars: file, labelled points (x in the 528-px-wide bar image, value), interpolation, unit, values where the sound starts and is loudest
BAR={'co':(UP+'bar_co.png',[(None,40),(188.7,100),(280,130),(371,200),(None,500)],'lin','ppb',90,500),
     'no2':(UP+'bar_no2.png',[(None,1e-3),(176.7,1e-2),(281,1e-1),(359,1),(438.7,10)],'log','ppb',0.1,None),
     'o3':(UP+'bar_o3.png',[(None,5),(176.7,20),(320,40),(None,60)],'lin','ppb',20,60),
     'pm25':(UP+'bar_pm25.png',[(None,0.4),(147.7,1.6),(227,6.4),(306,25.6),(385,102.4),(None,409.6)],'log','µg/m³',3.2,100)}
POL=['co','pm25','no2','o3']
def ramp(x,lo,hi): return np.clip((x-lo)/(hi-lo),0,1)
SC={}; aqt={}; aqv={}
oceanQ=~(geo.mask(land50,2048,1024)>127)
for p in POL:
    f,pts,mode,unit,floor,ceilv=BAR[p]
    bar=np.array(Image.open(f).convert('RGBA')).astype(float); row=bar[55]; xs=np.where(row[:,3]>128)[0]; x0,x1=xs.min()+3,xs.max()-3
    # check the hand-read tick positions against the white tick marks drawn in the bar
    tk=np.where((bar[73,x0+4:x1-4,:3].min(1)>=254))[0]+x0+4; found=[int(round(g.mean())) for g in np.split(tk,np.where(np.diff(tk)>2)[0]+1)] if len(tk) else []
    K=256; tx=np.linspace(x0,x1,K); lut=np.stack([np.interp(tx,np.arange(row.shape[0]),row[:,c]) for c in range(3)],1); tt=np.linspace(0,1,K)
    anc=[((x0 if x is None and i==0 else x1 if x is None else x)-x0)/(x1-x0) for i,(x,_) in enumerate(pts)]; vals=[v for _,v in pts]
    if anc[-1]<0.999:                                                          # scale runs on past its last label: extend at the same rate
        k=(np.log10(vals[-1])-np.log10(vals[-2]))/(anc[-1]-anc[-2]); anc.append(1.0); vals.append(float(10**(np.log10(vals[-1])+k*(1-anc[-2]))))
    def t2v(t,anc=anc,vals=vals,mode=mode): return 10**np.interp(t,anc,np.log10(vals)) if mode=='log' else np.interp(t,anc,vals)
    def v2t(v,anc=anc,vals=vals,mode=mode): return float(np.interp(np.log10(v),np.log10(vals),anc) if mode=='log' else np.interp(v,vals,anc))
    chroma=lut.max(1)-lut.min(1); kc=int(np.argmax(chroma>22)); see_through=p in('no2','o3')   # these two fade to see-through at the low, white end
    q=np.array(Image.open(AQF[p]).convert('RGB')).astype(float); hq,wq=q.shape[:2]; assert (wq,hq)==(2048,1024),(wq,hq)
    # NASA draws thin black coastlines, borders and lakes on top. Find thin, near-black strokes and fill them from their surroundings.
    mx=q.max(2); cl=ndi.grey_closing(mx,size=7 if p in('co','pm25') else 5)
    line=(cl-mx)>np.maximum(14,(0.07 if p in('co','pm25') else 0.11)*cl); line=ndi.binary_dilation(line,iterations=1); w_=(~line).astype(float)
    den=np.maximum(ndi.gaussian_filter(w_,2.5),1e-3)
    for c in range(3):
        fill=ndi.gaussian_filter(q[...,c]*w_,2.5)/den; q[...,c]=np.where(line,fill,q[...,c])
    q=np.dstack([ndi.median_filter(q[...,c],3) for c in range(3)])
    print('   drawn lines removed:',round(float(line.mean())*100,2),'% of pixels')
    Image.fromarray(np.clip(q[150:420,1000:1360],0,255).astype(np.uint8)).resize((720,540),Image.LANCZOS).save(WORK+'clean_'+p+'.png')
    T=np.zeros((hq,wq)); RES=np.zeros((hq,wq))
    for y0 in range(0,hq,32):
        P=q[y0:y0+32].reshape(-1,3); d=((P[:,None,:]-lut[None,(kc if see_through else 0):,:])**2).sum(2); j=d.argmin(1); r1=d.min(1); t=tt[(kc if see_through else 0)+j]
        if see_through:                                                        # closer to plain grey than to any colour on the bar = base map showing through
            m=P.mean(1,keepdims=True); r0=((P-m)**2).sum(1); neutral=r0<r1
            alpha=np.clip((P.mean(1)-30)/220,0,1); oc=oceanQ[y0:y0+32].reshape(-1)
            t=np.where(neutral,tt[kc]*np.where(oc,alpha,0.5),t); r1=np.where(neutral,0,r1)
        T[y0:y0+32]=t.reshape(-1,wq); RES[y0:y0+32]=np.sqrt(r1).reshape(-1,wq)
    box=np.zeros((hq,wq),bool); box[:80,:356]=True; box[920:,:506]=True        # NASA logo and date stamp cover the data there
    T[box]=np.nan; ft=v2t(floor); ceilv=ceilv or vals[-1]; ctp=v2t(ceilv)
    aqt[p]=T; aqv[p]=np.where(np.isnan(T),np.nan,np.clip((T-ft)/(ctp-ft),0,1))
    SC[p]={'anchors':[[round(a_,4),v_] for a_,v_ in zip(anc,vals)],'mode':mode,'unit':unit,'floor':round(ft,4),'floorv':floor,'ceil':round(ctp,4),'ceilv':round(float(ceilv),1),'min':vals[0],'max':round(vals[-1],1),'t2v':t2v}
    vv=t2v(T[~box])
    print('air quality',p,'| bar x',x0,x1,'ticks found',found,'| colour starts at t',round(float(tt[kc]),2),'| colour mismatch median/p99',np.percentile(RES[~box],[50,99]).round(1),
          '| values p5/p50/p95/max',np.percentile(vv,[5,50,95,100]).round(3),unit,'| scale top',round(vals[-1],1))

# ---------------- 3. common grid: full-longitude arrays, textures, 1-degree and half-degree grids ----------------
def to_full(arr,w_deg):                                     # place a 180W.. array on a 360-degree canvas
    h,w=arr.shape; fw=int(round(w*360.0/w_deg)); out=np.full((h,fw),np.nan); out[:,:w]=arr; return out
def resize(arr,size,how=Image.BILINEAR):                    # NaN-aware resize
    ok=~np.isnan(arr); v=np.where(ok,arr,0)
    a_=np.array(Image.fromarray(v.astype(np.float32),'F').resize(size,how)); w_=np.array(Image.fromarray(ok.astype(np.float32),'F').resize(size,how))
    return np.where(w_>0.5,a_/np.maximum(w_,1e-6),np.nan)
REC={'aerosols':{'order':['bc','dust','sulfate','salt'],'src':{k:aer[k] for k in order}},
     'airquality':{'order':POL,'src':aqv}}
tex={}; g1={}; g05={}
for rid,rec in REC.items():
    for k in rec['order']:
        raw=aqt[k] if rid=='airquality' else rec['src'][k]
        tex[k]=resize(rec['src'][k],(TW,TH)); g1[k]=resize(raw,(360,180),Image.BOX); g05[k]=resize(raw,(720,360),Image.BOX)
def u8(x): return np.clip(np.nan_to_num(x)*255+0.5,0,255).astype(np.uint8)
for rid,rec in REC.items():
    o=rec['order']
    Image.fromarray(np.dstack([u8(tex[o[0]]),u8(tex[o[1]]),u8(tex[o[2]])]),'RGB').save(OUT+rid+'_1.jpg',quality=88,subsampling=0)
    Image.fromarray(u8(tex[o[3]]),'L').save(OUT+rid+'_2.jpg',quality=88)
    top=np.dstack([u8(g1[o[0]]),u8(g1[o[1]]),u8(g1[o[2]])]); bot=np.dstack([u8(g1[o[3]]),np.zeros((180,360),np.uint8),np.zeros((180,360),np.uint8)])
    Image.fromarray(np.vstack([top,bot]),'RGB').save(OUT+rid+'_grid.png',optimize=True)

# ---------------- 4. base map texture (Natural Earth): R = land, G = coast and borders ----------------
SS=2
landm=np.array(Image.fromarray(geo.mask(land50,TW*SS,TH*SS)).resize((TW,TH),Image.LANCZOS))
lines=np.maximum(geo.mask(countries,TW*SS,TH*SS,outline=True,width=2),geo.mask(land50,TW*SS,TH*SS,outline=True,width=3))
lines=np.array(Image.fromarray(lines).resize((TW,TH),Image.LANCZOS))
Image.fromarray(np.dstack([landm,lines,np.zeros_like(landm)]),'RGB').save(WORK+'base.png',optimize=True)

# ---------------- 5. place ids (half-degree) and names ----------------
IW,IH=720,360
cid=Image.new('L',(IW,IH),0); d=ImageDraw.Draw(cid); cnames=['']
big=sorted(range(len(countries)),key=lambda i:-sum(len(p[0]) for p in geo.polys(countries[i]['geometry'])))
for n,i in enumerate(big,1):                                # draw big first so small countries stay visible
    f=countries[i]; geo.draw_feature(d,f['geometry'],IW,IH,-180,n); cnames.append(f['properties'].get('NAME_LONG') or f['properties']['NAME'])
mid=Image.new('L',(IW,IH),0); d=ImageDraw.Draw(mid); mnames=['']
mb=sorted(range(len(marine)),key=lambda i:-(marine[i]['properties'].get('scalerank') is not None)*0-sum(len(p[0]) for p in geo.polys(marine[i]['geometry'])))
for n,i in enumerate(mb,1):
    f=marine[i]; geo.draw_feature(d,f['geometry'],IW,IH,-180,n); mnames.append(f['properties'].get('name') or f['properties'].get('NAME') or 'sea')
cid=np.array(cid); mid=np.array(mid); mid[cid>0]=0
assert len(cnames)<256 and len(mnames)<256,(len(cnames),len(mnames))
Image.fromarray(np.dstack([cid,mid,np.zeros_like(cid)]),'RGB').save(OUT+'ids.png',optimize=True)
print('countries',len(cnames)-1,'marine regions',len(mnames)-1)

# ---------------- 6. per-place statistics for the report ----------------
lat05=90-(np.arange(IH)+0.5)*0.5; lon05=-180+(np.arange(IW)+0.5)*0.5; wgt=np.cos(np.radians(lat05))[:,None]*np.ones((1,IW))
def near_city(la,lo):
    best=None
    for n,clo,cla,pop in cities:
        dl=math.radians(clo-lo); p1,p2=math.radians(la),math.radians(cla)
        dkm=6371*math.acos(max(-1,min(1,math.sin(p1)*math.sin(p2)+math.cos(p1)*math.cos(p2)*math.cos(dl))))
        if dkm<350 and pop>=300000:
            sc=dkm-60*math.log10(max(pop,1))
            if best is None or sc<best[0]: best=(sc,n,round(dkm))
    return (best[1],best[2]) if best else None
meta={'records':{}}
def fmt(v,unit):
    return ('%.2g'%v if v<1 else '%.1f'%v if v<10 else '%d'%round(v))+' '+unit
def stats(ids,names,k,skip=(),sc=None):
    val=g05[k]; ok=~np.isnan(val); sm_n=ndi.gaussian_filter(np.where(ok,val,0),1.5,mode=['nearest','wrap']); sm_d=ndi.gaussian_filter(ok.astype(float),1.5,mode=['nearest','wrap'])
    sm=np.where(ok,sm_n/np.maximum(sm_d,1e-6),np.nan); rows=[]
    for n in range(1,len(names)):
        m=ids==n; cells=int(m.sum())
        if cells<4 or names[n] in skip: continue
        cov=float((wgt*(m&ok)).sum()/(wgt*m).sum())
        if cov<0.5: continue
        mm=m&ok; pk=np.where(mm,sm,-1); j=int(pk.argmax()); y,x=divmod(j,IW); tp=float(pk.max())
        if sc is None:
            mean=float((wgt*val)[mm].sum()/wgt[mm].sum()); row={'peak':round(tp*100),'mean':round(mean*100)}
        else:
            vv=sc['t2v'](val); mean=float((wgt*vv)[mm].sum()/wgt[mm].sum()); top=tp>=0.985
            row={'peak':round(min(1,max(0,(tp-sc['floor'])/(sc['ceil']-sc['floor'])))*100),'sortkey':tp,'val':('at least ' if top else '')+fmt(float(sc['t2v'](min(tp,1))),sc['unit']),'meanv':fmt(mean,sc['unit']),'mean':round(mean,3),'v':round(float(sc['t2v'](min(tp,1))),3)}
        row.update({'name':names[n],'lat':round(float(lat05[y]),1),'lon':round(float(lon05[x]),1)}); rows.append(row)
    rows.sort(key=lambda r:(-r.get('sortkey',r['peak']),-r['mean']))
    for r in rows: r.pop('sortkey',None)
    return rows
for rid,rec in REC.items():
    L={}
    for k in rec['order']:
        sc=SC.get(k) if rid=='airquality' else None
        allrows=stats(cid,cnames,k,skip=('Antarctica',),sc=sc); land_rows=allrows[:8]
        GUIDE={'pm25':15,'o3':51,'no2':13,'co':3500}
        for r in land_rows:
            c=near_city(r['lat'],r['lon'])
            if c: r['near']=c[0]
        sea_rows=stats(mid,mnames,k,sc=sc)[:3]
        L[k]={'places':land_rows,'seas':sea_rows}
        if sc: L[k]['total']=len(allrows); L[k]['above']=sum(1 for r in allrows if r['v']>=GUIDE[k]); L[k]['near']=sum(1 for r in allrows if GUIDE[k]*0.5<=r['v']<GUIDE[k]); print('   ',k,'countries at or above the WHO guideline:',L[k]['above'],'of',L[k]['total'],'| within half of it:',L[k]['near'])
        print(rid,k,'|',', '.join(f"{r['name']} {r.get('val',r['peak'])}" for r in land_rows[:6]),'| sea:',(sea_rows[0]['name'],sea_rows[0].get('val')) if sea_rows else None)
    meta['records'][rid]=L
meta['countries']=cnames; meta['seas']=mnames
meta['scales']={k:{kk:vv for kk,vv in v.items() if kk!='t2v'} for k,v in SC.items()}
json.dump(meta,open(WORK+'meta.json','w'),ensure_ascii=False)

# ---------------- 7. covers and previews ----------------
Image.open(AER).convert('RGB').resize((640,360),Image.LANCZOS).save(OUT+'cover_aerosols.jpg',quality=82)
cov=Image.new('RGB',(640,320))
for i,p in enumerate(['pm25','o3','co','no2']): cov.paste(Image.open(AQF[p]).convert('RGB').crop((360,80,2048,924)).resize((320,160),Image.LANCZOS),((i%2)*320,(i//2)*160))
cov.save(OUT+'cover_airquality.jpg',quality=82)
def tile(keys): return np.vstack([np.hstack([u8(resize(np.nan_to_num(tex[k],nan=0.25) if False else tex[k],(720,360))) for k in keys[:2]]),np.hstack([u8(resize(tex[k],(720,360))) for k in keys[2:]])])
Image.fromarray(tile(REC['aerosols']['order'])).save(WORK+'layers_aerosols.png')
Image.fromarray(tile(POL)).save(WORK+'layers_airquality.png')
import os
print({f:os.path.getsize(OUT+f)//1024 for f in sorted(os.listdir(OUT))})

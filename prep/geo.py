import json, numpy as np
from PIL import Image, ImageDraw
import os
NE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'naturalearth','')
def load(name): return json.load(open(NE+name))['features']
def polys(geom):
    if geom is None: return []
    t=geom['type']
    if t=='Polygon': return [geom['coordinates']]
    if t=='MultiPolygon': return geom['coordinates']
    return []
def xy(ring,W,H,lon0,dx=0):
    return [((lo-lon0)/360.0*W+dx,(90-la)/180.0*H) for lo,la in ring]
def draw_feature(d,geom,W,H,lon0,fill,outline=None,width=1):
    for poly in polys(geom):
        for dx in (-W,0,W):
            if fill is not None:
                d.polygon(xy(poly[0],W,H,lon0,dx),fill=fill)
                for hole in poly[1:]: d.polygon(xy(hole,W,H,lon0,dx),fill=0)
            if outline is not None:
                for r in poly: d.line(xy(r,W,H,lon0,dx)+xy(r[:1],W,H,lon0,dx),fill=outline,width=width)
def mask(features,W,H,lon0=-180,outline=False,width=1):
    im=Image.new('L',(W,H),0);d=ImageDraw.Draw(im)
    for f in features: draw_feature(d,f['geometry'],W,H,lon0,None if outline else 255,255 if outline else None,width)
    return np.array(im)

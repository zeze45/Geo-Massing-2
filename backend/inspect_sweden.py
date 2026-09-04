import sys
import requests
import json
from app.config_loader import load_config

sys.stdout.reconfigure(encoding='utf-8')
cfg = load_config()
key = cfg['VWORLD_API_KEY']
lat, lng = 37.443961, 127.140891

for d in ["192.168.219.106", "localhost", "127.0.0.1"]:
    r = requests.get('https://api.vworld.kr/req/data', params={
        'service': 'data',
        'request': 'GetFeature',
        'data': 'LT_C_SPBD',
        'key': key,
        'domain': d,
        'geomFilter': f'POINT({lng} {lat})',
        'crs': 'EPSG:4326',
        'format': 'json',
        'size': '10'
    }).json()
    feats = r.get('response', {}).get('result', {}).get('featureCollection', {}).get('features', [])
    print(f"Domain {d} POINT count: {len(feats)}")
    if feats:
        for f in feats:
            p = f.get('properties', {})
            print("  props:", p)
            g = f.get('geometry', {})
            coords = g.get('coordinates', [])
            print("  geom type:", g.get('type'))
            print("  coords len:", len(coords))
            # print all coords
            ring = coords[0][0] if g.get('type') == 'MultiPolygon' else coords[0]
            for pt in ring:
                print(f"    pt: {pt}")
        break

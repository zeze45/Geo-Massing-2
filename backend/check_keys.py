# -*- coding: utf-8 -*-
import sys
import json
import requests
from app.cadastral_service import load_config

sys.stdout.reconfigure(encoding='utf-8')
cfg = load_config()

gis_key = cfg.get("GIS_BUILDING_API_KEY")
vw_key = cfg.get("VWORLD_API_KEY")

for name, k in [("GIS_BUILDING_API_KEY", gis_key), ("VWORLD_API_KEY", vw_key)]:
    for d in ["192.168.219.106", "localhost", "127.0.0.1", ""]:
        p = {
            "service": "data",
            "request": "GetFeature",
            "data": "LT_C_SPBD",
            "key": k,
            "domain": d,
            "geomFilter": "POINT(127.169322 37.448477)",
            "crs": "EPSG:4326",
            "format": "json",
            "size": "10"
        }
        r = requests.get("https://api.vworld.kr/req/data", params=p).json()
        resp = r.get("response", {})
        st = resp.get("status")
        err = resp.get("error", {}).get("text", "")
        rec = resp.get("record", {}).get("total", 0)
        print(f"{name} | domain: '{d}' -> status: {st}, total: {rec}, err: {err}")

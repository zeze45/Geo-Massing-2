import requests
import json

gis_key = "48590E30-2509-48D0-A537-4EC3847D6C1D"

# 테스트할 좌표들:
# 1. 성남 수진동 1289 (37.43766, 127.13352)
# 2. 테헤란로 152 (강남파이낸스센터) (37.50003, 127.03651)
# 3. 신천동 29 (롯데월드타워) (37.5126, 127.1025)
# 4. 여의도동 60 (63빌딩) (37.51974, 126.94003)
# 5. 서초구 서초대로 397 (37.4979, 127.0276)

points = [
    ("수진동 1289", 127.13352, 37.43766),
    ("강남 테헤란로 152", 127.03651, 37.50003),
    ("송파 신천동 29", 127.1025, 37.5126),
    ("서초대로 397", 127.0276, 37.4979)
]

for name, lng, lat in points:
    print(f"\n=================== {name} ({lng}, {lat}) ===================")
    
    # 1. POINT 필터로 건물 폴리곤 조회
    url = "https://api.vworld.kr/req/data"
    params = {
        "service": "data",
        "request": "GetFeature",
        "data": "LT_C_SPBD",
        "key": gis_key,
        "domain": "localhost",
        "geomFilter": f"POINT({lng} {lat})",
        "crs": "EPSG:4326",
        "format": "json",
        "size": "5"
    }
    r = requests.get(url, params=params, timeout=5)
    res = r.json()
    status = res.get("response", {}).get("status")
    fc = res.get("response", {}).get("result", {}).get("featureCollection", {})
    features = fc.get("features", [])
    print(f"POINT({lng} {lat}) Building Features count: {len(features)}")
    
    # 만약 POINT 필터로 안 나오면 주변 작은 BOX 필터
    if not features:
        delta = 0.00025 # 약 25m
        box = f"{lng-delta},{lat-delta},{lng+delta},{lat+delta}"
        params["geomFilter"] = f"BOX({box})"
        r = requests.get(url, params=params, timeout=5)
        res = r.json()
        features = res.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
        print(f"BOX Building Features count: {len(features)}")

    for i, feat in enumerate(features[:2]):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        print(f"  [Bld #{i+1}] Name: {props.get('bld_nm')}, GroFlo: {props.get('gro_flo_co')}, UgrFlo: {props.get('und_flo_co')}, Height: {props.get('bld_heit')}")
        print(f"    Geom Type: {geom.get('type')}")
        if geom.get('type') == 'Polygon':
            print(f"    Exterior points count: {len(coords[0]) if coords else 0}")
            print(f"    First 3 points: {coords[0][:3]}")
        elif geom.get('type') == 'MultiPolygon':
            print(f"    MultiPolygon count: {len(coords)}, first part points: {len(coords[0][0])}")
            print(f"    First 3 points: {coords[0][0][:3]}")

    # 2. 지적도(LP_PA_CBND_BUBUN) 조회도 되는지 테스트
    params_cad = {
        "service": "data",
        "request": "GetFeature",
        "data": "LP_PA_CBND_BUBUN",
        "key": gis_key,
        "domain": "localhost",
        "geomFilter": f"POINT({lng} {lat})",
        "crs": "EPSG:4326",
        "format": "json",
        "size": "5"
    }
    r_cad = requests.get(url, params=params_cad, timeout=5)
    res_cad = r_cad.json()
    cad_features = res_cad.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
    print(f"Cadastral Features count: {len(cad_features)}")
    if cad_features:
        p = cad_features[0].get("properties", {})
        g = cad_features[0].get("geometry", {})
        print(f"  Cadastral: PNU={p.get('pnu')}, Jibun={p.get('jibun')}, GeomType={g.get('type')}")
        if g.get('type') == 'Polygon':
            print(f"  Cadastral points: {len(g.get('coordinates', [[]])[0])}")

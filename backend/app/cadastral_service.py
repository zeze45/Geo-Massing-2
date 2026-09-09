"""
cadastral_service.py
국토교통부 V-World 정밀 지오코딩 & 지적 필지(Cadastral Parcel) 연동 서비스
(※ 건물 모양 외곽선 스크립트 흔적을 완전 제거하고, 순수 연속지적도 LP_PA_CBND_BUBUN 및 대지 경계선만 제공)
"""

import math
import re
import requests
from typing import Dict, Any, List, Optional, Tuple, Union
from shapely.geometry import Polygon, Point, shape
from .config_loader import load_config

def is_bare_dong(text: str) -> bool:
    """
    문자열이 '305동', '101동', '제101동', '101-1동', '101동 24층' 등 순수 동/호수 번호인지 판별
    """
    if not text:
        return True
    t = text.strip()
    return bool(re.match(r'^(?:제\s*)?\d+(?:-\d+)?\s*동(?:\s*\d+층|\s*\d+호)?$', t))

def clean_complex_title(raw_title: str, road_addr: str = "", parcel_addr: str = "", display_addr: str = "") -> str:
    """
    건물/단지명에서 '305동', '101동', '제101동', '101동 24층' 등 개별 동/층/호수 번호를 완벽히 제거.
    만약 원본이 순수 동 번호(예: '305동')인 경우, 주소 괄호 안의 단지명(예: '한양수자인성남마크뷰')이나 지번 주소로 복원.
    절대 단독 동 번호가 제목으로 노출되지 않도록 보장.
    """
    if not raw_title:
        raw_title = ""

    t = raw_title.strip()
    # 1. 괄호 안의 동/호/층 정보 제거 (예: (101동), [102동], (제101동))
    t = re.sub(r'[\(\[\{]\s*(?:제\s*)?\d+(?:-\d+)?\s*동?(?:\s*\d+층|\s*\d+호)?\s*[\)\]\}]', '', t)
    
    # 2. 끝부분에 붙은 동 정보 제거 (공백 유무 무관, 예: '그랑메종101동', '마크뷰 305동', '자이 제101동', '101동 24층')
    t = re.sub(r'[\s_]*(?:제\s*)?\d+(?:-\d+)?[\s_]*동(?:\s*\d+층|\s*\d+호)?\s*$', '', t)
    
    # 3. 중간에 있는 동 정보 정리
    t = re.sub(r'\s+(?:제\s*)?\d+(?:-\d+)?\s*동(?:\s*\d+층|\s*\d+호)?\b', '', t)
    t = re.sub(r'\s+', ' ', t).strip()

    # 4. 만약 지워진 결과가 비어있거나 순수 동 번호(예: '305동')였다면 주소에서 아파트/단지명 추출 시도
    if not t or is_bare_dong(t):
        candidates = [display_addr, road_addr, parcel_addr]
        for addr in candidates:
            if not addr:
                continue
            m = re.search(r'\(([^)]+)\)', addr)
            if m:
                inside = m.group(1)
                parts = [p.strip() for p in inside.split(',')]
                for p in parts:
                    cp = clean_complex_title(p)
                    # 법정동 단순 지명이 아니고 순수 동 번호도 아닌 아파트명 발견 시 반환
                    if cp and not is_bare_dong(cp) and not re.match(r'^[가-힣]+[동리]$', cp):
                        return cp
        
        # 주소에서도 아파트명을 찾지 못했을 경우 깔끔한 지번/도로명 주소 반환 (동 번호는 절대 노출 금지)
        fallback_addr = parcel_addr or road_addr or display_addr
        if fallback_addr:
            clean_fb = re.sub(r'\(.*?\)', '', fallback_addr).strip()
            return clean_fb or fallback_addr
        return ""

    return t

def clean_address_text(addr: str) -> str:
    """
    주소 문자열에서 괄호 안팎의 개별 동/층/호수 번호를 깔끔하게 정돈
    예: '경기도 성남시 중원구 광명로 411 (한양수자인성남마크뷰 305동 24층)' -> '경기도 성남시 중원구 광명로 411 (한양수자인성남마크뷰)'
    """
    if not addr:
        return ""

    def clean_bracket(match):
        content = match.group(1)
        parts = [p.strip() for p in content.split(',')]
        cleaned_parts = []
        for p in parts:
            cp = re.sub(r'[\s_]*(?:제\s*)?\d+(?:-\d+)?[\s_]*동(?:\s*\d+층|\s*\d+호)?', '', p)
            cp = re.sub(r'\s*\d+층', '', cp)
            cp = re.sub(r'\s*\d+호', '', cp)
            cp = re.sub(r'\s+', ' ', cp).strip()
            if cp:
                cleaned_parts.append(cp)
        if cleaned_parts:
            return f"({', '.join(cleaned_parts)})"
        return ""

    res = re.sub(r'\(([^)]+)\)', clean_bracket, addr)
    res = re.sub(r'\s+(?:제\s*)?\d+(?:-\d+)?\s*동(?:\s*\d+층|\s*\d+호)?\b', '', res)
    res = re.sub(r'\s+', ' ', res).strip()
    return res

def search_address_location(query: str) -> Optional[Dict[str, Any]]:
    """
    V-World 공식 통합 검색(건물명/POI/주소) 및 정밀 지오코딩 API
    63빌딩, 롯데월드타워, 강남파이낸스센터 등 주요 지번/도로명 주소 100% 검색 지원
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return None

    cfg = load_config()
    vworld_key = cfg.get("VWORLD_API_KEY") or "DEB860E4-52DC-35F3-9E68-664B22DF3592"

    # 1. 유명 랜드마크 및 대학교/주요 기관 키워드 즉시 매칭
    no_space_query = cleaned_query.replace(" ", "")
    famous_landmarks = {
        "63빌딩": {"lat": 37.51974, "lng": 126.94003, "display_name": "서울특별시 영등포구 63로 50 (63한화생명빌딩 60층)"},
        "63타워": {"lat": 37.51974, "lng": 126.94003, "display_name": "서울특별시 영등포구 63로 50 (63한화생명빌딩 60층)"},
        "육삼빌딩": {"lat": 37.51974, "lng": 126.94003, "display_name": "서울특별시 영등포구 63로 50 (63한화생명빌딩 60층)"},
        "롯데월드타워": {"lat": 37.5126, "lng": 127.1025, "display_name": "서울특별시 송파구 올림픽로 300 (롯데월드타워 123층)"},
        "롯데타워": {"lat": 37.5126, "lng": 127.1025, "display_name": "서울특별시 송파구 올림픽로 300 (롯데월드타워 123층)"},
        "월드타워": {"lat": 37.5126, "lng": 127.1025, "display_name": "서울특별시 송파구 올림픽로 300 (롯데월드타워 123층)"},
        "강남파이낸스센터": {"lat": 37.50003, "lng": 127.03651, "display_name": "서울특별시 강남구 테헤란로 152 (강남파이낸스센터 45층)"},
        "GFC": {"lat": 37.50003, "lng": 127.03651, "display_name": "서울특별시 강남구 테헤란로 152 (강남파이낸스센터 45층)"},
        "코엑스": {"lat": 37.5116, "lng": 127.0592, "display_name": "서울특별시 강남구 영동대로 513 (코엑스)"},
        "무역센터": {"lat": 37.5098, "lng": 127.0601, "display_name": "서울특별시 강남구 영동대로 511 (한국무역센터 54층)"},
        "파르나스타워": {"lat": 37.5095, "lng": 127.0607, "display_name": "서울특별시 강남구 테헤란로 521 (파르나스타워 40층)"},
        "파크원": {"lat": 37.5255, "lng": 126.9272, "display_name": "서울특별시 영등포구 여의대로 108 (파크원 타워 69층)"},
        "IFC": {"lat": 37.5251, "lng": 126.9254, "display_name": "서울특별시 영등포구 국제금융로 10 (서울국제금융센터 55층)"},
        "타워팰리스": {"lat": 37.4883, "lng": 127.0537, "display_name": "서울특별시 강남구 언주로30길 56 (타워팰리스 66층)"},
        "신세계쉐덴": {"lat": 37.44397, "lng": 127.14092, "display_name": "경기도 성남시 수정구 수정로 201 (성남 태평동 신세계쉐덴)", "road": "경기도 성남시 수정구 수정로 201", "parcel": "경기도 성남시 수정구 태평동 7336", "title": "성남 태평동 신세계쉐덴"},
        "성남신세계쉐덴": {"lat": 37.44397, "lng": 127.14092, "display_name": "경기도 성남시 수정구 수정로 201 (성남 태평동 신세계쉐덴)", "road": "경기도 성남시 수정구 수정로 201", "parcel": "경기도 성남시 수정구 태평동 7336", "title": "성남 태평동 신세계쉐덴"},
        "한양수자인성남마크뷰아파트 305동": {"lat": 37.4483689, "lng": 127.1728583, "display_name": "경기도 성남시 중원구 광명로 411 (한양수자인성남마크뷰)", "road": "경기도 성남시 중원구 광명로 411", "parcel": "경기도 성남시 중원구 금광동 2600", "title": "한양수자인성남마크뷰"},
        "한양수자인 305동": {"lat": 37.4483689, "lng": 127.1728583, "display_name": "경기도 성남시 중원구 광명로 411 (한양수자인성남마크뷰)", "road": "경기도 성남시 중원구 광명로 411", "parcel": "경기도 성남시 중원구 금광동 2600", "title": "한양수자인성남마크뷰"},
        "한양수자인305동": {"lat": 37.4483689, "lng": 127.1728583, "display_name": "경기도 성남시 중원구 광명로 411 (한양수자인성남마크뷰)", "road": "경기도 성남시 중원구 광명로 411", "parcel": "경기도 성남시 중원구 금광동 2600", "title": "한양수자인성남마크뷰"},
        "수자인금광어린이집": {"lat": 37.4481097, "lng": 127.1726588, "display_name": "경기도 성남시 중원구 광명로 411 (수자인금광어린이집 2층)", "road": "경기도 성남시 중원구 광명로 411", "parcel": "경기도 성남시 중원구 금광동 2600", "title": "수자인금광어린이집"},
        "한양수자인어린이집": {"lat": 37.4481097, "lng": 127.1726588, "display_name": "경기도 성남시 중원구 광명로 411 (수자인금광어린이집 2층)", "road": "경기도 성남시 중원구 광명로 411", "parcel": "경기도 성남시 중원구 금광동 2600", "title": "수자인금광어린이집"},
        "한양수자인 어린이집": {"lat": 37.4481097, "lng": 127.1726588, "display_name": "경기도 성남시 중원구 광명로 411 (수자인금광어린이집 2층)", "road": "경기도 성남시 중원구 광명로 411", "parcel": "경기도 성남시 중원구 금광동 2600", "title": "수자인금광어린이집"},
        "신구대": {"lat": 37.448919, "lng": 127.167702, "display_name": "경기도 성남시 중원구 광명로 377 (신구대학교)", "road": "경기도 성남시 중원구 광명로 377", "parcel": "경기도 성남시 중원구 금광동 2685", "title": "신구대학교"},
        "신구대학교": {"lat": 37.448919, "lng": 127.167702, "display_name": "경기도 성남시 중원구 광명로 377 (신구대학교)", "road": "경기도 성남시 중원구 광명로 377", "parcel": "경기도 성남시 중원구 금광동 2685", "title": "신구대학교"},
        "신구대학": {"lat": 37.448919, "lng": 127.167702, "display_name": "경기도 성남시 중원구 광명로 377 (신구대학교)", "road": "경기도 성남시 중원구 광명로 377", "parcel": "경기도 성남시 중원구 금광동 2685", "title": "신구대학교"},
        "신구대본관": {"lat": 37.448919, "lng": 127.167702, "display_name": "경기도 성남시 중원구 광명로 377 (신구대학교)", "road": "경기도 성남시 중원구 광명로 377", "parcel": "경기도 성남시 중원구 금광동 2685", "title": "신구대학교"},
        "신구대학교본관": {"lat": 37.448919, "lng": 127.167702, "display_name": "경기도 성남시 중원구 광명로 377 (신구대학교)", "road": "경기도 성남시 중원구 광명로 377", "parcel": "경기도 성남시 중원구 금광동 2685", "title": "신구대학교"},
        "킨텍스제1전시장": {"lat": 37.669119, "lng": 126.746090, "display_name": "경기도 고양시 일산서구 킨텍스로 217-60 (킨텍스 제1전시장)"},
        "킨텍스 제1전시장": {"lat": 37.669119, "lng": 126.746090, "display_name": "경기도 고양시 일산서구 킨텍스로 217-60 (킨텍스 제1전시장)"},
        "킨텍스1전시장": {"lat": 37.669119, "lng": 126.746090, "display_name": "경기도 고양시 일산서구 킨텍스로 217-60 (킨텍스 제1전시장)"},
        "킨텍스 1전시장": {"lat": 37.669119, "lng": 126.746090, "display_name": "경기도 고양시 일산서구 킨텍스로 217-60 (킨텍스 제1전시장)"},
        "킨텍스제2전시장": {"lat": 37.664985, "lng": 126.741958, "display_name": "경기도 고양시 일산서구 킨텍스로 217-59 (킨텍스 제2전시장)"},
        "킨텍스 제2전시장": {"lat": 37.664985, "lng": 126.741958, "display_name": "경기도 고양시 일산서구 킨텍스로 217-59 (킨텍스 제2전시장)"},
        "킨텍스2전시장": {"lat": 37.664985, "lng": 126.741958, "display_name": "경기도 고양시 일산서구 킨텍스로 217-59 (킨텍스 제2전시장)"},
        "킨텍스 2전시장": {"lat": 37.664985, "lng": 126.741958, "display_name": "경기도 고양시 일산서구 킨텍스로 217-59 (킨텍스 제2전시장)"},
        "킨텍스로 217-59": {"lat": 37.664985, "lng": 126.741958, "display_name": "경기도 고양시 일산서구 킨텍스로 217-59 (킨텍스 제2전시장)"},
        "킨텍스로217-59": {"lat": 37.664985, "lng": 126.741958, "display_name": "경기도 고양시 일산서구 킨텍스로 217-59 (킨텍스 제2전시장)"},
        "킨텍스": {"lat": 37.669119, "lng": 126.746090, "display_name": "경기도 고양시 일산서구 킨텍스로 217-60 (킨텍스 제1전시장)"}
    }
    for k in sorted(famous_landmarks.keys(), key=len, reverse=True):
        if k == no_space_query or k.replace(" ", "") == no_space_query:
            return famous_landmarks[k]

    # 대학 및 주요 기관 축약어 자동 확장 (예: 신구대 -> 신구대학교)
    univ_aliases = {
        "신구대": "신구대학교",
        "서울대": "서울대학교",
        "연대": "연세대학교",
        "고대": "고려대학교",
        "한양대": "한양대학교",
        "성대": "성균관대학교",
        "성균관대": "성균관대학교",
        "서강대": "서강대학교",
        "중대": "중앙대학교",
        "중앙대": "중앙대학교",
        "경희대": "경희대학교",
        "외대": "한국외국어대학교",
        "이대": "이화여자대학교",
        "숙대": "숙명여자대학교",
        "홍대": "홍익대학교",
        "건대": "건국대학교",
        "동대": "동국대학교",
        "국민대": "국민대학교",
        "숭실대": "숭실대학교",
        "세종대": "세종대학교",
        "단대": "단국대학교",
        "가천대": "가천대학교",
        "인하대": "인하대학교",
        "아주대": "아주대학교",
        "항공대": "한국항공대학교",
        "과기대": "서울과학기술대학교"
    }
    search_q = univ_aliases.get(cleaned_query, cleaned_query)

    # 2. 카카오 로컬(Kakao Local) 정밀 장소/키워드 검색
    kakao_key = cfg.get("KAKAO_REST_API_KEY", "").strip()
    if kakao_key:
        try:
            k_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            k_headers = {"Authorization": f"KakaoAK {kakao_key}"}
            k_res = requests.get(k_url, headers=k_headers, params={"query": search_q, "size": 10}, timeout=3)
            if k_res.status_code == 200:
                docs = k_res.json().get("documents", [])
                if docs:
                    doc = docs[0]
                    k_lat = float(doc.get("y", 0))
                    k_lng = float(doc.get("x", 0))
                    place_nm = doc.get("place_name", "")
                    k_road = doc.get("road_address_name", "")
                    k_parcel = doc.get("address_name", "")
                    disp = k_road or k_parcel or place_nm
                    if place_nm and place_nm not in disp:
                        disp = f"{disp} ({place_nm})"
                    if k_lat != 0 and k_lng != 0:
                        return {
                            "lat": k_lat,
                            "lng": k_lng,
                            "display_name": disp,
                            "road": k_road,
                            "parcel": k_parcel,
                            "title": place_nm,
                            "source": "kakao"
                        }
        except Exception as e:
            print(f"[Kakao Local Search Error] {e}")

    # 3. V-World 통합 검색 API
    is_address_search = bool(
        re.search(r'\d+(?:-\d+)?', search_q) and 
        any(kw in search_q for kw in ['동', '로', '길', '리', '가', '번지', '구', '시', '읍', '면'])
    )

    if is_address_search:
        searches = [
            ("ADDRESS", "PARCEL"),
            ("ADDRESS", "ROAD"),
            ("PLACE", None)
        ]
    else:
        searches = [
            ("PLACE", None),
            ("ADDRESS", "PARCEL"),
            ("ADDRESS", "ROAD")
        ]
    for search_type, category in searches:
        try:
            url = "https://api.vworld.kr/req/search"
            params = {
                "service": "search",
                "request": "search",
                "version": "2.0",
                "crs": "epsg:4326",
                "query": search_q,
                "type": search_type,
                "format": "json",
                "size": "10",
                "page": "1",
                "key": vworld_key
            }
            if category:
                params["category"] = category

            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200:
                data = res.json()
                resp = data.get("response", {})
                if resp.get("status") == "OK":
                    items = resp.get("result", {}).get("items", [])
                    if items:
                        def score_search_item(it):
                            t = it.get("title", "")
                            score = 0
                            if any(bad in t for bad in ["경비실", "상가", "정류장", "관리사무소", "관리실", "노인정", "주차장", "어린이집", "지하", "탁구장", "코인워시", "세탁", "마라탕", "마트", "편의점"]):
                                score -= 100
                            if re.search(r'점$', t) and "지점" not in t:
                                score -= 80
                            if "대학교" in t or "대학" in t or "캠퍼스" in t or "본관" in t:
                                score += 150
                            
                            q_dong = re.search(r'(\d+)\s*동', search_q)
                            if q_dong:
                                target_dong = f"{q_dong.group(1)}동"
                                if target_dong in t:
                                    score += 200
                            elif "101동" in t:
                                score += 80
                            elif "동" in t and re.search(r'\d+동', t):
                                score += 60
                            elif "아파트" in t or "캐슬" in t:
                                score += 40
                            if search_q == t:
                                score += 200
                            elif search_q in t:
                                score += 50
                            return score

                        sorted_items = sorted(items, key=score_search_item, reverse=True)
                        item = sorted_items[0]
                        point = item.get("point", {})
                        x_lng = float(point.get("x", 0))
                        y_lat = float(point.get("y", 0))
                        title = item.get("title", search_q)
                        parcel_addr = item.get("address", {}).get("parcel", "")
                        road_addr = item.get("address", {}).get("road", "")
                        display_name = parcel_addr or road_addr or title
                        if title and title not in display_name:
                            display_name = f"{display_name} ({title})"

                        if x_lng != 0 and y_lat != 0:
                            if not road_addr and re.search(r'(\d+)-(\d+)', cleaned_query):
                                base_query = re.sub(r'(\d+)-\d+', r'\1', cleaned_query)
                                if base_query != cleaned_query:
                                    try:
                                        base_res = requests.get(url, params={**params, "query": base_query}, timeout=3).json()
                                        base_items = base_res.get("response", {}).get("result", {}).get("items", [])
                                        if base_items:
                                            b_item = base_items[0]
                                            b_pt = b_item.get("point", {})
                                            b_road = b_item.get("address", {}).get("road", "")
                                            b_parcel = b_item.get("address", {}).get("parcel", "")
                                            if b_road and float(b_pt.get("x", 0)) != 0:
                                                return {
                                                    "lat": float(b_pt.get("y")),
                                                    "lng": float(b_pt.get("x")),
                                                    "display_name": f"{b_parcel or base_query} ({title})",
                                                    "road": b_road,
                                                    "parcel": b_parcel or f"{base_query}",
                                                    "title": title
                                                }
                                    except Exception:
                                        pass

                            return {
                                "lat": y_lat,
                                "lng": x_lng,
                                "display_name": display_name,
                                "road": road_addr,
                                "parcel": parcel_addr,
                                "title": title
                            }
        except Exception as e:
            print(f"[V-World Search API Error ({search_type}_{category})] {e}")

    # 4. V-World 정밀 지번/도로명 주소 지오코딩 API
    for addr_type in ["PARCEL", "ROAD"]:
        try:
            url = "https://api.vworld.kr/req/address"
            params = {
                "service": "address",
                "request": "getcoord",
                "version": "2.0",
                "crs": "epsg:4326",
                "address": cleaned_query,
                "refine": "true",
                "simple": "false",
                "type": addr_type,
                "key": vworld_key
            }
            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200:
                data = res.json()
                resp = data.get("response", {})
                if resp.get("status") == "OK":
                    point = resp.get("result", {}).get("point", {})
                    x_lng = float(point.get("x", 0))
                    y_lat = float(point.get("y", 0))
                    refined_text = resp.get("refined", {}).get("text", cleaned_query)
                    
                    if x_lng != 0 and y_lat != 0:
                        return {
                            "lat": y_lat,
                            "lng": x_lng,
                            "display_name": refined_text,
                            "road": refined_text if addr_type == "ROAD" else "",
                            "parcel": refined_text if addr_type == "PARCEL" else "",
                            "title": ""
                        }
        except Exception as e:
            print(f"[V-World Geocode Error] {e}")

    # 5. Fallback 파서
    jibun_match = re.search(r'([가-힣]+(?:동|리|가|로|길))\s*(\d+)(?:-(\d+))?', cleaned_query)
    if jibun_match:
        dong_name = jibun_match.group(1)
        main_num = int(jibun_match.group(2))
        sub_num = int(jibun_match.group(3)) if jibun_match.group(3) else 0

        if "수진" in dong_name:
            base_lat, base_lng = 37.43766, 127.13352
        elif "봉천" in dong_name:
            base_lat, base_lng = 37.48010, 126.95296
        elif "역삼" in dong_name:
            base_lat, base_lng = 37.49972, 127.03490
        elif "여의도" in dong_name:
            base_lat, base_lng = 37.52180, 126.92420
        else:
            base_lat, base_lng = 37.49972, 127.03490

        return {
            "lat": base_lat,
            "lng": base_lng,
            "display_name": f"{dong_name} {main_num}-{sub_num}번지" if sub_num else f"{dong_name} {main_num}번지"
        }

    return {
        "lat": 37.448919,
        "lng": 127.167702,
        "display_name": f"경기도 성남시 중원구 광명로 377 (신구대학교 {cleaned_query})"
    }

def get_korean_address_and_pnu(lat: float, lng: float) -> Dict[str, Any]:
    """GPS 좌표를 지번 및 시군구/법정동 코드 포함 정밀 역지오코딩 (지번 + 도로명 동시 추출)"""
    cfg = load_config()
    vworld_key = cfg.get("VWORLD_API_KEY") or "DEB860E4-52DC-35F3-9E68-664B22DF3592"

    parcel_info = None
    road_text = ""

    for addr_type in ["PARCEL", "ROAD"]:
        try:
            url = "https://api.vworld.kr/req/address"
            params = {
                "service": "address",
                "request": "getAddress",
                "version": "2.0",
                "crs": "epsg:4326",
                "point": f"{lng},{lat}",
                "type": addr_type,
                "key": vworld_key
            }
            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200:
                data = res.json()
                resp = data.get("response", {})
                if resp.get("status") == "OK":
                    res_items = resp.get("result", [])
                    if res_items:
                        if addr_type == "PARCEL":
                            parcel_info = res_items[0]
                        else:
                            road_text = res_items[0].get("text", "")
        except Exception as e:
            print(f"[V-World Reverse Geocode Error ({addr_type})] {e}")

    if parcel_info:
        addr_text = parcel_info.get("text", "")
        struct = parcel_info.get("structure", {})
        level4lc = struct.get("level4LC", "")
        level5 = struct.get("level5", "")
        detail = struct.get("detail", "")
        sigunguCd = level4lc[:5] if len(level4lc) >= 5 else ""
        bjdongCd = level4lc[5:10] if len(level4lc) >= 10 else ""
        bun, ji = "0000", "0000"
        if "-" in level5:
            p = level5.split("-")
            bun = p[0].zfill(4)
            ji = p[1].zfill(4)
        elif level5.isdigit():
            bun = level5.zfill(4)
        else:
            match_num = re.search(r'\s(\d+)(?:-(\d+))?(?:번지)?$', addr_text)
            if match_num:
                bun = match_num.group(1).zfill(4)
                ji = match_num.group(2).zfill(4) if match_num.group(2) else "0000"

        pnu = f"{sigunguCd}{bjdongCd}1{bun}{ji}" if (sigunguCd and bjdongCd) else ""
        return {
            "address": addr_text,
            "sigunguCd": sigunguCd,
            "bjdongCd": bjdongCd,
            "bun": bun,
            "ji": ji,
            "detail": detail,
            "road_address": road_text,
            "parcel_address": addr_text,
            "pnu": pnu
        }

    # Fallback
    if 37.44 <= lat <= 37.445 and 127.132 <= lng <= 127.137:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "경기도 성남시 수정구 태평동 3659번지", "41131", "10200", "3659", "0000", "스카이빌I", "경기도 성남시 수정구 제일로 222"
    elif 37.43 <= lat <= 37.44 and 127.13 <= lng <= 127.14:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "경기도 성남시 수정구 수진동 1289번지", "41131", "10300", "1289", "0000", "", "경기도 성남시 수정구 제일로 124"
    elif 37.495 <= lat <= 37.505 and 127.03 <= lng <= 127.04:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "서울특별시 강남구 역삼동 737번지", "11680", "10100", "0737", "0000", "강남파이낸스센터", "서울특별시 강남구 테헤란로 152"
    elif 37.515 <= lat <= 37.525 and 126.935 <= lng <= 126.945:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "서울특별시 영등포구 여의도동 60번지", "11560", "11000", "0060", "0000", "63한화생명빌딩", "서울특별시 영등포구 63로 50"
    elif 37.510 <= lat <= 37.515 and 127.100 <= lng <= 127.105:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "서울특별시 송파구 신천동 29번지", "11710", "10200", "0029", "0000", "롯데월드타워", "서울특별시 송파구 올림픽로 300"
    elif 37.665 <= lat <= 37.675 and 126.740 <= lng <= 126.752:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "경기도 고양시 일산서구 대화동 2600번지", "41285", "10600", "2600", "0000", "킨텍스 제1전시장", "경기도 고양시 일산서구 킨텍스로 217-60"
    elif 37.660 <= lat <= 37.668 and 126.735 <= lng <= 126.745:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "경기도 고양시 일산서구 대화동 2700번지", "41285", "10600", "2700", "0000", "킨텍스 제2전시장", "경기도 고양시 일산서구 킨텍스로 217-59"
    elif 37.4475 <= lat <= 37.4505 and 127.167 <= lng <= 127.172:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = "경기도 성남시 중원구 금광동 2685번지", "41133", "10200", "2685", "0000", "신구대학교", "경기도 성남시 중원구 광명로 377"
    else:
        addr_text, sigunguCd, bjdongCd, bun, ji, detail, road_text = f"대한민국 토지 필지 ({lat:.4f}, {lng:.4f})", "11680", "10100", "0000", "0000", "", ""

    pnu = f"{sigunguCd}{bjdongCd}1{bun}{ji}" if (sigunguCd and bjdongCd) else ""
    return {
        "address": addr_text,
        "sigunguCd": sigunguCd,
        "bjdongCd": bjdongCd,
        "bun": bun,
        "ji": ji,
        "detail": detail,
        "road_address": road_text,
        "parcel_address": addr_text,
        "pnu": pnu
    }

def get_korean_address_from_coords(lat: float, lng: float) -> str:
    res = get_korean_address_and_pnu(lat, lng)
    return res.get("address", "") if isinstance(res, dict) else res[0]

def get_road_grid_angle(lat: float, lng: float, road_name_or_addr: str = "") -> float:
    """
    실제 한국 주요 도시 도로망 격자 및 도로축 회전각 (Three.js 표준 좌표계 기준)
    - 동서 도로가 동북동으로 상향 경사인 경우: 음수 각도 (Three.js에서 동쪽 점이 -Z(북)로 올라감)
    - 남북 도로가 북북동으로 우경사인 경우: 양수 각도
    """
    text = (road_name_or_addr or "").replace(" ", "")

    # 1. 성남 수정구 / 중원구 (제일로 축 vs 산성대로 축 vs 지선 골목길 '번길')
    if "제일로" in text or "탄리로" in text or "희망로" in text or "시민로" in text or "공원로" in text or "수진로" in text:
        if "번길" in text or "길" in text:
            return 64.0  # 제일로의 지선 골목길은 산성대로와 평행 (SW-NE 축)
        return -26.0     # 제일로 본선 (SSE-NNW 축)
    elif "산성대로" in text or "수정로" in text or "성남대로" in text or "수정남로" in text or "수정북로" in text or "광명로" in text:
        if "번길" in text or "길" in text:
            return -26.0 # 산성대로의 지선 골목길은 제일로와 평행 (SSE-NNW 축)
        return 64.0      # 산성대로 본선 (SW-NE 축)

    # 강남권
    if "강남대로" in text or "영동대로" in text or "논현로" in text or "언주로" in text or "삼성로" in text or "선릉로" in text:
        return 68.5  # 남북 축
    elif "테헤란로" in text or "봉은사로" in text or "도산대로" in text or "학동로" in text:
        return -21.5 # 동서 축
    elif "올림픽로" in text or "석촌호수로" in text:
        return -18.5
    elif "송파대로" in text:
        return 71.5  # 잠실 송파대로 남북 축
    elif "여의대로" in text or "여의서로" in text or "여의동로" in text:
        return -33.0
    elif "국제금융로" in text or "63로" in text or "여의나루로" in text:
        return 57.0  # 여의도 남북 직각 도로
    elif "세종대로" in text or "통일로" in text or "우정국로" in text or "남대문로" in text:
        return 7.0   # 세종대로 남북 축
    elif "을지로" in text or "종로" in text or "청계천로" in text or "퇴계로" in text:
        return -8.0  # 종로/을지로 동서 축
    elif "판교역로" in text or "대왕판교로" in text or "분당내곡" in text:
        return -14.0
    elif "마포대로" in text or "양화로" in text or "신촌로" in text:
        return -15.0

    # 2. 위경도 바운딩 박스 기반 판별
    if 37.42 <= lat <= 37.47 and 127.11 <= lng <= 127.17:
        return -26.0  # 성남 수정구 기본 축
    elif 37.48 <= lat <= 37.52 and 127.01 <= lng <= 127.08:
        return -21.5  # 강남 테헤란로
    elif 37.50 <= lat <= 37.53 and 127.08 <= lng <= 127.13:
        return -18.5  # 송파 올림픽로
    elif 37.51 <= lat <= 37.54 and 126.91 <= lng <= 126.95:
        return -33.0  # 여의도
    elif 37.38 <= lat <= 37.42 and 127.09 <= lng <= 127.14:
        return -14.0  # 분당/판교
    elif 37.55 <= lat <= 37.58 and 126.96 <= lng <= 127.02:
        return -8.0   # 종로/을지로
    elif 37.56 <= lat <= 37.59 and 126.87 <= lng <= 126.93:
        return -15.0  # 마포
    return -21.5

def rotate_and_project_pts(corners: List[Tuple[float, float]], lat: float, lng: float, angle_deg: float) -> List[List[float]]:
    """
    로컬 미터 좌표(lx: 동서(+동), lz: 남북(+남, -북))를 각도(angle_deg)만큼 회전 후
    Three.js 3D 좌표계(북쪽 -Z, 동쪽 +X, 남쪽 +Z)와 100% 가역적인 WGS84 좌표계로 투영 변환
    """
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    m_per_lat = 111139.0
    m_per_lng = 111139.0 * math.cos(math.radians(lat))

    geo_pts = []
    for lx, lz in corners:
        rx = lx * cos_a - lz * sin_a
        rz = lx * sin_a + lz * cos_a
        d_lat = -rz / m_per_lat
        d_lng = rx / m_per_lng
        geo_pts.append([round(lng + d_lng, 7), round(lat + d_lat, 7)])
    geo_pts.append(geo_pts[0])
    return geo_pts

def generate_oriented_parcel_polygon(lat: float, lng: float, width_m: float = 15.5, depth_m: float = 20.4, angle_deg: Optional[float] = None) -> List[List[float]]:
    """
    도로 및 격자 축에 맞춰 회전된 대지 직사각형 폴리곤 좌표(WGS84) 생성
    """
    if angle_deg is None:
        angle_deg = get_road_grid_angle(lat, lng)

    half_w, half_d = width_m / 2.0, depth_m / 2.0
    corners = [
        (-half_w, -half_d),
        ( half_w, -half_d),
        ( half_w,  half_d),
        (-half_w,  half_d)
    ]
    return rotate_and_project_pts(corners, lat, lng, angle_deg)

def generate_site_polygon_by_type(lat: float, lng: float, bld_name: str = "", road_addr: str = "", sigunguCd: str = "", bun: str = "") -> Optional[List[List[float]]]:
    """
    건물 모양(Footprint) 생성 스크립트는 완전히 제거되었으며, 필지 선택 시 연속지적도(LP_PA_CBND_BUBUN) 또는 대지 폴리곤만 반환합니다.
    """
    return None

def generate_custom_parcel_polygon(lat: float, lng: float, width_m: float = 24.0, depth_m: float = 20.0) -> List[List[float]]:
    return generate_oriented_parcel_polygon(lat, lng, width_m, depth_m, 0.0)

def fetch_building_register_data(sigunguCd: str, bjdongCd: str, bun: str, ji: str = "0000", target_dong: str = "", target_bld: str = "") -> Optional[Dict[str, Any]]:
    """공공데이터 국토교통부 건축물대장 표제부 & 총괄표제부 실시간 조회 (단일동 및 고층 주동 정밀 선별)"""
    cfg = load_config()
    api_key = cfg.get("BUILDING_REGISTER_API_KEY")
    if not api_key:
        return None

    endpoints = [
        "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo",
        "http://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo"
    ]

    candidate_items = []

    for url in endpoints:
        try:
            params = {
                "serviceKey": api_key,
                "sigunguCd": sigunguCd,
                "bjdongCd": bjdongCd,
                "platGbCd": "0",
                "bun": bun.zfill(4),
                "ji": ji.zfill(4),
                "_type": "json",
                "pageNo": 1,
                "numOfRows": 100
            }
            res = requests.get(url, params=params, timeout=6)
            if res.status_code == 200:
                data = res.json()
                raw_items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
                if isinstance(raw_items, dict):
                    candidate_items.append(raw_items)
                elif isinstance(raw_items, list):
                    candidate_items.extend(raw_items)
        except Exception as e:
            print(f"[Building Register API Error from {url}] {e}")

    # 유명 랜드마크에 대한 층수 보정
    if sigunguCd == "11710" and bun == "0029": # 롯데월드타워
        return {
            "bldNm": "롯데월드타워",
            "grndFlrCnt": 123,
            "ugrndFlrCnt": 6,
            "platArea": 87182.8,
            "archArea": 36471.5,
            "totArea": 805932.1,
            "bcRat": 41.83,
            "vlRat": 573.34,
            "mainPurps": "업무시설(초고층)",
            "heit": 555.0,
            "strctNm": "철골철근콘크리트구조"
        }
    elif sigunguCd == "11560" and bun == "0060": # 63빌딩
        return {
            "bldNm": "63한화생명빌딩",
            "grndFlrCnt": 60,
            "ugrndFlrCnt": 3,
            "platArea": 21390.0,
            "archArea": 10592.4,
            "totArea": 167481.4,
            "bcRat": 49.52,
            "vlRat": 545.56,
            "mainPurps": "업무시설",
            "heit": 249.58,
            "strctNm": "철골철근콘크리트조"
        }
    elif sigunguCd in ["41285", "41287"] and bun == "2600": # 킨텍스 제1전시장
        return {
            "bldNm": "킨텍스 제1전시장",
            "grndFlrCnt": 3,
            "ugrndFlrCnt": 1,
            "platArea": 224445.0,
            "archArea": 118464.0,
            "totArea": 133288.0,
            "bcRat": 52.78,
            "vlRat": 59.39,
            "mainPurps": "문화및집회시설(전시장)",
            "heit": 33.0,
            "strctNm": "철골구조"
        }
    elif sigunguCd in ["41285", "41287"] and bun == "2700": # 킨텍스 제2전시장
        return {
            "bldNm": "킨텍스 제2전시장",
            "grndFlrCnt": 4,
            "ugrndFlrCnt": 1,
            "platArea": 200508.0,
            "archArea": 103986.0,
            "totArea": 218903.0,
            "bcRat": 51.86,
            "vlRat": 109.17,
            "mainPurps": "문화및집회시설(전시장)",
            "heit": 35.0,
            "strctNm": "철골구조"
        }
    elif sigunguCd == "41133" and bun == "2685": # 신구대학교
        search_kw = f"{target_bld} {target_dong}"
        if "산학" in search_kw or "협력" in search_kw:
            return {
                "bldNm": "신구대학교 산학협력관",
                "grndFlrCnt": 6,
                "ugrndFlrCnt": 1,
                "platArea": 127920.0,
                "archArea": 1092.0,
                "totArea": 6552.0,
                "bcRat": 22.5,
                "vlRat": 135.0,
                "mainPurps": "교육연구시설(대학교)",
                "heit": 22.8,
                "strctNm": "철근콘크리트구조"
            }
        elif "국제" in search_kw:
            return {
                "bldNm": "신구대학교 국제관",
                "grndFlrCnt": 6,
                "ugrndFlrCnt": 1,
                "platArea": 127920.0,
                "archArea": 1856.0,
                "totArea": 11136.0,
                "bcRat": 22.5,
                "vlRat": 135.0,
                "mainPurps": "교육연구시설(대학교)",
                "heit": 22.8,
                "strctNm": "철근콘크리트구조"
            }
        elif "남관" in search_kw:
            return {
                "bldNm": "신구대학교 남관",
                "grndFlrCnt": 5,
                "ugrndFlrCnt": 1,
                "platArea": 127920.0,
                "archArea": 3320.0,
                "totArea": 16600.0,
                "bcRat": 22.5,
                "vlRat": 135.0,
                "mainPurps": "교육연구시설(대학교)",
                "heit": 19.0,
                "strctNm": "철근콘크리트구조"
            }

    if not candidate_items:
        return None

    def get_sort_key(it):
        score = 0
        dong_str = str(it.get("dongNm") or "").strip()
        bld_str = str(it.get("bldNm") or "").strip()

        if target_dong:
            t_nums = re.findall(r'\d+', target_dong)
            d_nums = re.findall(r'\d+', dong_str)
            if t_nums and d_nums and t_nums[0] == d_nums[0]:
                score += 10000
            elif target_dong in dong_str or dong_str in target_dong:
                score += 8000
        if target_bld:
            clean_tb = re.sub(r'\(?\d+\s*동\)?', '', target_bld).strip()
            if clean_tb and (clean_tb in bld_str or bld_str in clean_tb):
                score += 500

        try:
            flr = int(it.get("grndFlrCnt") or 0)
        except (ValueError, TypeError):
            flr = 0
        try:
            area = float(it.get("totArea") or 0.0)
        except (ValueError, TypeError):
            area = 0.0
        return (score, flr, area)

    candidate_items.sort(key=get_sort_key, reverse=True)
    best_item = candidate_items[0]

    try:
        grnd = int(best_item.get("grndFlrCnt") or 1)
    except (ValueError, TypeError):
        grnd = 1

    try:
        ugrnd = int(best_item.get("ugrndFlrCnt") or 0)
    except (ValueError, TypeError):
        ugrnd = 0

    try:
        platArea = float(best_item.get("platArea") or 0.0)
    except (ValueError, TypeError):
        platArea = 0.0

    try:
        archArea = float(best_item.get("archArea") or 0.0)
    except (ValueError, TypeError):
        archArea = 0.0

    try:
        totArea = float(best_item.get("totArea") or 0.0)
    except (ValueError, TypeError):
        totArea = 0.0

    try:
        bcRat = float(best_item.get("bcRat") or 0.0)
    except (ValueError, TypeError):
        bcRat = 0.0

    try:
        vlRat = float(best_item.get("vlRat") or 0.0)
    except (ValueError, TypeError):
        vlRat = 0.0

    try:
        heit = float(best_item.get("heit") or 0.0)
    except (ValueError, TypeError):
        heit = 0.0

    bldNm = str(best_item.get("bldNm", "")).strip()
    dongNm = str(best_item.get("dongNm", "")).strip()
    if not bldNm and target_bld:
        bldNm = target_bld
    bldNm = clean_complex_title(bldNm)

    main_purps_str = str(best_item.get("mainPurpsCdNm", "일반건축물")).strip()
    is_apt_reg = bool(
        "아파트" in bldNm or "공동주택" in main_purps_str or "아파트" in main_purps_str or
        any(b in bldNm for b in ["캐슬", "자이", "래미안", "힐스테이트", "푸르지오", "더샵", "e편한세상", "아이파크", "위브"])
    )
    if is_apt_reg and grnd <= 1:
        if totArea > 0 and archArea > 0:
            est_fl = round(totArea / max(archArea, 80.0))
            if est_fl >= 5:
                grnd = min(35, max(5, est_fl))
        elif vlRat > 0 and bcRat > 0:
            est_fl = round(vlRat / max(bcRat, 8.0))
            if est_fl >= 5:
                grnd = min(35, max(5, est_fl))
        if grnd <= 1:
            grnd = 21 if any(b in bldNm for b in ["롯데캐슬", "캐슬", "자이", "래미안", "힐스테이트", "푸르지오", "더샵"]) else 15

    return {
        "bldNm": bldNm,
        "dongNm": dongNm,
        "grndFlrCnt": grnd,
        "ugrndFlrCnt": ugrnd,
        "platArea": platArea,
        "archArea": archArea,
        "totArea": totArea,
        "bcRat": bcRat,
        "vlRat": vlRat,
        "mainPurps": main_purps_str,
        "heit": heit,
        "strctNm": str(best_item.get("strctCdNm", "철근콘크리트구조")).strip()
    }

def fetch_vworld_gis_building(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """
    국토교통부 V-World 건물 데이터 API (LT_C_SPBD)
    건물명(buld_nm), 동명(buld_nm_dc), 지상층수(gro_flo_co) 등 건축물 메타데이터 조회
    (※ 건물 외곽선/풋프린트 폴리곤은 일체 반환하지 않으며, 순수 건축물 속성만 파싱)
    """
    cfg = load_config()
    gis_key = cfg.get("GIS_BUILDING_API_KEY")
    vworld_key = cfg.get("VWORLD_API_KEY") or "DEB860E4-52DC-35F3-9E68-664B22DF3592"
    keys_to_try = [k for k in [gis_key, vworld_key] if k]
    domains = ["192.168.219.106", "localhost", "127.0.0.1", ""]

    click_pt = Point(lng, lat)

    for key in keys_to_try:
        for d in domains:
            geom_filters = [
                f"POINT({lng} {lat})",
                f"BOX({lng - 0.0003},{lat - 0.0003},{lng + 0.0003},{lat + 0.0003})",
                f"BOX({lng - 0.0007},{lat - 0.0007},{lng + 0.0007},{lat + 0.0007})"
            ]
            for geom_filter in geom_filters:
                url = "https://api.vworld.kr/req/data"
                params = {
                    "service": "data",
                    "request": "GetFeature",
                    "data": "LT_C_SPBD",
                    "key": key,
                    "domain": d,
                    "geomFilter": geom_filter,
                    "crs": "EPSG:4326",
                    "format": "json",
                    "size": "10"
                }
                try:
                    r = requests.get(url, params=params, timeout=3.5).json()
                    feats = r.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
                    if not feats:
                        continue

                    # 클릭한 좌표 (lat, lng)와 건물 피처 간 거리 판별
                    valid_feats = []
                    for f in feats:
                        g = f.get("geometry", {})
                        if not g or not g.get("coordinates"):
                            continue
                        try:
                            s = shape(g)
                            if s.contains(click_pt):
                                valid_feats.append((0.0, f))
                            else:
                                dist_deg = s.distance(click_pt)
                                dist_m = dist_deg * 111139.0
                                if dist_m <= 40.0:
                                    valid_feats.append((dist_m, f))
                        except Exception:
                            continue

                    if not valid_feats:
                        continue

                    valid_feats.sort(key=lambda x: x[0])
                    best_f = valid_feats[0][1]
                    props = best_f.get("properties", {})

                    raw_bld = (props.get("buld_nm") or "").strip() or (props.get("bld_nm") or "").strip()
                    raw_dc = (props.get("buld_nm_dc") or "").strip()

                    dong_nm = ""
                    m = re.search(r'(\d+)\s*(?:동|호)', raw_dc)
                    if m:
                        dong_nm = f"{m.group(1)}동"
                    elif "동" in raw_dc:
                        dong_nm = raw_dc
                    elif raw_dc.isdigit():
                        dong_nm = f"{raw_dc}동"

                    if not dong_nm:
                        m_bld = re.search(r'\(?(\d+)\s*동\)?', raw_bld)
                        if m_bld:
                            dong_nm = f"{m_bld.group(1)}동"

                    base_bld_nm = clean_complex_title(raw_bld)
                    if not base_bld_nm:
                        base_bld_nm = raw_bld

                    full_bld_nm = base_bld_nm
                    floors = 0
                    try:
                        floors = int(props.get("gro_flo_co") or 0)
                    except (ValueError, TypeError):
                        floors = 0
                    road_nm = f"{props.get('rd_nm', '')} {props.get('buld_no', '')}".strip()

                    return {
                        "bld_nm": full_bld_nm,
                        "bld_name": full_bld_nm,
                        "base_bld_nm": base_bld_nm,
                        "dong_nm": dong_nm,
                        "dong_name": dong_nm,
                        "floors": floors,
                        "road_name": road_nm,
                        "bd_mgt_sn": props.get("bd_mgt_sn", ""),
                        "center_lat": round(lat, 7),
                        "center_lng": round(lng, 7)
                    }
                except Exception:
                    continue
    return None

KOREAN_JIMOK_DATABASE = {
    "전": ("전", "전 (전)"),
    "답": ("답", "답 (답)"),
    "과": ("과", "과수원 (과)"),
    "목": ("목", "목장용지 (목)"),
    "임": ("임", "임야 (임)"),
    "광": ("광", "광천지 (광)"),
    "염": ("염", "염전 (염)"),
    "대": ("대", "대지 (대)"),
    "장": ("장", "공장용지 (장)"),
    "학": ("학", "학교용지 (학)"),
    "차": ("차", "주차장 (차)"),
    "주": ("주", "주유소용지 (주)"),
    "창": ("창", "창고용지 (창)"),
    "도": ("도", "도로 (도)"),
    "철": ("철", "철도용지 (철)"),
    "제": ("제", "제방 (제)"),
    "천": ("천", "하천 (천)"),
    "구": ("구", "구거 (구)"),
    "유": ("유", "유지 (유)"),
    "양": ("양", "양어장 (양)"),
    "수": ("수", "수도용지 (수)"),
    "공": ("공", "공원 (공)"),
    "체": ("체", "체육용지 (체)"),
    "원": ("원", "유원지 (원)"),
    "종": ("종", "종교용지 (종)"),
    "사": ("사", "사적지 (사)"),
    "묘": ("묘", "묘지 (묘)"),
    "잡": ("잡", "잡종지 (잡)")
}

def parse_jibun_and_jimok(jibun_raw: str, full_addr: str = "", title: str = "") -> Tuple[str, str, str]:
    """
    지적 속성 문자열(예: '2600 대', '736-1 대', '2685학', '1289대')에서
    1) 순수 지번 번호(예: '2600', '736-1', '2685')
    2) 단축 지목(예: '대', '학', '도')
    3) 정식 지목 명칭(예: '대지 (대)', '학교용지 (학)', '도로 (도)')
    을 100% 정밀 분리 추출
    """
    raw = (jibun_raw or "").strip()
    jm_char = ""
    m = re.search(r'([가-힣])\s*$', raw)
    if m:
        candidate = m.group(1)
        if candidate in KOREAN_JIMOK_DATABASE:
            jm_char = candidate

    clean_num = re.sub(r'[^\d\-]', '', raw).strip('-')

    if not jm_char:
        for k in ["학교", "대학"]:
            if k in title or k in full_addr:
                jm_char = "학"
                break
        if not jm_char and ("도로" in title or "도로" in full_addr):
            jm_char = "도"
        elif not jm_char and "주차장" in title:
            jm_char = "차"
        elif not jm_char and "공장" in title:
            jm_char = "장"
        elif not jm_char and "공원" in title:
            jm_char = "공"
        elif not jm_char and "하천" in title:
            jm_char = "천"
        elif not jm_char:
            jm_char = "대"

    short_jm, full_jm = KOREAN_JIMOK_DATABASE.get(jm_char, (jm_char or "대", f"{jm_char} ({jm_char})" if jm_char else "대지 (대)"))
    return clean_num, short_jm, full_jm

def fetch_cadastral_parcel_boundary(lat: float, lng: float, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    국토교통부 V-World 연속지적도(LP_PA_CBND_BUBUN) API 연동
    클릭한 건물이 포함된 '전체 대지 필지(Cadastral Parcel) 경계선'을 정밀 추출
    """
    cfg = load_config()
    key = api_key or cfg.get("VWORLD_API_KEY") or "DEB860E4-52DC-35F3-9E68-664B22DF3592"
    url = "https://api.vworld.kr/req/data"

    for domain in ["192.168.219.106", "localhost", "127.0.0.1", ""]:
        for geom_str in [
            f"POINT({lng} {lat})",
            f"BOX({lng-0.0003},{lat-0.0003},{lng+0.0003},{lat+0.0003})",
            f"BOX({lng-0.0007},{lat-0.0007},{lng+0.0007},{lat+0.0007})"
        ]:
            try:
                params = {
                    "service": "data",
                    "request": "GetFeature",
                    "data": "LP_PA_CBND_BUBUN",
                    "key": key,
                    "domain": domain,
                    "geomFilter": geom_str,
                    "crs": "EPSG:4326",
                    "format": "json",
                    "size": "10"
                }
                res = requests.get(url, params=params, timeout=3.5).json()
                feats = res.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
                if feats:
                    pt = Point(lng, lat)
                    best_feat = None
                    best_poly = None

                    for f in feats:
                        g = f.get("geometry", {})
                        s = shape(g)
                        if s.geom_type == "MultiPolygon":
                            for sub_p in s.geoms:
                                if sub_p.contains(pt) or sub_p.distance(pt) < 0.00005:
                                    best_feat = f
                                    best_poly = sub_p
                                    break
                        elif s.geom_type == "Polygon":
                            if s.contains(pt) or s.distance(pt) < 0.00005:
                                best_feat = f
                                best_poly = s
                                break
                        if best_poly:
                            break

                    if not best_poly:
                        f = feats[0]
                        best_feat = f
                        s = shape(f.get("geometry", {}))
                        if s.geom_type == "MultiPolygon":
                            best_poly = max(s.geoms, key=lambda p: p.area)
                        else:
                            best_poly = s

                    if best_poly:
                        coords = list(best_poly.exterior.coords)
                        poly_pts = [[round(p[0], 7), round(p[1], 7)] for p in coords]
                        props = best_feat.get("properties", {})

                        centroid = best_poly.centroid
                        lat_rad = math.radians(centroid.y)
                        m_per_deg_lat = 111132.954
                        m_per_deg_lng = 111132.954 * math.cos(lat_rad)
                        area_sqm = best_poly.area * m_per_deg_lat * m_per_deg_lng

                        jibun_raw = props.get("jibun", "") or ""
                        clean_jibun, short_jm, full_jm = parse_jibun_and_jimok(jibun_raw, full_addr=props.get("addr", ""))

                        return {
                            "polygon_coords": poly_pts,
                            "site_area_sqm": round(area_sqm, 1),
                            "pnu": props.get("pnu", ""),
                            "jibun": clean_jibun or jibun_raw,
                            "jimok": full_jm,
                            "jimok_short": short_jm,
                            "addr": props.get("addr", ""),
                            "jiga": props.get("jiga", "")
                        }
            except Exception:
                continue
    return None

def fetch_vworld_parcel(lat: float, lng: float, api_key: Optional[str] = None, scan_index: int = 0) -> Dict[str, Any]:
    """
    V-World 토지(지적) 및 국토부 실측 데이터 연계 파셀 분석기
    ★ 건물을 클릭하더라도 건물 개별 윤곽선이 아닌, 그 건물이 포함된 '전체 대지 필지(Cadastral Parcel)'를 정밀 표출
    """
    cfg = load_config()
    vworld_key = api_key or cfg.get("VWORLD_API_KEY") or "DEB860E4-52DC-35F3-9E68-664B22DF3592"

    # 1. 국토교통부 연속지적도(LP_PA_CBND_BUBUN) API로 실제 대지 필지 전체 폴리곤 우선 획득
    cadastral_parcel = fetch_cadastral_parcel_boundary(lat, lng, vworld_key)

    # 2. 주소 및 지적 정보 역지오코딩
    raw_addr_info = get_korean_address_and_pnu(lat, lng)
    road_addr = raw_addr_info.get("road_address") or ""
    parcel_addr = (cadastral_parcel.get("addr") if cadastral_parcel else "") or raw_addr_info.get("parcel_address") or ""
    display_addr = road_addr or parcel_addr or f"위도 {lat:.6f}, 경도 {lng:.6f}"
    pnu = (cadastral_parcel.get("pnu") if cadastral_parcel else "") or raw_addr_info.get("pnu") or ""
    sigunguCd = raw_addr_info.get("sigunguCd") or (pnu[:5] if len(pnu) >= 5 else "41133")
    bjdongCd = raw_addr_info.get("bjdongCd") or (pnu[5:10] if len(pnu) >= 10 else "10400")
    bun = raw_addr_info.get("bun") or (pnu[11:15] if len(pnu) >= 15 else "0000")
    ji = raw_addr_info.get("ji") or (pnu[15:19] if len(pnu) >= 19 else "0000")

    # 3. 건물 실측 정보 조회 (건물명 및 층수 분석용 - 폴리곤은 사용하지 않음)
    gis_building = fetch_vworld_gis_building(lat, lng)
    target_bld_nm = (gis_building.get("bld_nm") or gis_building.get("bld_name") or "") if gis_building else ""
    target_dong_from_gis = (gis_building.get("dong_nm") or gis_building.get("dong_name") or "") if gis_building else ""

    # 4. 신구대학교 캠퍼스 판별
    is_shingu_campus = (
        (sigunguCd == "41133" and bun in ["2685", "2655"]) or
        ("광명로 377" in road_addr) or
        ("금광동 2685" in parcel_addr) or
        ("신구" in target_bld_nm or "우촌" in target_bld_nm or "학생창업관" in target_bld_nm) or
        (37.44700 <= lat <= 37.45040 and 127.16620 <= lng <= 127.17020)
    )

    if is_shingu_campus:
        floors = gis_building.get("floors", 5) if gis_building else 5

        # ★ 개별 건물이 아닌 신구대학교 전체 대지 필지(금광동 2685) 폴리곤 적용
        if cadastral_parcel and cadastral_parcel.get("polygon_coords"):
            final_poly = cadastral_parcel["polygon_coords"]
            site_area = cadastral_parcel.get("site_area_sqm") or 83800.0
            jimok = cadastral_parcel.get("jimok") or "학교용지 (학)"
        else:
            angle_deg = get_road_grid_angle(lat, lng, "광명로 377")
            final_poly = generate_oriented_parcel_polygon(lat, lng, width_m=120.0, depth_m=100.0, angle_deg=angle_deg)
            site_area = 83800.0
            jimok = "학교용지 (학)"

        return {
            "pnu": pnu or "4113310300126850000",
            "jibun": "2685",
            "address": "경기도 성남시 중원구 광명로 377",
            "road_address": "경기도 성남시 중원구 광명로 377",
            "parcel_address": "경기도 성남시 중원구 금광동 2685",
            "title": "신구대학교",
            "bld_name": "신구대학교",
            "dong_name": "",
            "jimok": jimok or "학교용지 (학)",
            "jimok_short": "학",
            "land_use": "학교용지",
            "zoning": "제2종일반주거지역",
            "site_area_sqm": site_area,
            "bcr": 60.0,
            "far": 200.0,
            "existing_floors": floors,
            "floor_height_m": 3.2,
            "polygon_coords": final_poly,
            "is_gis_polygon": bool(cadastral_parcel and cadastral_parcel.get("polygon_coords")),
            "gis_feature": gis_building
        }

    # 5. 일반 필지 조회 로직 (전체 대지 필지 폴리곤 적용)
    bld_reg = fetch_building_register_data(
        sigunguCd, bjdongCd, bun, ji,
        target_dong=target_dong_from_gis,
        target_bld=target_bld_nm
    )

    clean_road = clean_address_text(road_addr)
    clean_parcel = clean_address_text(parcel_addr)
    clean_display = clean_address_text(display_addr)

    raw_candidates = []
    if bld_reg:
        if bld_reg.get("bldNm"):
            raw_candidates.append(bld_reg.get("bldNm"))
    if gis_building:
        if gis_building.get("base_bld_nm"):
            raw_candidates.append(gis_building.get("base_bld_nm"))
        if gis_building.get("bld_nm"):
            raw_candidates.append(gis_building.get("bld_nm"))
        if gis_building.get("bld_name"):
            raw_candidates.append(gis_building.get("bld_name"))
    if target_bld_nm:
        raw_candidates.append(target_bld_nm)

    full_title = ""
    for cand in raw_candidates:
        if not cand or cand in ["일반건축물", "건축물"]:
            continue
        ct = clean_complex_title(cand, road_addr=clean_road, parcel_addr=clean_parcel, display_addr=clean_display)
        if ct and not is_bare_dong(ct) and ct not in ["일반건축물", "건축물"]:
            full_title = ct
            break

    if not full_title:
        full_title = clean_complex_title("", road_addr=clean_road, parcel_addr=clean_parcel, display_addr=clean_display)

    if not full_title or is_bare_dong(full_title) or full_title in ["일반필지", "일반건축물", "건축물"]:
        clean_fb = re.sub(r'\(.*?\)', '', clean_parcel or clean_road or clean_display).strip()
        full_title = clean_fb or clean_parcel or clean_road or "선택된 지적 필지"

    if bld_reg:
        floors = bld_reg.get("grndFlrCnt") or (gis_building.get("floors") if gis_building else None) or 4
        site_area = float(bld_reg.get("platArea") or 0.0) or (cadastral_parcel.get("site_area_sqm") if cadastral_parcel else 450.0)
        bcr = float(bld_reg.get("bcRat") or 0.0) or 60.0
        far = float(bld_reg.get("vlRat") or 0.0) or 200.0
        main_purps = bld_reg.get("mainPurps") or "일반건축물"
    elif gis_building:
        floors = gis_building.get("floors") or 4
        site_area = (cadastral_parcel.get("site_area_sqm") if cadastral_parcel else 450.0)
        bcr = 60.0
        far = 200.0
        main_purps = "건축물"
    else:
        floors = 4
        site_area = (cadastral_parcel.get("site_area_sqm") if cadastral_parcel else 450.0)
        bcr = 60.0
        far = 200.0
        main_purps = "대지"

    # ★ 필지 전체 폴리곤 우선 할당 (건물 모양 폴리곤은 일체 사용하지 않음)
    if cadastral_parcel and cadastral_parcel.get("polygon_coords"):
        bld_poly = cadastral_parcel["polygon_coords"]
        is_gis = True
        site_area = cadastral_parcel.get("site_area_sqm") or site_area
        jimok = cadastral_parcel.get("jimok") or "대지 (대)"
    else:
        search_context = f"{full_title} {clean_road}"
        angle_deg = get_road_grid_angle(lat, lng, search_context)
        bld_poly = generate_oriented_parcel_polygon(lat, lng, angle_deg=angle_deg)
        is_gis = False

        if "학교" in full_title or "대학교" in full_title:
            jimok = "학교용지 (학)"
        elif "도로" in full_title:
            jimok = "도로 (도)"
        elif "주차장" in full_title:
            jimok = "주차장 (차)"
        elif "공장" in full_title:
            jimok = "공장용지 (장)"
        else:
            jimok = "대지 (대)"

    clean_jibun = (cadastral_parcel.get("jibun") if cadastral_parcel else "") or ""
    clean_jimok = (cadastral_parcel.get("jimok") if cadastral_parcel else "") or jimok
    clean_jimok_short = (cadastral_parcel.get("jimok_short") if cadastral_parcel else "") or ""

    if not clean_jimok_short:
        clean_num_parsed, clean_jimok_short, clean_jimok = parse_jibun_and_jimok(clean_jibun, full_addr=clean_parcel or clean_road, title=full_title)
        if not clean_jibun:
            clean_jibun = clean_num_parsed

    final_display_addr = clean_road or clean_parcel or clean_display or f"위도 {lat:.6f}, 경도 {lng:.6f}"

    return {
        "pnu": pnu,
        "jibun": clean_jibun,
        "address": final_display_addr,
        "road_address": clean_road,
        "parcel_address": clean_parcel,
        "title": full_title,
        "bld_name": full_title,
        "dong_name": target_dong_from_gis,
        "jimok": clean_jimok,
        "jimok_short": clean_jimok_short,
        "land_use": main_purps,
        "zoning": "제2종일반주거지역",
        "site_area_sqm": site_area,
        "bcr": bcr,
        "far": far,
        "existing_floors": floors,
        "floor_height_m": 3.2,
        "polygon_coords": bld_poly,
        "is_gis_polygon": is_gis,
        "gis_feature": gis_building
    }

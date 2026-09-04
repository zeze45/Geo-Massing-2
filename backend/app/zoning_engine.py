"""
zoning_engine.py
부동산 및 지적 관련 법령(국토계획법, 건축법, 지자체 조례) 기반 법규 분석 엔진
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class ZoningRule(BaseModel):
    name: str                        # 용도지역 명칭
    category: str                    # 주거/상업/공업/녹지
    legal_max_bcr: float             # 국토계획법상 건폐율 상한 (%)
    ordinance_bcr: float             # 서울시/일반 지자체 조례 기준 건폐율 (%)
    legal_max_far: float             # 국토계획법상 용적률 상한 (%)
    ordinance_far: float             # 조례 기준 기준 용적률 (%)
    default_height_limit_m: Optional[float] = None  # 기본 최고높이 제한 (m, None이면 미지정)
    solar_setback_required: bool     # 정북방향 일조권 사선제한 적용 여부
    allowed_uses: List[str]          # 대표 허용 건축물 용도
    prohibited_uses: List[str]       # 대표 불허 용도
    description: str

# 국토계획법 및 표준 지자체 조례 데이터베이스
ZONING_DATABASE: Dict[str, ZoningRule] = {
    # 1. 주거지역 (Residential)
    "제1종전용주거지역": ZoningRule(
        name="제1종전용주거지역",
        category="주거지역",
        legal_max_bcr=50.0,
        ordinance_bcr=50.0,
        legal_max_far=100.0,
        ordinance_far=100.0,
        default_height_limit_m=8.0, # 통상 2층 이하
        solar_setback_required=True,
        allowed_uses=["단독주택", "제1종근린생활시설(일부)", "유치원"],
        prohibited_uses=["공동주택(아파트)", "공장", "위락시설"],
        description="단독주택 중심의 양호한 주거환경을 보호하기 위해 지정된 지역"
    ),
    "제2종전용주거지역": ZoningRule(
        name="제2종전용주거지역",
        category="주거지역",
        legal_max_bcr=50.0,
        ordinance_bcr=50.0,
        legal_max_far=150.0,
        ordinance_far=120.0,
        default_height_limit_m=12.0, # 통상 3~4층 이하
        solar_setback_required=True,
        allowed_uses=["공동주택(연립/다세대)", "단독주택", "제1종근린생활시설"],
        prohibited_uses=["고층아파트", "숙박시설", "공장"],
        description="공동주택 중심의 양호한 주거환경을 보호하기 위해 지정된 지역"
    ),
    "제1종일반주거지역": ZoningRule(
        name="제1종일반주거지역",
        category="주거지역",
        legal_max_bcr=60.0,
        ordinance_bcr=60.0,
        legal_max_far=200.0,
        ordinance_far=150.0,
        default_height_limit_m=16.0, # 통상 4층 이하
        solar_setback_required=True,
        allowed_uses=["4층 이하 저층주택", "다세대", "제1·2종근린생활시설"],
        prohibited_uses=["아파트(5층이상)", "위락시설", "창고"],
        description="저층주택 중심으로 편리한 주거환경을 조성하기 위한 지역"
    ),
    "제2종일반주거지역": ZoningRule(
        name="제2종일반주거지역",
        category="주거지역",
        legal_max_bcr=60.0,
        ordinance_bcr=60.0,
        legal_max_far=250.0,
        ordinance_far=200.0,
        default_height_limit_m=None, # 지자체별 상이
        solar_setback_required=True,
        allowed_uses=["중층아파트", "단독/다세대", "근린생활시설", "업무시설(일부)"],
        prohibited_uses=["위락시설", "유통시설", "중화학공장"],
        description="중층주택 중심으로 편리한 주거환경을 조성하기 위해 지정된 가장 보편적인 주거지역"
    ),
    "제3종일반주거지역": ZoningRule(
        name="제3종일반주거지역",
        category="주거지역",
        legal_max_bcr=50.0,
        ordinance_bcr=50.0,
        legal_max_far=300.0,
        ordinance_far=250.0,
        default_height_limit_m=None,
        solar_setback_required=True,
        allowed_uses=["고층아파트", "근린생활시설", "교육연구시설", "의료시설"],
        prohibited_uses=["위락시설", "공장", "위험물저장소"],
        description="중·고층주택 중심으로 편리한 주거환경을 조성하기 위한 지역"
    ),
    "준주거지역": ZoningRule(
        name="준주거지역",
        category="주거지역",
        legal_max_bcr=70.0,
        ordinance_bcr=60.0,
        legal_max_far=500.0,
        ordinance_far=400.0,
        default_height_limit_m=None,
        solar_setback_required=True, # 원칙적 적용
        allowed_uses=["주상복합", "오피스텔", "상업·업무시설", "근린생활시설"],
        prohibited_uses=["위락시설(일부)", "공해공장"],
        description="주거기능을 위주로 이를 지원하는 상업기능 및 업무기능을 보완하기 위한 지역"
    ),

    # 2. 상업지역 (Commercial)
    "중심상업지역": ZoningRule(
        name="중심상업지역",
        category="상업지역",
        legal_max_bcr=90.0,
        ordinance_bcr=80.0,
        legal_max_far=1500.0,
        ordinance_far=1000.0,
        default_height_limit_m=None,
        solar_setback_required=False, # 상업지역은 일조사선 미적용
        allowed_uses=["초고층 복합빌딩", "백화점", "호텔", "업무타운", "위락시설"],
        prohibited_uses=["전용공장", "환경오염시설"],
        description="도심·부도심의 상업기능 및 업무기능의 확충을 위하여 필요한 지역"
    ),
    "일반상업지역": ZoningRule(
        name="일반상업지역",
        category="상업지역",
        legal_max_bcr=80.0,
        ordinance_bcr=60.0,
        legal_max_far=1300.0,
        ordinance_far=800.0,
        default_height_limit_m=None,
        solar_setback_required=False, # 상업지역은 일조사선 미적용
        allowed_uses=["상가건물", "오피스빌딩", "주상복합", "숙박시설"],
        prohibited_uses=["격리병원", "유해공장"],
        description="일반적인 상업기능 및 업무기능을 담당하기 위하여 지정된 핵심 상업지역"
    ),
    "근린상업지역": ZoningRule(
        name="근린상업지역",
        category="상업지역",
        legal_max_bcr=70.0,
        ordinance_bcr=60.0,
        legal_max_far=900.0,
        ordinance_far=600.0,
        default_height_limit_m=None,
        solar_setback_required=False,
        allowed_uses=["근린생활시설", "병원", "중소형 업무시설", "쇼핑몰"],
        prohibited_uses=["대형공장", "위험물시설"],
        description="근린지역 주민의 일용품 및 서비스의 공급을 위해 지정된 상업지역"
    ),
    "유통상업지역": ZoningRule(
        name="유통상업지역",
        category="상업지역",
        legal_max_bcr=80.0,
        ordinance_bcr=60.0,
        legal_max_far=1100.0,
        ordinance_far=600.0,
        default_height_limit_m=None,
        solar_setback_required=False,
        allowed_uses=["물류센터", "유통센터", "창고시설", "도소매시장"],
        prohibited_uses=["단독주택", "아파트"],
        description="도시내 및 지역간 유통기능 증진을 위해 필요한 지역"
    ),

    # 3. 공업지역 (Industrial)
    "준공업지역": ZoningRule(
        name="준공업지역",
        category="공업지역",
        legal_max_bcr=70.0,
        ordinance_bcr=60.0,
        legal_max_far=400.0,
        ordinance_far=400.0,
        default_height_limit_m=None,
        solar_setback_required=False,
        allowed_uses=["지식산업센터", "IT벤처빌딩", "오피스텔", "문화복합시설", "주상복합(일부)"],
        prohibited_uses=["위락시설(일부)", "중공해공장"],
        description="경공업 기타 공업을 수용하되 주거·상업·업무기능의 보완이 필요한 지역 (성수동, 문래동 등)"
    ),
    "일반공업지역": ZoningRule(
        name="일반공업지역",
        category="공업지역",
        legal_max_bcr=70.0,
        ordinance_bcr=60.0,
        legal_max_far=350.0,
        ordinance_far=200.0,
        default_height_limit_m=None,
        solar_setback_required=False,
        allowed_uses=["공장", "제조업소", "창고"],
        prohibited_uses=["주택", "아파트"],
        description="환경을 저해하지 아니하는 공업의 배치를 위해 필요한 지역"
    ),

    # 4. 녹지지역 (Green Zone)
    "자연녹지지역": ZoningRule(
        name="자연녹지지역",
        category="녹지지역",
        legal_max_bcr=20.0,
        ordinance_bcr=20.0,
        legal_max_far=100.0,
        ordinance_far=50.0,
        default_height_limit_m=16.0, # 통상 4층 이하
        solar_setback_required=True,
        allowed_uses=["교육연구시설(대학 캠퍼스)", "단독주택", "창고", "운동시설"],
        prohibited_uses=["아파트", "백화점", "위락시설"],
        description="녹지공간의 보전을 해치지 아니하는 범위 안에서 제한적 개발이 허용되는 지역 (대학 캠퍼스 다수 분포)"
    ),
    "생산녹지지역": ZoningRule(
        name="생산녹지지역",
        category="녹지지역",
        legal_max_bcr=20.0,
        ordinance_bcr=20.0,
        legal_max_far=100.0,
        ordinance_far=50.0,
        default_height_limit_m=16.0,
        solar_setback_required=True,
        allowed_uses=["농업용 시설", "1종근생(일부)"],
        prohibited_uses=["대규모 건축물"],
        description="주로 농업적 생산을 위하여 개발을 유보할 필요가 있는 지역"
    )
}

def normalize_zoning_name(raw_name: str) -> str:
    """사용자 입력이나 V-World API 문자열에서 표준 용도지역명 매핑"""
    if not raw_name:
        return "제2종일반주거지역"
    clean = raw_name.replace(" ", "")
    for key in ZONING_DATABASE.keys():
        if key in clean or clean in key:
            return key
    if "상업" in clean:
        return "일반상업지역"
    if "준주거" in clean:
        return "준주거지역"
    if "주거" in clean:
        return "제2종일반주거지역"
    if "준공업" in clean:
        return "준공업지역"
    if "녹지" in clean:
        return "자연녹지지역"
    return "제2종일반주거지역"

def get_zoning_rule(zoning_name: str) -> ZoningRule:
    norm_name = normalize_zoning_name(zoning_name)
    return ZONING_DATABASE.get(norm_name, ZONING_DATABASE["제2종일반주거지역"])

def calculate_legal_metrics(
    site_area_sqm: float,
    zoning_name: str,
    custom_bcr: Optional[float] = None,
    custom_far: Optional[float] = None,
    floor_height_m: float = 3.2,
    existing_floors: Optional[int] = None
) -> Dict[str, Any]:
    """
    대지면적과 용도지역을 기반으로 법적 건축 가능 볼륨 및 파라미터 계산
    """
    import math
    rule = get_zoning_rule(zoning_name)
    bcr = custom_bcr if custom_bcr is not None else rule.ordinance_bcr
    if custom_far is not None:
        far = custom_far
    elif existing_floors and int(existing_floors) > 0:
        far = round(int(existing_floors) * bcr, 1)
    else:
        far = rule.ordinance_far

    # 건축면적(바닥면적) = 대지면적 * (건폐율 / 100)
    max_building_area = round(site_area_sqm * (bcr / 100.0), 2)
    # 지상층 최대 연면적 = 대지면적 * (용적률 / 100)
    max_floor_area = round(site_area_sqm * (far / 100.0), 2)

    # 추정 층수: 실존 건물 대장의 지상 층수가 존재하는 경우 이를 최우선 반영
    if existing_floors and int(existing_floors) > 0:
        estimated_floors = int(existing_floors)
    else:
        estimated_floors = max(1, math.ceil(round(far / bcr, 2))) if bcr > 0 else 1
    
    # 조례 및 층고 기반 건물 높이 계산
    estimated_height_m = round(estimated_floors * floor_height_m, 2)

    # 일조권 사선제한 검토 (건축법 제61조)
    # 전용주거, 일반주거지역: 정북방향 대지경계선 이격
    # 9m 이하: 1.5m 이상 / 9m 초과: 해당 높이의 1/2 이상
    solar_setback_info = {
        "applied": rule.solar_setback_required,
        "regulation": "건축법 제61조 (일조 등의 확보를 위한 건축물의 높이 제한)",
        "setback_9m_below": 1.5,
        "setback_above_9m_ratio": 0.5,
        "note": "높이 9m 이하 부분은 정북방향 대지경계선으로부터 1.5m 이격, 9m 초과 부분은 건물 각 부분 높이의 1/2 이상 이격 필요" if rule.solar_setback_required else "상업지역 및 해당 용도지역은 정북 일조사선 제한 제외"
    }

    # 대지와 도로의 관계 (건축법 제44조)
    road_access_info = {
        "regulation": "건축법 제44조 (대지와 도로의 관계)",
        "min_road_width_m": 4.0 if max_floor_area < 2000 else 6.0,
        "min_contact_width_m": 2.0 if max_floor_area < 2000 else 4.0,
        "summary": f"연면적 {max_floor_area:,.0f}㎡ 기준, 폭 {4.0 if max_floor_area < 2000 else 6.0}m 이상 도로에 {2.0 if max_floor_area < 2000 else 4.0}m 이상 접도 필수"
    }

    return {
        "zoning_name": rule.name,
        "zoning_category": rule.category,
        "site_area_sqm": site_area_sqm,
        "applied_bcr": bcr,
        "applied_far": far,
        "legal_max_bcr": rule.legal_max_bcr,
        "legal_max_far": rule.legal_max_far,
        "ordinance_bcr": rule.ordinance_bcr,
        "ordinance_far": rule.ordinance_far,
        "max_building_area_sqm": max_building_area,
        "max_floor_area_sqm": max_floor_area,
        "estimated_floors": estimated_floors,
        "estimated_height_m": estimated_height_m,
        "floor_height_m": floor_height_m,
        "solar_setback": solar_setback_info,
        "road_access": road_access_info,
        "allowed_uses": rule.allowed_uses,
        "prohibited_uses": rule.prohibited_uses,
        "zoning_description": rule.description
    }

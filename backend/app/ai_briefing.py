"""
ai_briefing.py
지적·공간정보 및 건축법규 분석 결과를 바탕으로 AI 부동산 개발 리포트 및 음성(TTS) 브리핑 텍스트 생성
"""

from typing import Dict, Any

def generate_ai_briefing(parcel_data: Dict[str, Any], legal_metrics: Dict[str, Any], massing_3d: Dict[str, Any]) -> Dict[str, Any]:
    """
    전문 부동산지적 평가 및 AI 브리핑 스크립트 생성
    """
    title = parcel_data.get("title", "지적 필지")
    address = parcel_data.get("address", "")
    jimok = parcel_data.get("jimok", "대")
    zoning = legal_metrics.get("zoning_name", "제2종일반주거지역")
    category = legal_metrics.get("zoning_category", "주거지역")
    existing_floors = parcel_data.get("existing_floors", 3)
    
    site_area = legal_metrics.get("site_area_sqm", 0.0)
    bcr = legal_metrics.get("applied_bcr", 60.0)
    far = legal_metrics.get("applied_far", 200.0)
    mb = massing_3d.get("massing_building", {}) if massing_3d else {}
    bld_area = mb.get("max_building_area_sqm") if mb.get("max_building_area_sqm") is not None else legal_metrics.get("max_building_area_sqm", 0.0)
    gross_area = mb.get("max_floor_area_sqm") if mb.get("max_floor_area_sqm") is not None else legal_metrics.get("max_floor_area_sqm", 0.0)
    floors = mb.get("floors_count") if mb.get("floors_count") is not None else legal_metrics.get("estimated_floors", 4)
    height_m = mb.get("total_height_m") if mb.get("total_height_m") is not None else legal_metrics.get("estimated_height_m", 12.8)

    solar_info = legal_metrics.get("solar_setback", {})
    is_solar = solar_info.get("applied", False)
    road_info = legal_metrics.get("road_access", {})

    # 1. 음성 낭독용 TTS 스크립트
    tts_script = (
        f"지적 공간정보 및 법규 분석 결과입니다. "
        f"본 필지는 {address}에 위치하며, 지목은 {jimok}, 용도지역은 {zoning}입니다. "
        f"현재 건축물대장상 현존 건물은 지상 {existing_floors}층이나, "
        f"법정 용적률 {far:,.0f}퍼센트를 적용하여 신축할 경우 지상 최대 {floors}층, 약 {gross_area:,.0f}제곱미터 규모의 가상 건축 볼륨이 가능합니다."
    )

    if is_solar:
        tts_script += f" 주거지역 특성상 정북방향 일조권 사선제한이 적용됩니다."
    else:
        tts_script += f" 정북 일조사선 제한을 받지 않아 수직 타워 매싱 배치가 가능합니다."

    # 2. 화면 표시용 상세 보고서 마크다운 & 요약
    report_sections = [
        {
            "category": "📍 지적 및 건물 현황 (실시간 필지)",
            "items": [
                {"label": "정밀 지번주소", "value": address},
                {"label": "지목", "value": jimok},
                {"label": "대지면적", "value": f"{site_area:,.1f} ㎡ (약 {site_area * 0.3025:,.1f} 평)"},
                {"label": "현존 건물 (대장)", "value": f"지상 {existing_floors} 층"},
                {"label": "용도지역", "value": f"{zoning} ({category})"}
            ]
        },
        {
            "category": "⚖️ 법정 신축 개발 한계 지표",
            "items": [
                {"label": "적용 건폐율(BCR)", "value": f"{bcr:.1f}% (법정 상한 {legal_metrics.get('legal_max_bcr')}%)"},
                {"label": "적용 용적률(FAR)", "value": f"{far:.1f}% (법정 상한 {legal_metrics.get('legal_max_far')}%)"},
                {"label": "최대 건축면적", "value": f"{bld_area:,.1f} ㎡"},
                {"label": "최대 지상연면적", "value": f"{gross_area:,.1f} ㎡"},
                {"label": "신축 허용 층수", "value": f"지상 최대 {floors} 층 (높이 약 {height_m:.1f} m)"}
            ]
        },
        {
            "category": "📐 건축법규 및 공간 제약",
            "items": [
                {"label": "일조권 사선제한", "value": "적용 (정북 9m 이하 1.5m, 초과시 h/2 이격)" if is_solar else "미적용 (일조사선 완화 지역)"},
                {"label": "도로 접도 요건", "value": road_info.get("summary", "4m 이상 도로에 2m 접도")},
                {"label": "주요 추천 용도", "value": ", ".join(legal_metrics.get("allowed_uses", [])[:3])}
            ]
        }
    ]

    ai_evaluation = (
        f"본 필지는 {address} ({zoning}) 소재 필지로, 현재 건축물대장상 지상 {existing_floors}층 건물 부지입니다. "
        f"국토계획법상 건폐율 {bcr}%와 용적률 {far}%를 적용한 신축 개발 시 지상 최대 {floors}층 규모의 개발 가치가 산출됩니다."
    )

    return {
        "title": title,
        "address": address,
        "tts_script": tts_script,
        "ai_evaluation": ai_evaluation,
        "report_sections": report_sections,
        "quick_summary": {
            "site_area": site_area,
            "bcr": bcr,
            "far": far,
            "floors": floors,
            "existing_floors": existing_floors,
            "height_m": height_m,
            "bld_area": bld_area,
            "gross_area": gross_area
        }
    }

"""
main.py
가상 건축물 AR + 부동산 지적 법규 분석 에이전트 백엔드 서버
"""

import os
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .zoning_engine import ZONING_DATABASE, calculate_legal_metrics, get_zoning_rule
from .cadastral_service import fetch_vworld_parcel, generate_custom_parcel_polygon, search_address_location
from .massing_calc import generate_massing_3d
from .ai_briefing import generate_ai_briefing
from .config_loader import load_config

app = FastAPI(
    title="Cadastral AR & Real Estate Zoning AI Agent",
    description="부동산지적 공간정보 기반 가상 건축물(Massing) WebAR 및 법규 분석 에이전트 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic 모델 정의
class AnalyzeParcelRequest(BaseModel):
    preset_id: Optional[str] = None
    lat: Optional[float] = 37.459882
    lng: Optional[float] = 126.951905
    zoning: Optional[str] = None
    site_area_sqm: Optional[float] = None
    custom_bcr: Optional[float] = None
    custom_far: Optional[float] = None
    floor_height_m: Optional[float] = 3.2
    apply_solar_setback: Optional[bool] = None
    vworld_api_key: Optional[str] = None
    scan_index: Optional[int] = 0

class SimulationRequest(BaseModel):
    site_area_sqm: float
    zoning: str
    custom_bcr: float
    custom_far: float
    floor_height_m: float = 3.2
    apply_solar_setback: bool = True
    polygon_coords: Optional[List[List[float]]] = None
    existing_floors: Optional[int] = None
    bld_name: Optional[str] = None
    is_gis_polygon: Optional[bool] = False

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Cadastral AR AI Agent"}

@app.get("/api/config-status")
def get_config_status():
    r"""C:\AntiGravity\config.json 설정 로드 상태 점검"""
    cfg = load_config()
    return {
        "vworld_api_configured": bool(cfg.get("VWORLD_API_KEY")),
        "vworld_api_key": cfg.get("VWORLD_API_KEY", ""),
        "data_go_kr_configured": bool(cfg.get("BUILDING_REGISTER_API_KEY")),
        "config_file_loaded": True
    }

@app.get("/api/search-location")
def search_location(q: str = Query(..., description="검색할 한국 주소 또는 건물명")):
    """주소/건물명 검색 (예: 서울대학교, 강남역, 판교역) -> 위경도 변환"""
    res = search_address_location(q)
    if not res:
        raise HTTPException(status_code=404, detail="검색 결과가 없습니다.")
    return res

@app.get("/api/zoning-list")
def get_zoning_list():
    return {
        "zoning_types": [
            {
                "name": rule.name,
                "category": rule.category,
                "legal_max_bcr": rule.legal_max_bcr,
                "ordinance_bcr": rule.ordinance_bcr,
                "legal_max_far": rule.legal_max_far,
                "ordinance_far": rule.ordinance_far,
                "solar_setback_required": rule.solar_setback_required,
                "description": rule.description
            }
            for rule in ZONING_DATABASE.values()
        ]
    }

@app.post("/api/analyze-parcel")
def analyze_parcel(req: AnalyzeParcelRequest):
    parcel_data = fetch_vworld_parcel(
        lat=req.lat,
        lng=req.lng,
        api_key=req.vworld_api_key,
        scan_index=req.scan_index or 0
    )

    if req.zoning:
        parcel_data["zoning"] = req.zoning
    if req.site_area_sqm:
        parcel_data["site_area_sqm"] = req.site_area_sqm

    custom_bcr = req.custom_bcr if req.custom_bcr is not None else parcel_data.get("bcr")
    custom_far = req.custom_far if req.custom_far is not None else parcel_data.get("far")

    legal_metrics = calculate_legal_metrics(
        site_area_sqm=parcel_data["site_area_sqm"],
        zoning_name=parcel_data["zoning"],
        custom_bcr=custom_bcr,
        custom_far=custom_far,
        floor_height_m=req.floor_height_m or (parcel_data.get("floor_height_m") or 3.2),
        existing_floors=parcel_data.get("existing_floors")
    )

    is_gis = parcel_data.get("is_gis_polygon", False)
    massing_3d = generate_massing_3d(
        site_polygon_geo=parcel_data["polygon_coords"],
        site_area_sqm=parcel_data["site_area_sqm"],
        bcr=legal_metrics["applied_bcr"],
        far=legal_metrics["applied_far"],
        floors=legal_metrics["estimated_floors"],
        floor_height_m=legal_metrics["floor_height_m"],
        apply_solar_setback=req.apply_solar_setback if req.apply_solar_setback is not None else (False if is_gis else legal_metrics["solar_setback"]["applied"]),
        bld_name=parcel_data.get("bld_name") or parcel_data.get("title", ""),
        is_gis_polygon=is_gis
    )

    # 3D 뷰어 HUD 및 리포트 수치 100% 완벽 동기화
    if "massing_building" in massing_3d:
        mb = massing_3d["massing_building"]
        legal_metrics["max_building_area_sqm"] = mb.get("max_building_area_sqm", legal_metrics["max_building_area_sqm"])
        legal_metrics["max_floor_area_sqm"] = mb.get("max_floor_area_sqm", legal_metrics["max_floor_area_sqm"])
        legal_metrics["estimated_floors"] = mb.get("floors_count", legal_metrics["estimated_floors"])
        legal_metrics["estimated_height_m"] = mb.get("total_height_m", legal_metrics["estimated_height_m"])

    ai_report = generate_ai_briefing(parcel_data, legal_metrics, massing_3d)

    return {
        "parcel": parcel_data,
        "legal_metrics": legal_metrics,
        "massing_3d": massing_3d,
        "ai_report": ai_report
    }

@app.post("/api/simulate-custom")
def simulate_custom(req: SimulationRequest):
    legal_metrics = calculate_legal_metrics(
        site_area_sqm=req.site_area_sqm,
        zoning_name=req.zoning,
        custom_bcr=req.custom_bcr,
        custom_far=req.custom_far,
        floor_height_m=req.floor_height_m,
        existing_floors=None  # 실시간 시뮬레이션 조작 시에는 용적률/건폐율 변경에 따라 층수가 동적 재계산됨
    )

    polygon_coords = req.polygon_coords or generate_custom_parcel_polygon(37.459882, 126.951905, 30.0, 25.0)
    is_gis = bool(req.is_gis_polygon or (polygon_coords and len(polygon_coords) > 5))

    massing_3d = generate_massing_3d(
        site_polygon_geo=polygon_coords,
        site_area_sqm=req.site_area_sqm,
        bcr=req.custom_bcr,
        far=req.custom_far,
        floors=legal_metrics["estimated_floors"],
        floor_height_m=req.floor_height_m,
        apply_solar_setback=req.apply_solar_setback if not is_gis else False,
        bld_name=req.bld_name or "",
        is_gis_polygon=is_gis
    )

    # 3D 뷰어 HUD 및 리포트 수치 100% 완벽 동기화
    if "massing_building" in massing_3d:
        mb = massing_3d["massing_building"]
        legal_metrics["max_building_area_sqm"] = mb.get("max_building_area_sqm", legal_metrics["max_building_area_sqm"])
        legal_metrics["max_floor_area_sqm"] = mb.get("max_floor_area_sqm", legal_metrics["max_floor_area_sqm"])
        legal_metrics["estimated_floors"] = mb.get("floors_count", legal_metrics["estimated_floors"])
        legal_metrics["estimated_height_m"] = mb.get("total_height_m", legal_metrics["estimated_height_m"])

    dummy_parcel = {
        "title": req.bld_name or "실시간 시뮬레이션 필지",
        "address": "사용자 맞춤형 파라미터 적용 부지",
        "jimok": "대지 (대)"
    }
    ai_report = generate_ai_briefing(dummy_parcel, legal_metrics, massing_3d)

    return {
        "legal_metrics": legal_metrics,
        "massing_3d": massing_3d,
        "ai_report": ai_report
    }

# 프론트엔드 정적 파일 서빙
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

"""
config_loader.py
config.json 및 .env 파일 자동 로더
"""

import os
import json
from pathlib import Path
from typing import Dict, Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_JSON_PATH = ROOT_DIR / "config.json"
ENV_PATH = ROOT_DIR / ".env"

def load_config() -> Dict[str, str]:
    config = {
        "VWORLD_API_KEY": "",
        "BUILDING_REGISTER_API_KEY": "",
        "GIS_BUILDING_API_KEY": "",
        "KAKAO_REST_API_KEY": ""
    }

    # 1. config.json 읽기
    if CONFIG_JSON_PATH.exists():
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key in config:
                    if data.get(key):
                        config[key] = str(data[key]).strip()
        except Exception as e:
            print(f"[ConfigLoader Error JSON] {e}")

    # 2. .env 읽기
    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k in config and v:
                            config[k] = v
        except Exception as e:
            print(f"[ConfigLoader Error ENV] {e}")

    # 3. 환경변수 오버라이드
    for key in config:
        if os.getenv(key):
            config[key] = os.getenv(key).strip()

    return config

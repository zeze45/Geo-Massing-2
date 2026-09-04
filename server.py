import os
import sys
import uvicorn

# 의존성 및 FastAPI 앱 직접 로드 (Import 검증)
from backend.app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[BOOT] Starting FastAPI on 0.0.0.0:{port} ...", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=True)

"""
run.py
서버 실행 스크립트 (모바일 카메라/GPS 보안 컨텍스트 HTTPS 및 HTTP 지원)
"""

import os
import sys
import uvicorn
from ssl_helper import get_or_create_ssl_cert

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    cert_file, key_file = get_or_create_ssl_cert()

    use_ssl = "--ssl" in sys.argv
    ssl_key = key_file if use_ssl else None
    ssl_cert = cert_file if use_ssl else None

    protocol = "https" if use_ssl else "http"
    print("=================================================================")
    print(" [GEO-MASSING AR] Cadastral Legal Analysis Server Running")
    print("=================================================================")
    print(f" [PC / Local Access]: {protocol}://localhost:8000")
    print(f" [Network Access]:    {protocol}://127.0.0.1:8000")
    print("=================================================================")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=ssl_key,
        ssl_certfile=ssl_cert,
        reload=False
    )


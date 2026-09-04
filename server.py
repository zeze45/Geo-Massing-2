import os
import sys
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[BOOT] Starting FastAPI on 0.0.0.0:{port} ...", flush=True)
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, log_level="info", access_log=True)

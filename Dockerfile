FROM python:3.11-slim

WORKDIR /app

# 기본 환경변수 설정 (로그 버퍼링 방지 및 포트 설정)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080

# 의존성 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사
COPY . .

# 이전 빌드나 로컬의 pycache 찌꺼기 제거
RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
RUN find . -type f -name "*.pyc" -delete 2>/dev/null || true

EXPOSE 8080

# Cloud Run 표준 무결점 실행 명령어 (단일 프로세스 고속 비동기 서빙)
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]

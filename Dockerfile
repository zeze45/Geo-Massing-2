FROM python:3.11-slim

WORKDIR /app

# 기본 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 전체 복사
COPY . .

# 포트 설정 (Cloud Run은 환경변수 PORT를 기본 제공)
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]

FROM python:3.11-slim

WORKDIR /app

# 패키지 의존성 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 소스 복사
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Cloud Run 표준 진입점
CMD ["python", "server.py"]

FROM python:3.11-slim

WORKDIR /app

# 기본 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 전체 복사
COPY . .

ENV PYTHONPATH=/app
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]

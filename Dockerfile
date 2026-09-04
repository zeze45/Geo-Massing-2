FROM python:3.11-slim

WORKDIR /app

# 기본 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 소스코드 복사
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080

EXPOSE 8080

CMD ["python", "server.py"]

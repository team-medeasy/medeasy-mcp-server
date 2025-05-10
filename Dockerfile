# ====== 1단계: 빌드 환경 ======
FROM python:3.12.8-alpine AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ====== 2단계: 런타임 환경 ======
FROM python:3.12.8-alpine

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

# 한국 시간대 설정
RUN apk add --no-cache tzdata \
 && cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime \
 && echo "Asia/Seoul" > /etc/timezone

CMD ["python", "main.py"]


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
ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

CMD ["python", "main.py"]


# PostgreSQL 18 + iproute2 (lệnh tc, dùng để giả lập trễ mạng 30 ms bằng netem ở trạm trung tâm)
FROM postgres:18
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 \
 && rm -rf /var/lib/apt/lists/*

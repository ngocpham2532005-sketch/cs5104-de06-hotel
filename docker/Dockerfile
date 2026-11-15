# PostgreSQL 18 + iproute2 (lệnh tc) để `make delay-on` thêm trễ 30 ms bằng netem
FROM postgres:18
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 \
 && rm -rf /var/lib/apt/lists/*

# CS5104 · Đề 6 · Chuỗi khách sạn nghỉ dưỡng — hệ CSDL phân tán 4 trạm trên 2 máy
#
#   Máy B (Windows):  make all MACHINE=B        -> bật phuquoc, danang
#   Máy A (macOS):    make all                  -> bật nhatrang, dalat, ref; sinh + nạp dữ liệu; link; check;
#                                                  bench; mở giao diện nhập liệu và dashboard
#   Thử trên một máy: make all DEPLOY=deploy.local.toml  rồi  make up MACHINE=B DEPLOY=deploy.local.toml
#
# Mọi công thức chỉ gọi `docker` và `python`, nên chạy được bằng GNU make trên macOS, Linux và Windows.

MACHINE ?= A
SIZE    ?=
DEPLOY  ?= deploy.toml
PYTHONUTF8 := 1
export MACHINE DEPLOY SIZE PYTHONUTF8

ifeq ($(OS),Windows_NT)
  PY  ?= python
  VPY := .venv\Scripts\python.exe
else
  PY  ?= python3
  VPY := .venv/bin/python
endif

GEN := datagen/de06_hotel/generate.py

.PHONY: all up down data load link check bench slope delay-on delay-off entry dash q \
        venv build status stop-site start-site apps-start apps-stop help \
        ext-help ext-replica ext-replica-status ext-failover ext-failback ext-watch ext-replica-down \
        ext-2pc-crash ext-2pc-status ext-2pc-recover ext-bench \
        secure tls-status tls-test tls-ca-init tls-sign tls-off \
        tls-site-csr tls-site-install tls-site-status tls-site-uninstall sync-remote

help:
	@echo "make all [MACHINE=A|B] | up | data | load | link | check | bench | slope | delay-on | delay-off | entry | dash | down"
	@echo "make stop-site SITE=phuquoc | start-site SITE=phuquoc | status | q [QUERIES='Q2 Q3'] [EXPLAIN=1]"
	@echo "TLS (E3, mặc định bật): secure | tls-status | tls-test | tls-off · chế độ chặt từng máy: tls-site-csr | tls-site-install | tls-site-status | tls-site-uninstall [SITES=..] [CLIENT=1] [ROTATE=1] · máy A: tls-sign"
	@echo "cập nhật mã nguồn sang máy khác: make sync-remote SSH=user@host DEST=... KEY=..."
	@echo "Phần mở rộng (ngoài yêu cầu đề): make ext-help"

# ---------------------------------------------------------------- toàn bộ
ifeq ($(MACHINE),B)
all: build up
	@echo "Máy B sẵn sàng. Trên máy A chạy: make all"
else
all: venv build up secure data load link check bench apps-start
	@echo "Hệ đã dựng xong. Nhập liệu: http://localhost:8501   Dashboard: http://localhost:8502"
endif

# ---------------------------------------------------------------- hạ tầng
venv:
	$(PY) -m venv .venv
	$(VPY) -m pip install -q --upgrade pip
	$(VPY) -m pip install -q -r requirements.txt

build:
	$(PY) tools/deploy.py build

up:
	$(PY) tools/deploy.py up $(MACHINE)

down: apps-stop
	$(PY) tools/deploy.py down $(MACHINE)

status:
	$(PY) tools/deploy.py status

stop-site:
	$(PY) tools/deploy.py stop $(SITE)

start-site:
	$(PY) tools/deploy.py start $(SITE)

# ---------------------------------------------------------------- E3: bảo mật đường truyền (mặc định)
# make secure: CA nội bộ + chứng chỉ cho mọi nút (khoá sinh trong container của nút; nút ở máy B qua kênh quản trị SQL),
# pg_hba chỉ nhận kết nối mạng có TLS; chạy lại được (chứng chỉ còn hạn thì giữ nguyên). FORCE=1: cấp lại hết.
secure:
	$(VPY) tools/tls.py secure $(if $(FORCE),--force,)

tls-status:
	$(VPY) tools/tls.py status

tls-test:                ## 8 phép thử: không mã hoá / gọi bằng IP / thiếu hay sai chứng chỉ / thử ghi đều bị từ chối
	$(VPY) tools/tls.py test

tls-off:                 ## gỡ lỗi: tạm tắt TLS toàn hệ; bật lại: make secure && make link
	$(VPY) tools/tls.py off

tls-ca-init:
	$(PY) tools/tls.py ca-init

tls-sign:                ## chế độ chặt: ký CSR do từng máy gửi tới (CSR='a.csr b.csr' hoặc mọi *.csr trong build/e3/exchange)
	$(PY) tools/tls.py sign $(CSR)

# Chế độ chặt: chạy TẠI máy chứa nút, không ai cần quyền superuser qua mạng (chỉ cần python, không venv)
SITES ?=
SITE_FLAGS = $(if $(CLIENT),--client,) $(if $(ROTATE),--rotate,)
tls-site-csr:
	$(PY) tools/tls_site.py csr $(SITES) $(SITE_FLAGS)

tls-site-install:
	$(PY) tools/tls_site.py install $(SITES) $(SITE_FLAGS)

tls-site-status:
	$(PY) tools/tls_site.py status $(SITES)

tls-site-uninstall:
	$(PY) tools/tls_site.py uninstall $(SITES)

# ---------------------------------------------------------------- dữ liệu
data:
	$(PY) $(GEN) --size mini
	$(PY) $(GEN) --size lab

load:
	$(VPY) tools/load.py

link:
	$(VPY) tools/link.py

check:
	$(VPY) tools/check.py

bench:
	$(VPY) tools/bench.py

# số vòng khứ hồi mỗi truy vấn: đo ở trễ 30 và 60 ms, (T60-T30)/30 -> results/rtt_slope.txt
slope:
	$(VPY) tools/rtt_slope.py

delay-on:
	$(VPY) tools/delay.py on

delay-off:
	$(VPY) tools/delay.py off

q:                       ## demo D3–D6: chạy Q1–Q5, so với đối chứng (EXPLAIN=1 để in Remote SQL)
	$(VPY) tools/demo.py $(QUERIES) $(if $(EXPLAIN),-e,)

# ---------------------------------------------------------------- giao diện (máy A)
entry:
	$(VPY) -m streamlit run app/entry.py --server.port 8501 --server.headless true --browser.gatherUsageStats false

dash:
	$(VPY) -m streamlit run app/dash.py --server.port 8502 --server.headless true --browser.gatherUsageStats false

apps-start:
	$(VPY) tools/apps.py start

apps-stop:
	-$(VPY) tools/apps.py stop

# ================================================================ PHẦN MỞ RỘNG (ngoài yêu cầu đề)
# Không nằm trong `make all`; không đổi kết quả D1–D8, N1–N5. Chi tiết, kịch bản demo: docs/NANG_CAO.md
#   E1  bản sao dự phòng (streaming replication) cho trạm phuquoc + chuyển đọc khi trạm chết
#   E2  2PC có nhật ký điều phối bền vững + phục hồi giao dịch lưỡng lự
RSITE ?=

ext-help:
	@echo "E1 · make ext-replica | ext-replica-status | ext-failover | ext-failback | ext-watch | ext-replica-down  [RSITE=phuquoc]"
	@echo "E2 · make ext-2pc-crash CRASH=prepare|decision|mid-commit | ext-2pc-status | ext-2pc-recover [FORCE=1]"
	@echo "So sánh phương án E1/E2: make ext-bench  (-> results/ext/ext_bench.csv)"
	@echo "Xem docs/NANG_CAO.md"

ext-replica:             ## E1: tạo bản sao dự phòng ở máy A (pg_basebackup qua LAN từ trạm chính ở máy B)
	$(VPY) tools/ext_replica.py up $(RSITE)

ext-replica-status:
	$(VPY) tools/ext_replica.py status $(RSITE)

ext-failover:            ## E1: postgres_fdw của trạm trung tâm đọc mảnh từ bản sao (chỉ đọc)
	$(VPY) tools/ext_replica.py failover $(RSITE)

ext-failback:
	$(VPY) tools/ext_replica.py failback $(RSITE)

ext-watch:               ## E1: tự failover/failback theo nhịp 1 s (Ctrl+C để dừng)
	$(VPY) tools/ext_replica.py watch $(RSITE)

ext-replica-down:
	$(VPY) tools/ext_replica.py down $(RSITE)

CRASH ?= decision
ext-2pc-crash:           ## E2: tạo đoàn tour, bộ điều phối "chết" sau bước $(CRASH)
	-$(VPY) tools/twopc.py create --crash $(CRASH)

ext-2pc-status:
	$(VPY) tools/twopc.py status

ext-2pc-recover:
	$(VPY) tools/twopc.py recover $(if $(FORCE),--force,)

ext-bench:               ## so sánh: sync/async replication, đọc chính/bản sao, chi phí 2PC + nhật ký
	$(VPY) tools/ext_bench.py

# ---- cập nhật mã nguồn sang máy khác (vd. máy B) qua SSH, rồi so mã băm script ở hai đầu
SSH  ?=
DEST ?=
KEY  ?=
RPY  ?= python
sync-remote:
	$(PY) tools/sync_remote.py $(SSH) $(DEST) $(if $(KEY),--key $(KEY),) --python $(RPY)

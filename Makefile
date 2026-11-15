# CS5104 · Đề 6 — Chuỗi khách sạn nghỉ dưỡng (4 trạm, 2 máy)
# Máy B:  make up MACHINE=B
# Máy A:  make all          (bật trạm máy A, chờ máy B, sinh dữ liệu, nạp, nối, kiểm tra, đo, mở giao diện)
PY      ?= python3
MACHINE ?= A
SIZE    ?= lab
SITE    ?= phuquoc
COMPOSE  = docker compose -f build/compose.$(MACHINE).yml
export SIZE

.PHONY: help up data load link check bench bench-all delay-on delay-off entry dash apps stop-apps all down stop-site start-site psql

help:
	@echo "make up MACHINE=A|B · data · load · link · check · bench · delay-on · delay-off · entry · dash · all · down"
	@echo "phụ: bench-all (đo không trễ rồi có trễ) · stop-site/start-site SITE=phuquoc · apps (entry+dash chạy nền) · psql SITE=..."

up:                       ## bật đúng các trạm của máy này (theo deploy.toml)
	$(PY) tools/compose.py $(MACHINE)
	$(COMPOSE) up -d --build --wait

data:                     ## chạy bộ sinh (seed cố định) rồi chia CSV thành mảnh
	cd datagen/de06_hotel && $(PY) generate.py --size $(SIZE)
	$(PY) tools/split.py

load:                     ## CSDL đối chứng + nạp đúng mảnh vào từng trạm (chạy ở máy A)
	$(PY) tools/wait.py 600
	$(PY) tools/load.py

link:                     ## postgres_fdw + khung nhìn all_* tại trạm trung tâm
	$(PY) tools/link.py

check:                    ## ba quy tắc đúng đắn + khoá chính/khoá ngoại toàn hệ
	$(PY) tools/check.py

bench:                    ## đo Q1–Q5 (5 lần, bỏ lần đầu, trung vị), N1–N5, lưu results/
	$(PY) tools/bench.py

bench-all:
	$(PY) tools/delay.py off
	$(PY) tools/bench.py
	$(PY) tools/delay.py on
	$(PY) tools/bench.py
	$(PY) tools/delay.py off

delay-on:                 ## trễ 30 ms trên đường trạm trung tâm -> máy B (DELAY_MODE=tc|proxy)
	$(PY) tools/delay.py on

delay-off:
	$(PY) tools/delay.py off

entry:                    ## giao diện nhập liệu http://localhost:8080
	$(PY) app/entry.py

dash:                     ## dashboard http://localhost:8081
	$(PY) app/dash.py

apps: stop-apps           ## chạy entry + dash ở chế độ nền (log trong logs/)
	@mkdir -p logs
	nohup $(PY) app/entry.py > logs/entry.log 2>&1 & echo $$! > logs/entry.pid
	nohup $(PY) app/dash.py  > logs/dash.log  2>&1 & echo $$! > logs/dash.pid
	@echo "Nhập liệu: http://localhost:8080   Dashboard: http://localhost:8081"

stop-apps:
	-@for f in logs/entry.pid logs/dash.pid; do [ -f $$f ] && kill $$(cat $$f) 2>/dev/null; rm -f $$f; done; true

all:                      ## từ máy sạch, không thao tác tay (chạy ở máy A; máy B đã `make up MACHINE=B`)
	$(MAKE) up MACHINE=A
	$(MAKE) data
	$(MAKE) load
	$(MAKE) link
	$(MAKE) check
	$(MAKE) bench-all
	$(MAKE) apps

down: stop-apps           ## tắt và xoá các trạm của máy này
	-$(PY) tools/delay.py off 2>/dev/null
	$(PY) tools/compose.py $(MACHINE)
	$(COMPOSE) down -v

stop-site:                ## D8: tắt một trạm (chạy ở máy chứa trạm đó)
	docker stop hotel_$(SITE)

start-site:
	docker start hotel_$(SITE)

psql:                     ## mở psql vào một trạm: make psql SITE=nhatrang
	docker exec -it hotel_$(SITE) psql -U postgres -d hotel

# CS5104 · Đề 6 — Chuỗi khách sạn nghỉ dưỡng (4 trạm PostgreSQL, 2 máy)

Hệ CSDL phân tán: dữ liệu khách sạn/phòng/đặt phòng chia theo **vùng của khách sạn** ra 4 trạm
`dalat` · `nhatrang` (trung tâm) · `phuquoc` · `danang`, truy vấn xuyên trạm bằng `postgres_fdw`,
có giao diện nhập liệu và dashboard theo dõi từng trạm.

Seed 402738 · bộ sinh `datagen/de06_hotel/generate.py` (bản gốc của giảng viên, **không sửa**).

## 1. Thiết kế phân tán (tóm tắt — chi tiết trong báo cáo)

| Bảng | Cách chia | Lý do |
|---|---|---|
| `hotel` | **Ngang chính**: `hotel_i = σ(region = i)` | dữ liệu "lưu tại vùng của khách sạn"; `region` có sẵn |
| `room` | **Ngang dẫn xuất** `room ⋉ hotel_i` | phòng luôn đi cùng khách sạn |
| `booking` | **Ngang dẫn xuất** `booking ⋉ room_i` | lượt đặt lưu tại vùng khách sạn của phòng ⇒ Q1 cục bộ |
| `req_tour`, `req_business`, `req_family` | dẫn xuất `⋉ booking_i` | 1–0..1 với booking; jsonb và bản quan hệ cùng trạm ⇒ ghi chung một giao dịch |
| `req_family_child` | dẫn xuất `⋉ req_family_i` | |
| `room_type` (15 dòng), `tour_group` (800 dòng) | **Sao chép ra mọi trạm** | nhỏ, ít đổi, được mọi trạm tham chiếu ⇒ mọi khoá ngoại đều cục bộ |

Cấp phát: **máy A** = `nhatrang` (trung tâm, có CSDL đối chứng `hotel_ref`) + `dalat`;
**máy B** = `phuquoc` + `danang`. `dalat` đặt ở máy A để Q1 (chỉ trạm dalat) không chịu trễ mạng và
vẫn chạy khi máy B tắt (D6, D8).

- **Khoá chính**: dữ liệu gốc 1..999 999; dòng mới mỗi trạm tự cấp `1 000 000 + 10·n + site_no`
  (sequence `START 100000k INCREMENT 10`, CHECK `id < 1000000 OR id % 10 = site_no`). `tour_group`
  chỉ trạm trung tâm cấp (đuôi 0) và ghi ra cả 4 trạm bằng commit hai pha.
- **Khoá ngoại**: mọi cặp cha–con ở cùng trạm (bảng cha hoặc cùng mảnh dẫn xuất, hoặc được sao chép)
  ⇒ giữ nguyên `REFERENCES`. Khoá ngoại cục bộ đồng thời là ràng buộc mảnh dẫn xuất: không thể ghi
  phòng/lượt đặt vào trạm không có khách sạn/phòng cha.
- **CHECK**: `frag_hotel_region CHECK (region = '<trạm>')`; `booking_request_shape` kiểm tra dạng jsonb
  theo `guest_type` (đủ khoá, đúng kiểu, `tour_group_id` chỉ có khi tour, `group_code` khớp mã đoàn).
- **Liên vùng**: booking của đoàn tour có phòng ở ≥ 2 vùng (5 144 dòng = 6,43 %). Q3 phải đọc nhiều trạm.

## 2. Yêu cầu

- Hai máy cùng mạng LAN (hoặc điểm phát Wi-Fi điện thoại), mỗi máy có **Docker** (Compose v2) và
  **Python ≥ 3.11**. Không cần `pip install`: kết nối PostgreSQL dùng `tools/pgwire.py` (thuần Python).
- Linux/macOS, hoặc Windows qua WSL2 (cần `make`).
- Mở cổng 5433–5436 trên tường lửa máy B (và máy A nếu dùng chế độ trễ proxy).

## 3a. Chạy thử trên MỘT máy (Windows/macOS/Linux, không cần make)

```
cd cs5104-de06-hotel
python tools/onebox.py            # Windows: python tools\onebox.py
```

Tự dò IP LAN (máy A = máy B = máy này, ghi `build/deploy.onebox.toml`, không sửa `deploy.toml`), bật 4 container,
sinh + nạp dữ liệu, `check`, `bench` không trễ và trễ 30 ms (proxy), rồi mở nhập liệu `:8080` và dashboard `:8081`.
Thêm: `python tools/onebox.py apps` (mở lại giao diện) · `stop phuquoc` / `start phuquoc` (D8) · `down` (xoá hết).

## 3. Dựng hệ trên 2 máy

1. Sửa `deploy.toml`: IP máy A, IP máy B (xem `ip addr` / `ipconfig`).
2. **Máy B**: `make up MACHINE=B` (bật `phuquoc`, `danang`).
3. **Máy A**: `make all` — bật trạm máy A, chờ máy B, sinh dữ liệu, nạp, nối `postgres_fdw`, kiểm tra,
   đo (không trễ và trễ 30 ms), rồi chạy nền giao diện nhập liệu `:8080` và dashboard `:8081`.

Các lệnh riêng lẻ:

| Lệnh | Việc |
|---|---|
| `make up MACHINE=A\|B` | sinh `build/compose.<máy>.yml` từ `deploy.toml`, bật đúng trạm của máy |
| `make data` | chạy bộ sinh (`SIZE=lab` mặc định, `SIZE=mini` để xem bằng mắt) + chia mảnh `output/<size>/sites/` |
| `make load` | tạo `hotel_ref` (đối chứng) và nạp mảnh vào từng trạm, đối chiếu số dòng với `summary.json` |
| `make link` | `postgres_fdw`: `srv_<trạm>`, schema `s_<trạm>`, khung nhìn `all_<bảng>`, schema `ref` |
| `make check` | ba quy tắc đúng đắn, khoá chính, khoá ngoại, nhất quán jsonb ↔ bản quan hệ (`results/check.txt`) |
| `make bench` | Q1–Q5, 5 lần, bỏ lần đầu, trung vị → `results/results.csv`, `results/explain/`, `n1/n4/n5.csv` |
| `make delay-on` / `delay-off` | trễ 30 ms bằng `tc netem` trong container trạm trung tâm, chỉ với gói đi tới IP máy B |
| `make entry` / `make dash` | giao diện nhập liệu / dashboard (chạy tiền cảnh) |
| `make down` | tắt và xoá trạm của máy hiện tại |
| `make stop-site SITE=phuquoc` / `start-site` | tắt/bật một trạm (D8, chạy ở máy B) |

Không dùng được `tc` (ví dụ chạy thử trên một máy): `DELAY_MODE=proxy make delay-on` — trễ bằng
`tools/latency_proxy.py` chạy ở máy A, trỏ `srv_phuquoc`, `srv_danang` qua proxy.

## 4. Kịch bản demo D1–D8

| | Làm | Thấy |
|---|---|---|
| D1 | máy B `make up MACHINE=B`; máy A `make all` | `load` in số dòng từng mảnh "khớp"; dashboard 4 ô xanh |
| D2 | `make check` | mọi dòng ✓, `KẾT QUẢ: ĐẠT` |
| D3 | `make psql SITE=dalat` → `\i sql/queries/q1_site.sql`, `EXPLAIN` không có Foreign Scan; Q2 ở trung tâm | `bench`: cột `đúng` ✓ |
| D4 | Q3 (`\set tg 410` rồi `\i sql/queries/q3.sql`) | đoàn 410 có phòng ở dalat, phuquoc, danang; EXPLAIN 3 Foreign Scan + quét cục bộ |
| D5 | Q4 (jsonb) và Q5 (bản quan hệ) | cùng 3 413 dòng |
| D6 | `make delay-on && make bench && make delay-off` | Q1 gần như không đổi; Q2, Q3 tăng ≈ 10 × 30 ms |
| D7 | Giao diện `:8080`: 1 lượt đặt ở Phú Quốc (máy B); 1 lượt tour đoàn 410 ở Nha Trang (liên vùng); 100 ngẫu nhiên | dashboard đổi ≤ 2 s đúng ô; Q3 thấy dòng mới; `make check` vẫn ĐẠT |
| D8 | máy B `make stop-site SITE=phuquoc` … `make start-site SITE=phuquoc` | ô Phú Quốc đỏ → xanh; nhập liệu vào Phú Quốc báo lỗi; Q1 chạy, Q2 lỗi rồi chạy lại |

## 5. Cấu trúc

```
deploy.toml                trạm → máy, IP, cổng; mật khẩu; cổng giao diện
Makefile
datagen/de06_hotel/        bộ sinh của giảng viên (không sửa)
docker/Dockerfile          postgres:18 + iproute2 (tc)
sql/schema_central.sql     lược đồ tập trung (đúng Hình 6.1) + CHECK jsonb
sql/site_extra.sql         phần thêm ở mỗi trạm: CHECK mảnh, sequence + CHECK dải khoá, khung nhìn mảnh
sql/queries/               Q1–Q5 tại trung tâm, q1_site.sql (chạy ở dalat), ref/ (trên đối chứng), *_global.sql
tools/                     pgwire.py, cfg.py, split.py, load.py, link.py, check.py, bench.py, delay.py, ...
app/entry.py, app/dash.py  giao diện nhập liệu, dashboard (http.server, không thư viện ngoài)
results/                   kết quả đo; sample_1machine/ là lần chạy thử trên một máy (trễ bằng proxy)
```

## 6. Sử dụng công cụ AI

Mã nguồn và bản nháp báo cáo được viết với sự hỗ trợ của Claude (Anthropic). Nhóm đã đọc, chạy lại,
kiểm tra kết quả và chịu trách nhiệm về toàn bộ nội dung; mọi thành viên phải hiểu toàn bộ hệ.

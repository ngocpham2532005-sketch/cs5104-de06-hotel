# IMPLEMENT — Đề 6 · Chuỗi khách sạn nghỉ dưỡng (4 trạm, 2 máy macOS + Windows)

Tài liệu cài đặt: hệ được dựng thế nào, tệp nào làm gì, vì sao chọn như vậy, và kịch bản demo D1–D8.
Cách chạy nhanh xem [README.md](README.md); lập luận thiết kế và số liệu xem [docs/BAO_CAO.md](docs/BAO_CAO.md).
Phần mở rộng ngoài yêu cầu đề (E1, E2) xem [§11](#11-phần-mở-rộng-ngoài-yêu-cầu-đề) và [docs/NANG_CAO.md](docs/NANG_CAO.md).

---

## 1. Kiến trúc triển khai

```
                        LAN (Wi-Fi/Ethernet; dự phòng: điểm phát của điện thoại)
 ┌──────────────── MÁY A · macOS · 192.168.x.A ─────────────────┐        ┌──── MÁY B · Windows · 192.168.x.B ────┐
 │  Docker network cs5104_net                                   │        │  Docker Desktop (WSL2)                │
 │  ┌──────────────────────┐   fdw (mạng Docker)  ┌──────────┐  │        │  ┌──────────┐      ┌──────────┐       │
 │  │ cs5104_nhatrang :5433│ ───────────────────► │ dalat    │  │        │  │ phuquoc  │      │ danang   │       │
 │  │ TRẠM TRUNG TÂM       │                      │ :5434    │  │        │  │ :5435    │      │ :5436    │       │
 │  │ mảnh nhatrang        │   fdw (LAN, IP máy B)└──────────┘  │        │  └────▲─────┘      └────▲─────┘       │
 │  │ s_dalat/s_phuquoc/   │ ─────────────────────────────────────────────────────┴─────────────────┘             │
 │  │ s_danang (foreign)   │   tc netem +30 ms (chỉ gói tới trạm xa)│        └───────────────────────────────────────┘
 │  │ all_<bảng> (view)    │   fdw ──► ┌──────────┐               │
 │  └──────────▲───────────┘           │ ref :5440│ CSDL đối chứng│
 │             │ psycopg (thẳng tới    └──────────┘               │
 │  ┌──────────┴──────────┐  từng trạm, không qua fdw)           │
 │  │ entry :8501  dash :8502 (Streamlit)                        │
 │  └─────────────────────┘                                      │
 └───────────────────────────────────────────────────────────────┘
```

- Mỗi trạm là một container `cs5104-pg18` (= `postgres:18` + `iproute2`), dữ liệu ở volume `cs5104_<trạm>_data`.
- Trạm trung tâm gọi `dalat` qua tên container (cùng máy), gọi `phuquoc`/`danang` qua `IP_máy_B:cổng`.
- Giao diện và dashboard ở máy A kết nối **thẳng** từng trạm (127.0.0.1 cho trạm ở máy A, IP máy B cho trạm ở máy B).
- Máy B không cần Python venv và không bao giờ phải kết nối ngược về máy A: chỉ cần Docker, Python và make để bật container.

## 2. Thiết kế phân tán (tóm tắt — lập luận đầy đủ ở báo cáo §1)

| Bảng | Cách chia | Đặt ở đâu | Vị từ / phép nửa nối |
|---|---|---|---|
| `room_type` | sao chép | cả 4 trạm | toàn bộ |
| `tour_group` | sao chép | cả 4 trạm | toàn bộ; thêm mới bằng 2PC |
| `hotel` | ngang chính | trạm của vùng | `region = '<trạm>'` (CHECK) |
| `room` | ngang dẫn xuất | cùng trạm với `hotel` | `room ⋉ hotel_s` (FK cục bộ) |
| `booking` | ngang dẫn xuất | cùng trạm với `room` | `booking ⋉ room_s` (FK cục bộ) |
| `req_tour`, `req_business`, `req_family` | dẫn xuất | cùng trạm với `booking` | `req ⋉ booking_s` |
| `req_family_child` | dẫn xuất nối tiếp | cùng trạm với `req_family` | `child ⋉ req_family_s` |

Số dòng (cỡ lab): `hotel` 13/16/14/17 · `room` 1.193/1.662/1.387/1.758 · `booking` 16.275/20.091/19.755/23.879
(dalat/nhatrang/phuquoc/danang). Có 5.144 dòng liên vùng (6,43%), thuộc 115 đoàn.

**Khoá chính mới:** `booking_id DEFAULT nextval('booking_id_seq')`. Sequence của trạm số `no` chạy trong dải
`[no·10^7+1, (no+1)·10^7−1]`, có `CHECK (booking_id < 10^7 OR booking_id BETWEEN …)`. Đoàn tour mới lấy id từ
`tour_group_id_seq` ở trạm trung tâm (bắt đầu từ 100001).
**Khoá ngoại:** cha và con luôn cùng trạm, nên mọi FK được khai báo thật ở từng trạm; `make check` kiểm thêm trên toàn hệ.
**CHECK jsonb:** loại khách ∈ {tour, business, family}; `tour_group_id` có giá trị ⇔ khách đoàn; mỗi loại có đủ khoá,
đúng kiểu; `group_code = 'TG' || lpad(tour_group_id, 4, '0')`.

## 3. Tệp và vai trò

| Tệp | Vai trò |
|---|---|
| `deploy.toml` | nguồn sự thật duy nhất về trạm → máy, IP, cổng; mọi công cụ đọc từ đây |
| `tools/common.py` | đọc cấu hình; địa chỉ nhìn từ máy chủ (`host_addr`) và từ container trung tâm (`docker_addr`) |
| `tools/deploy.py` | `docker run` đúng các trạm của một máy, chờ sẵn sàng; stop/start một trạm. Chỉ dùng thư viện chuẩn |
| `tools/split.py` | chia CSV tập trung thành mảnh: hotel theo `region`, rồi room → booking → req_* theo chuỗi khoá ngoại |
| `tools/load.py` | chờ mọi trạm → nạp `ref` → nạp mảnh (COPY) → đối chiếu số dòng với `summary.json` → `results/n1_fragments.csv` |
| `tools/tls.py` | E3: CA nội bộ (container dùng một lần, không mạng), `make secure` cấp chứng chỉ cho mọi nút, `tls-status`, `tls-test`, `tls-off`, `/etc/hosts` của trạm trung tâm |
| `tools/tls_site.py` | E3: thao tác trên một nút (CSR, cài có kiểm tra/sao lưu/hoàn tác, trạng thái, gỡ); `docker exec` tại máy chứa nút hoặc kênh quản trị SQL từ máy A |
| `tools/link.py` | ở trạm trung tâm: `CREATE SERVER … postgres_fdw` qua TLS (fetch_size 10000, async_capable, parallel_commit), `IMPORT FOREIGN SCHEMA`, view `all_*`; ANALYZE bảng ngoài |
| `tools/check.py` | 6 nhóm kiểm tra (A–F), mọi truy vấn mong đợi 0 → `results/check.txt` |
| `tools/bench.py` | Q1–Q5 và các biến thể × {0, 30 ms}; 5 lần, bỏ lần đầu, trung vị; EXPLAIN; N4, N5 |
| `tools/delay.py` | `tc qdisc prio` + `netem delay 30ms` + bộ lọc u32 theo IP đích là trạm xa; `DELAY_MODE=proxy` dùng `latency_proxy.py` |
| `tools/latency_proxy.py` | proxy TCP (asyncio, thư viện chuẩn) giữ mỗi gói chiều về 30 ms; phương án dự phòng khi không dùng được `tc` |
| `tools/onebox.py` | chạy cả hệ trên một máy với `deploy.local.toml` mà không cần `make`; có `q`, `stop/start <trạm>`, `down`, `--dry-run` |
| `tools/demo.py` | `make q`: chạy Q1–Q5 cho demo, đối chiếu `ref`, in Remote SQL |
| `tools/apps.py` | chạy nền / tắt hai ứng dụng Streamlit |
| `app/lib.py` | `build_request()` sinh **cùng lúc** jsonb và các dòng bản quan hệ từ một dict; `write_booking()` ghi trong một giao dịch |
| `app/entry.py` | nhập liệu: chọn vùng → trạm đích; form đổi theo loại jsonb; báo trạm/máy đã ghi; lỗi khi trạm mất; nút N dòng; 2PC đoàn tour |
| `tools/ext_replica.py` | **mở rộng E1**: bản sao dự phòng (streaming replication) + failover/failback đọc qua `ALTER SERVER` |
| `tools/ext_bench.py` | **mở rộng**: `make ext-bench`, so sánh phương án E1/E2 → `results/ext/ext_bench.csv` |
| `tools/twopc.py` | **mở rộng E2**: 2PC có nhật ký điều phối (fsync) + `status`/`recover`; `entry.py` dùng chung |
| `app/dash.py` | dashboard: `st.fragment(run_every=1)`, 4 ô trạm (song song, timeout 1 s), bảng so với `ref`, nhật ký sự kiện |

## 4. Luồng `make all`

| Bước | Máy A | Máy B |
|---|---|---|
| 1 | `venv` (psycopg, streamlit, pandas) | — |
| 2 | `build`: image `cs5104-pg18` | `build` |
| 3 | `up A`: nhatrang, dalat, ref | `up B`: phuquoc, danang |
| 4 | `secure` (E3): chờ máy B → CA nội bộ → chứng chỉ máy chủ cho 5 nút + chứng chỉ máy khách `fdw_reader`; khoá sinh trong container của từng nút (máy B: qua kênh quản trị SQL); `pg_hba` chỉ nhận TLS | — (máy B không phải làm gì) |
| 5 | `data`: generate.py mini + lab (seed 402738) | — |
| 6 | `load`: split → nạp ref → nạp 4 trạm (sang máy B qua LAN, **TLS verify-full**) → đối chiếu summary.json | — |
| 7 | `link`: DNS nội bộ ở trạm trung tâm + fdw qua TLS + all_* | — |
| 8 | `check` (dừng nếu lỗi) | — |
| 9 | `bench` → `results/` | — |
| 10 | `apps-start`: 8501, 8502 (kết nối các trạm qua TLS) | — |

Đã chạy thử từ máy sạch (gỡ hết container, volume, venv, dữ liệu) bằng `deploy.local.toml`: hết khoảng **3 phút 6 giây**,
`make check` ĐẠT (103 phép kiểm tra), mọi biến thể Q1–Q5 đều cho kết quả giống CSDL đối chứng.

## 5. Chi tiết kỹ thuật quan trọng

### 5.1 Vì sao có khung nhìn `booking_detail` và `family_request_detail` ở mỗi trạm
Khi chưa có hai khung nhìn này, Q2 viết theo kiểu gộp hai giai đoạn trên ba bảng ngoài (`booking`, `room`, `hotel`) của cùng một trạm.
Trong trường hợp đó, bộ tối ưu (không bật `use_remote_estimate`) chỉ đẩy `room⋈hotel` xuống trạm, còn kéo 11–16 nghìn dòng `booking`
của mỗi trạm về để tự nối. Hệ quả: các nhánh con của Append là HashAggregate cục bộ nên **không chạy song song được**.
Q2 mất 1,2 s khi trễ 30 ms.
- Bật `use_remote_estimate`: đẩy được trọn JOIN + GROUP BY, nhưng lúc lập kế hoạch phải gửi nhiều lệnh `EXPLAIN` sang trạm xa,
  nên lập kế hoạch mất **1,97 s** khi trễ 30 ms.
- Dùng khung nhìn cục bộ (đề cho phép thêm khung nhìn): mỗi phần của Q2 chỉ là **một** bảng ngoài.
  postgres_fdw đẩy `WHERE + GROUP BY` xuống (`Relations: Aggregate on (s_dalat.booking_detail)`) và hỏi 3 trạm song song.
  Q2 còn **386 ms** (đo một máy; 436 ms trên 2 máy qua Wi-Fi) khi trễ 30 ms, lập kế hoạch 0,6 ms.

Cả ba phương án đều được giữ làm biến thể trong `make bench` (`base_join`, `base_join_remote_est`, `two_phase`).

### 5.2 Cấu hình postgres_fdw
`fetch_size 10000` (ít lần FETCH hơn), `async_capable true` (hỏi các trạm xa song song),
`parallel_commit true` (COMMIT tới các trạm song song, bớt 2 vòng khứ hồi), `connect_timeout 3` (trạm chết thì báo lỗi nhanh).
E3 (mặc định): `host '<nút>.db.nhom8.internal'`, `sslmode 'verify-full'`, `sslrootcert`, `sslnegotiation 'direct'`; trạm xa dùng user mapping
`fdw_reader` + `sslcert/sslkey` (không mật khẩu, chỉ SELECT), `ref` dùng `postgres` + mật khẩu qua TLS. Chi tiết: [docs/BAO_MAT.md](docs/BAO_MAT.md).

### 5.3 Giả lập trễ
`netem` đặt trên eth0 của container trung tâm, chỉ áp cho gói có **đích là trạm xa** (bộ lọc u32 theo IP).
Vì vậy Q1 (chạy trọn ở dalat), kết nối client → trung tâm và kết nối tới `ref` không bị ảnh hưởng.
Mỗi vòng khứ hồi trung tâm ↔ trạm xa chậm thêm đúng 30 ms.
Dự phòng: `DELAY_MODE=proxy make delay-on` chạy `tools/latency_proxy.py` trên máy A ở cổng (cổng trạm + 100), rồi `ALTER SERVER srv_<trạm>`
trỏ tới `host.docker.internal:<cổng proxy>`. `make delay-off` tắt proxy và trả `srv_*` về địa chỉ cũ. Đo trên 2 máy: Q2 430 ms, Q3 402 ms
(dùng `tc` là 436 / 428 ms). Không bật chung với `make ext-failover`, vì cả hai cùng sửa `srv_phuquoc`.

### 5.4 Cách đo
`psql` chạy **ngay trong container** của trạm thực hiện truy vấn (qua unix socket), 5 lần trong cùng một phiên, `\timing`.
Lần đầu gồm cả chi phí mở kết nối fdw nên bị bỏ; lấy trung vị của 4 lần còn lại. Kết quả ghi vào `results/results.csv`.
Mỗi biến thể còn được so khớp từng dòng với bản `_ref.sql` chạy trên CSDL đối chứng.

### 5.5 Nhập liệu và CSDL đối chứng
Dòng ghi thành công vào trạm được chép thêm sang `ref` (giữ nguyên `booking_id`). Nhờ vậy sau D7, Q1–Q5 vẫn so được với
đối chứng và `make check` vẫn đạt. Nhóm F của `make check` chỉ đếm dòng có id của bộ sinh, nên vẫn khớp `summary.json`.

## 6. Kịch bản demo D1–D8 (12 phút)

Trước buổi bảo vệ: hai máy đã `git pull`, đã chạy `make all` ít nhất một lần (image đã build, không cần internet).

| # | Lệnh / thao tác | Cần cho thấy | Câu giải thích |
|---|---|---|---|
| D1 | B: `make all MACHINE=B`; A: `make all` (hoặc `make up` + `make load link` nếu đã có image) | log `load` có số dòng mỗi mảnh khớp `summary.json`; dashboard có 4 ô xanh, ghi máy A/B và IP | tỉ lệ mảnh = trọng số vùng 0,20/0,26/0,24/0,30 |
| D2 | `make check` | 103 dòng OK, KẾT LUẬN: ĐẠT | đầy đủ / tái tạo (EXCEPT ALL hai chiều) / rời nhau; FK cục bộ; jsonb ⇄ quan hệ |
| D3 | `make q QUERIES="Q1 Q2" EXPLAIN=1` | Q1 có 0 Foreign Scan; Q1 và Q2 "giống CSDL đối chứng: CÓ" | Q1 chỉ đọc mảnh dalat; Q2 gộp hai giai đoạn, `Aggregate on` được đẩy xuống |
| D4 | `make q QUERIES=Q3 EXPLAIN=1` | 3 Async Foreign Scan, phòng của đoàn 1 ở nhatrang/phuquoc/danang | booking chia theo vùng khách sạn → đoàn nhiều vùng nằm ở nhiều trạm; không biết trước vùng nên hỏi cả 4 trạm |
| D5 | `make q QUERIES="Q4 Q5"` | cùng 3.413 dòng, cả hai khớp đối chứng | Q4 đẩy `@>`, `@?` xuống; Q5 đọc khung nhìn quan hệ |
| D6 | `make delay-on` → `make q QUERIES="Q1 Q2 Q3"` → `make delay-off` | Q1 ≈ 0,5 ms (không đổi); Q2, Q3 tăng lên ≈ 420–440 ms (2 máy, Wi-Fi) | khoảng 11 vòng khứ hồi × 30 ms; xem N3 |
| D7 | Nhập liệu: (1) vùng Phú Quốc → ghi; (2) vùng Đà Lạt, khách đoàn TG0001 → hiện "LIÊN VÙNG" → ghi; (3) tab N dòng = 100 | dashboard đổi đúng ô trong ≤ 1–2 s, nhật ký "➕ … ở trạm phuquoc (máy B)"; `make q QUERIES=Q3` có thêm dòng dalat; `make check` vẫn ĐẠT | trạm đích = vùng khách sạn; jsonb + req_* trong một giao dịch |
| D8 | B: `make stop-site SITE=phuquoc` → xem dashboard (đỏ, nhật ký "MẤT KẾT NỐI") → nhập liệu vùng Phú Quốc (báo lỗi) → A: `make q QUERIES="Q1 Q2"` (Q1 chạy, Q2 lỗi `could not connect to server "srv_phuquoc"`) → B: `make start-site SITE=phuquoc` → dashboard xanh, Q2 chạy lại | như cột trước | Q1 không phụ thuộc trạm xa; Q2 cần đủ 4 trạm; giao diện không ghi nhầm trạm |

## 7. Checklist trước buổi bảo vệ
- [ ] `deploy.toml` có đúng IP hai máy (và một bản dự phòng cho mạng điểm phát), đã chạy `make link` sau khi đổi IP.
- [ ] Windows: Docker Desktop đang chạy; firewall mở 5435, 5436; mạng đặt là Private; tắt chế độ ngủ.
- [ ] macOS: tắt chế độ ngủ (`caffeinate -d`); Docker Desktop cấp ≥ 4 GB RAM.
- [ ] Từ máy A: `nc -vz <IP_B> 5435` thông.
- [ ] Đã chạy `make bench` trên **hai máy thật** và cập nhật bảng số liệu trong báo cáo/slide.
- [ ] Mỗi thành viên tự chạy được D1–D8 và trả lời được §8.

## 8. Câu hỏi vấn đáp dự kiến
1. *Vì sao chia booking theo vùng khách sạn chứ không theo đoàn?* Theo đề, dữ liệu đặt phòng lưu tại vùng khách sạn.
   Q1 và các nghiệp vụ hằng ngày (nhận/trả phòng) đều tại chỗ. Chỉ 6,4% dòng thuộc đoàn nhiều vùng, nên chấp nhận để Q3 đi qua mạng.
2. *Ba quy tắc đúng đắn được bảo đảm thế nào?* Đầy đủ: mỗi dòng có đúng một khách sạn → đúng một vùng (FK + CHECK).
   Rời nhau: mỗi khách sạn chỉ có một region. Tái tạo: `all_*` là UNION ALL, kiểm bằng `EXCEPT ALL` hai chiều.
3. *Vì sao Q2 không tăng gấp 3 khi có 3 trạm xa?* Vì `async_capable`: FETCH tới 3 trạm chạy song song, và `parallel_commit`.
   Phần còn tuần tự là START/DECLARE/CLOSE cho từng trạm.
4. *Nếu trạm phuquoc chết lúc đang thêm đoàn tour?* Nếu chết trước PREPARE thì huỷ ở mọi trạm. Nếu chết sau khi mọi trạm đã PREPARE
   mà chưa COMMIT thì giao dịch treo ở trạng thái prepared (`pg_prepared_xacts`) và phải COMMIT/ROLLBACK PREPARED bằng tay —
   đây chính là điểm yếu "chặn" của 2PC (Chương 4). Phần mở rộng E2 ghi nhật ký quyết định và có `make ext-2pc-recover` để giải quyết tự động (§11).
5. *GIN có giúp Q4 không?* `jsonb_path_ops` chỉ hỗ trợ `@>` và phần so sánh bằng của `@?`. Điều kiện `children_ages[*] < 6` không
   dùng được chỉ mục; GIN lọc trước theo `airport_pickup`, rồi phải kiểm lại từng dòng (Recheck).
6. *Dòng liên vùng tăng lên 30% thì sao?* Số vòng khứ hồi của Q3 không đổi (đã hỏi đủ 4 trạm); chỉ tăng số dòng trả về.
   Q1, Q2, Q4, Q5 không đổi. Xem N4.

## 9. Xử lý sự cố
| Hiện tượng | Cách xử lý |
|---|---|
| `load` chờ mãi "đang chờ phuquoc" | máy B chưa chạy `make all MACHINE=B`, sai IP, hoặc firewall; thử `nc -vz IP 5435` |
| `could not connect to server "srv_phuquoc"` sau khi đổi mạng | sửa IP trong `deploy.toml` → `make link` |
| `make link`: `Connection refused` tới máy B ngay sau khi B vừa lên | Docker Desktop ở Windows cần vài giây để mở cổng cho container ngoài máy; chạy lại `make link check bench apps-start` |
| Windows qua SSH: `error getting credentials ... logon session does not exist` khi `docker build` | `docker pull postgres:18` trước, rồi chạy với `DOCKER_BUILDKIT=0` và `DOCKER_CONFIG` trỏ tới config.json không có `credsStore` (hoặc chạy `make all MACHINE=B` ngay trên màn hình Windows) |
| Windows qua SSH: `winget` báo `0x8a15000f` | cài make bằng bản zip GNU make (ezwinports) vào `C:\Tools\make\bin` và thêm vào PATH |
| `tc lỗi` khi `make delay-on` | container trung tâm cũ chưa có `NET_ADMIN`: `make down && make all` |
| Windows: `python` mở Microsoft Store | Settings → Apps → App execution aliases → tắt python.exe/python3.exe |
| Windows: chữ tiếng Việt lỗi trong console | Makefile đã đặt `PYTHONUTF8=1`; dùng Windows Terminal |
| Dashboard không cập nhật | xem `results/logs/dash.log`; chạy tiền cảnh bằng `make dash` |

## 10. Phân công gợi ý (3 thành viên)
| Thành viên | Phụ trách chính | Hiểu sâu để vấn đáp |
|---|---|---|
| Phạm Thị Kim Ngọc (2532005) | Hạ tầng: `deploy.py`, Docker, mạng hai máy, `delay.py`, `latency_proxy.py`, `onebox.py`; giao diện `entry.py`, `dash.py` | D1, D6, D7, D8, N3 |
| Đào Minh Hùng (2632006) | Thiết kế phân tán: `site_schema.sql`, `split.py`, `load.py`, `check.py`; TLS `tls.py`, `tls_site.py`; báo cáo | M1, D2, N1 |
| Nguyễn Khánh Hòa (2532018) | Truy vấn và đo đạc: `sql/queries`, `link.py`, `bench.py`; 2PC; slide | D3–D5, N2, N4, N5 |

## 11. Phần mở rộng (ngoài yêu cầu đề)

> **Ghi chú:** phần này là làm thêm. Nó không thuộc D1–D8, không chạy trong `make all`, không thêm bảng hay cột.
> E3 (TLS) **không** thuộc phần này: đã là mặc định, nằm trong `make all` (bước 4 ở trên, [docs/BAO_MAT.md](docs/BAO_MAT.md)).
> Tắt hẳn (không chạy `make ext-*`) thì hệ giống hệt bản bắt buộc. Tài liệu đầy đủ, số đo, kịch bản trình bày: [docs/NANG_CAO.md](docs/NANG_CAO.md).

| Mã | Làm gì | Vì sao | Điểm kỹ thuật |
|---|---|---|---|
| E1 | `phuquoc_replica` (máy A, cổng 5445) là hot standby của `phuquoc` (máy B), nhận WAL qua LAN; `make ext-failover` trỏ `srv_phuquoc` sang bản sao | D8 cho thấy một trạm chết thì mất đọc cả vùng; E1 giữ Q2–Q5 chạy được (chỉ đọc) | pg_hba sửa bằng `COPY … TO PROGRAM` từ máy A (máy B không phải làm gì); replication slot; không promote, để tránh split-brain và trùng dải `booking_id` |
| E2 | 2PC tạo đoàn: `begin` → PREPARE ×4 → `commit` (fsync, điểm cam kết) → COMMIT PREPARED ×4 → `end`; `recover` theo presumed abort | bản cơ bản không ghi quyết định, nên bộ điều phối chết sau PREPARE thì giao dịch treo; ngoài ra lỗi pha 2 làm rollback các trạm chưa commit, gây mất nguyên tử | `--crash prepare\|decision\|mid-commit` giả lập chết; `status` thử INSERT với `lock_timeout` để thấy khoá bị chặn |

Đã chạy thử trên hai máy thật (2026-11-15): E1 dựng trong ≈ 10 s, độ trễ sao chép trung vị 1,9 ms;
khi phuquoc tắt và đã failover, Q2/Q3 khớp đối chứng. E2 phục hồi đúng cả 3 điểm chết. Sau tất cả, `make check` vẫn ĐẠT.
`make ext-bench` (`tools/ext_bench.py`) so sánh phương án: ghi async/`on`/`remote_apply` 28,7/34,6/35,7 ms;
Q2 đọc trạm chính/bản sao ở trễ 30 ms 439,5/330,9 ms; tạo đoàn 4 INSERT/2PC/2PC + nhật ký 149/219/221 ms.
Dòng thử bị xoá sau khi đo, nên dữ liệu không đổi.

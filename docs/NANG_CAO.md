# Phần mở rộng / nâng cao — NGOÀI YÊU CẦU CỦA ĐỀ

> **Ghi chú quan trọng (đọc trước):**
> - Đề **không** yêu cầu phần này. Mọi thứ trong tài liệu này là **làm thêm**, đặt tên `ext-*` / `E1`, `E2` để không nhầm với phần bắt buộc.
> - Phần mở rộng **không nằm trong `make all`**, không đổi lược đồ của đề (không thêm bảng hay cột), không đổi kết quả D1–D8 và N1–N5.
>   Không bật phần mở rộng thì hệ chạy đúng như trong báo cáo.
> - **Khi demo D8 bắt buộc, KHÔNG bật `ext-failover`/`ext-watch`**: đề muốn thấy Q2 *lỗi* khi một trạm chết. E1 chỉ trình bày **sau** D8,
>   như một hướng khắc phục.
> - Đã chạy thử trên **hai máy thật** (A = macOS 192.168.100.218, B = Windows 192.168.100.198) ngày 2026-11-15; nhật ký ở `results/ext/`.

| Mã | Tên | Khắc phục giới hạn nào (KIEN_THUC_BAO_VE §8) | Kiến thức | Mã nguồn | Lệnh |
|---|---|---|---|---|---|
| **E1** | Bản sao dự phòng cho mảnh + chuyển đọc khi trạm chết | #5 "một trạm chết thì dữ liệu vùng đó không đọc được" | Ch.5 sao chép (streaming replication, hot standby) | `tools/ext_replica.py` | `make ext-replica`, `ext-failover`, `ext-failback`, `ext-watch`, `ext-replica-status`, `ext-replica-down` |
| **E2** | 2PC có nhật ký điều phối bền vững + phục hồi giao dịch lưỡng lự | #1 "2PC có thể treo nếu bộ điều phối chết sau PREPARE" | Ch.4 cam kết hai pha, presumed abort | `tools/twopc.py` (giao diện nhập liệu dùng chung) | `make ext-2pc-crash CRASH=…`, `ext-2pc-status`, `ext-2pc-recover` |
| **E3** | Đường postgres_fdw kiểu production: mTLS `verify-full`, DNS nội bộ, role chỉ đọc, không mật khẩu | trạm ở các nơi khác nhau: dữ liệu đi rõ, xác thực bằng IP + mật khẩu superuser | Ch.1 kiến trúc phân tán; PostgreSQL SSL, `pg_hba` `cert` | `tools/ext_secure.py` | `make ext-secure`, `ext-secure-status`, `ext-secure-test`, `ext-secure-bench`, `ext-secure-down` |

Tệp đã thêm hoặc sửa cho phần mở rộng:

| Tệp | Thay đổi |
|---|---|
| `tools/ext_replica.py` | **mới** — E1 |
| `tools/twopc.py` | **mới** — E2 (tham số `durable=False` chỉ để `ext-bench` đo bản không nhật ký) |
| `deploy.toml`, `deploy.local.toml` | thêm mục `[ext.replica.phuquoc]` (bản sao đặt ở máy A, cổng 5445) |
| `tools/common.py` | `Config` đọc `[ext.replica.*]` (nút `phuquoc_replica` dùng chung `host_addr`/`docker_addr`) |
| `tools/deploy.py` | `make down` xoá luôn container + volume bản sao nếu có |
| `app/entry.py` | tab "Thêm đoàn tour (2PC)" gọi `twopc.create_tour_group()`; thêm khung "Giao dịch lưỡng lự" có nút phục hồi |
| `tools/ext_secure.py` | **mới** — E3; `deploy*.toml` thêm `[ext.secure] domain`; `tools/common.py` đọc `cfg.secure` |
| `tools/ext_bench.py` | **mới** — `make ext-bench`: so sánh phương án của E1, E2 (mục *Đánh giá* bên dưới) |
| `Makefile` | nhóm lệnh `ext-*`, `make ext-help` |
| `results/ext/` | nhật ký chạy thử trên hai máy thật |

---

## E1 — Bản sao dự phòng cho mảnh `phuquoc` và chuyển đọc (read failover)

### Vấn đề
Mỗi mảnh chỉ có một bản. Ở D8, tắt `phuquoc` (máy B) thì Q2–Q5 lỗi `could not connect to server "srv_phuquoc"`:
dữ liệu của cả vùng Phú Quốc không đọc được, dù ba vùng còn lại vẫn chạy.

### Cách làm
```
 MÁY B (Windows)                                  MÁY A (macOS)
 ┌──────────────┐  WAL (streaming replication,    ┌──────────────────────┐
 │ phuquoc :5435│ ──── bất đồng bộ, qua LAN) ───► │ phuquoc_replica :5445│  hot standby, CHỈ ĐỌC
 │  TRẠM CHÍNH  │      replication slot           └──────────▲───────────┘
 └──────▲───────┘                                            │ khi failover
        │ bình thường                                        │
        └──────────── srv_phuquoc (postgres_fdw) ── trạm trung tâm nhatrang
```
1. `make ext-replica` (chạy ở máy A, máy B **không phải làm gì**):
   - kết nối trạm chính bằng SQL, nối dòng `host replication all all scram-sha-256` vào `pg_hba.conf`
     (qua `COPY … TO PROGRAM`, rồi `pg_reload_conf()`). Nhờ vậy không cần mở phiên trên máy Windows;
   - tạo replication slot `cs5104_phuquoc_replica`, để trạm chính giữ WAL cho tới khi bản sao nhận xong;
   - chạy container `cs5104_phuquoc_replica` ở máy A. Lần đầu nó chạy `pg_basebackup -R -X stream -S <slot>` qua LAN,
     sau đó khởi động ở chế độ hot standby. `max_connections` và `max_prepared_transactions` phải ≥ trạm chính (yêu cầu của standby).
2. `make ext-failover`: `ALTER SERVER srv_phuquoc OPTIONS (SET host …, SET port …)` ở trạm trung tâm, trỏ sang bản sao.
   `all_*` và Q2–Q5 **không phải sửa**: khung nhìn vẫn đọc `s_phuquoc.*`, chỉ máy chủ ngoài đổi địa chỉ.
   postgres_fdw tự bỏ kết nối cũ khi tuỳ chọn của server thay đổi.
3. `make ext-failback`: trỏ `srv_phuquoc` về trạm chính. `make ext-watch` làm cả hai việc tự động, kiểm tra mỗi 1 s.

### Vì sao chỉ chuyển ĐỌC, không nâng bản sao thành trạm chính (promote)
- Đề yêu cầu giao diện báo lỗi khi trạm đích mất và **không ghi nhầm sang trạm khác**. Bản sao chỉ đọc nên tự bảo đảm điều này
  (thử ghi sẽ báo `cannot execute INSERT in a read-only transaction`).
- Promote cần cơ chế rào (fencing). Nếu trạm chính chỉ bị đứt mạng chứ không chết, ta sẽ có **hai trạm chính** (split-brain).
  Ngoài ra, dải `booking_id` của trạm 3 đã cấp ở trạm chính nhưng chưa kịp sao chép có thể bị cấp lại ở bản sao.
- Sao chép bất đồng bộ nên dữ liệu bản sao có thể chậm vài ms (RPO > 0). Với đọc báo cáo (Q2) thì chấp nhận được.

### Kết quả đo (hai máy thật, 2026-11-15)
| Phép đo | Kết quả |
|---|---|
| `make ext-replica` (pg_basebackup ≈ 20 nghìn lượt đặt qua Wi-Fi + khởi động standby) | ≈ 10 s |
| Trạng thái | `streaming/async`, số dòng `booking` chính = bản sao = 19.755 (`results/ext/e1_replica_status.txt`) |
| Độ trễ nhìn thấy dòng mới: ghi vào `phuquoc` (máy B) → thấy ở bản sao (máy A), 10 lần | 0,6–6,5 ms, trung vị **1,9 ms** |
| D8 không có E1: tắt `phuquoc` → `make q QUERIES=Q2` | lỗi (như đề yêu cầu) |
| D8 + `make ext-failover` → `make q QUERIES="Q2 Q3"` | Q2: 60 dòng, Q3: 46 dòng, **giống CSDL đối chứng: CÓ** |
| `make ext-watch`: thời gian từ lúc trạm chết tới khi tự failover | ≤ 1–2 s (nhịp kiểm 1 s + `connect_timeout` 1 s) |
| Bật lại `phuquoc` | bản sao tự nối lại walsender; `ext-watch` tự failback |

### Kịch bản trình bày (≈ 2 phút, SAU D8)
```bash
make ext-replica                 # A: tạo bản sao (làm trước buổi bảo vệ cho nhanh)
make ext-replica-status          # streaming, số dòng khớp
# B: make stop-site SITE=phuquoc
make q QUERIES=Q2                # lỗi — giống D8
make ext-failover
make q QUERIES="Q2 Q3"           # chạy lại, giống đối chứng; dữ liệu vùng Phú Quốc đọc từ bản sao ở máy A
# B: make start-site SITE=phuquoc
make ext-failback                # hoặc chạy make ext-watch trong một cửa sổ riêng để thấy tự động
```

### Giới hạn còn lại của E1
- Chỉ có bản sao cho `phuquoc`. Thêm mục `[ext.replica.danang]` vào `deploy.toml` rồi chạy `make ext-replica RSITE=danang` để có thêm một bản.
- Bản sao đặt ở máy A, cùng máy với trạm trung tâm. Máy A chết thì cả hệ dừng (trạm trung tâm là điểm lỗi đơn lẻ, đề đã cố định như vậy).
- Khi bật trễ (`make delay-on`), bộ lọc netem chỉ nhắm IP của các trạm xa đã cấu hình. Đường trung tâm → bản sao (cùng máy A) không bị trễ.
- Nếu gỡ và tạo lại trạm chính (`make down MACHINE=B`), bản sao không còn khớp (khác system identifier):
  chạy `make ext-replica-down && make ext-replica`.

---

## E2 — 2PC có nhật ký điều phối bền vững và phục hồi

### Vấn đề
`tour_group` được sao chép ra 4 trạm, nên tạo đoàn mới là một giao dịch phân tán: 2PC với `PREPARE TRANSACTION` / `COMMIT PREPARED`.
Bản cơ bản có hai điểm yếu:
1. Bộ điều phối (giao diện nhập liệu) **không ghi lại quyết định**. Nếu nó chết sau PREPARE thì các trạm giữ giao dịch lưỡng lự
   (`pg_prepared_xacts`) và giữ khoá, mà không ai biết nên COMMIT hay ROLLBACK.
2. **Lỗi đúng đắn ở pha 2:** nếu `COMMIT PREPARED` lỗi ở một trạm sau khi các trạm trước đã commit, nhánh `except` lại
   `ROLLBACK PREPARED` các trạm còn lại. Kết quả là đoàn có ở trạm này mà không có ở trạm kia, tức **mất tính nguyên tử**.
   Bản E2 sửa: sau điểm cam kết thì không bao giờ rollback.

### Giao thức (`tools/twopc.py`)
```
begin(gid, trạm, dòng)  ──fsync──►  nhật ký results/2pc_coordinator.jsonl (máy A)
pha 1:  mỗi trạm  INSERT tour_group … ; PREPARE TRANSACTION   (lỗi ở đâu -> ghi abort, ROLLBACK PREPARED các trạm đã prepare)
commit(gid)             ──fsync──►  ĐIỂM CAM KẾT: từ đây giao dịch chắc chắn được cam kết
pha 2:  mỗi trạm  COMMIT PREPARED   (trạm lỗi -> để lại lưỡng lự; recover sẽ commit sau)
end(gid)                            khi mọi trạm đã xong
```
**Phục hồi** (`make ext-2pc-recover`) theo kiểu *presumed abort*: với mỗi giao dịch lưỡng lự ở mỗi trạm (`tpc_recover()`),
- nhật ký có `commit` → `COMMIT PREPARED`;
- không có quyết định → `ROLLBACK PREPARED`. Điều này an toàn vì chưa trạm nào có thể đã commit: commit chỉ được gửi sau khi quyết định nằm trên đĩa.

  Riêng giao dịch mới PREPARE dưới 10 s thì được bỏ qua (có thể bộ điều phối vẫn đang chạy), trừ khi chạy với `FORCE=1`.

`make ext-2pc-crash CRASH=…` giả lập bộ điều phối chết (`os._exit`) ngay sau một bước:

| `CRASH=` | Trạng thái để lại | `ext-2pc-status` cho thấy | `ext-2pc-recover` |
|---|---|---|---|
| `prepare` | 4 trạm đã PREPARE, chưa có quyết định | 4 lưỡng lự, "recover sẽ ROLLBACK" | ROLLBACK cả 4 (cần `FORCE=1` nếu < 10 s) |
| `decision` | quyết định commit đã ghi, chưa commit trạm nào | 4 lưỡng lự, đoàn chưa thấy ở trạm nào | COMMIT cả 4 |
| `mid-commit` | đã commit `dalat`, 3 trạm còn lưỡng lự | **⚠ bản sao không nhất quán**: đoàn chỉ thấy ở `dalat` | COMMIT 3 trạm còn lại |

Mỗi lần `status` còn thử `INSERT` đúng `tour_group_id` đang lưỡng lự với `lock_timeout = 700ms`. Kết quả là
`canceling statement due to lock timeout`: **thấy tận mắt tính "chặn" của 2PC** (Chương 4).

### Kết quả chạy thử (hai máy thật) — `results/ext/e2_crash_mid_commit.txt`
Cả ba điểm chết đều được phục hồi đúng (`decision`: 4 commit; `mid-commit`: 3 commit; `prepare`: 4 rollback).
Sau đó `make check` vẫn **ĐẠT**, CSDL đối chứng nhận đoàn đúng một lần (`ON CONFLICT DO NOTHING`).
Giao diện nhập liệu dùng cùng hàm `create_tour_group()`, nên mọi đoàn tạo từ giao diện cũng được ghi nhật ký.

### Kịch bản trình bày (≈ 2 phút)
```bash
make ext-2pc-crash CRASH=mid-commit   # bộ điều phối chết sau khi commit 1/4 trạm
make ext-2pc-status                   # 3 trạm lưỡng lự, bản sao không nhất quán, INSERT bị chặn
make ext-2pc-recover                  # đọc nhật ký -> COMMIT PREPARED 3 trạm còn lại
make ext-2pc-status && make check     # sạch, vẫn ĐẠT
```

### Giới hạn còn lại của E2
- 2PC vẫn **chặn**: trong khoảng từ lúc bộ điều phối chết tới lúc chạy recover, các trạm giữ khoá. Muốn không chặn thì phải dùng
  3PC hoặc commit dựa trên đồng thuận (Paxos/Raft commit, Chương 6).
- Nhật ký là một tệp trên máy A. Mất đĩa máy A thì mất quyết định. Bản thật sẽ đặt nhật ký trên lưu trữ bền có sao chép.
- Phục hồi chạy khi được gọi (lệnh hoặc nút trong giao diện), không phải tiến trình nền. Các trạm cũng không tự hỏi nhau
  (không có cooperative termination).

---

## E3 — Đường postgres_fdw kiểu production khi các trạm ở các nơi khác nhau

### Vấn đề
Trong lab, hai máy chung một Wi-Fi. `postgres_fdw` nối tới trạm xa bằng **IP**, **không mã hoá**, bằng **superuser `postgres`**,
và **mật khẩu nằm trong `deploy.toml`**. Khi các trạm ở các nơi khác nhau, mỗi điểm này là một lỗ hổng:
- dữ liệu khách (tên, mã số thuế trong `req_business`) đi qua mạng dạng rõ;
- ai giả được IP của trạm là đánh lừa được trạm trung tâm;
- lộ một mật khẩu là mất quyền superuser trên mọi trạm;
- IP đổi là phải `make link` lại.

Lớp mạng (WireGuard, site-to-site VPN, Tailscale hoặc Headscale) giải quyết chuyện *đi tới được*. E3 làm phần
**không tin mạng** ở chính lớp CSDL, nên vẫn đúng dù đường hầm VPN có bị lộ.

### Cách làm (`tools/ext_secure.py`, `make ext-secure`)
```
 build/e3/ (chỉ ở máy A, không vào git)          trạm xa (dalat, phuquoc, danang) — cấu hình qua SQL, máy B không phải làm gì
   ca.key, ca.crt  ── ký ──►  <trạm>.crt  ─────►  ssl = on, ssl_min_protocol_version = TLSv1.3, ssl_ca_file = ca.crt
                   └─ ký ──►  fdw_reader.crt       role fdw_reader: LOGIN, chỉ SELECT; không có mật khẩu
                                                   pg_hba (đầu tệp):  hostssl   hotel fdw_reader all cert
                                                                      hostnossl all   fdw_reader all reject
 trạm trung tâm nhatrang
   /etc/hosts: <trạm>.db.nhom8.internal -> IP     (giả lập vùng DNS nội bộ)
   srv_<trạm>:  host '<trạm>.db.nhom8.internal', sslmode 'verify-full', sslrootcert ca.crt, sslnegotiation 'direct'
   user mapping: user 'fdw_reader', sslcert/sslkey — KHÔNG còn password
```
- **PKI nội bộ:** CA ECDSA P-256 (openssl trong container trung tâm, sau đó chép ra `build/e3/` và xoá khỏi container).
  Chứng chỉ máy chủ có SAN là **tên** trạm, không có IP. Vì vậy `verify-full` vừa kiểm tra chứng chỉ do CA của nhóm ký,
  vừa kiểm tra đúng tên máy. Chứng chỉ máy khách có `CN=fdw_reader`, nên phương thức `cert` của `pg_hba` ánh xạ thẳng CN sang role.
- **Quyền tối thiểu:** `fdw_reader` chỉ có `CONNECT`, `USAGE` và `SELECT`. Q1–Q5 và `make check` chỉ đọc qua fdw.
  Ghi (nhập liệu, 2PC tạo đoàn) vẫn đi thẳng tới trạm như trước.
- **Không còn mật khẩu trong đường fdw:** user mapping dùng cặp khoá/chứng chỉ; khoá riêng nằm ở trạm trung tâm với quyền 0600.
- **Tên thay IP:** IP của máy B đổi thì chỉ cần sửa bản ghi tên, không phải `make link`. Bản thật dùng một vùng DNS riêng
  (Route 53 private zone, CoreDNS, MagicDNS của Tailscale); trong lab giả lập bằng `/etc/hosts` của container trung tâm.
- **`sslnegotiation=direct` (PostgreSQL ≥ 17):** bắt tay TLS ngay (ALPN `postgresql`), bỏ một vòng `SSLRequest`.
- **An toàn khi bật chung:** `up` từ chối nếu `srv_*` đang bị `ext-failover` hoặc `DELAY_MODE=proxy` sửa.
  `make ext-secure-down` (hoặc `make link`) trả `srv_*` về như cũ, tắt TLS, xoá role và các dòng `pg_hba` đã thêm.

### Kết quả (hai máy thật, 2026-11-17) — `results/ext/e3_run.txt`, `results/ext/e3_bench.csv`
`make ext-secure-test` thử từ máy A tới `phuquoc` (máy B) qua mạng thật: **7/7 ĐẠT**.

| Phép thử | Mong đợi | Thực tế |
|---|---|---|
| T1 tên đúng + CA nội bộ + chứng chỉ máy khách | vào được | OK (TLSv1.3) |
| T2 như T1, `sslnegotiation=direct` | vào được | OK (TLSv1.3) |
| T3 không mã hoá (`sslmode=disable`) | từ chối | `pg_hba.conf rejects connection … no encryption` |
| T4 gọi bằng IP (`verify-full`) | từ chối | `server certificate for "phuquoc.db.nhom8.internal" … does not match host name` |
| T5 có TLS nhưng không có chứng chỉ máy khách | từ chối | `connection requires a valid client certificate` |
| T6 chứng chỉ `CN=fdw_reader` nhưng do CA lạ ký | từ chối | `tlsv1 alert unknown ca` |
| T7 `fdw_reader` thử `UPDATE` | từ chối | `permission denied for table room_type` |

Khi E3 bật, `make ext-secure-status` thấy cả ba phiên fdw ở trạm xa là `fdw_reader`, TLSv1.3, `TLS_AES_256_GCM_SHA384`, `client_dn=/O=Nhom 8 CS5104/CN=fdw_reader`.
`make check` ĐẠT và `make q` cho Q1–Q5 khớp đối chứng.

**Chi phí** (`make ext-secure-bench`; mỗi chế độ 9 phiên mới; "mở kết nối" = lần chạy đầu của phiên trừ trung vị các lần sau):

| Trễ | Chế độ | Mở kết nối fdw | Truy vấn nhỏ khi đã mở | Q2 lần đầu / trung vị |
|---:|---|---:|---:|---:|
| 0 | không mã hoá + SCRAM (`make link`) | +114 ms | 41 ms | 336 / 97 ms |
| 0 | TLS + chứng chỉ | +96 ms | 45 ms | 320 / 102 ms |
| 0 | TLS direct + chứng chỉ | +85 ms | 40 ms | 298 / 75 ms |
| 30 | không mã hoá + SCRAM | **+469 ms** | 203 ms | 1.764 / 456 ms |
| 30 | TLS + chứng chỉ | **+382 ms** | 209 ms | 1.541 / 428 ms |
| 30 | TLS direct + chứng chỉ | **+340 ms** | 207 ms | 1.401 / 458 ms |

- **TLS chỉ tốn lúc mở kết nối.** Khi đã mở, ba chế độ chênh nhau trong biên dao động của Wi-Fi (truy vấn nhỏ 203–209 ms, Q2 428–458 ms):
  mã hoá AES-GCM có tăng tốc phần cứng nên gần như không tốn gì. `postgres_fdw` giữ kết nối suốt phiên, nên Bảng 3 không đổi.
- **Mở kết nối có TLS còn nhanh hơn kết nối không mã hoá.** Bắt tay TLS 1.3 tốn 1 vòng (cộng 1 vòng `SSLRequest`).
  Xác thực `cert` lại bỏ được 2 vòng trao đổi SASL của SCRAM và phần băm PBKDF2 4096 lần ở hai đầu, nên tổng cộng rẻ hơn.
- **`direct` bỏ đúng một vòng:** 382 → 340 ms (−42 ms ≈ 1,4 × 30 ms).
- Lần đầu Q2 (mở 3 kết nối) giảm từ 1.764 xuống 1.401 ms (−21%). Lợi này có ích khi trạm trung tâm phục vụ nhiều phiên ngắn.

### Kịch bản trình bày (≈ 2 phút, SAU D8)
1. `make ext-secure` → đọc 3 dòng `srv_* -> <trạm>.db.nhom8.internal (verify-full, …)`.
2. `make ext-secure-status` → phiên fdw ở trạm xa là `fdw_reader`, TLSv1.3, có `client_dn`; user mapping `password=không`.
3. `make ext-secure-test` → 7/7 ĐẠT. Nhấn vào T4 (gọi bằng IP bị từ chối: chống giả mạo trạm) và T7 (không ghi được).
4. `make q QUERIES=Q2` → vẫn khớp đối chứng. Tắt: `make ext-secure-down`.

### Giới hạn còn lại của E3
- Các tool chạy trên máy A (nạp, kiểm tra, nhập liệu, dashboard) vẫn dùng `postgres` với mật khẩu, không bắt buộc TLS. Bản thật nên cho
  mỗi ứng dụng một role và một chứng chỉ riêng, đồng thời chỉ cho `postgres` đăng nhập từ `localhost`.
- Mật khẩu `postgres` vẫn nằm trong `deploy.toml`. Bản thật lấy từ secret manager (Vault, Docker secrets, biến môi trường của CI).
- Khoá CA ở `build/e3/` trên máy A. Bản thật để CA ngoại tuyến hoặc dùng step-ca/Vault PKI, chứng chỉ ngắn hạn tự gia hạn, có CRL/OCSP để thu hồi.
- `/etc/hosts` của container mất khi container trung tâm khởi động lại; chạy lại `make ext-secure` (lệnh chạy lặp được, dùng lại PKI cũ).
- Đường `ref` và đường sao chép của E1 chưa đi qua TLS.

---

## Đánh giá — so sánh phương án (`make ext-bench`)

`tools/ext_bench.py` đo ba nhóm so sánh trên **hai máy thật** (Wi-Fi, 2026-11-15). Mỗi phương án đo 21 lần, bỏ lần đầu, lấy trung vị
(B2: 2 phiên psql × 5 lần, bỏ lần đầu mỗi phiên). Các dòng thử bị **xoá** khỏi 4 trạm và `ref` khi đo xong, và mọi cấu hình tạm thời
được trả lại trong khối `finally` (`synchronous_standby_names`, trễ, `srv_phuquoc`). Vì vậy dữ liệu không đổi và `make check` vẫn ĐẠT.
Số liệu thô ở `results/ext/ext_bench.csv`.

### B1 (E1) — sao chép bất đồng bộ hay đồng bộ: giá của việc không mất dữ liệu
Ghi một lượt đặt (`booking` + `req_business`, một giao dịch) từ máy A vào trạm chính `phuquoc` ở máy B. Bản sao ở máy A.

| `synchronous_commit` | Nghĩa | Ghi (trung vị) | Ghi xong → thấy ở bản sao | Mất dữ liệu khi trạm chính chết (RPO) |
|---|---|---:|---:|---|
| `local` (mặc định của hệ) | bất đồng bộ, không chờ bản sao | **28,7 ms** | 30,6 ms (chậm ≈ 1,9 ms) | có thể mất vài ms cuối |
| `on` | chờ bản sao ghi WAL xuống đĩa | 34,6 ms (+6,0) | 35,4 ms | 0 |
| `remote_apply` | chờ bản sao phát lại xong | 35,7 ms (+7,1) | 36,4 ms (thấy ngay) | 0, và đọc ở bản sao luôn thấy dòng mới |

Giải thích:
- 28,7 ms ≈ 4 vòng khứ hồi máy A → máy B qua Wi-Fi (BEGIN, INSERT booking, INSERT req_*, COMMIT), mỗi vòng ≈ 7 ms.
- Chế độ đồng bộ thêm **đúng một vòng khứ hồi máy B → máy A**: COMMIT phải chờ WAL sang bản sao và chờ xác nhận. Kết quả là +6–7 ms, tức +21–25%.
- `remote_apply` chỉ hơn `on` khoảng 1 ms (thời gian phát lại). Đổi lại, đọc ở bản sao ngay sau khi ghi luôn thấy dòng mới.
- **Vì sao vẫn chọn bất đồng bộ:** khi đặt đồng bộ, bản sao chết thì mọi COMMIT ở trạm chính **treo**. Một trạm phụ lại làm hỏng
  trạm chính, tức là ngược với mục đích tăng sẵn sàng. Mất vài ms dữ liệu chỉ xảy ra khi trạm chính chết đúng lúc đang ghi, nên chấp nhận được.

### B2 (E1) — Q2 đọc mảnh `phuquoc` từ trạm chính (máy B) hay từ bản sao (máy A)

| Trễ netem | `srv_phuquoc` → trạm chính (máy B) | `srv_phuquoc` → bản sao (máy A) | Chênh lệch |
|---:|---:|---:|---:|
| 0 ms | 68,2 ms | **43,5 ms** | −25 ms |
| 30 ms | 439,5 ms | **330,9 ms** | −109 ms ≈ 3,6 × 30 ms |

Giải thích:
- Bản sao nằm cùng máy với trạm trung tâm, nên đường tới nó không qua Wi-Fi và không bị netem làm trễ. Bộ lọc chỉ nhắm IP của các trạm xa đã cấu hình.
- Bớt **một** trạm xa thì Q2 bớt khoảng **3–4 vòng khứ hồi**, đúng với phân tích ở N3. FETCH chạy song song (async), nhưng
  START TRANSACTION / DECLARE CURSOR / CLOSE vẫn được gửi **lần lượt** cho từng trạm. Vì vậy mỗi trạm xa góp ≈ 3 vòng tuần tự.
  Đây là cách kiểm chứng độc lập cho con số 11 vòng (≈ 3 trạm × 3 vòng + 2).
- **Đọc kỹ con số:** phép so sánh này cho thấy cái lợi khi *đặt bản sao gần trạm truy vấn*, không phải "bản sao nhanh hơn".
  Trong thực tế bản sao nên ở một vùng khác để chịu được thảm hoạ. Khi đó nó cũng chịu trễ như trạm chính.

### B3 (E2) — chi phí của 2PC và của nhật ký điều phối
Tạo một đoàn tour, ghi vào 4 trạm (2 trạm ở máy A, 2 trạm ở máy B), đo từ máy A, gồm cả mở 4 kết nối.

| Phương án | Trung vị | So với mốc | Nguyên tử? | Phục hồi được khi bộ điều phối chết? |
|---|---:|---:|---|---|
| 4 INSERT autocommit lần lượt (chỉ làm mốc) | 149,4 ms | — | **Không** | — |
| 2PC không nhật ký (bản cơ bản) | 218,8 ms | +69 ms (+46%) | Có | Không: giao dịch lưỡng lự phải gỡ bằng tay |
| 2PC + nhật ký fsync (E2) | **220,6 ms** | +71 ms (+48%) | Có | **Có**: `make ext-2pc-recover` |

Giải thích:
- 2PC tốn thêm vì mỗi trạm có thêm BEGIN, PREPARE TRANSACTION và COMMIT PREPARED (≈ 2 vòng mỗi trạm, gửi lần lượt).
  Hai trạm ở máy B qua Wi-Fi chiếm phần lớn.
- **Nhật ký điều phối gần như miễn phí: +1,8 ms (≈ 0,8%)**, nhỏ hơn dao động giữa các lần đo. Lý do là ba lần fsync được ghi vào
  ổ SSD cục bộ, còn mỗi vòng mạng tốn vài ms. Lưu ý: trên macOS, `fsync` không ép xả bộ đệm của ổ đĩa (cần `F_FULLFSYNC`),
  nên đây là giới hạn dưới của chi phí thật.
- Cải tiến có thể làm tiếp: gửi PREPARE và COMMIT PREPARED **song song** tới 4 trạm (dùng luồng). Khi đó thời gian 2PC còn khoảng
  bằng thời gian của trạm chậm nhất, thay vì tổng của 4 trạm.

### Kết luận đánh giá
| Câu hỏi | Trả lời bằng số đo |
|---|---|
| Thêm bản sao có làm chậm việc ghi ở trạm chính không? | Bất đồng bộ: không (vẫn 28,7 ms). Đồng bộ: +6–7 ms, tức một vòng khứ hồi |
| Bản sao bất đồng bộ chậm bao nhiêu? | ≈ 2 ms qua Wi-Fi |
| Failover có làm Q2 sai hay chậm không? | Q2 khớp đối chứng; không chậm hơn (bản sao gần hơn nên còn nhanh hơn) |
| E2 tốn thêm bao nhiêu so với 2PC cơ bản? | ≈ 2 ms (< 1%), đổi lại phục hồi được tự động |

---

## Câu hỏi vấn đáp dự kiến về phần mở rộng
1. *Sao chép đồng bộ hay bất đồng bộ? Vì sao?* Bất đồng bộ (mặc định), nên ghi ở trạm chính không phải chờ vòng khứ hồi tới máy A.
   Đổi lại, khi trạm chính chết có thể mất vài ms dữ liệu chưa sao chép. Muốn RPO = 0 thì đặt `synchronous_standby_names`, nhưng khi đó
   bản sao chết sẽ làm ghi ở trạm chính bị treo.
2. *Vì sao không dùng logical replication?* Ta cần bản sao **toàn bộ mảnh**, chỉ đọc, giống từng byte, để thay thế trạm chính khi đọc.
   Physical streaming là đơn giản nhất. Logical replication hợp hơn cho việc sao chép một bảng (ví dụ `tour_group` thay cho 2PC).
3. *Failover xong thì Q2 có đúng không?* Đúng như ở thời điểm bản sao đã phát lại tới. Đo được độ trễ ≈ 2 ms, và kết quả so với đối chứng khớp.
4. *Vì sao recover được phép ROLLBACK khi nhật ký không có quyết định?* Bộ điều phối chỉ gửi `COMMIT PREPARED` sau khi
   `commit` đã được fsync. Không có `commit` trên đĩa nghĩa là chưa trạm nào commit, nên huỷ là an toàn (presumed abort).
5. *Sao không bật sao chép đồng bộ cho chắc?* Xem B1: chỉ tốn +6–7 ms. Nhưng bản sao chết thì ghi ở trạm chính treo,
   nên sẵn sàng của trạm chính phụ thuộc vào bản sao. Muốn có cả hai thì phải có ≥ 2 bản sao, với `synchronous_standby_names = 'ANY 1 (...)'`.
6. *Nhật ký fsync có làm 2PC chậm không?* Xem B3: +1,8 ms trên 220 ms. Chi phí 2PC nằm ở các vòng mạng, không nằm ở đĩa.
7. *Nếu một trạm chết đúng lúc pha 2?* Các trạm khác vẫn commit. Trạm chết giữ giao dịch đã PREPARE trên đĩa (sống lại vẫn còn),
   và `ext-2pc-recover` sẽ commit nó theo nhật ký. Trong lúc đó bản sao `tour_group` tạm thời không nhất quán. Đây là cái giá của 2PC.
   *(Nhánh mã này có trong `create_tour_group()`, nhưng chưa được chạy thử riêng bằng cách tắt trạm đúng lúc pha 2;
   trường hợp `mid-commit` cho thấy cùng trạng thái cuối và cùng cách phục hồi.)*

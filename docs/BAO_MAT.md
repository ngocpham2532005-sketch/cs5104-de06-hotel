# E3 — Bảo mật đường truyền (mặc định của hệ)

> Từ 2026-11-17, mọi kết nối qua mạng giữa các nút của hệ đều đi qua **TLS ≥ 1.3, `sslmode=verify-full`**. Các nút gồm
> 4 trạm và CSDL đối chứng `ref`; kết nối gồm `postgres_fdw`, nạp, kiểm tra, đo, nhập liệu và dashboard.
> `make all` tự cấp chứng chỉ (`make secure`). Mã nguồn: `tools/tls.py` (máy A: CA, điều phối, thử),
> `tools/tls_site.py` (thao tác trên một nút), `tools/link.py` (postgres_fdw qua TLS).

## 1. Vấn đề
Khi các trạm ở các nơi khác nhau, cấu hình "một LAN" ban đầu có bốn lỗ hổng:
1. dữ liệu khách (tên, mã số thuế trong `req_business`) đi qua mạng dạng rõ;
2. trạm trung tâm gọi trạm xa bằng **IP**: ai chiếm được IP là giả được trạm;
3. `postgres_fdw` dùng **superuser `postgres` + mật khẩu** nằm trong cấu hình: lộ một mật khẩu là mất mọi trạm;
4. IP đổi là phải `make link` lại.

Lớp mạng (cùng LAN, hoặc WireGuard/Tailscale khi ở hai nơi) chỉ giải quyết chuyện *đi tới được*. E3 làm phần
**không tin mạng** ở chính lớp CSDL, nên vẫn đúng dù mạng hay đường hầm VPN có bị lộ.

## 2. Thiết kế

| Thành phần | Cách làm | Chống lại |
|---|---|---|
| CA nội bộ | ECDSA P-256, 5 năm, `pathlen:0`; khoá CA chỉ ở `build/e3/` máy A (không vào git); mọi thao tác ký chạy trong **container dùng một lần, `--network none`** | lộ khoá CA qua một nút bị chiếm |
| Chứng chỉ máy chủ (5 nút) | CN = SAN = `<nút>.db.nhom8.internal`, **không có IP**, EKU `serverAuth`, hạn 90 ngày, serial ngẫu nhiên 128 bit; CA tự đặt phần mở rộng, không chép từ CSR | giả trạm bằng IP; CSR xin quyền lạ |
| Khoá riêng của nút | sinh **trong container của nút** (`umask 077`), không bao giờ ra ngoài; qua mạng chỉ có CSR và chứng chỉ (công khai) | lộ khoá khi truyền |
| `pg_hba` mỗi nút | loopback trong container giữ nguyên; `hostnossl all all all reject` và `hostnossl replication all all reject`; `fdw_reader` chỉ qua `hostssl … cert` | nghe lén; đăng nhập không mã hoá |
| Role `fdw_reader` | `LOGIN`, chỉ `CONNECT/USAGE/SELECT`, **không mật khẩu**, xác thực bằng chứng chỉ máy khách `CN=fdw_reader` | lộ khoá trạm trung tâm ⇒ chỉ đọc được, không sửa/xoá |
| `postgres_fdw` (trạm trung tâm) | `host '<nút>.db.nhom8.internal'`, `sslmode 'verify-full'`, `sslrootcert`, `sslnegotiation 'direct'`; trạm xa: user mapping `fdw_reader` + `sslcert/sslkey`; `ref`: `postgres` + mật khẩu qua TLS | giả trạm; mật khẩu trong cấu hình fdw |
| DNS nội bộ | `/etc/hosts` của container trung tâm: `<nút>.db.nhom8.internal → IP` (bản thật: vùng DNS riêng) | IP đổi; failover E1 đổi bản ghi tên thay vì đổi `srv_*` |
| Công cụ ở máy A | `host=<tên> hostaddr=<IP> sslmode=verify-full sslrootcert=build/e3/ca.crt` (không cần DNS ở máy A) | như trên |

## 3. Luồng `make secure` (trong `make all`, chạy lại được)
```
máy A: tls.py secure
  1. CA nội bộ (tạo nếu chưa có)                                    container dùng một lần, --network none
  2. chờ 5 nút (dalat, nhatrang, ref ở máy A; phuquoc, danang ở máy B)
  3. với mỗi nút chưa có chứng chỉ hợp lệ của CA hiện tại (hoặc còn < 30 ngày):
       csr      : openssl genpkey + req TRONG container của nút   ── nút ở máy A: docker exec
                                                                  └─ nút ở máy B: kênh quản trị SQL (COPY … FROM PROGRAM)
       sign     : kiểm chữ ký CSR, chính sách CN, CA đặt SAN/EKU/hạn, ghi build/e3/issued.jsonl
       install  : kiểm chuỗi CA, khớp khoá, CN/SAN, EKU, hạn → sao lưu → cp+mv nguyên tử → ALTER SYSTEM (ssl, TLSv1.3)
                  → role fdw_reader → pg_hba → reload → kiểm TLS 1.3 thật + vân tay chứng chỉ đang phục vụ; lỗi => hoàn tác
  4. chứng chỉ máy khách fdw_reader cho trạm trung tâm (cùng quy trình)
máy A: link.py  → DNS nội bộ ở trạm trung tâm + srv_* verify-full
```
- Lần đầu mất khoảng 13 s; chạy lại chỉ kiểm tra (khoảng 2 s): chứng chỉ còn hạn thì giữ nguyên. `make secure FORCE=1` cấp lại hết.
- **Kênh quản trị SQL:** lệnh `openssl` vẫn chạy trong container của nút ở máy B, nên khoá vẫn không rời nút. Cái giá là máy A
  phải đăng nhập superuser vào máy B; điều này vốn đã cần để nạp mảnh (`make load`), và giờ đi qua TLS.
- **Chế độ chặt** (không ai có quyền superuser qua mạng): mỗi máy tự `make tls-site-csr`, chép CSR sang máy A, `make tls-sign`,
  chép chứng chỉ về, `make tls-site-install`. Đã chạy thử trên hai máy thật (mục 5).

## 4. Phép thử (`make tls-test`, từ máy A tới `phuquoc` ở máy B, qua mạng thật) — 8/8 ĐẠT

| | Kết nối | Mong đợi | Thực tế |
|---|---|---|---|
| T1 | `fdw_reader`, tên đúng, CA nội bộ, chứng chỉ máy khách | vào được | OK (TLSv1.3) |
| T2 | như T1, `sslnegotiation=direct` | vào được | OK (TLSv1.3) |
| T3 | `fdw_reader` không mã hoá | từ chối | `pg_hba.conf rejects connection … no encryption` |
| T4 | gọi bằng IP thay vì tên | từ chối | `server certificate for "phuquoc.db.nhom8.internal" … does not match host name "192.168.100.198"` |
| T5 | TLS nhưng không có chứng chỉ máy khách | từ chối | `connection requires a valid client certificate` |
| T6 | chứng chỉ `CN=fdw_reader` do CA lạ ký | từ chối | `tlsv1 alert unknown ca` |
| T7 | `fdw_reader` thử `UPDATE` | từ chối | `permission denied for table room_type` |
| T8 | **`postgres` đúng mật khẩu nhưng không mã hoá** | từ chối | `pg_hba.conf rejects connection … user "postgres" … no encryption` |

`make tls-status` cho thấy cả ba phiên fdw ở trạm xa là `fdw_reader`, TLSv1.3, `TLS_AES_256_GCM_SHA384`,
`client_dn=/O=Nhom 8 CS5104/CN=fdw_reader`; user mapping của 3 trạm xa không có mật khẩu.

## 5. Phép thử cho chính quy trình cấp chứng chỉ (chế độ chặt, hai máy thật) — `results/ext/e3_prd_run.txt`

| | Tình huống | Kết quả |
|---|---|---|
| N1 | CSR xin `CN=postgres` | CA từ chối ký (ngoài chính sách) |
| N2 | CSR bị sửa một ký tự | CA từ chối (chữ ký CSR sai) |
| N3 | Đổi khoá nhưng cài lại chứng chỉ cũ | từ chối cài (không khớp khoá chờ); nút vẫn phục vụ chứng chỉ cũ |
| N4 | Lỗi sau reload (`E3_FAULT=after-reload`, điểm tiêm lỗi chỉ dùng khi thử) | tự hoàn tác; vân tay không đổi; fdw vẫn chạy; khoá chờ còn nguyên để cài lại |
| N5 | Cài lại không lỗi = đổi khoá khi hệ đang chạy | vân tay đổi; fdw không gián đoạn |
| N6 | Máy B gỡ TLS trong khi `srv_*` vẫn đòi `verify-full` | truy vấn báo lỗi, không lặng lẽ hạ xuống không mã hoá (fail-closed) |

Mã băm CSR in ở máy B khớp với lúc ký ở máy A (tệp không bị sửa trên đường chép). Nhật ký từng máy: `results/ext/e3_site_<máy>.log`.

## 6. Chi phí
TLS chỉ tốn lúc **mở** kết nối; `postgres_fdw` giữ kết nối suốt phiên, nên truy vấn gần như không đổi.
Đo riêng chi phí mở kết nối (`results/ext/e3_bench.csv`, đo 2026-11-17 trước khi TLS thành mặc định, trung vị 9 phiên, trễ 30 ms):

| Mở một kết nối fdw tới `phuquoc` | Thời gian |
|---|---:|
| không mã hoá + SCRAM (cấu hình cũ) | 469 ms |
| TLS 1.3 + chứng chỉ máy khách | 382 ms |
| TLS 1.3 direct + chứng chỉ máy khách (mặc định hiện tại) | **340 ms** |

Xác thực bằng chứng chỉ bỏ được 2 vòng trao đổi SASL của SCRAM, bù cho bắt tay TLS 1.3; `direct` bỏ thêm vòng `SSLRequest`.
Truy vấn (Bảng 3 của báo cáo, đo lại toàn bộ khi bật TLS, trễ 30 ms): Q2 436 → 459 ms, Q3 423 → 433, Q4 449 → 443, Q5 438 → 433 ms
so với lần đo không TLS; số vòng khứ hồi Q2 11,0 → 10,9. Chênh ±5% theo cả hai chiều, trong biên dao động của Wi-Fi.
`make all` từ máy sạch trên hai máy: 4 phút 35 giây, trong đó cấp chứng chỉ cho 5 nút mất 12 s.

## 7. Tương tác với các phần khác
- **D8:** tắt `phuquoc` thì Q1 vẫn chạy, Q2 lỗi `could not connect to server "srv_phuquoc"`; bật lại thì Q2 chạy lại. Cấu hình TLS
  nằm trong thư mục dữ liệu nên còn nguyên sau khi khởi động lại.
- **Trễ giả lập:** `tc netem` lọc theo IP nên không đổi. `DELAY_MODE=proxy` giữ `host` = tên, chỉ thêm `hostaddr` trỏ tới proxy;
  TLS đi xuyên proxy TCP và vẫn `verify-full`.
- **E1:** bản sao nhận WAL qua TLS (`PGSSLMODE=require`). Bản sao có cùng chứng chỉ máy chủ với trạm chính (pg_basebackup chép cả
  thư mục dữ liệu), nên failover chỉ đổi bản ghi DNS nội bộ `phuquoc.db.nhom8.internal` sang IP bản sao; `verify-full` vẫn đạt.
- **E2:** 2PC ghi thẳng tới từng trạm bằng `postgres` qua TLS; giả lập chết và phục hồi vẫn đúng.

## 8. Vận hành
| Việc | Lệnh |
|---|---|
| Xem chứng chỉ, hạn, phiên fdw | `make tls-status` (máy A) · `make tls-site-status` (từng máy) |
| Gia hạn (cảnh báo khi < 30 ngày) | `make secure` (tự cấp lại cái sắp hết hạn) · chế độ chặt: `tls-site-csr ROTATE=1` → `tls-sign` → `tls-site-install` |
| Tạm tắt để gỡ lỗi | `make tls-off` (mọi nút về không mã hoá, `srv_*` như cũ); bật lại: `make secure && make link` |
| Cập nhật mã nguồn sang máy B | `make sync-remote SSH=… DEST=… KEY=…` (so mã băm script hai đầu) |
| Container trung tâm khởi động lại | `make link` (ghi lại DNS nội bộ trong `/etc/hosts`) |

## 9. Giới hạn còn lại
- Mật khẩu `postgres` vẫn nằm trong `deploy.toml` (dùng cho công cụ quản trị, nay chỉ qua TLS). Bản thật lấy từ secret manager và cấp
  cho mỗi ứng dụng một role và một chứng chỉ riêng.
- Chưa có CRL/OCSP: thu hồi một chứng chỉ phải đổi CA hoặc sửa `pg_hba`; `issued.jsonl` có serial để làm CRL sau này.
- Khoá CA ở ổ đĩa máy A (dù chỉ được dùng trong container không mạng). Bản thật để CA ngoại tuyến hoặc HSM, hoặc dùng step-ca/Vault PKI.
- DNS nội bộ giả lập bằng `/etc/hosts`; đường sao chép của E1 dùng `sslmode=require` (mã hoá, chưa kiểm tên).

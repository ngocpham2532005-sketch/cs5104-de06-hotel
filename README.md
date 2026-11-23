# CS5104 · Đề 6 · Chuỗi khách sạn nghỉ dưỡng — CSDL phân tán 4 trạm trên 2 máy

Bốn trạm PostgreSQL 18 (`dalat`, `nhatrang` (trung tâm), `phuquoc`, `danang`), mỗi vùng một trạm, chạy trên
**máy A (macOS)** và **máy B (Windows)**. Trạm trung tâm truy vấn xuyên trạm bằng `postgres_fdw` qua các
khung nhìn toàn cục `all_<bảng>`; có giao diện nhập liệu và dashboard theo dõi từng trạm.
**Mọi kết nối qua mạng đều mã hoá TLS ≥ 1.3, `verify-full`** với CA nội bộ của nhóm (E3, mặc định; [docs/BAO_MAT.md](docs/BAO_MAT.md)).

| Máy | Hệ điều hành | Chạy | Cổng |
|---|---|---|---|
| A | macOS | `nhatrang` (trung tâm), `dalat`, `ref` (CSDL đối chứng), nhập liệu, dashboard | 5433, 5434, 5440, 8501, 8502 |
| B | Windows 10/11 | `phuquoc`, `danang` | 5435, 5436 |

**Nhóm 8** · Đào Minh Hùng (2632006) · Phạm Thị Kim Ngọc (2532005) · Nguyễn Khánh Hòa (2532018) 
· Đề 6, seed 402738 · Mã nguồn: <https://github.com/ngocpham2532005-sketch/cs5104-de06-hotel>, branch `nhom8-de06-hotel-ddb`
(bản nộp sẽ gắn tag `final`).

Tài liệu: [IMPLEMENT.md](IMPLEMENT.md) (thiết kế và cách cài đặt chi tiết) · [docs/BAO_CAO.md](docs/BAO_CAO.md) (báo cáo, bản PDF ở `docs/BAO_CAO.pdf`)
· [docs/NANG_CAO.md](docs/NANG_CAO.md) (**phần mở rộng, ngoài yêu cầu đề**) · [docs/KIEN_THUC_BAO_VE.md](docs/KIEN_THUC_BAO_VE.md) (ôn tập bảo vệ, nội bộ).

**Kết quả chính** (hai máy thật qua Wi-Fi LAN, chi tiết ở báo cáo mục 5):

| | Kết quả |
|---|---|
| Nạp dữ liệu | 190.831 dòng, từng mảnh khớp `summary.json`; tổng các mảnh = CSDL đối chứng |
| `make all` từ máy sạch | 4 phút 35 giây trên hai máy thật, gồm cấp chứng chỉ TLS cho 5 nút (12 s) |
| `make check` | ĐẠT 103/103 (ba quy tắc đúng đắn, PK/FK toàn hệ, jsonb ⇄ bản quan hệ) |
| `make tls-test` | 8/8 (không mã hoá, gọi bằng IP, thiếu/sai chứng chỉ, thử ghi đều bị từ chối) |
| Q1–Q5 | giống hệt CSDL đối chứng; Q1 chạy trọn tại `dalat` (0 Foreign Scan) |
| Trễ 30 ms (TLS bật) | Q1 0,55 ms (không đổi); Q2 459 ms, Q3 433 ms, Q4 443 ms, Q5 433 ms (≈ 11 vòng khứ hồi, như khi không TLS) |
| Dòng liên vùng | 5.144 / 80.000 = 6,43%; Q3 của đoàn một vùng tốn ngang đoàn ba vùng (431 / 433 ms) |

---

## 1. Chuẩn bị (làm một lần)

**Cả hai máy:** Docker Desktop (đang chạy), Python ≥ 3.11, GNU make, git.

**Mạng giữa hai máy** — máy A phải mở được kết nối TCP tới cổng 5435, 5436 của máy B:

| Hai máy ở đâu | Cách nối | Dùng cho |
|---|---|---|
| Cùng một mạng LAN hoặc Wi-Fi (kể cả hai băng 2.4/5 GHz của **cùng một router**) | không cần gì thêm | **demo D1–D8 và số đo trong báo cáo** (cách đề yêu cầu) |
| Cùng điểm phát Wi-Fi của điện thoại | không cần gì thêm | phương án dự phòng khi demo |
| Hai nơi khác nhau (hai router, hai Wi-Fi khác mạng) | VPN: WireGuard site-to-site, hoặc Tailscale/Headscale; ghi **IP VPN** của mỗi máy vào `deploy.toml` | phát triển, chạy thử từ xa; TLS của E3 (mặc định) vẫn bảo vệ dữ liệu dù VPN bị lộ |

Lưu ý khi hai máy ở hai nơi:
- Trễ thật của Internet (thường 10–50 ms) cộng thêm vào 30 ms giả lập, nên số đo **không so được** với Bảng 3 của báo cáo. Số liệu nộp bài đo trên cùng một LAN.
- **Không** mở cổng router để đưa PostgreSQL ra Internet: dù có TLS, mật khẩu quản trị mặc định vẫn nằm trong repo.
- Mạng Wi-Fi "Guest" thường chặn các máy nói chuyện với nhau. Windows phải đặt mạng là **Private**, nếu không tường lửa sẽ chặn.

**Máy A — macOS**
```bash
xcode-select --install          # có sẵn make, git
brew install python@3.12        # nếu chưa có Python ≥ 3.11
```

**Máy B — Windows** (PowerShell)
```powershell
winget install Docker.DockerDesktop      # bật WSL 2 backend, khởi động Docker Desktop
winget install Python.Python.3.12        # tắt "App execution aliases" python của Microsoft Store nếu bị trùng
winget install ezwinports.make
winget install Git.Git
# Mở cổng 5435, 5436 cho máy A (PowerShell chạy "Run as Administrator"):
New-NetFirewallRule -DisplayName "CS5104 PostgreSQL" -Direction Inbound -Protocol TCP -LocalPort 5435,5436 -Action Allow -Profile Private,Domain
# Đặt mạng Wi-Fi/LAN đang dùng là "Private network" (Settings > Network > Properties)
```

**Sửa `deploy.toml` (giống nhau trên cả hai máy):** `machines.A.ip`, `machines.B.ip` = IP LAN thật
(macOS: `ipconfig getifaddr en0` hoặc `en1`; Windows: `ipconfig`), hoặc IP VPN nếu hai máy ở hai nơi.
IP đổi (đổi Wi-Fi, khởi động lại router): sửa lại hai dòng này rồi chạy `make link` ở máy A, máy B không phải làm gì.

## 2. Dựng hệ — `make all`

```bash
# Máy B (Windows, mở PowerShell hoặc Git Bash trong thư mục repo) — chạy TRƯỚC
make all MACHINE=B          # build image, bật phuquoc + danang, chờ sẵn sàng

# Máy A (macOS)
make all                    # venv → build → bật nhatrang, dalat, ref → secure (CA + chứng chỉ TLS cho 5 nút, kể cả máy B)
                            # → sinh dữ liệu → nạp mảnh (cả sang máy B) → postgres_fdw qua TLS + all_* → make check
                            # → make bench → mở nhập liệu + dashboard
```
Máy A tự chờ (tối đa 10 phút) đến khi kết nối được hai trạm ở máy B, nên thứ tự chạy hai lệnh không bắt buộc.
Xong: nhập liệu <http://localhost:8501>, dashboard <http://localhost:8502>. Từ máy sạch mất khoảng 3–4 phút.

**Thử trên một máy** (máy B được giả lập trên chính máy A, gọi qua cổng của máy chủ):
```bash
make all MACHINE=B DEPLOY=deploy.local.toml
make all DEPLOY=deploy.local.toml
```
Không có `make` (ví dụ Windows chưa cài GNU make), chỉ cần Docker và Python ≥ 3.11:
```bash
python tools/onebox.py                # cả hệ trên một máy (deploy.local.toml), xong mở :8501, :8502
python tools/onebox.py q Q2 Q3 -e     # chạy truy vấn demo
python tools/onebox.py stop phuquoc   # D8 … rồi: start phuquoc
python tools/onebox.py down           # gỡ hết;  --dry-run để xem trước các bước
```

## 3. Các lệnh

| Lệnh | Máy | Việc làm |
|---|---|---|
| `make up MACHINE=A\|B` | A / B | bật đúng các trạm của máy theo `deploy.toml` |
| `make secure` | A | E3: CA nội bộ + chứng chỉ cho mọi nút (khoá sinh trong container của nút), `pg_hba` chỉ nhận TLS; chạy lại được |
| `make data` | A | chạy bộ sinh của giảng viên (`--size mini` và `--size lab`, seed 402738) |
| `make load` | A | nạp `ref` (lược đồ tập trung) + chia CSV thành mảnh và nạp vào 4 trạm; đối chiếu `summary.json` |
| `make link` | A | `postgres_fdw` qua TLS `verify-full` (trạm xa: `fdw_reader` + chứng chỉ, không mật khẩu) + khung nhìn `all_<bảng>` |
| `make tls-status` / `tls-test` | A | chứng chỉ, hạn, phiên fdw / 8 phép thử (không mã hoá, gọi bằng IP, thiếu/sai chứng chỉ, thử ghi đều bị từ chối) |
| `make tls-off` | A | gỡ lỗi: tạm tắt TLS toàn hệ; bật lại `make secure && make link` |
| `make check` | A | ba quy tắc đúng đắn, PK/FK toàn hệ, jsonb ⇄ bản quan hệ (D2) |
| `make bench` | A | Q1–Q5 × {0, 30 ms}, 5 lần bỏ lần đầu lấy trung vị → `results/results.csv`, `results/explain/` |
| `make delay-on` / `delay-off` | A | bật/tắt trễ 30 ms (tc netem ở trạm trung tâm, chỉ trên đường tới trạm xa) |
| `DELAY_MODE=proxy make delay-on` | A | dự phòng khi không chạy được `tc`: proxy TCP `tools/latency_proxy.py` (cổng trạm + 100); `make delay-off` như thường |
| `make q [QUERIES="Q2 Q3"] [EXPLAIN=1]` | A | chạy Q1–Q5 cho demo, so với đối chứng, in Remote SQL |
| `make entry` / `make dash` | A | chạy giao diện nhập liệu / dashboard ở tiền cảnh |
| `make stop-site SITE=phuquoc` / `start-site` | máy chứa trạm | tắt/bật một trạm (demo D8) |
| `make status` | A / B | trạng thái các container |
| `make down [MACHINE=B]` | A / B | tắt ứng dụng, xoá container + volume của máy |

Cập nhật mã nguồn sang máy B (khi máy B chưa có git): `make sync-remote SSH=<user>@<IP máy B> DEST=C:/cs5104/de06_hotel_ddb KEY=<khoá SSH>`.
Lệnh này so mã băm script ở hai đầu sau khi chép.

Khi đổi mạng (ví dụ chuyển sang điểm phát Wi-Fi): sửa IP trong `deploy.toml` rồi chạy lại `make link` ở máy A.

## 4. Phần mở rộng (ngoài yêu cầu đề)

> Làm thêm, **không bắt buộc**, không nằm trong `make all` và không đổi kết quả D1–D8, N1–N5. Chi tiết: [docs/NANG_CAO.md](docs/NANG_CAO.md).
> Lúc demo D8 bắt buộc thì **không** bật `ext-failover`/`ext-watch` (đề muốn thấy Q2 lỗi khi trạm chết).

| Mã | Nội dung | Lệnh |
|---|---|---|
| E1 | Bản sao dự phòng (streaming replication) của `phuquoc` đặt ở máy A; trạm chính chết thì postgres_fdw chuyển sang đọc bản sao | `make ext-replica` · `ext-replica-status` · `ext-failover` · `ext-failback` · `ext-watch` · `ext-replica-down` |
| E2 | 2PC tạo đoàn tour có nhật ký điều phối bền vững; giả lập bộ điều phối chết và phục hồi giao dịch lưỡng lự | `make ext-2pc-crash CRASH=prepare\|decision\|mid-commit` · `ext-2pc-status` · `ext-2pc-recover [FORCE=1]` |
| — | So sánh phương án E1/E2 (sync/async, đọc chính/bản sao, chi phí 2PC) | `make ext-bench` → `results/ext/ext_bench.csv` |

E1, E2 chạy ở máy A và đã được thử lại khi TLS bắt buộc (bản sao E1 nhận WAL qua TLS; failover đổi bản ghi DNS nội bộ).

### Bảo mật đường truyền (E3) — mặc định, chi tiết ở [docs/BAO_MAT.md](docs/BAO_MAT.md)
`make all` đã gồm `make secure`. Mỗi nút có chứng chỉ máy chủ `<nút>.db.nhom8.internal` do CA nội bộ ký; khoá riêng sinh trong container
của nút và không rời khỏi đó (nút ở máy B được điều khiển qua kênh quản trị SQL; lệnh `openssl` vẫn chạy trong container ở máy B).

**Chế độ chặt** (không ai cần quyền superuser qua mạng) — mỗi máy tự làm phần của mình:
```bash
make tls-site-csr                    # mỗi máy: khoá + CSR -> build/e3/exchange/*.csr   (máy A thêm: CLIENT=1)
make tls-sign                        # máy A: ký các CSR đã chép sang (container dùng một lần, không mạng)
make tls-site-install                # mỗi máy: sau khi chép <nút>.crt + ca.crt về build/e3/exchange/   (máy A thêm: CLIENT=1)
make link                            # máy A
make tls-site-status                 # mỗi máy · gia hạn: tls-site-csr ROTATE=1 → tls-sign → tls-site-install
```
Trên máy B (Windows), các lệnh `tls-site-*` chỉ cần Python, không cần venv; khi điều khiển qua SSH thì gọi
`powershell -File C:\cs5104\runB.ps1 <target>` (script bỏ credential helper của Docker, vốn lỗi trong phiên SSH).

## 5. Cấu trúc thư mục

```
deploy.toml / deploy.local.toml   trạm → máy, IP, cổng
Makefile                          các lệnh bắt buộc
docker/Dockerfile                 postgres:18 + iproute2 (tc netem)
datagen/de06_hotel/generate.py    bộ sinh của giảng viên — KHÔNG SỬA (sha1 528a57d7…)
sql/schema_central.sql            lược đồ tập trung (CSDL đối chứng)
sql/site_schema.sql               lược đồ một trạm: mảnh + CHECK + FK + sequence + khung nhìn cục bộ
sql/generated_link.sql            (sinh ra) SQL postgres_fdw + all_* ở trạm trung tâm
sql/queries/                      q1..q5 (bản phân tán), *_ref.sql (bản đối chứng), biến thể so sánh, q3_single (đoàn một vùng)
tools/                            deploy, split, load, link, check, bench, delay, demo, apps, rtt_slope (đo số vòng khứ hồi)
                                  onebox.py (chạy thử một máy, không cần make), latency_proxy.py (trễ dự phòng)
                                  sync_remote.py (cập nhật mã nguồn sang máy khác qua SSH)
                                  tls.py (E3: CA, ký, make secure, thử), tls_site.py (E3: một nút, chạy được tại từng máy)
                                  phần mở rộng: ext_replica.py (E1), twopc.py (E2), ext_bench.py
app/                              entry.py (nhập liệu), dash.py (dashboard) — Streamlit
results/                          results.csv, explain/, n1/n4/n5_*.csv, check.txt, ext/ (nhật ký phần mở rộng)
docs/                             BAO_CAO.md / .pdf, BAO_MAT.md (E3), NANG_CAO.md (phần mở rộng), KIEN_THUC_BAO_VE.md, ảnh giao diện
build/                            (sinh ra, không vào git) image context, mảnh CSV, PKI của E3 (build/e3/: khoá CA)
```

## 6. Nguồn gốc của branch này

Branch `nhom8-de06-hotel-ddb` thay toàn bộ cây thư mục của `main` (bản thử nghiệm ban đầu) bằng bản `de06_hotel_ddb`,
là bản đã chạy `make all` và đo trên hai máy thật. Branch giữ lại các ý hay của `main`: `onebox.py`, proxy trễ dự phòng
và phép so sánh Q3 giữa đoàn một vùng và đoàn nhiều vùng. Sau đó thêm E3 (TLS + chứng chỉ) và đưa E3 thành mặc định của hệ.

## 7. Sử dụng công cụ AI

Nhóm dùng trợ lý AI (Claude Code) để hỗ trợ viết mã (Python, SQL, Makefile) và soạn tài liệu. Toàn bộ thiết kế phân tán,
mã nguồn và số liệu đã được nhóm kiểm tra, chạy lại và giải thích được; số liệu tái lập được bằng bộ sinh của
giảng viên với seed cố định của đề.

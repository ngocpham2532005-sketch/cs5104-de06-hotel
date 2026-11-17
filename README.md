# CS5104 · Đề 6 · Chuỗi khách sạn nghỉ dưỡng — CSDL phân tán 4 trạm trên 2 máy

Bốn trạm PostgreSQL 18 (`dalat`, `nhatrang` (trung tâm), `phuquoc`, `danang`), mỗi vùng một trạm, chạy trên
**máy A (macOS)** và **máy B (Windows)**. Trạm trung tâm truy vấn xuyên trạm bằng `postgres_fdw` qua các
khung nhìn toàn cục `all_<bảng>`; có giao diện nhập liệu và dashboard theo dõi từng trạm.

| Máy | Hệ điều hành | Chạy | Cổng |
|---|---|---|---|
| A | macOS | `nhatrang` (trung tâm), `dalat`, `ref` (CSDL đối chứng), nhập liệu, dashboard | 5433, 5434, 5440, 8501, 8502 |
| B | Windows 10/11 | `phuquoc`, `danang` | 5435, 5436 |

**Nhóm 8** · Đào Minh Hùng (2632006) · Phạm Thị Kim Ngọc (2532005) · Nguyễn Khánh Hòa (2532018) · Vương Thảo Nguyên (2532013)
· Đề 6, seed 402738 · Mã nguồn: <https://github.com/ngocpham2532005-sketch/cs5104-de06-hotel>, branch `nhom8-de06-hotel-ddb`
(bản nộp sẽ gắn tag `final`).

Tài liệu: [IMPLEMENT.md](IMPLEMENT.md) (thiết kế và cách cài đặt chi tiết) · [docs/BAO_CAO.md](docs/BAO_CAO.md) (báo cáo, bản PDF ở `docs/BAO_CAO.pdf`)
· [docs/NANG_CAO.md](docs/NANG_CAO.md) (**phần mở rộng, ngoài yêu cầu đề**) · [docs/KIEN_THUC_BAO_VE.md](docs/KIEN_THUC_BAO_VE.md) (ôn tập bảo vệ, nội bộ).

**Kết quả chính** (hai máy thật qua Wi-Fi LAN, chi tiết ở báo cáo mục 5):

| | Kết quả |
|---|---|
| Nạp dữ liệu | 190.831 dòng, từng mảnh khớp `summary.json`; tổng các mảnh = CSDL đối chứng |
| `make check` | ĐẠT 103/103 (ba quy tắc đúng đắn, PK/FK toàn hệ, jsonb ⇄ bản quan hệ) |
| Q1–Q5 | giống hệt CSDL đối chứng; Q1 chạy trọn tại `dalat` (0 Foreign Scan) |
| Trễ 30 ms | Q1 0,5 ms (không đổi); Q2 436 ms, Q3 423 ms, Q4 449 ms, Q5 438 ms (≈ 11 vòng khứ hồi) |
| Dòng liên vùng | 5.144 / 80.000 = 6,43%; Q3 của đoàn một vùng tốn ngang đoàn ba vùng (426 / 428 ms) |

---

## 1. Chuẩn bị (làm một lần)

**Cả hai máy:** Docker Desktop (đang chạy), Python ≥ 3.11, GNU make, git.

**Mạng giữa hai máy** — máy A phải mở được kết nối TCP tới cổng 5435, 5436 của máy B:

| Hai máy ở đâu | Cách nối | Dùng cho |
|---|---|---|
| Cùng một mạng LAN hoặc Wi-Fi (kể cả hai băng 2.4/5 GHz của **cùng một router**) | không cần gì thêm | **demo D1–D8 và số đo trong báo cáo** (cách đề yêu cầu) |
| Cùng điểm phát Wi-Fi của điện thoại | không cần gì thêm | phương án dự phòng khi demo |
| Hai nơi khác nhau (hai router, hai Wi-Fi khác mạng) | VPN: WireGuard site-to-site, hoặc Tailscale/Headscale; ghi **IP VPN** của mỗi máy vào `deploy.toml` | phát triển, chạy thử từ xa; nên bật thêm **E3** (TLS + chứng chỉ, mục 4) |

Lưu ý khi hai máy ở hai nơi:
- Trễ thật của Internet (thường 10–50 ms) cộng thêm vào 30 ms giả lập, nên số đo **không so được** với Bảng 3 của báo cáo. Số liệu nộp bài đo trên cùng một LAN.
- **Không** mở cổng router để đưa PostgreSQL ra Internet: mật khẩu mặc định nằm trong repo.
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
make all                    # venv → build → bật nhatrang, dalat, ref → sinh dữ liệu → nạp mảnh (cả sang máy B)
                            # → postgres_fdw + all_* → make check → make bench → mở nhập liệu + dashboard
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
| `make data` | A | chạy bộ sinh của giảng viên (`--size mini` và `--size lab`, seed 402738) |
| `make load` | A | nạp `ref` (lược đồ tập trung) + chia CSV thành mảnh và nạp vào 4 trạm; đối chiếu `summary.json` |
| `make link` | A | `postgres_fdw` ở trạm trung tâm + khung nhìn `all_<bảng>` |
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
| E3 | Đường postgres_fdw kiểu production khi các trạm ở các nơi khác nhau: CA nội bộ, TLS `verify-full` + chứng chỉ máy khách, tên DNS nội bộ, role `fdw_reader` chỉ đọc, không mật khẩu | lab: `make ext-secure` · `ext-secure-status` · `ext-secure-test` · `ext-secure-bench` · `ext-secure-down` <br> PRD (khoá không rời trạm): mỗi máy `ext-secure-site-csr` → máy A `ext-secure-sign` → mỗi máy `ext-secure-site-install` → máy A `ext-secure-link` |
| — | So sánh phương án E1/E2 (sync/async, đọc chính/bản sao, chi phí 2PC) | `make ext-bench` → `results/ext/ext_bench.csv` |

E1, E2 và E3 chế độ lab chỉ chạy ở máy A. **E3 chế độ PRD** chạy ở cả hai máy, mỗi máy chỉ thao tác trên trạm của mình:
```bash
# 0. (máy A) cập nhật mã nguồn sang máy B
make sync-remote SSH=<user>@<IP máy B> DEST=C:/cs5104/de06_hotel_ddb KEY=<khoá SSH>
# 1. (máy A) CA nội bộ — một lần
make ext-secure-ca-init
# 2. (mỗi máy) sinh khoá TRONG container của trạm + CSR -> build/e3/exchange/*.csr
make ext-secure-site-csr                    # máy B: phuquoc, danang · máy A: dalat
make ext-secure-site-csr CLIENT=1           # máy A: chứng chỉ máy khách fdw_reader cho trạm trung tâm
# 3. chép *.csr của máy B sang build/e3/exchange/ của máy A, rồi (máy A) ký
make ext-secure-sign
# 4. chép <trạm>.crt + ca.crt về build/e3/exchange/ của máy B, rồi (mỗi máy) cài
make ext-secure-site-install                 # máy A thêm: make ext-secure-site-install CLIENT=1
# 5. (máy A) nối postgres_fdw bằng TLS + chứng chỉ, kiểm tra
make ext-secure-link && make ext-secure-test && make check
# trạng thái / gia hạn / gỡ
make ext-secure-site-status                  # cảnh báo khi chứng chỉ còn < 30 ngày
make ext-secure-site-csr ROTATE=1            # gia hạn: rồi sign → install như trên
make ext-secure-site-uninstall               # mỗi máy; sau đó (máy A) make ext-secure-down
```
Trên máy B (Windows), các lệnh `ext-secure-site-*` chỉ cần Python, không cần venv. Khi điều khiển qua SSH, gọi qua
`powershell -File C:\cs5104\runB.ps1 <target>` (script bỏ credential helper của Docker, vốn lỗi trong phiên SSH).
CSR và chứng chỉ là dữ liệu công khai, chép bằng scp, USB hoặc git đều được; khoá riêng không bao giờ rời container của trạm.

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
                                  phần mở rộng: ext_replica.py (E1), twopc.py (E2), ext_bench.py,
                                  ext_secure.py (E3: lab, CA, ký, nối fdw), ext_secure_site.py (E3 PRD, chạy tại từng máy)
app/                              entry.py (nhập liệu), dash.py (dashboard) — Streamlit
results/                          results.csv, explain/, n1/n4/n5_*.csv, check.txt, ext/ (nhật ký phần mở rộng)
docs/                             BAO_CAO.md / .pdf, NANG_CAO.md (phần mở rộng), KIEN_THUC_BAO_VE.md, ảnh giao diện
build/                            (sinh ra, không vào git) image context, mảnh CSV, PKI của E3 (build/e3/: khoá CA)
```

## 6. Nguồn gốc của branch này

Branch `nhom8-de06-hotel-ddb` thay toàn bộ cây thư mục của `main` (bản thử nghiệm ban đầu) bằng bản `de06_hotel_ddb`,
là bản đã chạy `make all` và đo trên hai máy thật. Branch giữ lại các ý hay của `main`: `onebox.py`, proxy trễ dự phòng
và phép so sánh Q3 giữa đoàn một vùng và đoàn nhiều vùng. Sau đó bổ sung phần mở rộng E3.

## 7. Sử dụng công cụ AI

Nhóm dùng trợ lý AI (Claude Code) để hỗ trợ viết mã (Python, SQL, Makefile) và soạn tài liệu. Toàn bộ thiết kế phân tán,
mã nguồn và số liệu đã được nhóm kiểm tra, chạy lại và giải thích được; số liệu tái lập được bằng bộ sinh của
giảng viên với seed cố định của đề.

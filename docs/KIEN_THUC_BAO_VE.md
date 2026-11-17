# Kiến thức cần nắm để báo cáo và bảo vệ — CS5104 · Đề 6

> Tài liệu ôn tập nội bộ của nhóm, không nộp. Đề yêu cầu **mọi thành viên hiểu toàn bộ hệ**, vì giảng viên chỉ định
> người trả lời và điểm vấn đáp tính chung cho cả nhóm. Mỗi người nên đọc hết, rồi tự trả lời các câu ở Mục 9
> mà không nhìn đáp án.
>
> Số liệu trong tài liệu đo trên **hai máy thật**: máy A macOS 192.168.100.218, máy B Windows 192.168.100.198, nối cùng mạng Wi-Fi.
> Nguồn: `results/results.csv`, `results/rtt_slope.txt`, `results/n4_cross.csv`, `results/n5_storage.csv`;
> phần mở rộng: `results/ext/` (Mục 14).
>
> **Phần mở rộng E1, E2 (Mục 14) là làm thêm, ngoài yêu cầu đề.** Đọc phần bắt buộc (Mục 0–13) cho chắc trước, rồi mới đọc Mục 14.

---

## Mục lục

0. [Đề chấm gì → cần nắm gì](#0-đề-chấm-gì--cần-nắm-gì)
1. [Hệ của nhóm trong 1 phút](#1-hệ-của-nhóm-trong-1-phút)
2. [Nền tảng lý thuyết (giáo trình)](#2-nền-tảng-lý-thuyết-giáo-trình)
3. [Thiết kế phân tán và lập luận](#3-thiết-kế-phân-tán-và-lập-luận)
4. [Hiện thực kỹ thuật](#4-hiện-thực-kỹ-thuật)
5. [Năm truy vấn Q1–Q5](#5-năm-truy-vấn-q1q5)
6. [Năm con số N1–N5 và lời giải thích](#6-năm-con-số-n1n5-và-lời-giải-thích)
7. [Tám thao tác demo D1–D8](#7-tám-thao-tác-demo-d1d8)
8. [Giới hạn, đánh đổi và hướng mở rộng](#8-giới-hạn-đánh-đổi-và-hướng-mở-rộng)
9. [Ngân hàng câu hỏi vấn đáp](#9-ngân-hàng-câu-hỏi-vấn-đáp)
10. [Bảng số phải thuộc](#10-bảng-số-phải-thuộc)
11. [Hiểu lầm hay gặp](#11-hiểu-lầm-hay-gặp)
12. [Thuật ngữ Anh – Việt](#12-thuật-ngữ-anh--việt)
13. [Tự kiểm tra trước buổi bảo vệ](#13-tự-kiểm-tra-trước-buổi-bảo-vệ)
14. [Phần mở rộng E1, E2 — ngoài yêu cầu đề](#14-phần-mở-rộng-e1-e2--ngoài-yêu-cầu-đề)

---

## 0. Đề chấm gì → cần nắm gì

| Phần | Điểm | Giảng viên nhìn vào | Phải nắm chắc |
|---|---:|---|---|
| **M1** Thiết kế phân tán | 1,5 | Báo cáo mục 1 | Chia từng bảng thế nào và vì sao; cấp phát; khoá chính toàn cục; khoá ngoại sau khi chia; CHECK mảnh và CHECK jsonb; dòng liên vùng |
| **M2** Hệ chạy được | 3,5 | Demo D1–D8 trên **≥ 2 máy** | Thao tác thuần thục, biết điều phải thấy và cách nói. Chỉ chạy trên một máy thì M2 tối đa 1,75; không dựng được thì tối đa 0,75 |
| **M3** Số liệu, báo cáo, slide | 2,5 | Báo cáo mục 5, slide 4 phút | Cách đo (5 lần, bỏ lần đầu, trung vị); giải thích N1–N5 bằng **số vòng khứ hồi** và **lượng dữ liệu truyền** |
| **M4** Vấn đáp | 2,5 | 9 phút, hỏi từng người | Toàn bộ Mục 2–8 của tài liệu này |

Buổi bảo vệ 25 phút: **demo 12 phút → slide N1–N5 4 phút → vấn đáp 9 phút.**

Sáu ràng buộc thiết kế bắt buộc của đề. Bị hỏi "đã thoả chưa, chứng minh ở đâu" thì phải chỉ ra được ngay:

| # | Ràng buộc | Nhóm thoả bằng | Chứng minh bằng |
|---|---|---|---|
| 1 | Mỗi trạm giữ dữ liệu vùng mình | `hotel` ngang theo `region`, các bảng con dẫn xuất | Dashboard, `n1_fragments.csv` |
| 2 | Đầy đủ, tái tạo được, rời nhau | `make check` nhóm A | `results/check.txt` (103 phép kiểm tra, đều bằng 0) |
| 3 | Q1 chạy trọn tại một trạm | Q1 chỉ dùng bảng cục bộ của dalat | `make q QUERIES=Q1 EXPLAIN=1`: không có Foreign Scan |
| 4 | Trung tâm trả lời Q1–Q5 giống đối chứng | `all_*` + truy vấn hai giai đoạn | Bench so khớp từng dòng với `ref` (cột `matches_ref`) |
| 5 | Giữ hoặc kiểm tra được mọi PK, FK | FK khai báo thật tại trạm; PK toàn cục bằng dải ID | `make check` nhóm C, D (và E cho jsonb ↔ quan hệ) |
| 6 | Không thêm, bớt, đổi tên bảng hay cột | Chỉ thêm CHECK, chỉ mục, sequence (DEFAULT), khung nhìn | So `site_schema.sql` với `schema_central.sql` |

---

## 1. Hệ của nhóm trong 1 phút

> Thuộc lòng đoạn này để mở đầu demo hoặc trả lời câu "tóm tắt thiết kế của nhóm".

"Đề 6 là chuỗi khách sạn ở 4 vùng. Mỗi vùng là một trạm PostgreSQL 18: **dalat, nhatrang (trung tâm), phuquoc, danang**.
**Máy A (macOS)** chạy nhatrang, dalat, CSDL đối chứng `ref`, giao diện nhập liệu và dashboard.
**Máy B (Windows)** chạy phuquoc và danang.

- `hotel` được **phân mảnh ngang theo `region`**.
- `room`, `booking`, các bảng `req_*` được **phân mảnh ngang dẫn xuất** theo chuỗi khoá ngoại. Vì vậy mỗi lượt đặt nằm ở
  **trạm của khách sạn**, và mọi khoá ngoại đều cục bộ.
- `room_type` và `tour_group` nhỏ, được mọi vùng tham chiếu, nên được **sao chép ra cả 4 trạm**. Đoàn mới được ghi bằng **cam kết hai pha**.
- Khoá chính toàn cục: **mỗi trạm có một dải `booking_id` riêng**, được ép bằng CHECK.
- Trạm trung tâm dùng **postgres_fdw**, có 7 khung nhìn `all_<bảng>`. Hai khung nhìn cục bộ ở mỗi trạm giúp đẩy nguyên phép gộp xuống trạm xa.

Kết quả:
- Q1 chạy trọn tại dalat (0,5 ms, không đổi khi bật trễ).
- Q2–Q5 hỏi song song 3 trạm xa, mất khoảng **11 vòng khứ hồi**, khoảng 430 ms ở trễ 30 ms.
- Mọi truy vấn cho kết quả giống hệt CSDL đối chứng."

---

## 2. Nền tảng lý thuyết (giáo trình)

### 2.1. CSDL phân tán và cái giá của mạng (Chương 1)

- **CSDL phân tán:** tập dữ liệu có liên quan logic, nằm trên nhiều trạm nối mạng. Hệ quản trị làm cho người dùng thấy như một CSDL duy nhất (**minh bạch**).
  Bốn lời hứa của hệ: minh bạch (về vị trí, phân mảnh, nhân bản), tin cậy, hiệu năng (dữ liệu gần nơi dùng), dễ mở rộng.
- **Công thức (1.1), trục của mọi lời giải thích số liệu:**

  **T ≈ (số vòng khứ hồi) × RTT + (thời gian xử lý) + (thời gian truyền dữ liệu)**

  Ở khoảng cách xa, số hạng đầu lấn át hai số hạng sau. Không có cách nào giảm RTT, chỉ có thể **giảm số vòng**.
- **Một truy vấn tối thiểu qua postgres_fdw tốn 5 vòng khứ hồi** (Hình 1.2): `START TRANSACTION` → `DECLARE CURSOR`
  → `FETCH` → `CLOSE` → `COMMIT`. Nhóm đo lại được: lượt hỏi tối thiểu ở trễ 30 ms mất 163 ms (dalat) và 202 ms (máy B);
  số vòng đo được 4,7–5,3.
- **fetch_size:** mặc định postgres_fdw lấy 100 dòng một lần, nên kéo N dòng tốn N/100 lần FETCH. Bảng 1.2 của giáo trình:
  7.581 dòng mất 2,7 s, tăng `fetch_size` lên 10.000 thì còn 0,22 s. Nhóm đặt `fetch_size 10000`, và giữ một biến thể
  `naive_fetch100` để so sánh: 8.084 ms ở trễ 30 ms.
- **Bài học "thử trên một máy rồi kết luận nhanh" là sai:** trên một máy thì RTT ≈ 0. Đây là lý do đề bắt dựng trên ≥ 2 máy
  và giả lập trễ 30 ms.

### 2.2. Phân mảnh, cấp phát (Chương 2)

| Cách | Định nghĩa | Đại số quan hệ | Trong Đề 6 |
|---|---|---|---|
| **Ngang chính** | Chia dòng theo vị từ trên chính bảng | Rᵢ = σ_pᵢ(R) | `hotel`: σ(region = 'dalat'), … |
| **Ngang dẫn xuất** | Chia bảng con theo cách chia của bảng cha (qua khoá ngoại) | Sᵢ = S ⋉ Rᵢ (**semijoin**) | `room ⋉ hotel`, `booking ⋉ room`, `req_* ⋉ booking`, `req_family_child ⋉ req_family` |
| **Dọc** | Chia cột; mỗi mảnh giữ khoá chính | Π_{K,A}(R) | Không dùng. Đề không cho đổi bảng/cột; tách `request` không có lợi gì |
| **Hỗn hợp** | Ngang rồi dọc, hoặc ngược lại | | Không dùng |
| **Sao chép** | Mỗi trạm giữ một bản đầy đủ | | `room_type`, `tour_group` |

**Ba quy tắc đúng đắn (Mục 2.2)** — `make check` kiểm tra đủ cả ba:
1. **Đầy đủ (completeness):** mọi dòng của R nằm trong ít nhất một mảnh.
   Kiểm tra: dòng của `ref` không có ở trạm nào = 0.
2. **Tái tạo được (reconstruction):** R = ∪ Rᵢ (ngang). Kiểm tra hai chiều bằng `EXCEPT ALL`:
   `ref EXCEPT ALL (∪ mảnh)` = 0 và `(∪ mảnh) EXCEPT ALL ref` = 0. Dùng `ALL` để bắt cả dòng trùng.
3. **Rời nhau (disjointness):** một dòng chỉ nằm trong một mảnh. Kiểm tra: khoá nằm ở ≥ 2 trạm = 0.
   Riêng bảng sao chép thì được phép trùng: kiểm tra 4 bản giống hệt `ref`.

**Vị từ đơn giản, đầy đủ và tối giản:** tập vị từ {region = 'dalat', 'nhatrang', 'phuquoc', 'danang'} **đầy đủ**, vì mọi khách sạn
thuộc đúng một trong 4 vùng (bộ sinh bảo đảm). Nó cũng **tối giản**, vì mỗi vị từ có truy vấn dùng riêng: Q1 lọc dalat, Q2 gộp theo region.

**Phân mảnh dẫn xuất đúng khi nào?** Khi khoá ngoại của con **NOT NULL** và trỏ tới đúng một cha. Trong đề, `room.hotel_id`,
`booking.room_id` và `req_*.booking_id` đều NOT NULL, nên semijoin chia con thành các mảnh vừa đầy đủ vừa rời nhau.
Nếu FK cho phép NULL, dòng có FK NULL sẽ không vào mảnh nào, và quy tắc đầy đủ bị vi phạm.

**Cấp phát (Mục 2.7):** đặt mảnh **gần nơi dùng nhiều nhất** (nơi phát sinh lượt đặt là khách sạn của vùng). Bảng nhỏ,
ít đổi, được đọc khắp nơi thì sao chép.

**Phân mảnh theo khoá (hash, Citus — Mục 2.8–2.9):** chia đều tải nhưng mất tính cục bộ theo vùng. Q1 sẽ phải hỏi mọi shard.
Đề yêu cầu "mỗi trạm giữ dữ liệu vùng mình", nên không dùng cách này.

### 2.3. Xử lý truy vấn phân tán (Chương 3)

- **Bốn bước:** phân rã truy vấn → **định vị dữ liệu** (đổi bảng toàn cục thành hợp các mảnh, loại mảnh chắc chắn rỗng) →
  **tối ưu toàn cục** (thứ tự nối, nơi thực hiện, giảm dữ liệu truyền) → tối ưu cục bộ tại từng trạm.
- **Định vị và rút gọn:** với mảnh ngang, nếu vị từ của truy vấn mâu thuẫn với vị từ của mảnh thì loại mảnh đó.
  Ví dụ: Q1 lọc `region = 'dalat'`, nên chỉ cần mảnh dalat. Với mảnh dẫn xuất, phép nối `booking ⋈ room ⋈ hotel` chỉ cần nối
  **mảnh cùng chỉ số**: booking_i ⋈ room_i ⋈ hotel_i. Không có cặp chéo, vì dòng con luôn cùng trạm với dòng cha.
- **Giảm dữ liệu truyền:**
  - **Đẩy xuống (pushdown):** WHERE, JOIN, GROUP BY, ORDER BY, LIMIT được gửi sang trạm xa, chỉ kết quả đi về.
  - **Gộp hai giai đoạn (Mã 3.2):** mỗi trạm tự `GROUP BY` (giai đoạn 1); trung tâm cộng dồn (giai đoạn 2).
    Q2 của nhóm dùng đúng mẫu này: mỗi trạm trả 15 dòng thay vì hàng chục nghìn.
  - **Semijoin:** gửi trước cột khoá để lọc bớt bên kia rồi mới gửi dữ liệu. Nhóm không cần, vì mọi phép nối đã là cục bộ trong từng trạm.
- **postgres_fdw đẩy được gì (Mục 3.5):** toán tử và hàm **có sẵn, IMMUTABLE** (kể cả `@>`, `@?`, `->>` của jsonb); JOIN giữa các bảng ngoài
  **cùng một server**; phép gộp. **Không** đẩy được: hàm do người dùng viết (trừ khi khai báo `extensions`), và JOIN giữa hai server khác nhau.
- **Đọc EXPLAIN (VERBOSE):**
  - `Foreign Scan` là một lượt hỏi trạm xa. `Async Foreign Scan` là các nhánh được hỏi song song.
  - Dòng `Remote SQL:` là câu SQL **thật sự** gửi đi, cho biết điều kiện nào được đẩy.
  - `Relations: Aggregate on (s_dalat.booking_detail)` nghĩa là phép gộp đã được đẩy xuống.
  - `Relations: (s_x.booking b) INNER JOIN (s_x.room r)` nghĩa là phép nối đã được đẩy xuống.

### 2.4. Giao dịch phân tán và cam kết hai pha (Chương 4)

- **ACID:** nguyên tử, nhất quán, cô lập, bền vững. **Khoá hai pha (2PL):** pha xin khoá rồi pha nhả khoá; bảo đảm khả tuần tự.
- **Cam kết hai pha (2PC):**
  - Pha 1 (bỏ phiếu): bộ điều phối gửi PREPARE. Mỗi bên tham gia ghi "sẵn sàng" xuống nhật ký rồi trả lời YES hoặc NO.
  - Pha 2 (quyết định): tất cả YES thì COMMIT, có một NO hoặc quá hạn thì ABORT. Bộ điều phối **ghi quyết định vào nhật ký trước** khi gửi.
- **Vì sao 2PC có thể bị treo (blocking, Mục 4.4.2):** nếu bộ điều phối chết sau khi các bên đã PREPARE, các bên không tự quyết được.
  Chúng vẫn giữ khoá và phải chờ bộ điều phối sống lại. Đây là "giao dịch lưỡng lự" (in-doubt).
- **Trong PostgreSQL (Mục 4.5):**
  - Ba lệnh của bên tham gia: `PREPARE TRANSACTION 'gid'`, `COMMIT PREPARED 'gid'`, `ROLLBACK PREPARED 'gid'`.
  - Cần `max_prepared_transactions > 0`; mặc định là 0. Nhóm đặt bằng 20 khi `docker run`.
  - Xem giao dịch đang treo bằng `SELECT * FROM pg_prepared_xacts`.
- **Trong hệ của nhóm:**
  - Tab "Đoàn tour" của giao diện nhập liệu là bộ điều phối, dùng `tpc_begin` / `tpc_prepare` / `tpc_commit` của psycopg.
  - Mở kết nối tới **cả 4 trạm**; trạm nào không kết nối được thì huỷ ngay, chưa ghi gì.
  - Lấy `tour_group_id` mới từ sequence ở trung tâm (bắt đầu từ 100001, nên không đụng ID của bộ sinh).
  - INSERT rồi PREPARE ở từng trạm, sau đó COMMIT PREPARED ở tất cả. Lỗi ở **pha 1** thì ROLLBACK PREPARED các trạm đã PREPARE.
  - Từ khi có phần mở rộng E2 (`tools/twopc.py`), bộ điều phối **ghi nhật ký** `begin` → `commit` → `end` (fsync) vào
    `results/2pc_coordinator.jsonl`. Ghi `commit` là **điểm cam kết**. Sau điểm đó, lỗi ở pha 2 **không bao giờ** dẫn tới rollback:
    trạm lỗi được để lại cho `make ext-2pc-recover` commit sau. Bản trước E2 có lỗi rollback ở pha 2, làm mất tính nguyên tử (Mục 14.2).
- **`parallel_commit` của postgres_fdw** không phải 2PC. Nó chỉ gửi COMMIT tới các trạm xa **song song** để bớt vòng khứ hồi.
  postgres_fdw **không** bảo đảm nguyên tử giữa các trạm khi ghi; nhóm không ghi qua fdw.

### 2.5. Sao chép và nhất quán (Chương 5–6)

- **Bảng bốn ô (Mục 5.2):** *khi nào* đồng bộ (đồng bộ ngay — eager, hay đồng bộ sau — lazy) × *ở đâu* được ghi
  (một nút chủ — primary copy, hay ghi ở bất kỳ đâu — update anywhere).
- **Bảng sao chép của nhóm thuộc ô "đồng bộ ngay":** đoàn mới được ghi vào cả 4 bản trong một giao dịch 2PC.
  Bộ điều phối duy nhất là giao diện nhập liệu, và ID lấy từ một nguồn (sequence trung tâm), nên gần với primary copy.
  - Ưu: 4 bản luôn giống nhau. `make check` nhóm B kiểm tra điều này sau D7.
  - Nhược: **một trạm chết thì không tạo được đoàn mới.** Hệ ưu tiên nhất quán hơn sẵn sàng (C thay vì A trong CAP),
    chấp nhận được vì bảng ít khi được ghi.
- **CAP / PACELC (Mục 6.3):** khi mạng bị chia cắt (P), phải chọn nhất quán (C) hoặc sẵn sàng (A). Khi không có sự cố (E),
  phải chọn độ trễ (L) hoặc nhất quán (C). Với `tour_group`, nhóm chọn **PC/EC**: luôn nhất quán, chịu trễ thêm 2 vòng
  của 2PC và chịu mất sẵn sàng khi có trạm chết.
- **Ngưỡng R + W > N (Mục 6.4):** ghi cả 4 bản (W = 4) thì đọc một bản bất kỳ (R = 1) đã luôn thấy giá trị mới. Hệ của nhóm đúng là như vậy.
- `room_type` chỉ được nạp lúc đầu, không có đường ghi, nên chỉ cần sao chép tĩnh.
- **Sao chép vật lý (streaming replication) của PostgreSQL**, dùng ở phần mở rộng E1: trạm chính gửi luồng WAL (nhật ký ghi trước)
  cho bản sao. Bản sao phát lại WAL và cho đọc trong lúc đó (*hot standby*), nhưng không cho ghi. Mặc định là **bất đồng bộ** (lazy, primary copy):
  COMMIT ở trạm chính không chờ bản sao. `synchronous_commit = on | remote_apply` cùng với `synchronous_standby_names` thì thành **đồng bộ** (eager).
  Bảng sao chép `tour_group` của nhóm cũng là eager, nhưng làm ở mức **giao dịch ứng dụng** (2PC), không ở mức WAL.

### 2.6. jsonb so với bản quan hệ (Chương 8)

- **Mô hình tài liệu (Mục 8.3):** dữ liệu nhúng thì đọc một lần là đủ; dữ liệu tham chiếu thì phải nối.
  Cột `request` là phần nhúng; `req_*` là bản tham chiếu tương đương.
- **jsonb trong PostgreSQL (Mục 8.4):**
  - Dạng nhị phân, đã phân tích sẵn, khoá được sắp xếp, không giữ khoảng trắng hay khoá trùng.
  - **Mỗi giá trị lặp lại tên khoá**, nên thường lớn hơn bản quan hệ về phần dữ liệu.
- **Toán tử cần biết:**

| Toán tử | Ý nghĩa | Dùng ở đâu |
|---|---|---|
| `->`, `->>` | lấy giá trị (jsonb / text) | Q3 `request ->> 'meal_plan'`; CHECK |
| `?`, `?&`, `?\|` | có khoá / có đủ các khoá / có ít nhất một khoá | CHECK `request ?& ARRAY['group_code', …]` |
| `@>` | chứa (containment) | Q4 `request @> '{"airport_pickup": true}'` |
| `@?` | jsonpath có trả về phần tử nào không | Q4 `request @? '$.children_ages[*] ? (@ < 6)'` |
| `jsonb_typeof` | kiểu của giá trị | CHECK kiểu boolean/array |

- **Chỉ mục GIN:**
  - `jsonb_ops` (mặc định): lập chỉ mục từng khoá và từng giá trị riêng. Hỗ trợ `?`, `?&`, `?|`, `@>`, `@?`, `@@`. Lớn hơn.
  - `jsonb_path_ops`: lưu **băm của cả đường dẫn + giá trị**. Chỉ hỗ trợ `@>`, `@?`, `@@`. Nhỏ hơn và thường nhanh hơn cho `@>`.
  - GIN chỉ lọc được phần **so sánh bằng hoặc tồn tại**. Điều kiện khoảng (`@ < 6`) không lập chỉ mục được,
    nên phải kiểm tra lại (*Recheck*) trên dòng thật.

---

## 3. Thiết kế phân tán và lập luận

### 3.1. Bảng quyết định cho từng bảng

| Bảng | Cách chia | Vị từ / theo bảng | Lý do |
|---|---|---|---|
| `hotel` (60) | **Ngang chính** | `region = '<trạm>'` | Đề nói dữ liệu khách sạn lưu tại vùng của nó; `region` có sẵn và là "vùng = trạm" |
| `room` (6.000) | **Ngang dẫn xuất** | `room ⋉ hotel` | Phòng thuộc khách sạn; Q1 cần phòng cùng chỗ với khách sạn để tính số đêm có thể bán |
| `booking` (80.000) | **Ngang dẫn xuất** | `booking ⋉ room` (vùng **khách sạn**) | Lượt đặt phát sinh tại khách sạn; Q1, Q2 tính theo khách sạn/vùng, nên giữ được tính cục bộ |
| `req_tour`, `req_business`, `req_family` | **Ngang dẫn xuất** | `req_* ⋉ booking` | Quan hệ 1 – 0..1 với booking; luôn đọc cùng booking (Q5) |
| `req_family_child` | **Ngang dẫn xuất** (nối tiếp) | `req_family_child ⋉ req_family` | FK của nó trỏ tới `req_family` (theo Hình 6.1) |
| `room_type` (15) | **Sao chép** ra 4 trạm | — | Rất nhỏ, không đổi, được `room` ở mọi vùng tham chiếu (FK), được Q2 dùng để lấy tên loại phòng |
| `tour_group` (800) | **Sao chép** ra 4 trạm | — | Nhỏ; một đoàn có phòng ở nhiều vùng nên không đặt vào vùng nào được; sao chép giữ FK `booking.tour_group_id` cục bộ |

### 3.2. Câu hỏi lớn nhất: vì sao chia `booking` theo vùng khách sạn, không theo đoàn hay theo khách?

| Phương án | Q1 | Q2 | Q3 | Khoá ngoại | Kết luận |
|---|---|---|---|---|---|
| **Theo vùng khách sạn (đã chọn)** | cục bộ ✓ | mỗi trạm tự gộp ✓ | hỏi 4 trạm (≈ 11 vòng) | `booking → room` cục bộ ✓ | Đáp ứng ràng buộc 3; 4/5 truy vấn có lợi |
| Theo đoàn tour | **phải qua mạng** ✗ (6,4% lượt đặt nằm khác trạm với phòng) | phải kéo dữ liệu | cục bộ | `booking → room` **xuyên trạm** ✗ | Vi phạm ràng buộc 3, FK không cục bộ |
| Băm theo `booking_id` | qua mạng ✗ | qua mạng | qua mạng | xuyên trạm ✗ | Mất tính cục bộ hoàn toàn |
| Dồn hết về trung tâm | — | — | — | — | Vi phạm ràng buộc 1 |

**Một câu để nói:** "Bốn trên năm truy vấn đi theo khách sạn hoặc vùng, và Q1 bắt buộc phải cục bộ. Chỉ Q3 đi theo đoàn,
và chỉ 6,4% lượt đặt là liên vùng. Vì vậy hệ chịu cho Q3 đi qua mạng để giữ cục bộ cho phần còn lại."

### 3.3. Cấp phát

| Máy | Trạm | Lý do |
|---|---|---|
| **A (macOS)** | nhatrang (trung tâm, cổng 5433), dalat (5434), `ref` (5440), giao diện :8501, dashboard :8502 | Đề bắt máy A chạy trạm trung tâm, giao diện và dashboard. Đặt dalat ở A để demo được "trạm cùng máy" và "trạm khác máy" |
| **B (Windows)** | phuquoc (5435), danang (5436) | Đề bắt máy B có ≥ 1 trạm; hai trạm thì Q2, Q3 chắc chắn đi qua LAN |

`deploy.toml` là bản đồ trạm → máy, IP, cổng. `make up MACHINE=A` hoặc `MACHINE=B` chỉ bật các trạm của máy đó.

### 3.4. Khoá chính duy nhất toàn hệ

- **Bài toán:** mỗi trạm tự thêm lượt đặt mới. Nếu cùng dùng một sequence bắt đầu từ 1, hai trạm sẽ sinh trùng `booking_id`.
- **Giải pháp:** mỗi trạm có số thứ tự `no` và dải riêng: **booking_id ∈ [no·10⁷ + 1, (no+1)·10⁷ − 1]**.
  - dalat (no = 1): 10.000.001 – 19.999.999
  - nhatrang (2): 20.000.001 – …
  - phuquoc (3): 30.000.001 – …
  - danang (4): 40.000.001 – …
  - Dữ liệu của bộ sinh (≤ 80.000) nằm dưới 10⁷.
- **Cách hiện thực:**
  - `booking_id_seq` có `START`, `MINVALUE`, `MAXVALUE` theo dải, làm DEFAULT của `booking_id`.
  - Thêm `CHECK (booking_id < 10000000 OR booking_id BETWEEN lo AND hi)`. Kể cả ai đó tự chèn ID tay sai dải, trạm vẫn từ chối.
- **Vì sao không dùng cách khác:**
  - **UUID:** đề không cho đổi kiểu cột (`integer`).
  - **Sequence chung ở trung tâm:** mỗi lần ghi tốn thêm một vòng tới trung tâm, và trung tâm chết thì không ghi được.
  - **Sequence bước nhảy (`INCREMENT 4`, `START no`):** cũng đúng, nhưng dải ID khó đọc hơn khi demo. Dải 10⁷ cho biết ngay dòng do trạm nào sinh.
- **Bảng con:** `req_*` dùng chung `booking_id` của cha. `req_family_child` dùng (booking_id, seq), nên tự động duy nhất.
- **`tour_group_id` mới:** lấy từ một sequence duy nhất ở trung tâm, bắt đầu từ 100.001, ghi bằng 2PC.

### 3.5. Khoá ngoại sau khi chia

| Khoá ngoại | Cha và con cùng trạm? | Xử lý |
|---|---|---|
| `room.hotel_id → hotel` | **Có** (dẫn xuất) | Khai báo FK thật tại trạm |
| `room.room_type_code → room_type` | **Có** (bảng cha được sao chép) | FK thật |
| `booking.room_id → room` | **Có** (dẫn xuất) | FK thật |
| `booking.tour_group_id → tour_group` | **Có** (cha được sao chép) | FK thật |
| `req_tour / req_business / req_family .booking_id → booking` | **Có** | FK thật |
| `req_family_child.booking_id → req_family` | **Có** | FK thật |

Tổng cộng 8 FK đều cục bộ, **không có FK xuyên trạm**. `make check` vẫn kiểm tra thêm "dòng mồ côi" tại từng trạm (nhóm C)
và tính duy nhất của PK trên toàn hệ (nhóm D).

Nếu bị hỏi "nếu có FK xuyên trạm thì xử lý sao?", có ba cách:
1. Kiểm tra bằng truy vấn định kỳ (`NOT EXISTS` qua fdw).
2. Trigger ở trạm con hỏi trạm cha qua fdw (chậm, và hỏng khi trạm cha chết).
3. Sao chép bảng cha, đúng như nhóm đã làm với `tour_group`.

### 3.6. CHECK

**CHECK ràng buộc mảnh** (mỗi trạm chỉ nhận dòng của mình):
- `hotel`: `CHECK (region = '<trạm>')`.
- Bảng con không cần CHECK riêng: FK tới cha cục bộ đã ép dòng con thuộc vùng của trạm. Chèn `room` của khách sạn vùng khác
  thì FK báo lỗi, vì khách sạn đó không có ở trạm này.
- `booking`: CHECK dải `booking_id` (Mục 3.4).

**CHECK cho cột jsonb** (`booking_request_shape_chk` và các CHECK đi kèm):
- `guest_type IN ('tour','business','family')`.
- `(guest_type = 'tour') = (tour_group_id IS NOT NULL)`: chỉ khách đoàn mới có mã đoàn.
- `jsonb_typeof(request) = 'object'`, và theo từng `guest_type`:
  - **tour:** có đủ khoá `group_code`, `meal_plan`, `guide_room`; `meal_plan ∈ {BB, HB, FB}`; `guide_room` là boolean;
    **`group_code` khớp `tour_group_id`** (`'TG' || lpad(id, 4, '0')`). Đây là ràng buộc liên cột giữa jsonb và quan hệ.
  - **business:** có `company`, `tax_code`, `late_checkout` (boolean).
  - **family:** có `extra_bed`, `airport_pickup` (boolean), `children_ages` (array).
- Bản quan hệ cũng có CHECK riêng: `meal_plan IN (…)`, `age BETWEEN 0 AND 17`, `nights BETWEEN 1 AND 60`, `rate > 0`.

**Tính nhất quán jsonb ↔ quan hệ cho dòng mới:** giao diện sinh **cả hai từ cùng một dict** (`build_request` trong `app/lib.py`),
rồi ghi `booking` và `req_*` trong **một giao dịch** (`write_booking`). Hoặc cả hai cùng có, hoặc không có gì.

### 3.7. Dòng liên vùng và truy vấn bị ảnh hưởng

- **Định nghĩa trong đề:** lượt đặt thuộc đoàn tour có phòng ở ≥ 2 vùng trong cùng chuyến.
- **Với thiết kế của nhóm:** dòng liên vùng **vẫn nằm đúng trạm của khách sạn**, không vi phạm gì. Hệ quả là
  **phòng của một đoàn bị rải ra nhiều trạm**.
- **Truy vấn bị ảnh hưởng: chỉ Q3.** Q3 hỏi theo đoàn; không bảng nào cho biết đoàn đi những vùng nào, nên không loại được trạm nào và phải hỏi cả 4.
- **Q1, Q2, Q4, Q5 không bị ảnh hưởng:** chúng không quan tâm đoàn, và mỗi dòng nằm đúng chỗ của nó.

---

## 4. Hiện thực kỹ thuật

### 4.1. Hạ tầng

- **Docker Desktop** trên cả hai máy (Windows dùng WSL2).
  - Image `cs5104-pg18` = `postgres:18` + `iproute2` (để có lệnh `tc`).
  - Mỗi trạm là một container `cs5104_<trạm>`, có volume riêng và mở cổng ra LAN (`-p 0.0.0.0:543x:5432`).
  - Tuỳ chọn khi chạy container: `--cap-add NET_ADMIN` (để `tc` hoạt động), `-c max_prepared_transactions=20` (cho 2PC).
- **Hai loại địa chỉ** (`tools/common.py`):
  - `host_addr`: địa chỉ mà chương trình trên máy chủ (nạp dữ liệu, giao diện, dashboard) dùng.
    Trạm cùng máy thì `127.0.0.1:cổng`; trạm khác máy thì `IP máy:cổng`.
  - `docker_addr`: địa chỉ mà **container trung tâm** dùng cho postgres_fdw. Trạm cùng máy thì `cs5104_dalat:5432`
    (qua mạng Docker nội bộ `cs5104_net`); trạm ở máy B thì `192.168.100.198:5435`.
- **Makefile chạy được trên cả hai hệ điều hành:** các lệnh chỉ gọi `docker` và `python`. Trên Windows dùng `PY=python`,
  `.venv\Scripts\python.exe`, và đặt `PYTHONUTF8=1` để in được tiếng Việt.
- **Máy B không cần venv:** `deploy.py` chỉ dùng thư viện chuẩn, không cần psycopg.

### 4.2. Luồng `make all`

```
Máy B:  make all MACHINE=B   → build image → up B (phuquoc, danang)
Máy A:  make all             → venv → build → up A → data → load → link → check → bench → apps-start
```

| Bước | Tệp | Làm gì |
|---|---|---|
| `data` | `datagen/de06_hotel/generate.py --size lab` | Sinh CSV + `summary.json` (seed 402738, **không sửa tệp này**) |
| `load` | `tools/split.py`, `tools/load.py` | Chờ đủ 5 nút; chia CSV thành mảnh; nạp `ref` bằng `schema_central.sql` + `COPY`; nạp từng trạm bằng `site_schema.sql` (thay `__SITE__`, `__ID_LO__`, `__ID_HI__`); đối chiếu số dòng với `summary.json` |
| `link` | `tools/link.py` | Ở trung tâm: `CREATE SERVER` + `USER MAPPING` + `IMPORT FOREIGN SCHEMA` vào `s_dalat`, `s_phuquoc`, `s_danang` và `ref`; tạo 7 khung nhìn `all_*`; `ANALYZE` các bảng ngoài |
| `check` | `tools/check.py` | 103 truy vấn kiểm tra, mỗi truy vấn phải trả 0 |
| `bench` | `tools/bench.py` | Q1–Q5 và các biến thể × {0, 30 ms}; N4, N5 |
| `apps-start` | `tools/apps.py` | Chạy nền Streamlit :8501 (nhập liệu), :8502 (dashboard) |

### 4.3. postgres_fdw ở trạm trung tâm

```sql
CREATE EXTENSION postgres_fdw;
CREATE SERVER srv_phuquoc FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host '192.168.100.198', port '5435', dbname 'hotel',
           fetch_size '10000', async_capable 'true', parallel_commit 'true', connect_timeout '3');
CREATE USER MAPPING FOR CURRENT_USER SERVER srv_phuquoc OPTIONS (user 'postgres', password '…');
IMPORT FOREIGN SCHEMA public FROM SERVER srv_phuquoc INTO s_phuquoc;
CREATE VIEW all_booking AS
  SELECT * FROM public.booking UNION ALL SELECT * FROM s_dalat.booking
  UNION ALL SELECT * FROM s_phuquoc.booking UNION ALL SELECT * FROM s_danang.booking;
```

| Tuỳ chọn | Tác dụng | Bằng chứng trong số liệu |
|---|---|---|
| `fetch_size 10000` | Mỗi lần FETCH lấy tới 10.000 dòng | Q2 trên `all_*` ở trễ 30 ms: 1.118 ms với 10.000 so với 8.084 ms với 100 |
| `async_capable true` | Các nhánh `Append` của nhiều trạm được FETCH **song song** (`Async Foreign Scan`) | Tắt thì Q2: 436 → 543 ms (11 → 13 vòng) |
| `parallel_commit true` | COMMIT gửi tới các trạm xa cùng lúc | Tắt thì Q2: 436 → 499 ms (11 → 13 vòng) |
| `connect_timeout 3` | Trạm chết thì lỗi sau ≤ 3 s, không treo | D8 |
| `use_remote_estimate` (không bật) | Lập kế hoạch bằng cách gửi `EXPLAIN` sang trạm xa | Bật cho Q2 nối bảng gốc: lập kế hoạch mất 2.227 ms |

**Hai khung nhìn cục bộ ở mỗi trạm** (đề cho phép thêm khung nhìn) — điểm kỹ thuật đáng nói nhất:
- `booking_detail` = `booking ⋈ room ⋈ hotel`. `family_request_detail` = `booking ⋈ req_family`, kèm `youngest_child_age` và `children`.
- **Vấn đề:** Q2 viết trên 3 bảng ngoài thì bộ tối ưu không bật `use_remote_estimate` không đoán được chi phí. Nó chỉ đẩy `room ⋈ hotel`,
  còn **kéo `booking` về** (11–16 nghìn dòng mỗi trạm), và các nhánh không chạy song song được: 1.201 ms.
  Bật `use_remote_estimate` thì đẩy được hết, nhưng lập kế hoạch tốn thêm hàng chục vòng EXPLAIN: 2.576 ms.
- **Cách giải quyết:** đối với trung tâm, khung nhìn ở trạm xa chỉ là **một bảng ngoài**. Bảng ngoài đơn lẻ thì postgres_fdw luôn
  đẩy được `WHERE + GROUP BY` (`Relations: Aggregate on (s_dalat.booking_detail)`). Mỗi trạm trả 15 dòng, nên Q2 còn 436 ms.

### 4.4. Giả lập trễ (`tools/delay.py`)

```
tc qdisc add dev eth0 root handle 1: prio bands 4
tc qdisc add dev eth0 parent 1:4 handle 40: netem delay 30ms
tc filter add dev eth0 parent 1: protocol ip u32 match ip dst <IP trạm xa>/32 flowid 1:4   (mỗi trạm xa một bộ lọc)
```

- Áp **ngay trong container trung tâm**, ở chiều đi ra, **chỉ cho gói có đích là trạm xa**: dalat qua IP container 172.19.0.x;
  phuquoc và danang qua 192.168.100.198.
- Trễ 30 ms một chiều đi ra, nên **mỗi vòng khứ hồi chậm thêm đúng 30 ms**.
- Gói tới `ref`, giao diện và dashboard không bị trễ, nên phép so khớp và dashboard không bị ảnh hưởng.
- **dalat cùng máy vẫn bị trễ.** Trễ mô phỏng **khoảng cách địa lý** giữa các vùng, không phải ranh giới máy.
- Vì sao dùng `prio` + bộ lọc mà không đặt `netem` thẳng lên `root`? Đặt lên `root` thì **mọi** gói đều bị trễ, kể cả
  kết nối từ máy chủ vào trung tâm và từ trung tâm tới `ref`.

### 4.5. Cách đo (`tools/bench.py`) — phải nói được trôi chảy

1. Mỗi truy vấn chạy **5 lần trong cùng một phiên `psql`, ngay trong container** của trạm thực hiện (`docker exec`, qua unix socket),
   lấy thời gian bằng `\timing`. Như vậy không lẫn độ trễ client ↔ trạm.
2. **Bỏ lần đầu:** lần đầu có thêm chi phí mở kết nối postgres_fdw tới trạm xa (bắt tay TCP, xác thực) và nạp bộ nhớ đệm.
   **Lấy trung vị** của 4 lần còn lại, vì trung vị ít bị ảnh hưởng bởi một lần dao động mạng.
3. Đo ở 2 trạng thái: **0 ms và 30 ms**. Đo thêm 60 ms (`make slope`) để tính **số vòng = (T₆₀ − T₃₀) / 30**.
   Phép trừ triệt tiêu thời gian xử lý và RTT gốc của Wi-Fi, chỉ còn số lượt đi về tuần tự.
4. Mỗi biến thể được **so khớp từng dòng** với kết quả của truy vấn tương đương chạy trên `ref`.
5. Lưu `results/results.csv` (5 lần chạy, trung vị, số dòng, khớp, số trạm chạm, số Foreign Scan, số nhánh Async,
   thời gian lập kế hoạch và thực thi) và `results/explain/<Q>_<biến thể>_d<trễ>.txt`.

### 4.6. Giao diện nhập liệu (`app/entry.py`) và dashboard (`app/dash.py`)

**Giao diện nhập liệu:**
- **Thêm lượt đặt:**
  - Chọn vùng → khách sạn → phòng. **Vùng quyết định trạm đích**, không phải trạm trung tâm ghi giùm.
  - Chọn `guest_type` thì form đổi đúng các trường của loại đó.
  - Ghi `booking` + `req_*` trong một giao dịch, **kết nối thẳng** tới trạm đích, rồi báo `booking_id`, trạm, máy, IP.
  - Tự nhận biết dòng liên vùng (đoàn đã có phòng ở vùng khác).
- **Thêm ngẫu nhiên N dòng:** phân bổ theo tỉ lệ vùng của đề, ghi theo lô vào từng trạm.
- **Thêm đoàn tour:** 2PC trên 4 trạm (Mục 2.4), có nhật ký điều phối; khung "Giao dịch lưỡng lự" có nút phục hồi (E2, Mục 14.2).
- **Trạm đích mất kết nối thì báo lỗi, không ghi sang trạm khác.** Ghi sang trạm khác sẽ làm sai thiết kế phân mảnh (vi phạm CHECK/FK) và sai Q1.
- **Mọi dòng mới cũng được ghi vào `ref`** (`mirror_ref`), nên sau D7 `make check` và phép so khớp Q1–Q5 vẫn đạt.

**Dashboard:**
- Mỗi giây hỏi **song song** 5 nút (4 trạm + `ref`), **thẳng bằng psycopg, không qua postgres_fdw**, timeout 1 s.
- Hiện mỗi trạm một ô: máy, IP, xanh/đỏ, số dòng 9 bảng, `booking_id` mới nhất.
- Bên dưới là bảng tổng hợp so với `ref`, và nhật ký sự kiện (dòng mới, trạm mất/kết nối lại).
- Tự làm mới bằng `st.fragment(run_every=1)`, đáp ứng yêu cầu "≤ 2 giây".
- Vì sao không qua fdw? Đề yêu cầu vậy. Hơn nữa, nếu đọc qua trung tâm thì trung tâm chết sẽ làm dashboard thấy mọi trạm đều chết.

---

## 5. Năm truy vấn Q1–Q5

| | Nội dung | Chạy ở | Trạm chạm | Foreign Scan | Kết quả | 0 ms | 30 ms |
|---|---|---|---:|---|---:|---:|---:|
| **Q1** | Công suất phòng các khách sạn Đà Lạt, tháng 7/2025 | **dalat** | 1 | **0** | 13 dòng | 0,65 | **0,47** |
| **Q2** | Doanh thu theo vùng × loại phòng, năm 2025 | trung tâm | 4 | 3 async | 60 dòng | 69 | **436** |
| **Q3** | Mọi phòng đã đặt của đoàn TG0001, sắp theo ngày nhận | trung tâm | 4 | 3 async | 46 dòng | 60 | **423** |
| **Q4** | Khách gia đình có trẻ < 6 tuổi + đón sân bay (**jsonb**) | trung tâm | 4 | 3 async | 3.413 | 72 | **449** |
| **Q5** | Như Q4 nhưng trên `req_family` + `req_family_child` | trung tâm | 4 | 3 async | 3.413 | 71 | **438** |

### Q1 — công suất phòng
- **Đêm đã bán** = phần giao của [check_in, check_in + nights) với [2025-07-01, 2025-08-01).
  Lượt nhận phòng cuối tháng 6 kéo sang tháng 7 cũng được tính phần trong tháng 7: `least(...) − greatest(...)`.
- **Đêm có thể bán** = số phòng × 31. Công suất = đã bán / có thể bán × 100.
- Điều kiện `check_in >= '2025-07-01' − 60` được phép thêm vì có CHECK `nights ≤ 60`. Nó giúp dùng được chỉ mục `check_in`.
- **Vì sao trọn tại một trạm:** chỉ cần `hotel`, `room`, `booking` của vùng dalat, và cả ba bảng này đều nằm ở trạm dalat (ngang + dẫn xuất).
- **So sánh:** cũng Q1 nhưng chạy ở trung tâm trên `all_*` (biến thể `central_all_views`) mất 201 ms (0 ms trễ) và **1.286 ms**
  (30 ms trễ). Đây là minh hoạ trực tiếp cho lợi ích của cấp phát đúng chỗ.

### Q2 — doanh thu, gộp hai giai đoạn
- Giai đoạn 1 (mỗi trạm): `SELECT region, room_type_code, sum(nights*rate), count(*) FROM booking_detail WHERE check_in in 2025 GROUP BY 1,2`.
  Mỗi trạm trả ≤ 15 dòng.
- Giai đoạn 2 (trung tâm): `UNION ALL` 4 phần → `JOIN room_type` (bản sao cục bộ) để lấy tên → `GROUP BY` → `ORDER BY`.
- **Đúng vì sao?** `sum` và `count` **phân phối được** qua phép hợp: tổng của các tổng bằng tổng chung.
  Lưu ý: `avg` thì không gộp thẳng được, phải gửi cả `sum` và `count`.
- **Mô hình 11 vòng:** 3 START + 3 DECLARE (tuần tự từng trạm) + 1 FETCH (song song) + 3 CLOSE (tuần tự) + 1 COMMIT (song song).
  Đo được: **11,0**.

### Q3 — đoàn tour liên vùng
- Mỗi trạm tự nối `booking ⋈ room ⋈ hotel` và lọc `tour_group_id = 1`. Phép nối ba bảng ngoài **cùng server** được đẩy xuống.
- Trả về: dalat 0, nhatrang 14, phuquoc 22, danang 10 dòng; tổng 46.
- **Vì sao chạm cả 4 trạm, kể cả dalat (0 dòng):** không có thông tin nào cho biết đoàn đi vùng nào để loại trạm (định vị dữ liệu không rút gọn được).
  Hỏi dalat vẫn tốn khoảng 3 vòng tuần tự (START, DECLARE, CLOSE).
- **Cải tiến có thể bàn khi được hỏi:** thêm bảng chỉ mục "đoàn → các vùng" (sao chép), để trung tâm biết đoàn 1 không có ở dalat và bớt một trạm.
  Đánh đổi: phải cập nhật bảng đó mỗi khi có lượt đặt mới (thêm một lần ghi xuyên trạm).

### Q4 — jsonb
- `guest_type = 'family' AND request @> '{"airport_pickup": true}' AND request @? '$.children_ages[*] ? (@ < 6)'`.
- `@?` trả về đúng khi jsonpath tìm được **ít nhất một** phần tử, tức "có ít nhất một trẻ dưới 6 tuổi".
- Cả ba điều kiện dùng toán tử có sẵn nên được đẩy xuống từng trạm (xem `Remote SQL`). Trung tâm chỉ hợp và sắp xếp.

### Q5 — bản quan hệ
- `airport_pickup AND youngest_child_age < 6` trên khung nhìn `family_request_detail`.
- **Tương đương Q4:** min(age) < 6 ⇔ tồn tại một trẻ có age < 6. Gia đình không có trẻ thì `youngest_child_age` là NULL, và `NULL < 6` không đúng,
  nên bị loại. Q4 cũng loại trường hợp này, vì mảng rỗng không có phần tử nào thoả.
- **D5:** Q4 và Q5 ra **cùng 3.413 dòng**, cùng khớp `ref`. Đây là bằng chứng jsonb và bản quan hệ nhất quán.
- Biến thể `base_join` (nối bảng gốc qua `all_*`): 2.093 ms ở trễ 30 ms, vì kéo `req_family_child` về trung tâm để nối.

---

## 6. Năm con số N1–N5 và lời giải thích

### N1 — Số dòng mỗi mảnh

| Bảng | dalat | nhatrang | phuquoc | danang | Tổng = ref |
|---|---:|---:|---:|---:|---:|
| hotel | 13 | 16 | 14 | 17 | 60 |
| room | 1.193 | 1.662 | 1.387 | 1.758 | 6.000 |
| booking | 16.275 | 20.091 | 19.755 | 23.879 | 80.000 |
| req_tour | 7.537 | 8.621 | 9.285 | 10.681 | 36.124 |
| req_business | 5.498 | 7.292 | 6.710 | 8.433 | 27.933 |
| req_family | 3.240 | 4.178 | 3.760 | 4.765 | 15.943 |
| req_family_child | 4.833 | 6.144 | 5.740 | 7.239 | 23.956 |
| room_type, tour_group | 15 / 800 ở **mỗi** trạm (sao chép) | | | | 15 / 800 |

**Lời giải thích:**
- **hotel 13/16/14/17:** bộ sinh dùng tỉ lệ 0,20/0,26/0,24/0,30 qua `split_counts(60, W, 2)`.
  - Mỗi vùng được trước 2 khách sạn.
  - 52 khách sạn còn lại chia theo tỉ lệ rồi làm tròn xuống: 10/13/12/15.
  - 2 khách sạn dư chia cho dalat và nhatrang → 13/16/14/17.
- **room:** mỗi khách sạn có trọng số ngẫu nhiên U(0,5; 1,5), nên tỉ lệ phòng (19,9/27,7/23,1/29,3%) lệch nhẹ khỏi tỉ lệ khách sạn.
- **booking (20,3/25,1/24,7/29,8%):** khách lẻ (55%) chọn vùng theo tỉ lệ của đề; khách đoàn chọn ngẫu nhiên một trong các vùng của đoàn.
- **req_\*:** đi theo booking. Tổng ba bảng `req_tour + req_business + req_family` = 80.000, vì mỗi lượt đặt có đúng một loại yêu cầu.
- **Tổng các mảnh bằng đúng bảng đối chứng**; `load` và `make check` đều xác nhận.

### N2 — Số trạm mỗi truy vấn chạm
- Q1: **1 trạm**, 0 Foreign Scan.
- Q2–Q5: **4 trạm** (trung tâm cục bộ + 3 trạm xa), 3 `Async Foreign Scan`.
- Đọc `Remote SQL` để chỉ ra điều kiện nào được đẩy:
  - Q2: cả `WHERE` + `GROUP BY` (`Aggregate on`).
  - Q3: `JOIN` 3 bảng + `tour_group_id = 1`.
  - Q4: `@>`, `@?`, `guest_type`.
  - Q5: `airport_pickup AND youngest_child_age < 6`.
- **So sánh với biến thể kém:**
  - Q2 nối bảng gốc: 6 Foreign Scan; chỉ `room ⋈ hotel` được đẩy, còn `booking` bị kéo về.
  - Q2/Q3 trên `all_*`: 9 Foreign Scan; chỉ WHERE từng bảng được đẩy, JOIN và GROUP BY làm ở trung tâm.

### N3 — Thời gian, số vòng khứ hồi, trạm cùng máy và trạm khác máy

| | 0 ms | 30 ms | Số vòng đo được |
|---|---:|---:|---:|
| Q1 tại dalat | 0,65 | 0,47 | 0 |
| Lượt hỏi tối thiểu | 0,31 (dalat) · 36–45 (B) | 163 · 202–203 | 4,7–5,3 |
| Q2 | 69 | 436 | 11,0 |
| Q2 tắt async | 100 | 543 | 13,0 |
| Q2 tắt parallel_commit | 71 | 499 | 13,0 |
| Q3 | 60 | 423 | 11,5 |

**Lời giải thích:**
1. **Q1 gần như không đổi**, vì không có gói nào đi trên đường bị trễ. Chênh 0,65 so với 0,47 ms chỉ là dao động đo.
2. **Q2, Q3 tăng khoảng 365 ms ≈ 11–12 vòng × 30 ms.** Số hạng (số vòng) × RTT lấn át thời gian xử lý.
3. **Vì sao số vòng tăng theo số trạm xa:**
   - Mỗi trạm xa cần 5 lệnh.
   - `async_capable` chỉ cho FETCH chồng lên nhau; `START`, `DECLARE`, `CLOSE` vẫn tuần tự từng trạm.
   - `parallel_commit` gộp các COMMIT thành 1 vòng.
   - Vì vậy mỗi trạm xa thêm khoảng 3 vòng: 3 trạm xa → 3·3 + 2 = 11 vòng. Tắt async hoặc parallel_commit thì thêm 2 vòng → 13 (đo được 13,0).
4. **Trạm cùng máy so với trạm ở máy B:**
   - Khi tắt trễ, lượt hỏi tới dalat mất 0,31 ms (mạng Docker nội bộ, RTT gần 0), tới máy B mất 36–45 ms
     (5 vòng × RTT Wi-Fi khoảng 7–9 ms, cộng chi phí NAT của Docker Desktop hai đầu).
   - Vì vậy ngay cả khi tắt trễ giả lập, Q2–Q5 vẫn mất 60–70 ms, so với vài ms khi chạy cả 4 trạm trên một máy.
   - Khi bật trễ 30 ms, cả ba trạm xa cùng bị cộng thêm, nên số vòng (≈ 11) không đổi theo vị trí máy. Thời gian tuyệt đối của trạm ở máy B
     vẫn cao hơn khoảng 40 ms, bằng 5 × RTT Wi-Fi.
5. **Lượng dữ liệu cũng quan trọng:**
   - `fetch_size 100` trên `all_*`: 8.084 ms, vì khoảng 450 lần FETCH.
   - Nối bảng gốc: 1.201 ms, vì kéo khoảng 40 nghìn dòng.
   - `use_remote_estimate`: lập kế hoạch 2.227 ms, vì gửi EXPLAIN sang trạm xa.

### N4 — Tỉ lệ dòng liên vùng
- **5.144 / 80.000 = 6,43%** lượt đặt thuộc **115 đoàn** có phòng ở ≥ 2 vùng (115/800 = 14% số đoàn).
  Đúng với "5–10%" trong đề, và khớp `summary.json`.
- Đoàn 1 có 46 phòng: nhatrang 14, phuquoc 22, danang 10.
- **Vì sao làm Q3 đi qua mạng:** booking đặt theo vùng **khách sạn**, nên phòng của một đoàn liên vùng nằm ở nhiều trạm.
  Trung tâm không biết trước đoàn đi đâu, nên phải hỏi cả 4 trạm.
- **Dự đoán khi tỉ lệ lên 30%:**
  - Với thiết kế này, **Q3 gần như không đổi** (vẫn khoảng 11 vòng, khoảng 420 ms), vì đã hỏi đủ 4 trạm. Số dòng một đoàn (khoảng 45)
    vẫn vừa một lần FETCH.
  - Q1, Q2, Q4, Q5 **không đổi**, vì mỗi dòng vẫn nằm đúng trạm khách sạn.
  - Ngược lại, nếu đã chia booking theo đoàn, 30% lượt đặt sẽ nằm khác trạm với phòng của nó. Khi đó Q1, Q2 phải qua mạng và FK `booking → room` xuyên trạm.
  - **Kết luận:** tỉ lệ liên vùng càng cao, thiết kế theo vùng khách sạn càng hợp lý.
  - Một trường hợp làm Q3 tệ hơn: nếu Q3 hỏi **nhiều đoàn** cùng lúc, số dòng trả về tăng nhưng số vòng vẫn vậy, nên ảnh hưởng nhỏ.

### N5 — Dung lượng jsonb so với bản quan hệ, có và không có GIN

| | Dung lượng | Ghi chú |
|---|---:|---|
| `booking.request` (jsonb) | **6,17 MB** | trung bình 77 B: tour 66, business 86, family 87 B |
| 4 bảng `req_*` (chỉ heap) | **4,96 MB** | 103.956 dòng |
| 4 bảng `req_*` + PK | 7,52 MB | |
| GIN `jsonb_path_ops` | 2,18 MB | Q4 trên `ref`: 5,2 → **2,4 ms** |
| GIN `jsonb_ops` | 2,92 MB | Q4: 3,0 ms |

**Lời giải thích:**
- **jsonb lớn hơn phần dữ liệu quan hệ khoảng 24%,** vì mỗi giá trị lặp lại tên khoá (ví dụ `"group_code"`, `"meal_plan"`,
  `"guide_room"` khoảng 29 B), cộng phần đầu và bảng vị trí của jsonb. Cùng hiện tượng với Bảng 8.4 của giáo trình (+45%).
- **Bản quan hệ cũng có chi phí riêng:** mỗi dòng có tiêu đề bộ khoảng 24 B và con trỏ 4 B, lặp lại `booking_id`, mỗi trẻ là một dòng
  (23.956 dòng), và cần PK để nối. Tính cả chỉ mục thì bản quan hệ (7,52 MB) lớn hơn jsonb.
- **`jsonb_path_ops` nhỏ hơn `jsonb_ops`,** vì nó chỉ lưu một mục băm cho mỗi đường dẫn + giá trị, thay vì một mục cho mỗi khoá và mỗi giá trị.
  Đổi lại nó chỉ phục vụ `@>`, `@?`.
- **GIN chỉ lọc được phần bằng hoặc tồn tại:** `airport_pickup = true` và sự có mặt của `children_ages` cho 7.861 ứng viên.
  Điều kiện `< 6` bị kiểm tra lại (*Recheck*), loại 4.448 dòng. Thời gian vẫn giảm một nửa so với quét toàn bảng.
- **Trong hệ phân tán, chênh lệch Q4 so với Q5 (449 so với 438 ms) không đáng kể** so với chi phí 11 vòng khứ hồi.
  Chọn jsonb hay quan hệ ở đây là chuyện lưu trữ và tiện dụng, không phải tốc độ mạng.

---

## 7. Tám thao tác demo D1–D8

> Tổng 12 phút. Chuẩn bị sẵn: hai máy đã chạy `make all` trước buổi bảo vệ (có thể chạy lại tại chỗ), một terminal ở máy A,
> một terminal ở máy B, trình duyệt mở :8501 và :8502, điểm phát Wi-Fi điện thoại để dự phòng.

| Mã | Thao tác | Phải cho thấy | Câu nói chính |
|---|---|---|---|
| **D1** | Máy B: `make all MACHINE=B`; máy A: `make all` (hoặc `make status` nếu đã dựng) | 4 trạm chạy; bảng đối chiếu số dòng với `summary.json` đều OK; dashboard 4 ô xanh | "Cùng một Makefile trên macOS và Windows; `deploy.toml` là bản đồ trạm → máy" |
| **D2** | `make check` | 103 dòng OK, "KẾT LUẬN: ĐẠT" | 6 nhóm: A ba quy tắc (`EXCEPT ALL` hai chiều); B bản sao giống `ref`; C đúng mảnh tại từng trạm, không mồ côi; D PK/FK toàn hệ; E jsonb ↔ quan hệ nhất quán; F dữ liệu gốc khớp `summary.json` |
| **D3** | `make q QUERIES="Q1 Q2" EXPLAIN=1` | Q1 khớp đối chứng, **Foreign Scan: 0**; Q2 khớp, `Remote SQL` có `GROUP BY` | "Q1 chạy trọn ở dalat vì hotel ngang theo vùng và mọi bảng con dẫn xuất theo" |
| **D4** | `make q QUERIES=Q3 EXPLAIN=1` | 46 dòng khớp; chạm 4 trạm, dalat trả 0 dòng | "Đoàn 1 có phòng ở 3 vùng, không biết trước nên phải hỏi cả 4 trạm" |
| **D5** | `make q QUERIES="Q4 Q5"` | Cùng 3.413 dòng, đều khớp | "jsonb và bản quan hệ nhất quán; toán tử `@>`, `@?` được đẩy xuống" |
| **D6** | `make delay-on` → `make q QUERIES="Q1 Q2 Q3"` → `make delay-off` | Q1 ≈ 0,5 ms; Q2, Q3 ≈ 420–440 ms | "Tăng khoảng 365 ms ≈ 11 vòng × 30 ms; đo ở 60 ms thì số vòng đúng là 11" |
| **D7** | Giao diện: (a) một lượt đặt ở khách sạn **phuquoc hoặc danang** (máy B); (b) một lượt đặt của đoàn TG0001 ở vùng mới (**liên vùng**); (c) "thêm ngẫu nhiên 100 dòng". Sau đó `make q QUERIES=Q3` và `make check` | Ô đúng trạm tăng số dòng trong ≤ 2 s; nhật ký có sự kiện; Q3 thấy dòng mới (booking_id trong dải của trạm, ví dụ 30000001 ở phuquoc); check vẫn đạt | "Giao diện ghi thẳng tới trạm của vùng, jsonb và quan hệ trong một giao dịch; ID trong dải riêng của trạm" |
| **D8** | Máy B: `make stop-site SITE=danang` → xem dashboard, thử ghi vào danang, `make q QUERIES="Q1 Q2"` → `make start-site SITE=danang` → chạy lại Q2 | Ô danang đỏ; giao diện báo lỗi, không ghi sang trạm khác; Q1 vẫn chạy; Q2 lỗi `could not connect to server "srv_danang"`; bật lại thì ô xanh, Q2 chạy và khớp | "Q1 không phụ thuộc máy B; Q2 cần đủ 4 phần nên lỗi chứ không trả kết quả thiếu; postgres_fdw tự kết nối lại" |

> ⚠ **D8 phải cho thấy Q2 LỖI.** Nếu đã dựng phần mở rộng E1 thì **không** chạy `make ext-failover` hay `make ext-watch` trước D8,
> và kiểm tra `make ext-replica-status` báo `srv_phuquoc … đang trỏ tới 192.168.100.198:5435` (trạm chính).
> Bảng trên dùng `danang` cho D8, còn `IMPLEMENT.md` dùng `phuquoc`. Dùng trạm nào cũng được: bản sao **có chạy** cũng không sao,
> chỉ cần không bật failover/watch thì Q2 vẫn lỗi đúng như đề yêu cầu.
> Muốn trình bày E1 thì làm **sau** D8 (Mục 14.4).

**Sự cố có thể gặp khi demo:**

| Hiện tượng | Xử lý nhanh |
|---|---|
| `load` chờ mãi một trạm ở máy B | Kiểm tra IP trong `deploy.toml`, firewall 5435–5436, mạng đặt là Private; thử `nc -vz <IP B> 5435` |
| `make link` báo `Connection refused` ngay sau khi máy B vừa lên | Docker Desktop ở Windows cần vài giây để mở cổng; chạy lại `make link check` |
| Đổi sang Wi-Fi điện thoại (IP đổi) | Sửa `deploy.toml` → `make link` (dữ liệu vẫn còn trong volume) |
| `tc` lỗi khi `delay-on` | Container cũ thiếu `NET_ADMIN`: `make down && make all` |
| Q2 vẫn lỗi sau khi bật lại trạm | Chờ khoảng 5 s cho Postgres sẵn sàng rồi chạy lại; kết nối fdw lỗi sẽ được tạo lại ở lần sau |

---

## 8. Giới hạn, đánh đổi và hướng mở rộng

> Chủ động nói giới hạn trước khi bị hỏi sẽ được đánh giá cao hơn là chống chế.

1. **2PC có thể treo** nếu giao diện (bộ điều phối) chết sau PREPARE. Khi đó các bản sao giữ giao dịch lưỡng lự trong `pg_prepared_xacts`
   và giữ khoá dòng. Phục hồi bằng tay (trước E2): đọc `gid` (`tg<id>`), rồi đoán. Đoán sai sẽ làm các bản sao lệch nhau.
   → **Đã làm thêm ở phần mở rộng E2** ([NANG_CAO.md](NANG_CAO.md)): nhật ký quyết định fsync + `make ext-2pc-recover`.
   Đồng thời E2 sửa lỗi pha 2 (bản cũ rollback các trạm chưa commit nếu một trạm lỗi lúc commit).
2. **Tạo đoàn mới cần cả 4 trạm sống** (đồng bộ ngay, ưu tiên nhất quán). Phương án thay thế là sao chép logic (logical replication) từ trung tâm:
   sẵn sàng hơn nhưng có độ trễ đồng bộ.
3. **Truy vấn toàn cục không có ảnh chụp nhất quán giữa các trạm.** Mỗi trạm xa dùng ảnh chụp riêng (postgres_fdw mở
   giao dịch REPEATABLE READ ở trạm xa), không đồng bộ thời điểm. Nếu có người ghi đồng thời, Q2 có thể thấy trạm A "trước" và trạm B "sau".
4. **Ghi qua trung tâm (qua `all_*`) không được hỗ trợ:** khung nhìn `UNION ALL` không ghi được, và postgres_fdw không bảo đảm nguyên tử
   khi ghi nhiều trạm. Thiết kế cố ý để giao diện ghi thẳng.
5. **Không có bản dự phòng cho mảnh:** một trạm chết thì dữ liệu vùng đó không đọc được (D8). Mở rộng: streaming replication
   cho từng trạm (Chương 5), hoặc hệ có đồng thuận (Raft, Chương 6).
   → **Đã làm thêm ở phần mở rộng E1** ([NANG_CAO.md](NANG_CAO.md)): bản sao hot standby của `phuquoc` ở máy A + `make ext-failover`
   (chỉ chuyển đọc, không promote). Lúc demo D8 bắt buộc thì không bật.
6. **Q3 hỏi thừa trạm.** Có thể thêm bảng "đoàn → vùng" được sao chép để cắt trạm, đánh đổi bằng chi phí ghi (Mục 5).
7. **Trễ chỉ giả lập trên đường trung tâm → trạm xa.** Đường giao diện → trạm (khi ghi) không bị trễ.
8. **`ref` được giao diện ghi kèm** để phục vụ kiểm tra. Đây là công cụ chấm, không phải một phần của kiến trúc phân tán.

---

## 9. Ngân hàng câu hỏi vấn đáp

> Che cột đáp án, tự trả lời thành tiếng trong 30–60 giây, rồi mới mở ra xem.

### A. Thiết kế

1. **Vì sao `hotel` phân mảnh ngang mà không sao chép, dù chỉ có 60 dòng?**
   Đề yêu cầu dữ liệu khách sạn lưu tại vùng của nó. `hotel` là gốc của chuỗi dẫn xuất, và CHECK `region` ép mỗi trạm chỉ nhận vùng mình.
   Sao chép cũng đọc được, nhưng mất ràng buộc "rời nhau", và mọi cập nhật khách sạn sẽ phải ghi 4 nơi.
2. **Phân mảnh dẫn xuất là gì, viết bằng đại số quan hệ?**
   roomᵢ = room ⋉_{hotel_id} hotelᵢ. Đó là semijoin: giữ các dòng `room` có `hotel_id` thuộc mảnh hotelᵢ.
3. **Vì sao các mảnh dẫn xuất rời nhau và đầy đủ?**
   Vì FK NOT NULL và trỏ tới đúng một cha; cha nằm ở đúng một mảnh, nên con cũng nằm ở đúng một mảnh.
4. **Vì sao không phân mảnh dọc `booking` để tách cột `request`?**
   Đề không cho đổi bảng hay cột. Không truy vấn nào hưởng lợi, vì Q4 cần `request` cùng `booking_id`, `guest_name`, `check_in`.
   Phân mảnh dọc còn bắt mỗi mảnh giữ khoá và phải nối lại.
5. **Vì sao `tour_group` sao chép chứ không phân mảnh?**
   Một đoàn có phòng ở nhiều vùng, nên không đặt vào một vùng được mà vẫn giữ FK cục bộ. Bảng nhỏ (800 dòng) và ít ghi, nên sao chép rẻ.
6. **Nếu chia booking theo đoàn thì sao?**
   Xem Mục 3.2: Q3 cục bộ, nhưng Q1, Q2 phải qua mạng (vi phạm ràng buộc 3), và FK `booking → room` xuyên trạm.
7. **Khoá chính toàn cục làm thế nào? Vì sao không dùng UUID?**
   Dải `booking_id` theo trạm + CHECK (Mục 3.4). UUID đổi kiểu cột, mà đề cấm.
8. **CHECK nào ép một trạm chỉ nhận dòng của mình? Bảng `room` có CHECK riêng không?**
   `hotel.region = '<trạm>'`. `room` không cần: FK tới `hotel` cục bộ đã ép phòng thuộc khách sạn vùng mình.
9. **Ràng buộc jsonb nào đáng chú ý nhất?**
   `group_code` phải khớp `tour_group_id`, tức ràng buộc liên cột giữa jsonb và quan hệ. Cùng với đó là `(guest_type = 'tour') = (tour_group_id IS NOT NULL)`.
10. **Có FK xuyên trạm không? Nếu có thì xử lý sao?**
    Không. Nếu có: kiểm tra bằng truy vấn qua fdw, trigger, hoặc sao chép bảng cha (Mục 3.5).
11. **Dòng liên vùng là gì, ảnh hưởng truy vấn nào?** Mục 3.7: chỉ Q3.
12. **Vì sao dalat đặt ở máy A?**
    Đề chỉ bắt máy B có ≥ 1 trạm. Đặt dalat ở A để Q1 chạy trên máy demo, và để so được trạm cùng máy với trạm khác máy (N3).

### B. postgres_fdw và xử lý truy vấn

13. **postgres_fdw gửi mấy lệnh cho một truy vấn? Kể tên.** 5 lệnh: START TRANSACTION, DECLARE CURSOR, FETCH, CLOSE, COMMIT.
14. **`async_capable` làm gì, vì sao không giảm hết số vòng?**
    Nó cho các nhánh Append FETCH song song. START, DECLARE, CLOSE vẫn tuần tự, nên chỉ bớt được 2 vòng (13 → 11).
15. **`parallel_commit` khác 2PC thế nào?**
    `parallel_commit` chỉ gửi COMMIT song song, không có pha PREPARE, nên không bảo đảm nguyên tử giữa các trạm.
16. **`fetch_size` ảnh hưởng gì?**
    Nó quyết định số dòng mỗi lần FETCH, tức số vòng khi kéo nhiều dòng. Q2 trên `all_*`: 1.118 ms với 10.000 so với 8.084 ms với 100.
17. **Vì sao cần khung nhìn `booking_detail` ở trạm? Sao không bật `use_remote_estimate`?**
    Mục 4.3: bật thì đẩy được hết, nhưng lập kế hoạch mất 2,2 s vì gửi EXPLAIN sang trạm xa. Khung nhìn biến phép nối thành một bảng ngoài
    nên luôn đẩy được phép gộp.
18. **Điều kiện nào không đẩy xuống được?** Hàm người dùng tự viết, hàm VOLATILE, và JOIN giữa hai server khác nhau.
19. **Đọc kế hoạch này giúp tôi.** Chỉ vào: `Async Foreign Scan`, `Relations: Aggregate on (...)`, `Remote SQL: SELECT ... GROUP BY`.
    Nếu không có `Foreign Scan` thì truy vấn chạy cục bộ.
20. **Gộp hai giai đoạn đúng với hàm gộp nào?**
    `sum`, `count`, `min`, `max` gộp thẳng được. `avg` phải gửi `sum` và `count`. `count(DISTINCT)` không gộp được nếu giá trị trùng giữa các trạm.
21. **Vì sao Q3 hỏi cả dalat dù dalat trả 0 dòng? Cải tiến thế nào?** Mục 5, phần Q3.
22. **Trung tâm có phải là điểm chết duy nhất không?**
    Với truy vấn toàn cục thì có. Q1 tại dalat và giao diện ghi thẳng thì không. Dashboard đọc thẳng nên vẫn chạy khi trung tâm chết.

### C. Giao dịch và sao chép

23. **Trình bày 2PC. Vì sao bộ điều phối phải ghi quyết định vào nhật ký trước khi gửi?**
    Nếu nó chết rồi sống lại, nó phải biết đã quyết COMMIT hay ABORT để trả lời bên tham gia, tránh trạm commit trạm abort.
24. **2PC treo khi nào? Trong hệ của nhóm phục hồi ra sao?** Mục 8.1 và 14.2: nhật ký điều phối + `make ext-2pc-recover` (presumed abort).
25. **Tạo đoàn mới khi phuquoc chết thì sao?** Giao diện không mở được kết nối thì huỷ ngay, chưa trạm nào ghi gì, và báo lỗi.
26. **Bảng sao chép của nhóm thuộc ô nào trong bảng bốn ô? CAP chọn gì?** Mục 2.5.
27. **Thêm một lượt đặt cần 2PC không?**
    Không. Lượt đặt chỉ ghi vào một trạm (booking + req_* cùng trạm), một giao dịch cục bộ là đủ ACID.
28. **Giao dịch ghi booking và req_* như thế nào?**
    `with conn.transaction():` gồm INSERT booking ... RETURNING booking_id, rồi INSERT req_*. Lỗi giữa chừng thì cả hai cùng huỷ.

### D. Số liệu

29. **Vì sao Q1 không đổi khi bật trễ?** Không có gói nào đi qua đường bị trễ.
30. **Q2 tăng bao nhiêu, tương ứng bao nhiêu vòng, tính thế nào?** 436 − 69 ≈ 367 ms ≈ 12 vòng. Đo chính xác: (T₆₀ − T₃₀)/30 = 11,0.
31. **Vì sao bỏ lần đầu, vì sao lấy trung vị?** Mục 4.5.
32. **Vì sao đo trong container chứ không từ máy chủ?** Để không lẫn độ trễ client ↔ trạm trung tâm; chỉ đo phần trung tâm ↔ trạm xa.
33. **Trạm cùng máy và trạm ở máy B khác nhau thế nào?** Mục 6, N3, ý 4.
34. **Khi tỉ lệ liên vùng lên 30% thì sao?** Mục 6, N4.
35. **Vì sao jsonb lớn hơn mà tính cả chỉ mục lại nhỏ hơn bản quan hệ?** Mục 6, N5.
36. **`jsonb_ops` và `jsonb_path_ops` khác nhau thế nào?** Mục 2.6.
37. **Vì sao GIN không lọc được `< 6`?**
    GIN lập chỉ mục theo giá trị rời rạc (bằng hoặc có mặt), không có thứ tự nên không phục vụ được so sánh khoảng.
38. **Thời gian tắt trễ của Q2 trên hai máy (69 ms) khác một máy (6,5 ms) vì sao?**
    RTT Wi-Fi thật khoảng 7–9 ms × 11 vòng ≈ 80 ms. Mạng thật vốn đã có độ trễ.

### E. Hiện thực

39. **`make all` trên Windows chạy được nhờ đâu?**
    Các lệnh trong Makefile chỉ gọi `docker` và `python`; Makefile nhận diện `OS=Windows_NT`; đặt `PYTHONUTF8=1`.
40. **Container trung tâm tới trạm ở máy B bằng địa chỉ nào? Tới dalat bằng địa chỉ nào?**
    Máy B qua `192.168.100.198:5435`; dalat qua `cs5104_dalat:5432` (mạng Docker nội bộ).
41. **Giả lập trễ thế nào, vì sao không đặt netem lên root?** Mục 4.4.
42. **Dashboard làm mới thế nào, vì sao không đọc qua fdw?** Mục 4.6.
43. **Vì sao sau D7, `make check` vẫn đạt dù đã thêm dòng?**
    Giao diện ghi kèm mỗi dòng mới vào `ref`, và dòng mới nằm đúng trạm (CHECK, FK, dải ID).
44. **Dòng nhóm thêm làm sao nhất quán giữa jsonb và quan hệ?** Mục 3.6.
45. **Đã sửa bộ sinh hay lược đồ không?**
    Không. Bộ sinh được chép nguyên (giữ nguyên SHA1 của tệp); tên bảng và cột giữ nguyên. Chỉ thêm CHECK, chỉ mục, sequence, khung nhìn.
46. **Nhóm dùng AI thế nào?** Ghi trong README: AI hỗ trợ viết mã và văn bản; nhóm kiểm tra, chạy và giải thích được toàn bộ.

### F. Câu hỏi mở (để tỏ ra hiểu sâu)

47. **Nếu có 10 vùng thì sao?** Q2–Q5 tăng khoảng 3 vòng mỗi trạm xa thêm vào (≈ 3·9 + 2 = 29 vòng). Muốn giảm thì cần mở kết nối và DECLARE song song,
    hoặc gom truy vấn ở tầng ứng dụng.
48. **Nếu một vùng quá lớn (lệch tải)?** Phân mảnh hỗn hợp: theo vùng rồi theo khoảng `check_in` hoặc băm trong vùng. Hoặc dùng Citus.
49. **Có nên dùng MongoDB cho `request`?** Không cần: jsonb + GIN của PostgreSQL đáp ứng đủ (Mục 8.4), lại có ACID và JOIN với bảng quan hệ.
50. **Muốn trạm trung tâm không phải điểm chết duy nhất?** Bất kỳ trạm nào cũng có thể có fdw và `all_*` (chạy `link.py` với trung tâm khác),
    hoặc dùng streaming replication cho trung tâm. Nhóm đã làm thử streaming replication cho một trạm thường (E1, Mục 14.1).

---

## 10. Bảng số phải thuộc

| Nhóm | Con số |
|---|---|
| Đề | Đề 6, seed **402738**, 4 trạm, trung tâm **nhatrang**, tỉ lệ khách sạn 0,20/0,26/0,24/0,30 |
| Quy mô | 60 khách sạn · 6.000 phòng · 80.000 lượt đặt · 15 loại phòng · 800 đoàn |
| Máy | A macOS 192.168.100.218 (nhatrang 5433, dalat 5434, ref 5440, UI 8501/8502) · B Windows 192.168.100.198 (phuquoc 5435, danang 5436) |
| Mảnh hotel | 13 / 16 / 14 / 17 |
| Mảnh booking | 16.275 / 20.091 / 19.755 / 23.879 |
| Check | **103** phép kiểm tra, tất cả = 0 |
| Liên vùng | 5.144 / 80.000 = **6,43%**, 115 đoàn; đoàn 1: 14 / 22 / 10 (nhatrang / phuquoc / danang) |
| Kết quả | Q1 13 dòng · Q2 60 · Q3 46 · Q4 = Q5 = 3.413 |
| Thời gian ở trễ 30 ms | Q1 **0,47** · Q2 **436** · Q3 **423** · Q4 **449** · Q5 **438** ms |
| Số vòng | lượt hỏi tối thiểu ≈ 5 · Q2 **11** · tắt async 13 · tắt parallel_commit 13 |
| Biến thể kém (30 ms) | Q1 trên all_* 1.286 · Q2 nối bảng gốc 1.201 · remote_estimate 2.576 (lập kế hoạch 2.227) · fetch_size 100: 8.084 ms |
| N5 | jsonb 6,17 MB · req_* 4,96 MB (7,52 MB có PK) · GIN path_ops 2,18 MB · jsonb_ops 2,92 MB · Q4 5,2 → 2,4 ms |
| Dải ID | trạm số `no` → [no·10⁷+1, (no+1)·10⁷−1]; tour_group mới từ 100.001 |
| Mở rộng E1 *(ngoài đề)* | bản sao `phuquoc_replica` máy A :5445 · dựng ≈ 10 s · trễ sao chép ≈ **1,9 ms** · ghi async/`on`/`remote_apply` = **28,7 / 34,6 / 35,7 ms** · Q2 đọc chính/bản sao: 68 / 43 ms (0 ms), **440 / 331 ms** (30 ms) |
| Mở rộng E2 *(ngoài đề)* | tạo đoàn: 4 INSERT 149 ms · 2PC 219 ms · 2PC + nhật ký **221 ms** (+1,8 ms) · 3 điểm chết `prepare`/`decision`/`mid-commit` phục hồi đúng |

---

## 11. Hiểu lầm hay gặp

| Sai | Đúng |
|---|---|
| "Trễ 30 ms nên Q2 tăng 30 ms" | Tăng **30 ms × số vòng khứ hồi** (≈ 11) |
| "async_capable làm mọi thứ song song" | Chỉ FETCH song song; START, DECLARE, CLOSE vẫn tuần tự |
| "parallel_commit là 2PC" | Chỉ là COMMIT song song, không có PREPARE |
| "Dòng liên vùng nằm sai trạm" | Nó nằm **đúng** trạm khách sạn; chỉ là đoàn có phòng ở nhiều trạm |
| "Trạm dalat cùng máy nên không bị trễ" | Có bị: trễ mô phỏng khoảng cách vùng, lọc theo IP container dalat |
| "Q3 chỉ hỏi 3 trạm có dữ liệu" | Hỏi cả 4, vì không biết trước đoàn đi đâu |
| "jsonb luôn nhỏ hơn / luôn lớn hơn" | Phần dữ liệu thì lớn hơn (+24%); tính cả chỉ mục cần cho phép nối thì nhỏ hơn |
| "GIN tăng tốc mọi điều kiện jsonb" | Chỉ bằng hoặc có mặt (`@>`, `?`, `@?` phần bằng); khoảng phải *Recheck* |
| "Khung nhìn `all_*` ghi được" | `UNION ALL` không ghi được; giao diện ghi thẳng tới trạm |
| "Kết quả đo trên một máy là đủ" | Một máy thì RTT ≈ 0; đề bắt ≥ 2 máy (một máy thì M2 tối đa 1,75) |
| "Q2 lỗi khi danang chết là lỗi hệ" | Là hành vi đúng: kết quả toàn cục cần đủ mảnh; trả thiếu mới là sai |
| "Có bản sao thì cho ghi vào bản sao khi trạm chính chết" (E1) | Bản sao chỉ đọc; promote cần fencing, nếu không sẽ có split-brain và trùng dải `booking_id` |
| "Đọc bản sao nhanh hơn trạm chính" (E1, B2) | Nhanh hơn vì bản sao **ở gần** trạm trung tâm (cùng máy A, không bị netem), không phải vì là bản sao |
| "Nhật ký điều phối làm 2PC chậm" (E2, B3) | +1,8 ms trên 220 ms; chi phí 2PC nằm ở các vòng mạng |
| "Có nhật ký thì 2PC hết chặn" (E2) | Vẫn chặn cho tới khi chạy recover; muốn không chặn phải dùng 3PC hoặc commit dựa trên đồng thuận |

---

## 12. Thuật ngữ Anh – Việt

| Tiếng Anh | Tiếng Việt |
|---|---|
| horizontal / derived horizontal / vertical fragmentation | phân mảnh ngang / ngang dẫn xuất / dọc |
| replication, replica | sao chép, bản sao |
| allocation | cấp phát |
| completeness, reconstruction, disjointness | đầy đủ, tái tạo được, rời nhau |
| semijoin | kết nối có lọc trước (nửa kết nối) |
| round trip time (RTT) | thời gian một vòng khứ hồi |
| pushdown | đẩy (điều kiện / phép tính) xuống trạm xa |
| two-phase aggregation | gộp hai giai đoạn |
| foreign data wrapper, foreign table | bộ nối dữ liệu ngoài, bảng ngoài |
| two-phase commit (2PC), in-doubt transaction | cam kết hai pha, giao dịch lưỡng lự |
| two-phase locking (2PL) | khoá hai pha |
| eager / lazy replication | sao chép đồng bộ ngay / đồng bộ sau |
| primary copy / update anywhere | một nút chủ / ghi ở bất kỳ đâu |
| containment (`@>`), jsonpath | chứa, biểu thức đường dẫn JSON |
| GIN (Generalized Inverted Index) | chỉ mục đảo tổng quát |
| reference (centralized) database | CSDL tập trung đối chứng |
| WAL (write-ahead log), streaming replication | nhật ký ghi trước, sao chép bằng luồng WAL (E1) |
| primary / hot standby / replication slot | trạm chính / bản sao chỉ đọc đang phát lại / khe sao chép (giữ WAL cho bản sao) |
| failover / failback / promote | chuyển sang bản sao / chuyển về trạm chính / nâng bản sao thành trạm chính |
| split-brain, fencing | hai trạm cùng tưởng mình là chính; rào trạm cũ lại |
| RPO (recovery point objective) | lượng dữ liệu tối đa có thể mất khi sự cố |
| coordinator log, presumed abort | nhật ký bộ điều phối, giả định huỷ khi không có quyết định (E2) |

---

## 13. Tự kiểm tra trước buổi bảo vệ

Mỗi thành viên tự đánh dấu. Ô nào chưa chắc thì đọc lại mục tương ứng.

- [ ] Vẽ được sơ đồ 2 máy, 5 container, cổng, mũi tên fdw, trong 1 phút (Mục 3.3, Hình 1 của báo cáo).
- [ ] Nói được cách chia **từng bảng trong 9 bảng** và lý do (Mục 3.1).
- [ ] Giải thích vì sao không chia booking theo đoàn (Mục 3.2).
- [ ] Giải thích dải `booking_id` và CHECK (Mục 3.4).
- [ ] Kể 8 FK và vì sao đều cục bộ (Mục 3.5).
- [ ] Đọc được một kế hoạch EXPLAIN VERBOSE, chỉ ra Foreign Scan, Async, Remote SQL (Mục 2.3).
- [ ] Đếm được 11 vòng của Q2 bằng tay (Mục 5, phần Q2).
- [ ] Giải thích 13 vòng khi tắt async hoặc tắt parallel_commit (Mục 6, N3).
- [ ] Trình bày 2PC và tình huống treo (Mục 2.4, 8.1).
- [ ] Giải thích N1 (13/16/14/17), N4 (6,43% và dự đoán khi 30%), N5 (+24%, GIN) (Mục 6).
- [ ] Tự chạy được D1–D8 trên hai máy mà không cần người khác (Mục 7).
- [ ] Biết xử lý khi đổi mạng (sửa `deploy.toml` → `make link`).
- [ ] Nêu được ít nhất 3 giới hạn của hệ (Mục 8).
- [ ] *(Mở rộng)* Nói được E1, E2 giải quyết giới hạn nào, chạy được kịch bản Mục 14.4, và đọc được 3 bảng B1–B3 (Mục 14.3).
- [ ] *(Mở rộng)* Trước D8: `srv_phuquoc` trỏ về trạm chính, không có `ext-watch` đang chạy.

**Gợi ý slide 4 phút cho N1–N5** (mỗi slide một con số, khoảng 45 giây):
1. N1: bảng số dòng + câu "tổng = đối chứng; tỉ lệ theo WEIGHTS của bộ sinh".
2. N2: trích một đoạn EXPLAIN của Q2 (Async Foreign Scan + Remote SQL có GROUP BY) đặt cạnh Q1 không có Foreign Scan.
3. N3: biểu đồ cột 0 ms so với 30 ms cho Q1–Q3, cùng bảng số vòng 11 / 13 / 13.
4. N4: 6,43%, sơ đồ đoàn 1 có phòng ở 3 vùng, dự đoán khi 30%.
5. N5: bảng dung lượng jsonb, quan hệ, GIN.

---

## 14. Phần mở rộng E1, E2 (ngoài yêu cầu đề) và E3 (bảo mật đường truyền, nay là mặc định)

> **Đề không yêu cầu phần này.** Nhóm làm thêm để khắc phục hai giới hạn ở Mục 8 (#1 và #5). Phần này không nằm trong `make all`,
> không thêm bảng hay cột, không đổi D1–D8 hay N1–N5. Tài liệu gốc: [NANG_CAO.md](NANG_CAO.md); báo cáo §5.6.
> **Cách nói khi trình bày:** *"Phần bắt buộc đã xong. Nhóm làm thêm hai việc cho hai giới hạn mà chính nhóm chỉ ra: một trạm chết thì mất đọc cả vùng,
> và bộ điều phối 2PC chết thì giao dịch bị treo."*

### 14.1. E1 — Bản sao dự phòng cho mảnh `phuquoc` + chuyển đọc

**Vấn đề:** mỗi mảnh chỉ có một bản. D8 tắt một trạm thì Q2–Q5 lỗi, mất đọc cả vùng.

**Cách làm (`tools/ext_replica.py`):**
- `phuquoc_replica` là một container PostgreSQL ở **máy A** (cổng 5445), chế độ *hot standby*. Nó nhận WAL của `phuquoc` (máy B) qua LAN
  bằng streaming replication bất đồng bộ.
- `make ext-replica` làm hết từ máy A, **máy B không phải thao tác gì**:
  1. Kết nối `phuquoc` bằng SQL, nối dòng `host replication all all scram-sha-256` vào `pg_hba.conf` bằng `COPY … TO PROGRAM`, rồi `pg_reload_conf()`.
  2. Tạo **replication slot** để trạm chính giữ WAL cho tới khi bản sao nhận xong. Nếu không có slot, bản sao tắt lâu có thể bị thiếu WAL.
  3. Chạy container, lần đầu chạy `pg_basebackup -R -X stream -S <slot>` (sao chép toàn bộ thư mục dữ liệu + tự cấu hình làm standby).
     `max_connections` và `max_prepared_transactions` của bản sao phải ≥ trạm chính, nếu không standby không khởi động.
- `make ext-failover`: `ALTER SERVER srv_phuquoc OPTIONS (SET host …, SET port …)` ở trạm trung tâm.
  `all_*` và Q2–Q5 **giữ nguyên**: chúng vẫn đọc `s_phuquoc.*`, chỉ địa chỉ của máy chủ ngoài thay đổi.
  postgres_fdw tự bỏ kết nối cũ khi tuỳ chọn server đổi.
- `make ext-failback` làm ngược lại. `make ext-watch` kiểm tra mỗi 1 s, tự failover khi trạm chính mất và tự failback khi trạm chính sống lại.

**Ba quyết định phải giải thích được:**
1. **Chỉ chuyển ĐỌC, không promote.** Đề yêu cầu "không ghi nhầm sang trạm khác", và bản sao chỉ đọc tự bảo đảm điều đó.
   Promote thì cần fencing: nếu trạm chính chỉ đứt mạng mà vẫn sống thì sẽ có hai trạm chính (*split-brain*).
   Ngoài ra, các `booking_id` trạm chính đã cấp nhưng chưa kịp sao chép có thể bị bản sao cấp lại.
2. **Bất đồng bộ chứ không đồng bộ** (số liệu ở B1): đồng bộ chỉ tốn +6–7 ms, nhưng bản sao chết sẽ làm mọi COMMIT ở trạm chính treo.
   Như vậy sẵn sàng của trạm chính lại phụ thuộc vào trạm phụ.
3. **Sao chép vật lý chứ không logic:** ta cần một bản giống hệt cả mảnh để thay trạm chính khi đọc. Logical replication hợp hơn cho
   từng bảng (ví dụ có thể thay 2PC của `tour_group`, đổi lấy độ trễ đồng bộ).

**Kết quả (hai máy thật):** dựng ≈ 10 s; trạng thái `streaming/async`; số dòng chính = bản sao = 19.755; trễ sao chép trung vị 1,9 ms.
Tắt `phuquoc` thì Q2 lỗi; sau failover Q2 (60 dòng) và Q3 (46 dòng) **khớp đối chứng**. `ext-watch` chuyển trong ≤ 1–2 s.

### 14.2. E2 — 2PC có nhật ký điều phối bền vững + phục hồi

**Vấn đề:**
1. Bộ điều phối (giao diện) không ghi quyết định. Nếu nó chết sau PREPARE thì 4 trạm giữ giao dịch lưỡng lự và giữ khoá, và không ai biết nên commit hay huỷ.
2. **Lỗi đúng đắn của bản cũ:** nếu `COMMIT PREPARED` lỗi ở một trạm sau khi trạm trước đã commit, nhánh `except` lại ROLLBACK các trạm còn lại.
   Kết quả là đoàn có ở trạm này mà không có ở trạm kia, tức mất nguyên tử. E2 sửa lỗi này.

**Giao thức (`tools/twopc.py`, giao diện dùng chung hàm `create_tour_group()`):**
```
nhật ký: begin(gid, 4 trạm, dòng)  fsync
pha 1  : mỗi trạm INSERT + PREPARE TRANSACTION        lỗi -> ghi abort, ROLLBACK PREPARED các trạm đã prepare
nhật ký: commit(gid)  fsync        <- ĐIỂM CAM KẾT
pha 2  : mỗi trạm COMMIT PREPARED                      lỗi -> để lại lưỡng lự, KHÔNG rollback
nhật ký: end(gid)
```
**Phục hồi** `make ext-2pc-recover` theo kiểu **presumed abort**: duyệt `tpc_recover()` ở từng trạm.
- Nhật ký có `commit` → COMMIT PREPARED.
- Không có quyết định → ROLLBACK PREPARED. Điều này an toàn vì commit chỉ được gửi sau khi `commit` đã nằm trên đĩa.
- Giao dịch mới PREPARE dưới 10 s thì được bỏ qua (bộ điều phối có thể vẫn đang chạy), trừ khi chạy với `FORCE=1`.

**Giả lập bộ điều phối chết:** `make ext-2pc-crash CRASH=…` (dùng `os._exit`, không dọn dẹp gì):

| `CRASH=` | Để lại | `ext-2pc-status` | `ext-2pc-recover` |
|---|---|---|---|
| `prepare` | 4 trạm đã PREPARE, chưa có quyết định | 4 lưỡng lự, "sẽ ROLLBACK" | ROLLBACK 4 trạm |
| `decision` | đã ghi commit, chưa commit trạm nào | 4 lưỡng lự, đoàn chưa thấy ở đâu | COMMIT 4 trạm |
| `mid-commit` | đã commit `dalat`, 3 trạm còn lưỡng lự | **⚠ bản sao không nhất quán**: chỉ `dalat` thấy đoàn | COMMIT 3 trạm còn lại |

`status` còn thử INSERT lại đúng `tour_group_id` đang lưỡng lự (`lock_timeout 700ms`) và nhận lỗi `lock timeout`.
Đây là bằng chứng **tận mắt** của tính "chặn" trong 2PC (Mục 2.4).

### 14.3. Đánh giá — so sánh phương án (`make ext-bench`, `results/ext/ext_bench.csv`)

Mỗi phương án đo 21 lần, bỏ lần đầu, lấy trung vị. Dòng thử bị xoá khi xong; cấu hình tạm được trả lại trong `finally`; `make check` vẫn ĐẠT.

**B1 — ghi một lượt đặt vào `phuquoc` (máy B), bản sao ở máy A:**

| `synchronous_commit` | Ghi | Ghi → thấy ở bản sao | RPO |
|---|---:|---:|---|
| `local` (bất đồng bộ, mặc định) | **28,7 ms** | 30,6 ms | vài ms |
| `on` (chờ bản sao ghi đĩa) | 34,6 ms | 35,4 ms | 0 |
| `remote_apply` (chờ bản sao phát lại) | 35,7 ms | 36,4 ms | 0, đọc bản sao thấy ngay |

→ 28,7 ms ≈ 4 vòng A→B qua Wi-Fi (BEGIN, 2 INSERT, COMMIT). Chế độ đồng bộ thêm **đúng 1 vòng** B→A (+6–7 ms, +21–25%).

**B2 — Q2 khi `srv_phuquoc` trỏ tới trạm chính (máy B) hoặc bản sao (máy A):**

| Trễ | Trạm chính | Bản sao | Chênh |
|---:|---:|---:|---:|
| 0 ms | 68,2 ms | 43,5 ms | −25 ms |
| 30 ms | 439,5 ms | 330,9 ms | −109 ms ≈ **3,6 vòng** |

→ Bớt một trạm xa thì bớt ≈ 3–4 vòng, vì START/DECLARE/CLOSE được gửi lần lượt cho từng trạm. Đây là một cách **kiểm chứng độc lập** con số 11 vòng
của N3 (≈ 3 trạm × 3 vòng + 2). Bản sao nhanh hơn chỉ vì nó **ở gần** (cùng máy A, không bị netem). Bản sao thật nên đặt ở vùng khác.

**B3 — tạo một đoàn tour ở 4 trạm:**

| Phương án | Thời gian | Nguyên tử | Phục hồi tự động |
|---|---:|---|---|
| 4 INSERT autocommit (mốc) | 149,4 ms | Không | — |
| 2PC không nhật ký | 218,8 ms (+46%) | Có | Không |
| 2PC + nhật ký fsync (E2) | **220,6 ms** (+1,8 ms so với 2PC) | Có | **Có** |

→ 2PC tốn ≈ 2 vòng mỗi trạm (BEGIN/PREPARE, COMMIT PREPARED). Nhật ký gần như miễn phí, vì fsync vào SSD cục bộ còn mỗi vòng mạng tốn vài ms.
(Trên macOS `fsync` không ép xả bộ đệm của ổ đĩa, nên đây là giới hạn dưới.) Cải tiến tiếp: gửi PREPARE/COMMIT **song song** tới 4 trạm.

### 14.4. Kịch bản trình bày (chỉ khi còn thời gian hoặc được hỏi; làm SAU D8)

```bash
# chuẩn bị trước buổi bảo vệ: make ext-replica   (≈ 10 s)
make ext-replica-status               # streaming, số dòng khớp, srv_phuquoc -> trạm chính
# máy B: make stop-site SITE=phuquoc
make q QUERIES=Q2                     # lỗi — như D8
make ext-failover && make q QUERIES="Q2 Q3"   # chạy lại, khớp đối chứng
# máy B: make start-site SITE=phuquoc
make ext-failback

make ext-2pc-crash CRASH=mid-commit   # bộ điều phối chết sau khi commit 1/4 trạm
make ext-2pc-status                   # 3 trạm lưỡng lự, bản sao lệch, INSERT bị chặn
make ext-2pc-recover && make check    # commit nốt theo nhật ký; vẫn ĐẠT
```

### 14.5. Câu hỏi vấn đáp về phần mở rộng

51. **E1, E2 có bắt buộc không? Có làm thay đổi kết quả chấm không?** Không. Chúng nằm ngoài `make all`; D1–D8, N1–N5 và lược đồ giữ nguyên.
52. **Bản sao bất đồng bộ thì failover có mất dữ liệu không?** Có thể mất phần chưa sao chép, đo được ≈ 2 ms (B1). Chỉ xảy ra khi trạm chính chết đúng lúc đang ghi.
    Muốn RPO = 0 thì dùng `synchronous_commit = on`: tốn +6 ms, nhưng bản sao chết thì ghi bị treo.
    Cách có cả hai: ≥ 2 bản sao, `synchronous_standby_names = 'ANY 1 (r1, r2)'`.
53. **Sao không promote bản sao để ghi tiếp?** Mục 14.1, quyết định 1: split-brain, cần fencing, và trùng dải ID.
54. **Vì sao Q2 đọc từ bản sao lại nhanh hơn?** Do vị trí (cùng máy với trung tâm, không bị netem), không do bản sao. Bớt một trạm xa thì bớt ≈ 3,6 vòng (B2).
55. **`pg_hba.conf` ở máy Windows được sửa thế nào mà không cần vào máy B?** Superuser chạy `COPY (SELECT …) TO PROGRAM 'cat >> …/pg_hba.conf'`
    ngay trong container của trạm chính, rồi `pg_reload_conf()`. Đây cũng là lý do trong thực tế không bao giờ cấp superuser cho ứng dụng.
56. **Replication slot để làm gì, có rủi ro gì?** Để trạm chính giữ WAL cho tới khi bản sao nhận. Rủi ro: bản sao bỏ đi mà không xoá slot thì WAL
    tích mãi, làm đầy đĩa. Vì vậy `make ext-replica-down` có xoá slot.
57. **Vì sao bộ điều phối phải fsync quyết định TRƯỚC khi gửi COMMIT PREPARED?** Nếu nó chết sau khi một trạm đã commit mà quyết định chưa nằm trên đĩa,
    thì lúc phục hồi nó sẽ presumed abort và rollback các trạm còn lại, làm mất nguyên tử.
58. **Presumed abort là gì, vì sao an toàn?** Không thấy quyết định thì coi như huỷ. An toàn vì quy tắc "ghi commit rồi mới gửi commit" bảo đảm
    không có `commit` trên đĩa nghĩa là chưa trạm nào commit.
59. **Có nhật ký rồi 2PC còn chặn không?** Còn: từ lúc bộ điều phối chết tới lúc chạy recover, các trạm vẫn giữ khoá (`status` cho thấy INSERT bị chặn).
    Muốn không chặn thì dùng 3PC hoặc commit dựa trên đồng thuận (Paxos/Raft commit, Chương 6).
60. **Lỗi pha 2 trong bản cũ là gì?** Một trạm lỗi lúc COMMIT PREPARED thì code cũ rollback các trạm chưa commit, dù trạm trước đã commit,
    nên mất nguyên tử. E2: sau điểm cam kết không bao giờ rollback.
61. **Nhật ký đặt ở đâu, mất thì sao?** Tệp `results/2pc_coordinator.jsonl` ở máy A. Mất tệp thì recover chỉ còn presumed abort; giao dịch đã commit
    một phần sẽ không tự hoàn tất được. Bản thật đặt nhật ký trên lưu trữ bền có sao chép.
62. **2PC tốn bao nhiêu, nhật ký tốn bao nhiêu?** B3: 2PC +69 ms so với 4 INSERT; nhật ký thêm +1,8 ms.

63. **Q3 của đoàn chỉ đi một vùng có rẻ hơn không?** Không. Đoàn 3 (45 phòng, chỉ ở danang) mất 426 ms, đoàn 1 (3 vùng) mất 428 ms ở trễ 30 ms
    (`results/n4_q3_single_vs_multi.csv`). Trung tâm không biết trước đoàn đi đâu nên lúc nào cũng hỏi đủ 4 trạm. Muốn rẻ hơn thì phải có
    bảng chỉ mục "đoàn → vùng" ở trung tâm (đổi lại mỗi lượt đặt tour phải ghi thêm một chỗ, tức thêm một bước 2PC).
64. **Không chạy được `tc` thì đo trễ bằng cách nào?** `DELAY_MODE=proxy make delay-on` dùng proxy TCP giữ mỗi gói chiều về 30 ms
    (`tools/latency_proxy.py`). Kết quả gần như `tc` (Q2 430 so với 436 ms) vì mỗi vòng khứ hồi vẫn chậm thêm đúng 30 ms. Khác biệt:
    proxy chạy ở máy chủ (thêm một chặng container → host), và chỉ áp cho kết nối postgres_fdw chứ không phải mọi gói.

64b. **Vì sao E3 thành mặc định?** Đề yêu cầu hai máy thật; khi các trạm ở các nơi khác nhau thì dữ liệu khách đi qua mạng.
    Chi phí TLS chỉ nằm ở lúc mở kết nối (mở bằng TLS + chứng chỉ còn nhanh hơn không mã hoá + SCRAM), nên không có lý do để tắt.
    Mọi số đo trong báo cáo (Bảng 3) đã đo lại khi bật TLS.
65. **E3 làm gì, khác VPN thế nào?** VPN (WireGuard, Tailscale) lo phần *đi tới được* và mã hoá đường hầm. E3 lo phần *tin ai* ở chính lớp CSDL:
    trạm xa chỉ nhận `fdw_reader` khi kết nối có TLS và chứng chỉ máy khách do CA của nhóm ký; trạm trung tâm chỉ nói chuyện với
    máy có chứng chỉ đúng tên (`verify-full`). Lộ VPN hay giả IP vẫn không vào được (T3–T6).
66. **Vì sao gọi bằng IP lại bị từ chối (T4)?** Chứng chỉ máy chủ chỉ có SAN là tên `phuquoc.db.nhom8.internal`. `verify-full` so tên
    đã gọi với SAN, nên gọi bằng IP thì không khớp. Nhờ vậy kẻ chiếm được IP mà không có khoá riêng của trạm sẽ không giả làm trạm được.
67. **TLS làm chậm truy vấn bao nhiêu?** Gần như không: Bảng 3 đo lại khi bật TLS, Q2 459 ms so với 436 ms không TLS, Q3 433 so với 423 (±5%, dao động Wi-Fi); số vòng Q2 10,9 so với 11,0. TLS chỉ tốn lúc mở kết nối,
    và mở bằng TLS + `cert` còn nhanh hơn không mã hoá + SCRAM (382 so với 469 ms ở trễ 30 ms), vì bỏ được 2 vòng SASL.
    `sslnegotiation=direct` bỏ thêm vòng `SSLRequest` (340 ms).
68. **Vì sao `fdw_reader` chỉ có SELECT?** Mọi thứ đi qua fdw (Q1–Q5, `make check`) đều chỉ đọc; ghi đi thẳng tới trạm. Lộ khoá của trạm
    trung tâm thì kẻ tấn công cũng chỉ đọc được, không sửa hay xoá được mảnh (T7).
69. **Còn thiếu gì để thật sự production?** Mật khẩu `postgres` vẫn trong `deploy.toml` (nên dùng secret manager và mỗi ứng dụng một role);
    CA nên để ngoại tuyến, chứng chỉ ngắn hạn tự gia hạn và có thu hồi (CRL/OCSP); DNS thật thay cho `/etc/hosts`.
70. **`make all` cấp chứng chỉ cho máy B thế nào mà khoá không rời máy B?** Máy A gửi lệnh qua kênh quản trị SQL (`COPY … FROM PROGRAM`):
    `openssl genpkey` chạy TRONG container của trạm ở máy B, chỉ CSR quay về máy A, chỉ chứng chỉ được gửi sang. Muốn không ai có
    superuser qua mạng thì dùng chế độ chặt: mỗi máy tự `make tls-site-csr` / `tls-site-install`, máy A chỉ `make tls-sign`.
71. **CA ký thế nào cho an toàn?** Trong container dùng một lần, `--network none`, chỉ gắn `build/e3/`. CA kiểm chữ ký CSR và áp chính sách
    (chỉ CN của 3 trạm xa hoặc `fdw_reader`), tự đặt SAN/EKU, cấp hạn 90 ngày, serial ngẫu nhiên, ghi `issued.jsonl`. CSR xin `CN=postgres` bị từ chối (N1).
72. **Cài lỗi giữa chừng thì sao?** Trước khi cài đã sao lưu `pg_hba.conf`, `postgresql.auto.conf` và chứng chỉ cũ. Sau reload, script kiểm tra lại:
    `pg_hba` không có dòng lỗi, TLS 1.3 thật, máy chủ phục vụ đúng vân tay chứng chỉ mới. Sai một điểm là tự hoàn tác (N4) và giữ khoá chờ để cài lại.
73. **Gia hạn chứng chỉ có phải dừng hệ không?** Không. `csr ROTATE=1` → `sign` → `install`, reload cấu hình, kết nối mới dùng chứng chỉ mới (N5).
    Nếu máy B gỡ TLS mà trạm trung tâm vẫn đòi `verify-full` thì truy vấn báo lỗi chứ không tự hạ xuống không mã hoá (N6, fail-closed).

**Giới hạn còn lại (nói trước khi bị hỏi):** chỉ `phuquoc` có bản sao; bản sao ở máy A nên máy A chết thì vẫn hết (trung tâm là điểm lỗi đơn lẻ);
recover chạy khi được gọi, không phải tiến trình nền; trường hợp một trạm chết đúng lúc pha 2 đã có mã xử lý nhưng chưa được thử riêng.

# Đặc tả: Project Kernel & Canonical Engineering Object Model

> **Trạng thái tài liệu:** Bước 1 ("schema + module trơn", mục 11) **đã có code**, cả 4 câu
> hỏi nghiệp vụ ở mục 13 (gốc) **đã được quyết** (2026-08-14) và triển khai —
> `src/project_kernel.py` + `tests/test_project_kernel.py` (47 test) +
> `tests/test_project_kernel_postgres.py` (8 test, **chạy thật** trên Postgres 16 cục bộ,
> không phải chỉ viết cú pháp). Toàn bộ bộ test dự án: 801 đạt/0 lỗi khi có
> `TEST_DATABASE_URL`, 793 đạt/8 skip khi không có (đúng kiểu graceful skip như test OCR).
> Module vẫn đứng **độc lập** — chưa nối vào `agents.py`/`graph.py`/`tools.py`, chưa có
> route API (mục 10, 11 bước 2–4). Xem mục 13 để biết quyết định cụ thể cho từng câu hỏi.

---

## 1. Vấn đề đang giải quyết

Hệ thống hiện tại **không có khái niệm "dự án" nào sống lâu hơn một phiên hội thoại**.

Bằng chứng cụ thể trong code hiện có:

- `src/state.py::AgentState` là state của **một lượt hội thoại LangGraph**, xóa/tạo lại
  mỗi thread. Không có bảng nào ghi "dự án X có những bản vẽ nào, đã bóc khối lượng lần
  nào chưa, kết quả trước và sau khi sửa khác nhau ở đâu".
- `src/workspace.py` cô lập **theo người dùng** (`get_user_workspace`), không phải theo
  **dự án**. Một người dùng có 3 dự án thì cả 3 vẫn dùng chung một thư mục, không có ranh
  giới nào giữa chúng ngoài tên file người dùng tự đặt.
- `src/cad_revision.py` theo dõi lịch sử **một file .dxf**, không theo dõi lịch sử của
  *đối tượng kỹ thuật* (một AHU, một tuyến ống) xuyên suốt nhiều file, nhiều lần bóc khối
  lượng, nhiều lần sửa.
- Không có ID nào của một đối tượng kỹ thuật (thiết bị, đoạn ống, tủ điện) tồn tại ngoài
  phạm vi một lần gọi tool. Gọi `auto_quantity_takeoff` hai lần trên cùng bản vẽ ra hai kết
  quả độc lập, không có cách nào biết "ống này ở lần bóc thứ 2 chính là ống nào ở lần bóc
  thứ 1" để so sánh hay truy vết.

`progress.md` gọi đây là mảnh thiếu lớn nhất của Phase B: **Project State / Digital Twin /
Engineering Graph** (mục 3.1, dòng "Điểm thiếu lớn nhất"). Project Kernel là lớp nền để lấp
mảnh đó — không phải một tính năng mới cho người dùng cuối, mà là hạ tầng để các tính năng
sau này (Ask the Building, impact analysis, what-if) có chỗ đứng.

## 2. Phạm vi & KHÔNG phạm vi của đặc tả này

**Trong phạm vi** (P0 #1–#4 theo `progress.md` mục 39):

- Project Kernel: registry cho project, revision, source, object.
- Canonical Engineering Object Model: schema chung mọi discipline dùng.
- Stable ID: quy tắc sinh ID không đổi suốt vòng đời đối tượng.
- Source references: liên kết đối tượng → file gốc sinh ra nó.

**KHÔNG trong phạm vi** (để lại cho đặc tả riêng sau, không giải quyết ở đây):

- Engineering Knowledge Graph traversal engine (truy vấn đồ thị nhiều bước, impact
  analysis) — `object_relations` ở mục 6.6 chỉ là **bảng lưu cạnh**, chưa phải engine
  truy vấn. Đó là P1, không phải P0.
- Evidence Engine, Rule Engine, Job/Event platform — mỗi cái là một đặc tả riêng.
- Đổi bất kỳ tool hiện có (`hvac_tools.py`, `cad_*.py`, ...) để ghi vào Project Kernel.
  Mục 11 có nói tới hướng nối, nhưng **không đề xuất làm ngay** — đúng nguyên tắc "đọc
  trước khi sửa" và "không rewrite vì muốn kiến trúc đẹp" (`progress.md` mục 40.1).
- Multi-tenant thật (tổ chức nhiều công ty dùng chung hạ tầng). Phạm vi ở đây là
  nhiều **dự án** trong cùng một triển khai, đã đủ để lấp khoảng trống hiện tại.

## 3. Nguyên tắc khóa cứng

Kế thừa nguyên văn từ `progress.md` mục 47, áp dụng cụ thể cho đặc tả này:

1. **Project state là canonical** — mọi agent đọc/ghi qua Project Kernel, không tự giữ
   bản sao trạng thái dự án riêng (đúng như cách `TOOLS_BY_ROLE` là nguồn duy nhất cho bộ
   tool của một vai trò, không ai được tự thêm tay).
2. **Không tạo graph database** khi Postgres/pgvector chưa đủ (mục 40.5) — `object_relations`
   là một bảng quan hệ thường, không phải Neo4j.
3. **Không thêm phụ thuộc mới nếu thư viện chuẩn đủ dùng** — đúng quyết định đã ghi trong
   `src/users.py` (SQLite qua `sqlite3`, không bcrypt/argon2, không ORM). Project Kernel đi
   theo đúng lựa chọn đó, xem mục 5.
4. **Đừng đoán schema Postgres/production khi chưa có ai duyệt** (`TECH_DEBT.md` mục 1) —
   backend Postgres để ngỏ qua `DATABASE_URL` đã có sẵn trong `config.py`, nhưng **không
   hiện thực ở lượt này**.
5. **Mọi thao tác file vẫn đi qua `resolve_safe_path`** — Project Kernel không thay thế
   `workspace.py`, chỉ thêm một lớp registry ở trên. File CAD/Excel thật vẫn nằm trong
   workspace như hiện tại; Project Kernel chỉ lưu **tham chiếu** (path/key), không lưu nội
   dung file.

## 4. Vị trí trong kiến trúc hiện có

Theo bảng "module theo tầng" ở `docs/DAC_TA_HE_THONG.md` mục 2, Project Kernel là module
tầng **Hạ tầng**, ngang hàng với `workspace.py`, `storage.py`, `checkpointer_factory.py` —
**không phải** một trong ba điểm nối mở rộng hiện có (`tools.py`, `standards_backend.py`,
`supervisor_pipeline.py`), vì nó không phải hành vi của agent mà là trạng thái nền mọi
agent dùng chung.

```text
                 ┌────────────────────────────────┐
                 │      src/project_kernel.py       │  ← module mới (mục 9)
                 │  (registry: project / revision /  │
                 │        source / object)           │
                 └─────────────────┬──────────────────┘
                                   │ đọc/ghi
                 ┌─────────────────┴──────────────────┐
                 │    data/project_kernel.sqlite        │  (mục 5)
                 └───────────────────────────────────────┘
                                   ▲
                 Chưa nối — mục 10 chỉ mô tả HƯỚNG nối,
                     không triển khai lượt này
                                   │
       ┌───────────────────────────┴───────────────────────────┐
  agents.py / graph.py                                 api.py (route mới,
  (không đổi ở lượt này)                                 opt-in, mục 11 bước 3)
```

## 5. Lưu trữ: SQLite mặc định, Postgres khi có instance thật ✅ Cả hai đã chạy thử

Khi viết đặc tả, quyết định là "SQLite trước, Postgres để ngỏ" — cùng lý do đã ghi ở
`src/users.py`, và vì lúc đó **chưa có instance Postgres thật để chạy thử**
(`TECH_DEBT.md` mục 1). Môi trường code hiện tại có Postgres 16 cài sẵn, nên quyết định đã
tiến thêm một bước: **cả hai backend đều đã triển khai và chạy thử thật**, không còn là kế
hoạch để ngỏ.

- **Mặc định (không có `DATABASE_URL`):** SQLite qua `sqlite3` thư viện chuẩn — cùng lựa
  chọn `src/users.py`, không thêm phụ thuộc. Đường dẫn qua `PROJECT_KERNEL_DB_PATH`, mặc
  định `data/project_kernel.sqlite`. Tách file riêng với `users.sqlite` để hai schema độc
  lập không khóa lẫn nhau khi ghi đồng thời, và xóa thử CSDL dự án lúc phát triển không
  đụng tài khoản người dùng thật.
- **Có `DATABASE_URL` thật + đã cài `psycopg`** (`uv sync --extra phase-c`, nhóm phụ thuộc
  đã có sẵn trong `pyproject.toml`, không phải thêm mới): dùng Postgres — đúng khuôn
  `src/checkpointer_factory.py::try_postgres_checkpointer` (Postgres nếu cấu hình được, rơi
  về SQLite nếu thiếu `DATABASE_URL` hoặc thiếu `psycopg`, không sập).
- **Không viết SQL hai lần theo dialect.** Toàn bộ câu lệnh DML dùng chung placeholder `?`;
  `_exec()` là điểm duy nhất dịch sang `%s` khi backend là Postgres. DDL (`CREATE TABLE`)
  portable sẵn giữa hai dialect vì mọi khóa chính là `TEXT` (uuid4), không dùng
  `AUTOINCREMENT`/`SERIAL`. Hai chỗ khác nhau thật sự: `INSERT OR IGNORE` (SQLite) so với
  `INSERT ... ON CONFLICT DO NOTHING` (Postgres) — gói trong `_insert_ignore()`; và kiểu
  lỗi va chạm khóa (`sqlite3.IntegrityError` so với `psycopg.errors.UniqueViolation`) —
  gói trong `_is_unique_violation()`.
- **Đã chạy thử thật, không chỉ viết cú pháp:** `tests/test_project_kernel_postgres.py` (8
  test) chạy trên một instance Postgres 16 cục bộ thật khi có biến môi trường
  `TEST_DATABASE_URL`, dùng một schema Postgres riêng cho mỗi test (tạo/xóa quanh test,
  cùng tinh thần cô lập với `tmp_path` của nhánh SQLite). Không có biến đó thì test tự
  `skip`, không fail — đúng cách các test phụ thuộc hạ tầng khác trong dự án xử lý (VD test
  OCR bỏ qua khi thiếu `tesseract-ocr`).
- **Chưa kiểm chứng** (thành thật, không tự nhận hơn những gì đã đo): concurrency thật của
  nhiều Celery worker cùng ghi (test ở trên chạy tuần tự trong một tiến trình), Postgres
  quản lý (RDS/Cloud SQL) với độ trễ mạng thật, connection pooling (mỗi lời gọi vẫn mở
  connection mới, giống hệt cách `users.py` làm với SQLite — chưa thành vấn đề ở quy mô
  hiện tại nhưng sẽ cần `psycopg_pool` nếu Project Kernel bị gọi tần suất cao).

## 6. Schema dữ liệu

Tất cả cột JSON lưu dưới dạng `TEXT` (SQLite không có kiểu JSON riêng), parse bằng module
`json` chuẩn khi đọc — đúng cách `unit_prices.meta.json` và `task_events.py` đang làm, không
cần phụ thuộc mới.

### 6.1 `projects`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `project_id` | TEXT PRIMARY KEY | Stable ID, xem mục 7 |
| `name` | TEXT NOT NULL | Tên dự án do người dùng đặt |
| `owner` | TEXT NOT NULL | `sub` của JWT / username — dùng chung khái niệm với `task_owner.py` |
| `status` | TEXT NOT NULL DEFAULT `'active'` | `active` \| `archived` |
| `created_at` | INTEGER NOT NULL | Unix timestamp |
| `metadata` | TEXT | JSON tự do (địa chỉ công trình, chủ đầu tư, ...) |

### 6.2 `revisions`

Revision ở đây là **revision của dự án** (project-wide), khác với revision file `.dxf` mà
`cad_revision.py` đang quản lý — xem phân biệt và câu hỏi mở ở mục 13.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `revision_id` | TEXT PRIMARY KEY | Stable ID |
| `project_id` | TEXT NOT NULL | Khóa ngoại tới `projects` |
| `parent_revision_id` | TEXT | NULL cho revision đầu tiên của dự án |
| `note` | TEXT | Mô tả lần sửa |
| `created_by` | TEXT NOT NULL | |
| `created_at` | INTEGER NOT NULL | |
| `status` | TEXT NOT NULL DEFAULT `'draft'` | `draft` \| `active` \| `superseded` |

Ràng buộc: mỗi `project_id` có đúng một revision `status='active'` tại một thời điểm — đây
là revision mà `get_object`/`list_objects` mặc định đọc nếu không truyền `revision_id`.

### 6.3 `sources`

Ghi nhận **file gốc**, phân biệt SOURCE/DERIVED đúng mục 8 của `progress.md`.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `source_id` | TEXT PRIMARY KEY | Stable ID |
| `project_id` | TEXT NOT NULL | |
| `kind` | TEXT NOT NULL | `dwg` \| `dxf` \| `ifc` \| `pdf` \| `xlsx` \| `spec` \| `standard` |
| `storage_key` | TEXT NOT NULL | Key trong `src/storage.py` (`LocalStorage`/`S3Storage`), **không phải path tuyệt đối** |
| `checksum` | TEXT | SHA-256 nội dung file lúc nạp — phát hiện file bị thay ngầm |
| `uploaded_by` | TEXT NOT NULL | |
| `uploaded_at` | INTEGER NOT NULL | |

Ràng buộc cứng: **không được ghi đè hàng đã có trong `sources`**. Một file sửa lại phải
tạo `source_id` mới — khớp nguyên tắc "không được ghi đè source" (`progress.md` mục 8).

### 6.4 `engineering_objects` — Canonical Engineering Object Model

Đây là bảng trung tâm. Schema JSON trong `progress.md` mục 10 được cụ thể hóa thành cột:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `object_id` | TEXT PRIMARY KEY | Stable ID, **không đổi** suốt vòng đời kể cả khi `properties` đổi — xem mục 7 |
| `project_id` | TEXT NOT NULL | |
| `revision_id` | TEXT NOT NULL | Revision mà bản ghi này thuộc về |
| `tag` | TEXT | Nhãn hiển thị cho kỹ sư (`"AHU-003"`) — xem phân biệt với `object_id` ở mục 7 |
| `type` | TEXT NOT NULL | `"AHU"`, `"pipe_segment"`, `"panel"`, ... — từ điển mở, không enum cứng (mỗi discipline tự định nghĩa type của mình, xem mục 13) |
| `discipline` | TEXT NOT NULL | `mechanical` \| `electrical` \| `plumbing` \| `firefighting` \| `bim` (khớp tên vai trò hiện có trong `TOOLS_BY_ROLE`) |
| `parent_id` | TEXT | Tự tham chiếu `object_id` — dựng cây hierarchy (Site→Building→Level→Zone→Space→System→Equipment→Component), KHÔNG cần cột riêng cho từng tầng |
| `properties` | TEXT (JSON) | Trường đặc thù discipline — xem ràng buộc ở mục 13 |
| `status` | TEXT NOT NULL DEFAULT `'discovered'` | Xem state machine mục 8 |
| `confidence` | REAL NOT NULL DEFAULT `1.0` | `0.0`–`1.0`. OCR/YOLO sinh object phải gán `< 1.0`, đúng nguyên tắc "OCR không đủ tư cách đi thẳng vào bảng khối lượng" đã áp dụng ở `TECH_DEBT.md` mục 13 |
| `created_at` | INTEGER NOT NULL | |
| `updated_at` | INTEGER NOT NULL | |

`geometry` trong schema mẫu ở `progress.md` **cố ý không có cột riêng** ở đây: hình học
thật đã có định dạng xác định trong DXF/IFC gốc, lặp lại nó trong SQLite là một bản sao có
thể lệch khỏi nguồn. Đối tượng trỏ tới hình học qua `object_source_refs.locator` (mục 6.5),
không sao chép tọa độ vào `properties`.

Index bắt buộc: `(project_id, revision_id)`, `(project_id, type)`, `(parent_id)` — đúng các
truy vấn liệt kê theo dự án/loại/cây phân cấp sẽ dùng nhiều nhất.

### 6.5 `object_source_refs`

Liên kết N–N giữa đối tượng và nguồn — một đối tượng có thể tổng hợp từ nhiều file (ví dụ
một thiết bị vừa có trong DXF vừa có trong specification PDF).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `object_id` | TEXT NOT NULL | |
| `source_id` | TEXT NOT NULL | |
| `locator` | TEXT | Vị trí trong nguồn: `"layer=M-DUCT,handle=1A2B"` cho DXF, `"page=3,cell=B12"` cho Excel, GUID cho IFC — chuỗi tự do vì mỗi loại nguồn có cách định vị khác nhau, ép chung một schema cứng sẽ mất thông tin |
| `extracted_at` | INTEGER NOT NULL | |

Khóa chính composite `(object_id, source_id, locator)`.

### 6.6 `object_relations`

Lưu cạnh của đồ thị quan hệ — **chỉ lưu**, không có engine truy vấn nhiều bước (ngoài phạm
vi, xem mục 2).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `from_id` | TEXT NOT NULL | |
| `to_id` | TEXT NOT NULL | |
| `relation_type` | TEXT NOT NULL | Một trong từ điển ở `progress.md` mục 9.1 (`contains`, `serves`, `powered_by`, `depends_on`, ...) |
| `project_id` | TEXT NOT NULL | Trùng lặp có chủ đích với `from_id`/`to_id` để lọc theo dự án không cần JOIN |
| `revision_id` | TEXT NOT NULL | |
| `created_at` | INTEGER NOT NULL | |

Khóa chính composite `(from_id, to_id, relation_type, revision_id)` — cùng một cặp đối
tượng có thể có nhiều loại quan hệ (`powered_by` và `near` cùng lúc), nhưng không trùng loại.

### 6.7 `project_members` — trả lời quyết định #3 ở mục 13

Thêm sau khi mục 13 (bản gốc) được quyết — không có trong bản đặc tả ban đầu.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `project_id` | TEXT NOT NULL | |
| `username` | TEXT NOT NULL | Không tham chiếu tới `users.sqlite` — cố ý tách khỏi CSDL người dùng (xem mục 13) |
| `role` | TEXT NOT NULL DEFAULT `'engineer'` | `viewer` \| `engineer` \| `admin` — cùng tên với `users.ROLES` nhưng phạm vi riêng từng dự án |
| `added_at` | INTEGER NOT NULL | |

Khóa chính composite `(project_id, username)`. `create_project` tự thêm `owner` làm thành
viên `admin` đầu tiên. Thêm lại một `username` đã có thì **cập nhật vai trò** (upsert qua
`ON CONFLICT ... DO UPDATE`) — khác với `sources` (mục 6.3), nơi ghi đè bị cấm tuyệt đối:
đổi vai trò thành viên là thao tác hợp lệ, đổi nội dung một file nguồn thì không.

## 7. Stable ID: quy tắc sinh và bất biến

Hai khái niệm tách biệt, dễ nhầm nếu gộp làm một:

- **`object_id`** — ID nội bộ, **không bao giờ đổi**, không bao giờ tái sử dụng, không
  mang ý nghĩa nghiệp vụ. Định dạng: `{type}:{uuid4_hex}`, ví dụ `ahu:3f9a2b1c8e7d4a5f9b0c1d2e3f4a5b6c`.
  Tiền tố `type` chỉ để dò lỗi bằng mắt khi đọc log/DB, **không được parse** để suy luận gì
  — logic không bao giờ được `if object_id.startswith("ahu:")`, phải đọc cột `type`.
  Sinh bằng `uuid.uuid4().hex` (thư viện chuẩn, không thêm phụ thuộc ULID/ksuid).
- **`tag`** — nhãn hiển thị cho kỹ sư (`"AHU-003"`), **có thể đổi** (đổi tên thiết bị vẫn
  là thiết bị đó), duy nhất trong phạm vi `(project_id, type)` chứ không toàn cục — hai dự
  án khác nhau đều có thể có `"AHU-003"` của riêng mình.

Vì sao tách: nếu dùng `tag` làm khóa chính (như ví dụ `"equipment:AHU-003"` trong
`progress.md` mục 7.2 dùng tạm để minh họa), đổi tên thiết bị hoặc trùng tag giữa hai lần
bóc tách sẽ làm ID "đổi", phá vỡ đúng bất biến "stable ID" mà P0 #3 yêu cầu. Quy tắc chốt ở
đây: **`object_id` bất biến, `tag` là dữ liệu nghiệp vụ bình thường nằm trong bảng, không
phải khóa chính.**

Đối tượng bị merge (hai lần bóc tách phát hiện cùng một thiết bị) **không được xóa một
trong hai `object_id` cũ rồi tạo mới** — phải giữ cả hai, đánh dấu một cái `status=superseded`
trỏ `properties.superseded_by = <object_id còn lại>`. Xóa cứng phá vỡ mọi
`object_relations`/`object_source_refs` đã trỏ tới ID đó.

## 8. Vòng đời đối tượng

Theo đúng state machine đã phác ở `progress.md` mục 7.2:

```text
DISCOVERED → NORMALIZED → VALIDATED → ACTIVE → MODIFIED → SUPERSEDED → ARCHIVED
```

| Trạng thái | Ý nghĩa | Ai chuyển |
|---|---|---|
| `discovered` | Vừa được một tool tự động phát hiện (CAD parse, OCR, YOLO) | Ghi tự động |
| `normalized` | Đã qua chuẩn hóa (đơn vị, tên loại) | Ghi tự động |
| `validated` | Đã qua rule/quy chuẩn — **ngoài phạm vi đặc tả này**, chờ Rule Engine | Rule Engine (chưa có) |
| `active` | Đang là trạng thái chính thức của dự án | Con người duyệt, hoặc tự động nếu confidence cao và không có rule chặn |
| `modified` | Có thay đổi đang chờ, chưa chốt vào revision mới | Agent/con người sửa |
| `superseded` | Bị thay thế bởi object khác (merge, sửa lớn) | Xem mục 7 |
| `archived` | Không còn dùng nhưng giữ lại để truy vết | Con người |

Chỉ cho phép **đi tới** trong danh sách trên hoặc `active → modified → active` (vòng sửa
lặp lại); không cho phép nhảy lùi tùy ý (ví dụ `archived → active` phải qua thao tác phục
hồi tường minh, không phải `UPDATE status`). Việc thực thi ràng buộc này thuộc về hàm
`update_object_status()` ở mục 9, không phải kiểm tra ở tầng gọi.

## 9. Module surface: `src/project_kernel.py`

> ✅ Đã triển khai (2026-08-14) — chữ ký hàm thật trong `src/project_kernel.py` khớp với
> phác thảo dưới đây, cộng thêm vài hàm đọc phụ (`get_revision`, `get_source`) và các bước
> kiểm tra ràng buộc (dự án/revision/parent phải tồn tại, `confidence` trong `0.0`–`1.0`)
> mà bản phác thảo không liệt kê hết. Coi khối bên dưới là tài liệu thiết kế, đọc code thật
> để biết chi tiết chính xác.

Theo đúng khuôn của `src/users.py` — module docstring giải thích quyết định, `_connect()`
riêng, `init_db()` idempotent, khóa `threading.Lock()` quanh ghi:

```python
"""Project Kernel — canonical project state cho Engineering OS.

[docstring giải thích 2-3 quyết định thiết kế chính, theo khuôn users.py]
"""

def init_db() -> None: ...

# --- Project ---
def create_project(name: str, owner: str, metadata: dict | None = None) -> dict: ...
def get_project(project_id: str) -> dict | None: ...
def list_projects(owner: str) -> list[dict]: ...

# --- Revision ---
def create_revision(project_id: str, created_by: str, note: str = "",
                     parent_revision_id: str | None = None) -> dict: ...
def activate_revision(revision_id: str) -> None: ...
def get_active_revision(project_id: str) -> dict | None: ...

# --- Source ---
def register_source(project_id: str, kind: str, storage_key: str,
                     uploaded_by: str, checksum: str = "") -> dict: ...

# --- Thành viên dự án (quyết định #3, mục 13) ---
def add_project_member(project_id: str, username: str, role: str = "engineer") -> dict: ...
def remove_project_member(project_id: str, username: str) -> None: ...
def list_project_members(project_id: str) -> list[dict]: ...
def get_member_role(project_id: str, username: str) -> str | None: ...

# --- Schema properties theo type (quyết định #1, mục 13) ---
def register_property_schema(type_: str, required_fields: list[str] | tuple[str, ...]) -> None: ...
def get_property_schema(type_: str) -> tuple[str, ...]: ...

# --- Object ---
def register_object(project_id: str, revision_id: str, type: str, discipline: str,
                     tag: str = "", parent_id: str | None = None,
                     properties: dict | None = None, confidence: float = 1.0) -> dict: ...
def get_object(object_id: str) -> dict | None: ...
def list_objects(project_id: str, revision_id: str | None = None,
                  type: str | None = None, discipline: str | None = None) -> list[dict]: ...
def update_object_status(object_id: str, new_status: str) -> None:
    """Ném ValueError nếu chuyển trạng thái không hợp lệ — xem bảng mục 8."""
def try_auto_activate(object_id: str) -> bool:
    """Tự chuyển validated -> active nếu confidence đạt ngưỡng cấu hình (quyết định #4)."""

# --- Source ref & relation ---
def attach_source_ref(object_id: str, source_id: str, locator: str = "") -> None: ...
def link_objects(from_id: str, to_id: str, relation_type: str,
                  project_id: str, revision_id: str) -> None: ...
def get_relations(object_id: str, relation_type: str | None = None) -> list[dict]: ...
```

Không có hàm `delete_object` — đúng mục 7, đối tượng chỉ chuyển trạng thái, không xóa cứng
(trừ hàm dọn dữ liệu test riêng, giống `reset_storage_for_tests()` trong `storage.py`).

## 10. Điểm nối với hệ thống hiện có

**Ở lượt đặc tả này, module đứng độc lập — không nối vào `agents.py`/`graph.py`/`tools.py`.**
Lý do: bài học mục 3.5 của `progress.md` là mọi lỗi nặng nhất đều sinh ra khi hai phần
*ghép* với nhau, không phải khi từng phần đứng riêng. Viết Project Kernel độc lập trước,
có test riêng chạy xanh, rồi mới nối — đúng thứ tự "regression baseline trước, ghép sau".

Hướng nối dự kiến cho **lượt code sau** (không làm ở đây, chỉ ghi lại để không quên):

- Một tool mới, đăng ký qua đúng điểm nối đã có (`src/tools.py` → `TOOLS_BY_ROLE`), gọi
  `register_object`/`link_objects` sau khi `auto_quantity_takeoff` hoặc CAD parse chạy
  xong — **opt-in**, không đổi hành vi mặc định của các tool hiện có.
  Việc gọi Project Kernel không được nằm bên trong `hvac_tools.py`/`cad_*.py` bằng cách sửa
  trực tiếp các hàm đó (sẽ lặp lại đúng lỗi "patch lúc import" — ở đây là "gọi chéo lúc
  không cần"); phải là một bước riêng, rõ ràng trong luồng, agent chủ động gọi.
- Route FastAPI mới `src/api.py` (`/api/v1/projects`, `/api/v1/projects/{id}/objects`),
  dùng `Depends(require_api_key)`/`Depends(require_role(...))` **y hệt** các route hiện có
  — không có route nào miễn xác thực (đúng nguyên tắc dự án mục 6 trong `CLAUDE.md`).
- Workspace vẫn không đổi: `storage_key` trong bảng `sources` trỏ tới key trong
  `src/storage.py`, không trỏ thẳng tới path trên đĩa.

## 11. Kế hoạch triển khai theo giai đoạn

1. ✅ **Schema + module trơn** (2026-08-14). `src/project_kernel.py` với đủ hàm ở mục 9,
   `init_db()`, `tests/test_project_kernel.py` (20 test: đường vui, cách ly dự án, bất biến
   ID, vòng đời đối tượng, không ghi đè source, không tạo quan hệ trùng). Không có route
   API, không có tool nào gọi vào — canh bằng `test_project_kernel_khong_import_tools_hoac_agents`
   trong `tests/test_no_import_cycles.py`. Đứng độc lập như `storage.py` lúc mới thêm.
2. ⬜ **Một đường ghi thật, opt-in.** Chọn đúng MỘT luồng hiện có (đề xuất:
   `auto_quantity_takeoff`) để thử ghi object vào kernel sau khi chạy xong, sau một cờ cấu
   hình tắt theo mặc định (`PROJECT_KERNEL_ENABLED=false` mặc định) — không đổi hành vi ai
   đang dùng hệ thống.
3. ⬜ **Route API + xác thực**, để web/Revit/AutoCAD plugin đọc được project state.
4. ⬜ **Digital Twin traversal / impact analysis** — chỉ sau khi có dữ liệu thật từ bước 2
   để biết `object_relations` thực tế trông ra sao, tránh thiết kế truy vấn cho dữ liệu
   tưởng tượng.

Không nhảy thẳng vào bước 3–4 trước khi bước 1–2 chạy đạt bằng dữ liệu thật — đúng
`progress.md` mục 40.1 ("không rewrite vì muốn kiến trúc đẹp") áp theo chiều ngược: cũng
không *xây* vì muốn kiến trúc đẹp trước khi có dữ liệu thật để kiểm chứng thiết kế đó đúng.

## 12. Kế hoạch test

Theo văn hóa dự án (mọi PR chạy `uv run pytest -q` đủ bộ, không chỉ test phần mới):

- **`tests/test_project_kernel.py`** (file mới):
  - Tạo project → tạo revision → đăng ký object → object đọc lại đúng nguyên trường.
  - `object_id` không đổi qua hai lần `register_object` khác `tag` cho cùng một object (áp
    dụng khi có API update; nếu `register_object` luôn tạo mới thì test là "gọi 2 lần tạo
    2 `object_id` khác nhau", tức test đúng "ID không tái sử dụng").
  - Cách ly dự án: object của `project_id=A` không xuất hiện trong `list_objects(project_id=B)`.
  - `update_object_status` từ chối chuyển trạng thái không hợp lệ (`archived → active` trực
    tiếp phải ném lỗi).
  - `object_relations`: `link_objects` hai lần cùng `relation_type` không tạo hàng trùng
    (khóa chính composite chặn).
  - Không ghi đè được hàng `sources` đã có (`register_source` với `source_id` trùng phải
    ném lỗi, không phải `UPDATE`).
- **`tests/test_no_import_cycles.py`** (file đã có): thêm `src.project_kernel` vào danh
  sách module nạp trong tiến trình sạch — module này không được import `tools.py`/`agents.py`
  (đúng nguyên tắc mục 10: đứng độc lập, được gọi TỪ tool chứ không gọi ngược).
- Test cách ly khỏi CSDL người dùng thật: dùng `PROJECT_KERNEL_DB_PATH` trỏ file tạm trong
  `tmp_path` của pytest, đúng cách `tests/test_users.py` (nếu có) hoặc `test_api.py` đang
  cô lập `USER_DB_PATH`/`UPLOAD_DIR`.
- **`tests/test_project_kernel_postgres.py`** (file mới, thêm sau khi mục 13 được quyết):
  chạy lại một tập rút gọn (không phải toàn bộ 47 test — chỉ phần khác biệt thật giữa hai
  backend) trên Postgres 16 thật khi có `TEST_DATABASE_URL`; tự `skip` khi không có. Cô lập
  bằng một schema Postgres riêng mỗi test (tạo/xóa quanh test), cùng tinh thần `tmp_path`
  của nhánh SQLite.

## 13. Bốn câu hỏi nghiệp vụ — ĐÃ QUYẾT (2026-08-14)

Mục này ban đầu liệt kê 4 câu hỏi chưa có câu trả lời, chặn việc bắt đầu bước 2. Đã quyết
theo hướng "xây đúng cơ chế, không đoán thay chuyên môn" — chi tiết kỹ thuật ở docstring
đầu `src/project_kernel.py`, tóm tắt quyết định + lý do ở đây:

1. **Schema `properties` theo discipline — QUYẾT: điểm mở rộng, không hardcode.**
   `register_property_schema(type_, required_fields)` cho phép mỗi discipline module tự
   đăng ký trường bắt buộc cho `type` của mình (cùng khuôn `standards_backend.register_backend`).
   **Lý do không khóa cứng JSON Schema cho AHU/pump/cáp...:** vẫn đúng như đặc tả gốc nói —
   chưa ai duyệt danh sách trường, đoán là sai văn hóa dự án. Nhưng KHÔNG đoán không có
   nghĩa là không xây được gì: cái thiếu là *danh sách trường cụ thể*, không phải *cơ chế
   ép trường bắt buộc*. Xây cơ chế trước, để trống nội dung schema cho tới khi discipline
   module thật đăng ký — đây là hướng "chất lượng cao nhất" mà không đoán domain.
2. **Quan hệ với revision file CAD — QUYẾT: giữ tách biệt, không tự động hóa.** Revision dự
   án (mục 6.2) và revision file CAD (`cad_revision.py`) là hai khái niệm độc lập theo
   thiết kế, không phải "chưa quyết được nên tạm tách" — quyết định CHÍNH LÀ tách. Bước 2
   (khi nối vào tool) sẽ không tự tạo revision dự án từ `snapshot_cad`; việc "chốt" một
   revision dự án luôn là hành động tường minh của người gọi (tool/route), không suy luận
   ngầm trong kernel. Không cần thêm cột/bảng nào để nối hai khái niệm này.
3. **Mô hình quyền truy cập dự án — QUYẾT: bảng `project_members`.** Đã thêm (mục 6.7):
   `project_id`/`username`/`role`, 3 vai trò cùng tên `users.ROLES` nhưng phạm vi riêng
   từng dự án. `create_project` tự thêm owner làm `admin` đầu tiên. **Không** tái dùng vai
   trò hệ thống của `users.py` trực tiếp — một người có thể là `viewer` hệ thống nhưng
   `admin` của dự án họ tạo; gắn cứng hai khái niệm sẽ sai khi công ty có nhiều dự án phân
   quyền khác nhau cho cùng một người.
4. **Ngưỡng `confidence` — QUYẾT: `PROJECT_KERNEL_AUTO_ACTIVATE_CONFIDENCE`, mặc định
   0.8.** `try_auto_activate()` tự chuyển `validated` → `active` nếu đạt ngưỡng, giữ nguyên
   `validated` (chờ người duyệt) nếu chưa đạt. **Ranh giới thành thật:** đây là ngưỡng MẶC
   ĐỊNH kỹ thuật hợp lý (giống `OCR_MIN_CONFIDENCE` = 60 lúc mới thêm), KHÔNG phải số đã
   được người có kinh nghiệm QS/thiết kế đo bằng dữ liệu thật — đúng ranh giới
   `TECH_DEBT.md` mục 13 đã từng vạch ra cho OCR. Cấu hình được qua `config.py`, không phải
   hardcode, nên hiệu chỉnh sau này không cần sửa code.

Cả 4 quyết định đã có test thật (`tests/test_project_kernel.py`, phần "Quyết định #1–#4"),
kể cả trên backend Postgres (`tests/test_project_kernel_postgres.py`).

## 14. Tiêu chí "xong"

Tiêu chí xong của **đặc tả gốc**:

- [x] Schema đủ chi tiết để viết `CREATE TABLE` không cần đoán thêm.
- [x] Phân biệt rõ `object_id` (bất biến) và `tag` (nghiệp vụ) — điểm dễ làm sai nhất.
- [x] Có kế hoạch test trước khi có code (mục 12).
- [x] Liệt kê tường minh câu hỏi mở thay vì tự quyết định thay người có chuyên môn — sau đó
      đã quyết theo hướng "xây cơ chế, không đoán nội dung domain" (mục 13).

Tiêu chí xong của **bước 1 ("schema + module trơn", mục 11) + 4 quyết định mục 13**:

- [x] `src/project_kernel.py` khớp module surface mục 9, gồm cả phần mở rộng cho 4 quyết định.
- [x] `tests/test_project_kernel.py` (47 test): đường vui, cách ly dự án, bất biến ID, vòng
      đời đối tượng, không ghi đè source, không tạo quan hệ trùng, registry schema
      properties, thành viên dự án, tự động active theo ngưỡng confidence.
- [x] `tests/test_project_kernel_postgres.py` (8 test): **chạy thật** trên Postgres 16 cục
      bộ khi có `TEST_DATABASE_URL`, tự `skip` khi không có.
- [x] `uv run pytest -q` đủ bộ vẫn xanh — 793 đạt/8 skip (không có `TEST_DATABASE_URL`),
      801 đạt/0 skip (có) — 2026-08-14. Không chỉ test mới.
- [x] Không nối vào `agents.py`/`graph.py`/`tools.py` — canh bằng
      `test_project_kernel_khong_import_tools_hoac_agents`.

**Còn lại trước khi bước 2 (nối vào tool thật):** không còn câu hỏi thiết kế nào ở mục 13,
nhưng bước 2 vẫn là việc CHƯA làm — chọn đúng một luồng hiện có để nối (mục 11 đề xuất
`auto_quantity_takeoff`), sau cờ tắt mặc định, và cần review riêng vì lần đầu Project Kernel
chạm vào code đang phục vụ người dùng thật.

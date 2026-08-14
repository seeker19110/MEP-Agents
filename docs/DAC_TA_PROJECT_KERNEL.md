# Đặc tả: Project Kernel & Canonical Engineering Object Model

> **Trạng thái tài liệu:** Bước 1 ("schema + module trơn", mục 11) **đã có code** —
> `src/project_kernel.py` + `tests/test_project_kernel.py` (781 test đạt/0 lỗi toàn bộ bộ
> test, xác minh 2026-08-14). Module đứng **độc lập**, đúng như mục 10 quy định: chưa nối
> vào `agents.py`/`graph.py`/`tools.py`, chưa có route API. Bước 2–4 (đường ghi thật opt-in,
> route API, Digital Twin traversal) **vẫn chưa làm** — mục 13 liệt kê 4 câu hỏi nghiệp vụ
> cần duyệt trước khi bước 2 chạm vào bất kỳ tool hiện có nào.

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

## 5. Lưu trữ: SQLite trước, Postgres để ngỏ

Giống hệt quyết định đã đưa ra trong `src/users.py` (mục "Ba quyết định thiết kế" ở đầu
file đó), và vì cùng một lý do:

- SQLite qua `sqlite3` thư viện chuẩn — dự án đã dùng cho `users.sqlite` và checkpoint
  LangGraph, không thêm phụ thuộc.
- `DATABASE_URL` trong `config.py` để ngỏ cho Postgres, **cố ý chưa hiện thực** — viết
  schema Postgres mà không có instance thật để chạy thử là đoán mò (`TECH_DEBT.md` mục 1).
- Toàn bộ truy vấn đi qua module `src/project_kernel.py` như một lớp mỏng (xem mục 9);
  thêm backend Postgres sau này không đổi chữ ký hàm gọi từ nơi khác.
- Đường dẫn file đọc qua biến môi trường có mặc định, theo đúng khuôn `db_path()` của
  `users.py`: `PROJECT_KERNEL_DB_PATH`, mặc định `data/project_kernel.sqlite`.

**Vì sao không dùng chung file `users.sqlite`:** tách file để hai schema độc lập không
khóa lẫn nhau khi ghi đồng thời (SQLite khóa ở mức file/database), và để xóa thử nghiệm
CSDL dự án (khi phát triển) không đụng tới tài khoản người dùng thật.

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

# --- Object ---
def register_object(project_id: str, revision_id: str, type: str, discipline: str,
                     tag: str = "", parent_id: str | None = None,
                     properties: dict | None = None, confidence: float = 1.0) -> dict: ...
def get_object(object_id: str) -> dict | None: ...
def list_objects(project_id: str, revision_id: str | None = None,
                  type: str | None = None, discipline: str | None = None) -> list[dict]: ...
def update_object_status(object_id: str, new_status: str) -> None:
    """Ném ValueError nếu chuyển trạng thái không hợp lệ — xem bảng mục 8."""

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

## 13. Việc CHƯA quyết — cần người duyệt trước khi viết code

Đây là lý do đặc tả này dừng ở mức thiết kế, không tự chuyển sang code:

1. **Schema JSON cụ thể của `properties` theo từng discipline chưa tồn tại.** Ví dụ AHU
   cần `{"cong_suat_lanh_kw": ..., "luu_luong_gio_m3h": ...}`, đoạn ống cần
   `{"duong_kinh_mm": ..., "vat_lieu": ...}` — mỗi discipline một schema riêng, và hiện
   chưa có ai duyệt danh sách trường bắt buộc cho từng `type`. Khóa cứng JSON Schema cho
   từng loại mà chưa có đủ ví dụ thực tế từ `hvac_tools.py`/`elec_tools.py`/... là đoán mò.
   **Đề xuất:** lượt code đầu chỉ ép `properties` là JSON hợp lệ (không rỗng schema), việc
   chuẩn hóa trường bắt buộc theo `type` để lại cho lượt sau khi đã có dữ liệu thật từ bước
   2 ở mục 11.
2. **Quan hệ giữa "revision của dự án" (mục 6.2) và "revision của file CAD"
   (`cad_revision.py`) chưa rõ.** Một revision dự án có thể gồm nhiều lần sửa file CAD lẻ
   tẻ (`snapshot_cad` gọi nhiều lần) trước khi "chốt" thành một revision dự án — cần người
   quyết định ngưỡng "chốt" đó là gì (thủ công bấm nút, hay tự động theo phiên làm việc).
   Không đoán ở đây; mục 11 bước 2 cố ý chọn `auto_quantity_takeoff` (không sửa file) để
   tránh đụng câu hỏi này trước.
3. **Cơ chế cách ly dự án chưa gắn với cách ly người dùng hiện có.** `workspace.py` cô lập
   theo `user_id`; Project Kernel cô lập theo `project_id`. Một dự án có nhiều người dùng
   cộng tác (kỹ sư + kiểm duyệt) chưa có mô hình quyền truy cập — hiện `owner` trong bảng
   `projects` (mục 6.1) chỉ là một chuỗi, chưa có bảng `project_members`. Để lại cho đặc tả
   quyền truy cập riêng, không giải quyết ở đây.
4. **Ngưỡng `confidence` dùng để làm gì** (chặn tự động chuyển `active`? chỉ hiển thị cảnh
   báo?) chưa có quyết định nghiệp vụ — cần người có kinh nghiệm QS/thiết kế xác nhận mức
   nào là "đủ tin để đưa vào BOQ", tương tự cách `OCR_MIN_CONFIDENCE` đã cần đo bằng hồ sơ
   scan thật (`TECH_DEBT.md` mục 13) chứ không suy ra từ code.

## 14. Tiêu chí "xong"

Tiêu chí xong của **đặc tả**:

- [x] Schema đủ chi tiết để viết `CREATE TABLE` không cần đoán thêm.
- [x] Phân biệt rõ `object_id` (bất biến) và `tag` (nghiệp vụ) — điểm dễ làm sai nhất.
- [x] Có kế hoạch test trước khi có code (mục 12).
- [x] Liệt kê tường minh câu hỏi mở thay vì tự quyết định thay người có chuyên môn (mục 13).

Tiêu chí xong của **bước 1 ("schema + module trơn", mục 11)**:

- [x] `src/project_kernel.py` khớp module surface mục 9.
- [x] `tests/test_project_kernel.py` phủ đường vui, cách ly dự án, bất biến ID, vòng đời
      đối tượng, không ghi đè source, không tạo quan hệ trùng.
- [x] `uv run pytest -q` đủ bộ vẫn xanh (781 đạt/0 lỗi, 2026-08-14) — không chỉ test mới.
- [x] Không nối vào `agents.py`/`graph.py`/`tools.py` — canh bằng
      `test_project_kernel_khong_import_tools_hoac_agents`.

**Lưu ý về mục 13:** bước 1 được code **trước khi** 4 câu hỏi ở mục 13 có câu trả lời
chính thức — có chủ đích, vì cả 4 câu hỏi đó (schema `properties` theo discipline, quan hệ
với revision CAD, mô hình quyền truy cập dự án, ngưỡng `confidence`) chỉ ảnh hưởng tới
**bước 2 trở đi** (đường ghi thật nối vào tool, route API), không ảnh hưởng gì tới schema
đứng độc lập của bước 1. **Mục 13 vẫn là điều kiện bắt buộc trước khi bắt đầu bước 2** —
chưa có gì ở đó được coi là đã trả lời.

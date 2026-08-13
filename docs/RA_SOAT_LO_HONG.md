# Rà soát Lỗ hổng & Thiếu sót — đợt viết lại đặc tả

**Ngày:** 2026-08-13. **Phạm vi:** toàn bộ 59 module `src/`, `app.py`, `main.py`, tầng
API/Celery, tài liệu. **Cách làm:** đọc mã nguồn + kiểm chứng bằng cách chạy thật, không
suy đoán từ tên hàm.

Mọi mục dưới đây đều **đã kiểm chứng bằng cách chạy**, không có mục nào suy luận suông.
Mục nào chưa chạy được thì ghi rõ là chưa chạy.

| # | Vấn đề | Mức | Trạng thái |
|---|---|---|---|
| 1 | Xác thực JWT chưa từng có hiệu lực — API mở toang ở chế độ JWT | 🔴 Nghiêm trọng | ✅ Đã sửa |
| 2 | Tài liệu nói "hết patch" trong khi 4 module vẫn gán đè lúc import | 🟠 Cao | ✅ Đã trả — **xóa hết 4 module patch** |
| 3 | Celery nhận `pickle` — chạy code tùy ý qua broker | 🟠 Cao | ✅ Đã sửa |
| 4 | Endpoint AutoCAD nhận đường dẫn tùy ý — công cụ dò file | 🟠 Cao | ✅ Đã sửa (chặn theo đuôi + chế độ nghiêm ngặt) |
| 5 | `qs_auditor` nhận cả 90 tool, gồm tool sửa bản vẽ | 🟠 Cao | ✅ Đã sửa |
| 6 | Không có quyền sở hữu tài nguyên — ai cũng tải được BOQ của người khác | 🟠 Cao | ✅ Đã trả |
| 7 | `tools_lazy` cache vĩnh viễn, không có đường làm mới | 🟡 Vừa | ✅ Đã trả |
| 8 | Redis trong Compose không mật khẩu, cổng mở ra host | 🟡 Vừa | ✅ Đã trả (chưa chạy thử được) |
| 9 | Không giới hạn tần suất, không giới hạn dung lượng upload | 🟡 Vừa | ✅ Đã trả |
| 10 | Bộ test cũ không hề kiểm tra xác thực qua request thật | 🟠 Cao | ✅ Đã sửa (17 test mới) |

---

## 1. 🔴 Xác thực JWT chưa từng có hiệu lực — API mở toang ✅ Đã sửa

**Đây là lỗ hổng nặng nhất tìm được trong đợt rà soát.**

`src/api_phase_c_mount.py` nâng cấp xác thực bằng cách gán đè `api.require_api_key` bằng
một bản có kiểm tra JWT. Việc đó **không có tác dụng gì**. FastAPI đọc
`Depends(require_api_key)` và chốt tham chiếu hàm vào route **ngay lúc định nghĩa route**,
tức là lúc `src/api.py` chạy tới dòng `@app.post(...)` — trước khi
`api_phase_c_mount` chạy (nó được import ở **dòng cuối** `api.py`). Gán lại thuộc tính
module sau đó chỉ đổi cái tên, route vẫn giữ bản hàm cũ chỉ biết API key.

Kiểm chứng, trước khi sửa:

```
$ JWT_SECRET=testsecret python -c "... TestClient(api.app).post('/api/v1/revit/analyze', ...)"
require_api_key (thuộc tính module): <function apply_api_phase_c.<locals>.require_api_key at 0x...5580>
dependency mà route thật sự giữ:     <function require_api_key at 0x...4680>   ← KHÁC
jwt_enabled: True
POST /api/v1/revit/analyze không kèm xác thực → 200 OK
```

**Hệ quả thật.** Ai làm đúng theo `README`/`TECH_DEBT` — bật `JWT_SECRET` để có xác thực
người dùng, không đặt `MEP_AGENTS_API_KEY` vì tưởng JWT đã thay thế — thì **mọi endpoint
mở toang cho khách nặc danh**: upload file, chạy phân tích, tải BOQ của người khác. Đọc
code lại thấy "đã có xác thực JWT". Đây đúng loại lỗi mà `TECH_DEBT.md` mục 10 mô tả:
từng module đứng riêng đều đúng, chỉ sai khi ghép — và lần này cái sai là một lỗ hổng bảo
mật, không phải một con số lệch.

**Đã sửa.** Luật xác thực kép (JWT **hoặc** API key) nay nằm thẳng trong
`src/api.py::require_api_key`, nên route chốt đúng bản có đủ logic.
`src/api_phase_c_mount.py` rút lại còn đúng một việc nó thật sự làm được: gắn router
`/api/v1/auth`. WebSocket cũng nhận JWT qua `?token=` — trước đây chỉ biết `?api_key=`,
nên chạy chế độ JWT thì kênh WebSocket hoặc mở toang hoặc không vào được.

**Chống tái phát:** `tests/test_api_auth.py` (10 test) gửi **request thật** qua
`TestClient`, không gọi hàm trực tiếp. Test gọi hàm sẽ báo xanh cho đúng lỗ hổng này.

---

## 2. 🟠 Tài liệu nói "hết patch" trong khi 4 module vẫn gán đè ✅ Đã trả

`TECH_DEBT.md` mục 10 ghi *"✅ Đã trả — không còn chỗ nào gán đè hàm/tool"*, và
`CLAUDE.md` nhắc lại. **Không đúng.** Tại thời điểm rà soát, năm module vẫn gán đè lúc
import:

| Module | Gán đè cái gì | Rủi ro |
|---|---|---|
| `api_phase_c_mount.py` | `api.require_api_key` | 🔴 **Vô tác dụng → lỗ hổng.** Xem mục 1 |
| `cad_loader_perf_patch.py` | `cad_loader.load_drawing`, `resolve_xref_segments` | 🟠 Chính module đã sinh ra sự cố XREF ở PR #32 |
| `agents_perf_patch.py` | `agents.call_mepf_agent` | 🟡 Ai `from src.agents import call_mepf_agent` lấy bản chưa cắt message |
| `qs_perf_patch.py` | `qs_tools.load_unit_prices` | 🟡 Tương tự, với cache đơn giá |
| `tools_lazy.py` | `tools.get_tools_for_role` | 🟡 Cộng thêm mục 7 |

**Đã trả hết — bằng cách XÓA, không phải thêm tầng.** Bản rà soát trước đề xuất dựng điểm
nối thứ tư (`register_wrapper`). Nhìn kỹ lại thì cả bốn module perf chỉ làm đúng một việc:
bọc một hàm để thêm cache hoặc cắt bớt dữ liệu. Không có thứ tự phụ thuộc, không có nhiều
lớp chồng nhau, không ai cần gỡ ra lúc chạy. Dựng cả một registry cho nhu cầu đó là thêm
phức tạp mà không đổi được rủi ro — trong khi đưa logic về thẳng hàm gốc thì **xóa được
bốn module** và diệt luôn cả lớp lỗi. Đúng nguyên tắc "xóa nhiều hơn thêm" của dự án.

| Module đã xóa | Logic nay nằm ở |
|---|---|
| `agents_perf_patch.py` | `agents.py::_trimmed_messages`, gọi trong `call_mepf_agent` |
| `qs_perf_patch.py` | `qs_tools.py::load_unit_prices` (ba tầng cache: bộ nhớ → Redis → đĩa) |
| `cad_loader_perf_patch.py` | `cad_loader.py::load_drawing` + mặc định `readfile` của `resolve_xref_segments` |
| `tools_lazy.py` | `tools.py::get_tools_for_role` + `clear_role_tools_cache` + `register_role_tool` |

**Lợi ích không chỉ là gọn hơn.** Các tối ưu này trước đây chỉ có tác dụng với ai import
`src.graph` trước — nghĩa là **Celery worker, `python -m src.ingest` và mọi test gọi thẳng
module đều lặng lẽ chạy bản chưa tối ưu**. Không ai từng biết, vì không có dấu hiệu gì.

**Chống tái phát:** `tests/test_no_import_patching.py` chạy trong **tiến trình con** cố ý
không import `src.graph`, khẳng định cắt message / cache DXF / cache tool đều hoạt động,
và danh tính năm hàm lõi không đổi sau khi nạp `src.graph`. Phải tách tiến trình vì trong
cùng một phiên pytest, file test khác đã import `src.graph` rồi — đúng cái làm lớp lỗi này
vô hình suốt thời gian dài.

**Một lỗi cùng gốc tìm thấy trong lúc gỡ:** `load_unit_prices` đọc bảng đơn giá từ Redis
bằng `pickle.loads` — chạy code tùy ý trong tiến trình QS nếu ai đó ghi được vào Redis.
Cùng lớp lỗi với mục 3, và Redis vốn không đặt mật khẩu (mục 8). Nay đọc/ghi bằng Arrow
IPC, thứ chỉ mang dữ liệu bảng chứ không mang code.

---

## 3. 🟠 Celery nhận `pickle` ✅ Đã sửa

`src/celery_app.py` đặt `accept_content=['json', 'pickle']`. Worker sẽ **unpickle** bất kỳ
message nào có trong hàng đợi, mà unpickle dữ liệu không tin cậy là chạy code tùy ý ngay
trong tiến trình Worker — Worker lại là nơi có quyền đọc/ghi toàn bộ thư mục bản vẽ.

Kết hợp với mục 8 (Redis trong Compose không mật khẩu, cổng 6379 mở ra host), chuỗi tấn
công là: đẩy một message pickle vào hàng đợi → chiếm Worker.

**Đã sửa:** `accept_content=['json']`. Không chỗ nào trong dự án gửi task bằng pickle
(`task_serializer='json'` từ đầu), nên không mất tính năng nào. Canh bằng
`tests/test_hardening.py::test_celery_does_not_accept_pickle`.

---

## 4. 🟠 Endpoint AutoCAD nhận đường dẫn tùy ý ✅ Đã sửa

`POST /api/v1/autocad/analyze` nhận `file_path` là **đường dẫn tuyệt đối trên máy chủ** do
client gửi lên, rồi `os.path.exists(payload.file_path)` và đẩy thẳng vào hàng đợi. Không
qua `resolve_safe_path` — trái với bất biến số 3 của dự án.

Thông báo "Không tìm thấy file: …" chính là câu trả lời **có/không** cho mọi đường dẫn
khách hàng đoán: `/etc/shadow`, `/home/*/.ssh/id_rsa`, đường dẫn dự án của khách khác.

**Đã sửa, hai lớp:**

1. **Luôn bật:** đuôi file phải là `.dwg`/`.dxf`. Cắt hẳn việc dò đường dẫn ngoài CAD.
2. **`MEP_AGENTS_STRICT_PATHS=true`:** buộc file nằm trong workspace của server.

Lớp 2 mặc định **tắt**, và đây là đánh đổi có chủ ý: endpoint này vốn thiết kế cho kịch
bản plugin AutoCAD và server chạy **cùng một máy**, bật cứng sẽ phá một tích hợp đang chạy
được của người dùng. Triển khai nhiều người dùng thì **phải** bật — đã ghi vào
`.env.example` và mục 7.3 của đặc tả.

---

## 5. 🟠 `qs_auditor` nhận cả 90 tool ✅ Đã sửa

Vai trò `qs_auditor` không có mặt trong `TOOLS_BY_ROLE`, nên `get_tools_for_role` rơi vào
nhánh mặc định và trả về **toàn bộ 90 tool**:

```
$ python -c "from src.tools import get_tools_for_role; print(len(get_tools_for_role('qs_auditor')))"
90        # trong khi 'qs' chỉ có 27
```

Hai vấn đề:

- **Sai quyền.** Prompt của vai trò này nói rõ *"bạn không được phép tính lại từ đầu, chỉ
  Đánh giá (Audit)"*, nhưng nó cầm `edit_cad`, `write_cad`, `execute_python_code`,
  `auto_quantity_takeoff`. Kiểm toán viên có công cụ tự sửa bài mình đang chấm — chốt chất
  lượng cuối cùng của cả hệ thống không còn độc lập.
- **Đắt.** Nhồi schema của 90 tool vào mỗi request, đúng thứ mà cơ chế thu gọn theo vai
  trò sinh ra để tránh.

**Đã sửa:** thêm entry `qs_auditor` (14 tool, chỉ đọc: `read_cad`,
`analyze_cad_spatial_context`, `lookup_unit_price`, `qs_audit_checklist`, `compare_boq` +
bộ chung) và bảng `ROLE_ALIASES` nối `"QSAuditor"` (tên rút từ tên node) với khóa
snake_case.

Thêm test `test_known_roles_all_have_explicit_toolsets` canh **mọi** vai trò có node trong
graph — để lần sau thêm vai trò mà quên khai báo thì test đỏ, thay vì im lặng nhận 90 tool.

---

## 6. 🟠 Không có quyền sở hữu tài nguyên ✅ Đã trả

Xác thực trả lời "anh là ai", nhưng **không có chỗ nào hỏi "cái này có phải của anh
không"**: ai xác thực được là tải được BOQ của **bất kỳ** `task_id` nào. `task_id` là UUID
nên khó đoán, nhưng "khó đoán" không phải là kiểm soát truy cập — UUID lộ ra trong log,
trong URL chia sẻ, trong ảnh chụp màn hình. Tham số `user_id` của `parse_cad_to_db_task`
thì được nhận rồi **bỏ đi**, API luôn truyền hằng số `"web_client"`/`"cad_client"`.

**Đã trả.** Thêm `src/task_owner.py`: bản ghi "task này của ai", lưu ở Redis (dùng chung
giữa các tiến trình API/Worker) và rơi về bộ nhớ tiến trình khi không có Redis.

- `require_api_key` nay **trả về danh tính** (`sub` của JWT, hoặc khóa chung, hoặc nặc
  danh) thay vì chỉ gật đầu. Endpoint nhận qua `identity: str = Depends(...)` — khai trong
  `dependencies=[...]` thì giá trị trả về bị vứt đi.
- Chủ sở hữu được ghi ngay khi tạo task, ở cả hai đường (`/takeoff` và
  `/autocad/analyze`), và `user_id` thật được truyền xuống Worker thay cho hằng số.
- `/api/v1/task/{id}`, `/api/v1/download/{id}` và **kênh WebSocket** đều kiểm tra. Bỏ sót
  WebSocket là bịt cửa trước để ngỏ cửa sau — nó cũng là một đường đọc dữ liệu task.

**Ba luật, và lý do của luật thứ nhất.** Kiểm tra được bỏ qua khi hệ thống chỉ có MỘT chủ
thể: không bật xác thực, **hoặc** xác thực bằng khóa chung. Khóa chung theo định nghĩa là
một danh tính dùng chung — ai có khóa cũng là cùng một người — nên so sánh chủ sở hữu
không thêm được chút an toàn nào mà chỉ thêm một đường hỏng (mất bản ghi là chặn nhầm
người dùng hợp lệ). Có bản ghi thì phải khớp. Không có bản ghi mà đang chạy danh tính
riêng (JWT) thì **từ chối** — fail-closed có chủ ý: người dùng chỉ cần chạy lại phân tích,
còn cho qua thì không ai biết là đã cho qua.

> **Giới hạn phải nói rõ:** `MEP_AGENTS_API_KEY` là khóa cấp quản trị. Ai cầm nó đọc được
> task của mọi người, kể cả của người dùng JWT. Muốn tách người dùng thật thì dùng JWT và
> **không** phát khóa chung ra ngoài. Đây là giới hạn của cơ chế khóa chung, không phải
> lỗi — nhưng phải nói ra để không ai phát nó cho từng khách hàng rồi tưởng đã tách được
> dữ liệu.

**Còn lại của việc đa người dùng:** vẫn chưa có CSDL người dùng (JWT hiện chỉ có một tài
khoản bootstrap từ biến môi trường), chưa có phân quyền theo vai trò, chưa thu hồi được
token, và Worker vẫn ghi vào `uploads/` chung thay vì workspace riêng từng người. Quyền sở
hữu tài nguyên là mảnh lớn nhất và đã xong; ba mảnh còn lại vẫn thuộc mục 6 của
`TECH_DEBT.md`.

---

## 7. 🟡 Cache tool theo vai trò không có đường làm mới ✅ Đã trả

`tools_lazy` cache kết quả `get_tools_for_role` và **không bao giờ tự làm mới**. Hàm
`clear_role_tools_cache()` có tồn tại nhưng không ai gọi — cache chỉ có đường vào, không
có đường ra.

**Đã trả** cùng lúc với mục 2: cache nay nằm trong `tools.py`, kèm `clear_role_tools_cache()`
và `register_role_tool(role, tool)` — đường đúng để thêm tool lúc chạy, tự xóa cache.
Thêm một sửa nhỏ mà quan trọng: `get_tools_for_role` trả về **bản sao**. Bản cũ trả thẳng
danh sách trong cache, trong khi `agents.build_tools_for_llm` có `append` thêm
`replace_blocks_by_mapping` vào chính danh sách nhận được — tức là mỗi lượt gọi lại nhồi
thêm một tool vào bản cache dùng chung. Canh bằng `test_role_tools_result_is_a_copy`.

---

## 8. 🟡 Redis trong Compose không mật khẩu ✅ Đã trả (chưa chạy thử được)

Redis vừa là broker Celery vừa là result backend: ai ghi được vào đó là điều khiển được
Worker, mà Worker đọc/ghi được toàn bộ thư mục bản vẽ.

**Đã sửa trong `docker-compose.yml`:**

- `redis-server --requirepass ${REDIS_PASSWORD:?...}` — cú pháp `:?` là cố ý: thiếu biến
  thì `docker compose up` **dừng kèm thông báo rõ** thay vì lặng lẽ chạy mở toang. Đây là
  chỗ duy nhất trong dự án không áp dụng graceful fallback: một hàng đợi mở không phải là
  suy giảm nhẹ nhàng, mà là mất quyền kiểm soát Worker.
- Mọi URL Redis đổi sang `redis://:${REDIS_PASSWORD}@redis:6379/0`; `healthcheck` dùng
  `redis-cli -a`; ba chỗ đọc Redis trong code (`qs_tools`, `task_owner`, `task_events`)
  đều đọc thêm `REDIS_PASSWORD`.
- **Postgres**: `ports: "5432:5432"` → `"127.0.0.1:5432:5432"`. Dạng cũ nghe trên **mọi**
  địa chỉ của máy chủ, kèm mật khẩu mặc định ghi thẳng trong file — cơ sở dữ liệu coi như
  công khai nếu máy có IP công cộng.

**Chưa chạy thử được:** đã xác nhận `REDIS_PASSWORD=... docker compose config` parse thành
công và thiếu biến thì báo lỗi đúng như thiết kế, nhưng **chưa từng chạy `docker compose
up --build`** — môi trường viết code không có Docker daemon. Vẫn nguyên như `TECH_DEBT.md`
mục 3 đã ghi: cần người có Docker thật chạy một lần cho tử tế.

---

## 9. 🟡 Không giới hạn tần suất, không giới hạn dung lượng upload ✅ Đã trả

`POST /api/v1/takeoff` đọc **toàn bộ** file vào RAM (`await file.read()`) rồi mới ghi đĩa,
không kiểm tra dung lượng. Một file 5 GB là một lần hết RAM của cả tiến trình API.

**Đã sửa:**

- Ghi theo khối 1 MB, dừng ngay khi vượt `MAX_UPLOAD_MB` (mặc định 200) và trả 413. Phần
  đã ghi được **xóa đi** — file dở dang vừa tốn đĩa vừa có thể bị đọc nhầm thành bản vẽ
  hỏng ở lượt sau.
- `src/rate_limit.py`: cửa sổ trượt, đếm theo **danh tính** chứ không theo địa chỉ IP
  (nhiều người dùng có thể chung một IP sau NAT, và một người có thể đổi IP). Áp cho
  endpoint tạo việc nặng qua dependency `require_quota`; endpoint đọc trạng thái **không**
  bị giới hạn — chặn cả đường đó sẽ làm hỏng chính vòng theo dõi tiến độ của Web App.

> **Mức bảo vệ thật sự có:** bộ đếm nằm trong RAM của từng tiến trình, nên chạy nhiều
> worker uvicorn thì hạn mức thực tế là `giới hạn × số worker`. Đây là chốt chặn chống lạm
> dụng vô ý và script ngây thơ, **không phải** phòng thủ trước tấn công từ chối dịch vụ có
> chủ đích — thứ đó cần bộ đếm dùng chung (Redis) hoặc chặn ở tầng reverse proxy.

Con số mặc định (200 MB, 60 request/phút) là ước lượng rộng rãi, **chưa đối chiếu với số
liệu vận hành thật**. Cả hai đều chỉnh được bằng biến môi trường; nên xem lại sau khi có
bản vẽ và lưu lượng thật của khách.

---

## 10. 🟠 Bộ test cũ không kiểm tra xác thực qua request thật ✅ Đã sửa

Đây là **nguyên nhân gốc** khiến mục 1 sống sót qua nhiều PR. 600 test, `tests/test_api.py`
phủ khá kỹ upload/download/path traversal, nhưng **không có một test nào khẳng định
endpoint trả 401 khi thiếu xác thực**. `tests/test_phase_c.py` có test JWT, nhưng chỉ gọi
`create_access_token` / `decode_access_token` trực tiếp — tầng thư viện, không phải tầng
route. Cả hai đều xanh trong khi API mở toang.

**Bài học:** với xác thực, test gọi hàm là **không đủ**. Lớp lỗi nguy hiểm nhất ở đây là
"hàm đúng nhưng route không dùng nó", và chỉ request thật mới thấy.

**Đã sửa:** `tests/test_api_auth.py` (10 test) + `tests/test_hardening.py` (7 test), tất
cả đi qua `TestClient`, phủ: chế độ mở, chế độ API key, chế độ JWT, hai chế độ song song,
token giả mạo, WebSocket, và router đăng nhập.

---

## 11. 🟡 WebSocket vẫn tự polling ở phía server ✅ Đã trả

Ghi nhận thêm trong đợt này (`TECH_DEBT.md` mục 4 đã nêu, chưa ai làm). Nhìn từ trình
duyệt thì `/ws/task/{id}` là real-time, nhưng nhìn từ server nó vẫn là vòng lặp hỏi Celery
result backend **mỗi giây, cho mỗi kết nối**: 100 người xem cùng lúc là 100 vòng lặp, phần
lớn để nhận lại đúng cái đã biết. Độ trễ cũng bị chặn dưới bởi chu kỳ polling.

**Đã sửa:** thêm `src/task_events.py` — Worker tự phát sự kiện lên channel Redis Pub/Sub
khi trạng thái đổi (bắt đầu xử lý, xong, lỗi), endpoint WebSocket đăng ký nghe channel đó
thay vì tự hỏi vòng quanh.

Ba chi tiết quyết định việc này có dùng được thật hay không:

1. **Luôn gửi trạng thái hiện tại trước.** Client mở kết nối muộn (task đã xong) sẽ không
   nhận được sự kiện nào nữa; chỉ ngồi chờ Pub/Sub là treo vô hạn dù dữ liệu đã sẵn sàng.
2. **Vẫn có thời gian chờ tối đa** (5 giây) rồi tra lại trạng thái. Không phải chu kỳ
   polling — có sự kiện thì nhận ngay — mà là lưới an toàn cho trường hợp Worker chết giữa
   chừng, không kịp phát sự kiện nào.
3. **Không có Redis thì quay về đường polling cũ**, y nguyên hành vi trước. Mất tối ưu,
   không mất tính năng.

Task cũng phát sự kiện lỗi **trước khi** ném lại exception: nếu không, client đang nghe sẽ
treo tới hết thời gian chờ thay vì biết ngay là task đã hỏng.

**Còn lại của mục 4 `TECH_DEBT.md`:** plugin AutoCAD/Revit vẫn là gửi một lần rồi chờ HTTP
response, chưa nhận cập nhật real-time. Cần sửa phía plugin C#, không phải phía Python.

---

## Tổng kết đợt rà soát

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Test | 600 | **654** |
| Module `src/` | 59 | 61 (xóa 4 module patch, thêm 6 module chức năng) |
| Lỗ hổng bảo mật đã bịt | — | 5 (mục 1, 3, 4, 6, 8) + pickle trong `load_unit_prices` |
| Sai phạm vi quyền đã sửa | — | 1 (mục 5) |
| Module patch còn lại | 5 | **0** |
| Vấn đề ghi nhận, chưa làm | — | 0 mục sửa được bằng code |

## Còn lại — và vì sao chưa làm được ở đây

Mọi mục sửa được bằng code đã sửa. Phần còn lại **không phải là code chưa viết**, mà là
việc cần tài nguyên hoặc quyết định mà môi trường viết code không có. Ghi đúng như backlog,
không viết code đoán trước — cùng lý do đã ghi ở đầu `TECH_DEBT.md`.

| Việc | Cần gì để làm | Vì sao không đoán trước được |
|---|---|---|
| Chạy thật `docker compose up --build` | Máy có Docker daemon | Rất có thể lộ lỗi runtime chưa lường: quyền thư mục volume, thiếu biến bắt buộc, healthcheck sai lệnh. Chỉ chạy thật mới biết |
| CSDL người dùng + phân quyền + thu hồi token | Duyệt thiết kế schema | Tự bịa schema chưa ai duyệt rồi migrate là rủi ro cao hơn để trống |
| Postgres/pgvector/S3 thật | Instance thật để migrate và chạy thử | Như trên |
| Workspace riêng từng người trong Worker | Đi cùng CSDL người dùng | Không tách được khỏi việc trên |
| Local LLM air-gapped | GPU 16–24 GB VRAM | Mua/thuê phần cứng, không phải sửa code |
| YOLO nhận diện ký hiệu bản vẽ rác | Dữ liệu gán nhãn thật | Model huấn luyện trên dữ liệu bịa còn tệ hơn không có model |
| Kiểm thử thật với Revit/AutoCAD | Máy cài Revit/AutoCAD | Không giả lập được |
| Real-time cho plugin AutoCAD/Revit | Sửa phía plugin C# | Nằm ngoài phần Python; cần môi trường build plugin |
| Chỉnh số hạn mức upload/tần suất | Số liệu vận hành thật | Con số tự bịa sẽ chặn nhầm bản vẽ hợp lệ của khách — tệ hơn không chặn |

# Rà soát Lỗ hổng & Thiếu sót — đợt viết lại đặc tả

**Ngày:** 2026-08-13. **Phạm vi:** toàn bộ 59 module `src/`, `app.py`, `main.py`, tầng
API/Celery, tài liệu. **Cách làm:** đọc mã nguồn + kiểm chứng bằng cách chạy thật, không
suy đoán từ tên hàm.

Mọi mục dưới đây đều **đã kiểm chứng bằng cách chạy**, không có mục nào suy luận suông.
Mục nào chưa chạy được thì ghi rõ là chưa chạy.

| # | Vấn đề | Mức | Trạng thái |
|---|---|---|---|
| 1 | Xác thực JWT chưa từng có hiệu lực — API mở toang ở chế độ JWT | 🔴 Nghiêm trọng | ✅ Đã sửa |
| 2 | Tài liệu nói "hết patch" trong khi 4 module vẫn gán đè lúc import | 🟠 Cao | ⚠️ Đã đính chính, còn 3 module |
| 3 | Celery nhận `pickle` — chạy code tùy ý qua broker | 🟠 Cao | ✅ Đã sửa |
| 4 | Endpoint AutoCAD nhận đường dẫn tùy ý — công cụ dò file | 🟠 Cao | ✅ Đã sửa (chặn theo đuôi + chế độ nghiêm ngặt) |
| 5 | `qs_auditor` nhận cả 90 tool, gồm tool sửa bản vẽ | 🟠 Cao | ✅ Đã sửa |
| 6 | Không có quyền sở hữu tài nguyên — ai cũng tải được BOQ của người khác | 🟠 Cao | ❌ Chưa làm (cần đa người dùng) |
| 7 | `tools_lazy` cache vĩnh viễn, không có đường làm mới | 🟡 Vừa | ⚠️ Đã ghi nhận |
| 8 | Redis trong Compose không mật khẩu, cổng mở ra host | 🟡 Vừa | ⚠️ Đã ghi nhận |
| 9 | Không giới hạn tần suất, không giới hạn dung lượng upload | 🟡 Vừa | ❌ Chưa làm |
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

## 2. 🟠 Tài liệu nói "hết patch" trong khi 4 module vẫn gán đè ⚠️ Đã đính chính

`TECH_DEBT.md` mục 10 ghi *"✅ Đã trả — không còn chỗ nào gán đè hàm/tool"*, và
`CLAUDE.md` nhắc lại. **Không đúng.** Tại thời điểm rà soát, bốn module vẫn gán đè lúc
import:

| Module | Gán đè cái gì | Rủi ro |
|---|---|---|
| `api_phase_c_mount.py` | `api.require_api_key` | 🔴 **Vô tác dụng → lỗ hổng.** Xem mục 1 — đã gỡ |
| `cad_loader_perf_patch.py` | `cad_loader.load_drawing`, `resolve_xref_segments` | 🟠 Chính module đã sinh ra sự cố XREF ở PR #32. Nay có giữ tham chiếu gốc đúng cách và có ghi chú cấm gán đè `ezdxf.readfile` |
| `agents_perf_patch.py` | `agents.call_mepf_agent` | 🟡 Ai `from src.agents import call_mepf_agent` sẽ lấy bản chưa cắt message |
| `qs_perf_patch.py` | `qs_tools.load_unit_prices` | 🟡 Tương tự, với cache đơn giá |
| `tools_lazy.py` | `tools.get_tools_for_role` | 🟡 Xem mục 7 |

Ba module perf còn lại **chưa gỡ trong đợt này**, và đây là lựa chọn có chủ ý: cả ba đều
là lớp tối ưu bọc quanh một hàm, gỡ đúng cách cần một điểm nối thứ tư (kiểu
`register_wrapper`) hoặc đưa logic vào thẳng hàm gốc — cả hai đều là thay đổi kiến trúc
đáng một PR riêng, không nên trộn vào một PR viết đặc tả. Gỡ vội mà không có test đo được
hiệu năng trước/sau là đúng kiểu thay đổi đã sinh ra sự cố XREF.

**Đã làm:** đính chính `TECH_DEBT.md` mục 10 và `CLAUDE.md` để tài liệu nói đúng hiện
trạng. Một tài liệu báo "đã sạch" trong khi còn 4 chỗ nguy hiểm còn tệ hơn không có tài
liệu — người đọc sau sẽ không đi tìm.

**Đề xuất PR tiếp theo:** thêm điểm nối thứ tư `register_wrapper(tên, hàm_bọc, ưu tiên)`
theo đúng mẫu `supervisor_pipeline`, chuyển ba module perf sang dùng nó, kèm test khẳng
định danh tính hàm không đổi sau khi import.

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

## 6. 🟠 Không có quyền sở hữu tài nguyên ❌ Chưa làm

Xác thực trả lời "anh là ai", nhưng **không có chỗ nào hỏi "cái này có phải của anh
không"**:

- `GET /api/v1/download/{task_id}` — ai xác thực được là tải được BOQ của **bất kỳ**
  `task_id` nào. `task_id` là UUID nên khó đoán, nhưng "khó đoán" không phải là kiểm soát
  truy cập.
- `parse_cad_to_db_task(dwg_path, user_id)` — nhận `user_id` rồi **không dùng vào việc
  gì**. API luôn truyền hằng số `"web_client"` / `"cad_client"`.
- Worker không đặt workspace theo người dùng, nên mọi phiên ghi vào cùng `uploads/` và
  `data/boq/`.

**Vì sao chưa làm:** đây là phần lõi của đa người dùng thật (mục 6 `TECH_DEBT.md`), cần
CSDL người dùng + mô hình phân quyền mà chưa ai duyệt thiết kế. Vá nửa vời (VD nhét
`user_id` vào JWT rồi so sánh chuỗi) tạo cảm giác an toàn sai, nguy hiểm hơn là ghi rõ
chưa có. **Cho tới khi làm xong: không triển khai hệ thống này cho nhiều khách hàng dùng
chung một instance.** Câu này cũng đã ghi vào đặc tả mục 7.3.

---

## 7. 🟡 `tools_lazy` cache vĩnh viễn ⚠️ Đã ghi nhận

`src/tools_lazy.py` cache kết quả `get_tools_for_role` theo vai trò và **không bao giờ tự
làm mới**. Hàm `clear_role_tools_cache()` có tồn tại nhưng không ai gọi. Đăng ký tool mới
lúc chạy thì vai trò nào đã được hỏi trước đó sẽ mãi nhận danh sách cũ — im lặng, không
cảnh báo.

Hiện tại **chưa gây lỗi** vì `TOOLS_BY_ROLE` là bảng tĩnh, dựng xong lúc import. Nó chỉ
thành lỗi khi có ai thêm tool động lúc chạy. Ghi lại ở đây để lần đó không mất buổi chiều
đi tìm. Nên gộp vào PR "điểm nối thứ tư" ở mục 2: registry nào thay đổi thì gọi
`clear_role_tools_cache()`.

---

## 8. 🟡 Redis trong Compose không mật khẩu ⚠️ Đã ghi nhận

`docker-compose.yml` chạy Redis không đặt `requirepass`. Redis vừa là broker Celery vừa là
result backend, tức là ai ghi được vào Redis thì điều khiển được Worker (rõ rệt nhất khi
kết hợp mục 3, nay đã bịt).

**Chưa sửa trong đợt này** vì đúng nguyên tắc của dự án: `docker-compose.yml` **chưa từng
chạy thật** (môi trường viết code không có Docker daemon — `TECH_DEBT.md` mục 3). Sửa cấu
hình hạ tầng mà không chạy thử được là đoán mò; nó thuộc về đúng buổi mà người có Docker
ngồi chạy `docker compose up --build` lần đầu.

**Việc cần làm trong buổi đó:** đặt `requirepass` qua biến môi trường, bỏ `ports:` của
Redis ra khỏi host (chỉ để các service trong mạng nội bộ nói chuyện với nhau), và cập nhật
`CELERY_BROKER_URL` sang dạng `redis://:<mật khẩu>@redis:6379/0`.

---

## 9. 🟡 Không giới hạn tần suất, không giới hạn dung lượng upload ❌ Chưa làm

`POST /api/v1/takeoff` đọc **toàn bộ** file vào RAM (`await file.read()`) rồi mới ghi đĩa,
không kiểm tra dung lượng. Một file 5 GB là một lần hết RAM. Không endpoint nào có giới
hạn tần suất, và mỗi lần gọi đều tốn token LLM thật — tức là tốn tiền thật.

Chưa làm vì cần biết hạn mức thật của môi trường triển khai (dung lượng bản vẽ lớn nhất
khách hay gửi, số request/phút chấp nhận được) — con số tự bịa sẽ chặn nhầm bản vẽ hợp lệ,
mà chặn nhầm bản vẽ của khách còn tệ hơn không chặn. Cần một buổi ngồi với người vận hành.

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

## Tổng kết đợt rà soát

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Test | 600 | **617** |
| Lỗ hổng bảo mật đã bịt | — | 3 (mục 1, 3, 4) |
| Sai phạm vi quyền đã sửa | — | 1 (mục 5) |
| Vấn đề ghi nhận, chưa làm | — | 5 (mục 2 phần còn lại, 6, 7, 8, 9) |

## Lộ trình đề xuất, theo thứ tự

1. **Điểm nối thứ tư `register_wrapper`** → gỡ nốt ba module perf còn gán đè (mục 2), gộp
   luôn việc làm mới cache của `tools_lazy` (mục 7). Thuần refactor, có test canh, không
   cần hạ tầng gì thêm — nên làm trước.
2. **Chạy thật `docker compose up --build`** một lần cho tử tế → đóng mục 8 và phần "chưa
   chạy thử" của `TECH_DEBT.md` mục 3. Cần người có Docker daemon.
3. **Đa người dùng thật** (mục 6) — CSDL người dùng, quyền sở hữu tài nguyên, workspace
   theo người dùng trong Worker. Việc lớn nhất còn lại, và là điều kiện bắt buộc trước khi
   nhiều khách hàng dùng chung một instance.
4. **Giới hạn tần suất và dung lượng** (mục 9) — sau khi có số liệu vận hành thật.

Ba việc 2–4 đều cần tài nguyên hoặc quyết định mà môi trường viết code không có. Ghi ra
đây đúng như backlog, không viết code đoán trước — cùng lý do đã ghi ở đầu `TECH_DEBT.md`.

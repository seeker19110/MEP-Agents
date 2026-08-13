# Đặc tả Hệ thống MEP-Agents

Đặc tả này mô tả **mã nguồn đang chạy**, không phải dự định. Mỗi mục nói rõ hệ thống làm
gì, ràng buộc nào không được vi phạm, và chỗ nào hiện chưa đạt. Chỗ chưa đạt được liệt kê
đầy đủ ở [`RA_SOAT_LO_HONG.md`](RA_SOAT_LO_HONG.md) chứ không giấu trong văn xuôi.

**Viết lại:** 2026-08-13, sau đợt quét toàn bộ 59 module `src/` và 59 file test.
**Mốc kiểm chứng:** `uv run pytest -q` → 617 đạt / 0 lỗi.

---

## 1. Hệ thống này là gì

Một văn phòng tư vấn thiết kế MEPF mô phỏng bằng phần mềm. Khách hàng gõ một yêu cầu bằng
tiếng Việt ("bóc khối lượng bản vẽ điện tầng 3 và lập dự toán"); hệ thống tự chia việc cho
các bộ phận chuyên môn, mỗi bộ phận gọi công cụ tính toán xác định, rồi trả về **file sản
phẩm thật** (Excel BOQ, bản vẽ DXF đã sửa, báo cáo Word) kèm cảnh báo về mọi chỗ dữ liệu
còn thiếu.

Điều phân biệt nó với "một con chatbot biết nói chuyện MEP" nằm ở một nguyên tắc duy
nhất, chi phối toàn bộ kiến trúc:

> **LLM không bao giờ được sinh ra một con số kỹ thuật.**

LLM chỉ làm ba việc: hiểu yêu cầu, chọn tool, diễn giải kết quả. Mọi con số — tải lạnh,
tiết diện cáp, cột áp bơm, khối lượng ống, đơn giá — đến từ hàm Python xác định trong
`src/*_tools.py`. Kéo theo đó là nguyên tắc thứ hai:

> **Thiếu dữ liệu phải kêu lên, không được lặng lẽ bỏ qua.**

Một bảng khối lượng thiếu 3 hạng mục mà khách tưởng là đủ nguy hiểm hơn nhiều so với một
bảng có dòng chữ đỏ "3 hạng mục CHƯA CÓ ĐƠN GIÁ". Nguyên tắc này là lý do có mục 6 dưới
đây, và là thước đo để đánh giá mọi thay đổi trong tương lai.

---

## 2. Bản đồ kiến trúc

```
                         Người dùng
              ┌──────────────┬──────────────┬─────────────────┐
              │              │              │                 │
        Streamlit UI     React/Vite     Plugin Revit    Plugin AutoCAD
          (app.py)        (web/)        (revit/)         (autocad/)
              │              │              │                 │
              │              └──────────────┴─────────────────┘
              │                             │
              │                    FastAPI (src/api.py)
              │                    xác thực: JWT | API key
              │                             │
              │                    Celery (src/celery_app.py)
              │                     ├─ broker/backend: Redis
              │                     └─ task: parse_cad_to_db_task
              │                             │
              └──────────────┬──────────────┘
                             │
                  LangGraph (src/graph.py)
                             │
      ┌──────────────────────┴───────────────────────┐
      │                Supervisor (PM)               │
      │   src/agents.py::supervisor_node             │
      │   + chuỗi middleware (supervisor_pipeline)   │
      └──────────────────────┬───────────────────────┘
                             │ định tuyến
   ┌────────┬────────┬───────┼───────┬────────┬────────┐
mechanical electrical plumbing firefighting qs   cad    bim
   └────────┴────────┴───────┼───────┴────┬───┴────────┘
                             │            └─→ qs_auditor
                     ToolNode (90 tool)
                             │
                        Reviewer  ──→ quay lại Supervisor
```

### Bảng module theo tầng

| Tầng | Module | Trách nhiệm |
|---|---|---|
| **Lõi điều phối** | `agents.py`, `graph.py`, `state.py` | Định nghĩa node, máy trạng thái, luật định tuyến |
| **Điểm nối mở rộng** | `supervisor_pipeline.py`, `standards_backend.py`, `tools.py` | Ba (và chỉ ba) chỗ được phép cắm thêm hành vi |
| **Tool tính toán** | `hvac_tools.py`, `elec_tools.py`, `plumb_tools.py`, `ff_tools.py`, `qs_tools.py`, `bim_tools.py`, `panel_schedule.py` | Công thức kỹ thuật xác định — không có LLM ở đây |
| **CAD** | `cad_loader.py`, `cad_geometry.py`, `cad_standards.py`, `cad_revision.py`, `cad_block_replace.py`, `cad_pipe_ops.py`, `cad_text_ops.py`, `cad_title_ops.py`, `cad_units.py`, `cad_macros.py`, `cad_batch_edit.py`, `cad_cache.py` | Đọc / sửa / tối ưu / chuẩn hóa / lưu revision bản vẽ |
| **Tra cứu tiêu chuẩn** | `vectorstore.py`, `hybrid_search.py`, `local_embeddings.py`, `ingest.py` | RAG tiêu chuẩn TCVN/ASHRAE/NFPA |
| **Hạ tầng** | `api.py`, `celery_app.py`, `auth_jwt.py`, `storage.py`, `checkpointer_factory.py`, `config.py`, `workspace.py`, `usage.py` | Cửa ngõ, hàng đợi, xác thực, lưu trữ, cấu hình |
| **Nền** | `mepf_spec.py` | Chuẩn hóa ký hiệu MEPF. **KHÔNG được import module nào khác** |

`mepf_spec.py` cố ý không có phụ thuộc: cả `tools.py` và `qs_tools.py` đều cần nó, mà hai
module này lại import lẫn nhau. Vòng import đó từng làm `import src.qs_tools` trực tiếp vỡ
với `partially initialized module`. Ràng buộc "không import gì" được canh bằng
`tests/test_no_import_cycles.py`.

---

## 3. Máy trạng thái

### 3.1 `AgentState` (`src/state.py`)

State của LangGraph là một `TypedDict` với **reducer** cho từng trường — reducer quyết
định giá trị mới được cộng dồn hay ghi đè. Đây là chỗ dễ sai nhất trong toàn hệ thống, vì
reducer sai không gây lỗi, chỉ gây hành vi lạ kéo dài.

| Trường | Reducer | Vì sao |
|---|---|---|
| `messages` | `operator.add` | Lịch sử hội thoại, luôn cộng dồn |
| `next` | (không) | Ghi đè — node kế tiếp |
| `context` | `update_dict` | Trộn dict, khóa mới đè khóa cũ |
| `errors` | `replace_errors` | **Phải thay thế, không cộng dồn.** Với `operator.add`, trả về `errors=[]` để xóa lỗi là vô nghĩa (`old + [] == old`), nên chỉ cần một lỗi là state "dính lỗi" vĩnh viễn suốt phiên |
| `sender` | (không) | Node vừa chạy, dùng tên node ("mechanical") chứ không phải tên agent |
| `retry_count` | (không) | Chặn vòng lặp tự sửa; ghi đè để node vừa tăng vừa reset được |
| `completed_agents` | `append_or_reset` | Cộng dồn, trừ khi nhận sentinel `RESET` thì xóa sạch — cần thiết vì danh sách này chỉ có nghĩa trong phạm vi MỘT yêu cầu |
| `awaiting_human`, `hil_reason` | (không) | Chốt chặn Human-in-the-loop |
| `agent_queue` | `replace_queue` | Hàng đợi đa ý định, last-write-wins |
| `parallel_workers` | (không) | Danh sách bộ phận chạy song song do Phase D phát hiện |

**Ràng buộc:** thêm trường mới vào `AgentState` phải nói rõ reducer và lý do. Mặc định
"không reducer" (ghi đè) an toàn hơn `operator.add` — cộng dồn nhầm thì không thể xóa.

### 3.2 Luật định tuyến

Định tuyến do `_core_supervisor_node` quyết định bằng LLM có cấu trúc
(`RouteResponse`), nhưng **bốn luật được chốt cứng bằng code** vì prompt không đáng tin:

1. **Yêu cầu mới của khách** (`HumanMessage` cuối cùng) → xóa `completed_agents`, reset
   `retry_count`. Không có luật này, trần `MAX_AGENT_HANDOFFS` cạn dần và các câu hỏi sau
   bị FINISH ngay.
2. **Reviewer TỪ CHỐI** → quay về đúng `sender` đã gây lỗi, không phải mặc định `qs`.
3. **Vừa xong `cad`** → FINISH. Bản vẽ vừa bị sửa thì luồng phải dừng cho khách mở file
   kiểm tra trước khi bóc khối lượng. Luật này từng chỉ nằm trong prompt, và LLM bỏ qua.
4. **`len(completed_agents) >= MAX_AGENT_HANDOFFS` (4)** → FINISH. Trần chống quay vòng
   đốt token.

Ba hằng số điều khiển vòng lặp:

| Hằng số | Giá trị | Ở đâu |
|---|---:|---|
| `MAX_AGENT_HANDOFFS` | 4 | `agents.py` — số lượt giao việc tối đa cho một yêu cầu |
| `max_review_retries` | 2 | `config.py` — số lần Reviewer được bắt làm lại |
| `recursion_limit` | 25 | `config.py` — trần bước của LangGraph |

### 3.3 Reviewer — hai điều KHÔNG được làm

Reviewer là chốt chất lượng cuối, nên nó có hai quy tắc phản trực giác đã đổi bằng lỗi
thật:

- **Không tự động PHÊ DUYỆT lần thử thứ hai.** Trước đây, hễ state đã có lỗi là Reviewer
  auto-pass để thoát vòng lặp, nghĩa là bản sửa lần hai **không bao giờ được kiểm duyệt**.
  Nay hạn mức đếm tường minh qua `retry_count`; chạm trần thì dừng kèm thông báo trung
  thực "CHƯA ĐẠT", chứ không báo "đã duyệt".
- **Không fail-open khi lỗi kết nối.** LLM Reviewer gọi hỏng thì trả về "LỖI HỆ THỐNG:
  kết quả CHƯA được kiểm duyệt", không phải "PHÊ DUYỆT". Nội dung cố ý không chứa chuỗi
  "TỪ CHỐI" để Supervisor vẫn FINISH thay vì lặp lại.

**Chốt chặn nói suông:** nếu yêu cầu của khách chứa từ khóa đòi sản phẩm ("bóc khối
lượng", "dự toán", "xuất excel", "boq"...) mà cả luồng chưa hề gọi tool nào trong
`DELIVERABLE_TOOLS`, Reviewer TỪ CHỐI. Kiểm tra này dựa trên **cấu trúc** (có `tool_calls`
tên đó hay không), thay cho blacklist chuỗi tiếng Việt cũ — blacklist chỉ cần LLM đổi cách
diễn đạt là lọt.

---

## 4. Ba điểm nối mở rộng — và vì sao chỉ có ba

Các Phase A/B/C/D **từng** nối vào hệ thống bằng cách gán đè hàm/tool của module khác lúc
import. Kiểu nối đó sinh ra lỗi thật, nặng nhất là `cad_cache` tự gọi chính nó gây đệ quy
vô hạn, khiến **mọi XREF bị loại khỏi khối lượng** trong im lặng (PR #32). Từng module
đứng riêng đều đúng; chỉ sai khi ghép.

| Muốn thêm gì | Dùng | Cơ chế |
|---|---|---|
| Tool mới cho một vai trò | `src/tools.py` — `TOOLS_BY_ROLE` + `tools` | Khai báo tĩnh |
| Đường tra cứu tiêu chuẩn mới | `src/standards_backend.py` — `register_backend(tên, hàm, ưu tiên)` | Ưu tiên cao thắng; hỏng thì lùi xuống đường kế tiếp, cuối cùng về fallback offline |
| Luật định tuyến mới | `src/supervisor_pipeline.py` — `register_middleware(tên, hàm, ưu tiên)` | `fn(state, call_next)`; ưu tiên cao nằm ngoài; middleware ném lỗi thì bỏ qua lớp đó, không sập luồng |

Cả hai registry đều **đăng ký theo tên**: đăng ký lại cùng tên thay thế lớp cũ, nên import
hai lần không tạo hai lớp chồng nhau (kiểu gán đè trước đây thì có).

Điểm mấu chốt của thiết kế này: **danh tính đối tượng không bao giờ đổi**.
`agents.supervisor_node` và `tools.search_standards` là cùng một object suốt vòng đời tiến
trình. Ai giữ tham chiếu tới chúng — `ToolNode` đã dựng xong, cache theo vai trò, một list
đã sao chép — đều nhận đúng hành vi đầy đủ. Đó là điều kiểu patch không bảo đảm được.

### Hai quy tắc còn giá trị

- Nếu buộc phải bọc một hàm, **giữ tham chiếu hàm gốc ngay lúc import**, không gọi lại qua
  tên module — tên đó có thể đã bị người khác thay.
- **Luôn chạy đủ bộ test.** Lỗi do ghép module không bao giờ lộ ra khi chạy riêng.

### Phần chưa đạt (nói thẳng)

Bốn module vẫn còn gán đè lúc import, `TECH_DEBT.md` mục 10 từng ghi là "đã trả hết" —
không đúng. Danh sách đầy đủ và mức rủi ro từng cái nằm ở
[`RA_SOAT_LO_HONG.md`](RA_SOAT_LO_HONG.md) mục 2. Một trong số đó (`api_phase_c_mount`)
đã **không có tác dụng gì** suốt thời gian tồn tại, và cái không-có-tác-dụng đó là một lỗ
hổng xác thực — nay đã sửa.

---

## 5. Tool: hợp đồng và phạm vi

### 5.1 Bộ tool theo vai trò

Mỗi vai trò chỉ nhận đúng bộ tool của mình, không nhận cả 90 — vừa để tiết kiệm token, vừa
để **phân quyền**: kiểm toán viên không được cầm công cụ sửa bản vẽ.

| Vai trò | Số tool | Đặc điểm |
|---|---:|---|
| `mechanical` | 23 | HVAC: tải lạnh, ống gió, tâm lý học không khí, chọn chiller/AHU |
| `electrical` | 20 | Cáp, sụt áp, ngắn mạch, chống sét, bảng tủ điện |
| `plumbing` | 19 | Cấp/thoát nước, bể, bơm, nước nóng, bẫy mỡ |
| `firefighting` | 18 | Sprinkler, bơm chữa cháy, chữa cháy khí, thoát khói |
| `qs` | 27 | Bóc khối lượng, dự toán, đơn giá, xuất Excel |
| `qs_auditor` | 14 | **CHỈ ĐỌC** — kiểm toán, đối chiếu; không có tool ghi |
| `cad` | 33 | Đọc/sửa/tối ưu/chuẩn hóa bản vẽ, revision, thị giác máy tính |
| `bim` | 24 | Xung đột, kết nối tuyến, IFC |
| *(không xác định)* | 90 | Toàn bộ — nhánh dự phòng để không bao giờ thiếu tool |

**Ràng buộc:** thêm một vai trò có node trong graph thì **phải** thêm entry trong
`TOOLS_BY_ROLE`. Rơi vào nhánh mặc định là im lặng nhận đủ 90 tool — không lỗi, không cảnh
báo, chỉ đắt và sai quyền. Đúng loại "bỏ sót âm thầm" mà dự án này cấm. Canh bằng
`tests/test_hardening.py::test_known_roles_all_have_explicit_toolsets`.

Tên vai trò rút từ tên node (`"QSAuditor"` → `"qsauditor"`) không phải lúc nào cũng trùng
khóa snake_case; bảng `ROLE_ALIASES` trong `tools.py` nối hai cách viết.

### 5.2 Hợp đồng chung của mọi tool

1. **Trả về chuỗi cho người đọc**, không phải cấu trúc dữ liệu. Người đọc là LLM và cuối
   cùng là kỹ sư — nên chuỗi phải tự giải thích được.
2. **Mọi thao tác file đi qua `resolve_safe_path`** (`src/workspace.py`). Đường dẫn do LLM
   đưa vào không bao giờ được dùng thẳng. Workspace là contextvar, nên hai phiên Streamlit
   song song không đọc/ghi vào file của nhau.
3. **Sửa CAD phải snapshot trước khi ghi đè** (`src/cad_revision.py`, tối đa
   `max_cad_revisions=3` bản).
4. **Lỗi là kết quả, không phải exception.** Tool hỏng phải trả về chuỗi mô tả lỗi kèm
   hướng khắc phục (VD "máy chủ chưa cài ODA File Converter, cài theo…"), để agent chuyển
   nguyên văn cho khách. Ném exception ra ngoài làm vỡ cả lượt.
5. **Cảnh báo phải nổi lên tới khách.** `auto_quantity_takeoff` phát ra ít nhất bốn loại:
   % hao hụt đã cộng, Block bị chèn lệch tỷ lệ, không tìm thấy file XREF, phụ kiện ống là
   ước tính hình học. Prompt của QS/BIM buộc đọc lại từng loại.

---

## 6. Nguyên tắc "không bỏ sót âm thầm" — hiện thực ở đâu

Đây là nguyên tắc nghiệp vụ quan trọng nhất, nên nó phải có địa chỉ cụ thể trong code chứ
không chỉ nằm trong tài liệu:

| Rủi ro bỏ sót | Chốt chặn | Ở đâu |
|---|---|---|
| Trả lời lý thuyết suông, không xuất file | Reviewer TỪ CHỐI theo cấu trúc `tool_calls` | `agents.py::reviewer_agent_node` |
| Hạng mục không có đơn giá → tổng dự toán thiếu | Liệt kê "CHƯA CÓ ĐƠN GIÁ", cấm bịa giá | `qs_tools.py::calc_boq_cost` |
| Bảng đơn giá quá cũ | Cảnh báo độ tươi của `data/unit_prices.csv` | `tests/test_unit_price_freshness.py` |
| XREF không đọc được → thiếu hẳn một phần bản vẽ | Ghi note vào kết quả bóc khối lượng | `cad_loader.py::resolve_xref_segments` |
| Sai đơn vị bản vẽ (INSUNITS ≠ mm) làm sai MỌI kích thước | `audit_cad_drawing_errors`, buộc hỏi lại khách | `cad_units.py`, prompt CAD |
| Xung đột 2D không có cao độ Z | Nói rõ là bản vẽ thuần 2D, mọi điểm cần đối chiếu tay | `bim_tools.py::detect_clashes` |
| Đầu tuyến hở: lỗi vẽ hay điểm đấu nối hợp lệ? | Báo cả hai khả năng, không kết luận thay khách | `bim_tools.py::check_pipe_connectivity` |
| Reviewer hỏng → tưởng đã duyệt | Báo "CHƯA được kiểm duyệt", không fail-open | `agents.py::reviewer_agent_node` |
| Token/chi phí ước lượng bịa (`len/4`) | Đọc `usage_metadata` thật từ nhà cung cấp | `usage.py` |
| Model không có trong bảng giá | Chỉ đếm token, không quy ra tiền | `usage.py::PRICE_PER_MTOK` |

**Ràng buộc cho thay đổi tương lai:** thêm một đường mà dữ liệu có thể thiếu thì phải thêm
một dòng vào bảng này. Cảnh báo bị nuốt là lỗi nghiêm trọng, không phải chuyện nhỏ.

---

## 7. Mô hình bảo mật

### 7.1 Ranh giới tin cậy

| Ranh giới | Ai ở phía không tin | Chốt chặn |
|---|---|---|
| Đường dẫn file do LLM sinh | LLM | `resolve_safe_path` — mọi tool file |
| Tên file upload đa phần | Client HTTP | `_safe_upload_filename` — basename, lọc ký tự, ép đuôi `.dwg/.dxf` |
| Đường dẫn bản vẽ từ plugin AutoCAD | Client HTTP | Đuôi file `.dwg/.dxf`; `MEP_AGENTS_STRICT_PATHS=true` thì buộc trong workspace |
| Message trong hàng đợi Celery | Ai vào được Redis | `accept_content=['json']` — **không** pickle |
| Code do LLM sinh | LLM | `execute_python_code` chạy trong sandbox hạn chế builtins |
| Token/khóa API | Client HTTP | `require_api_key` — JWT hoặc API key |

### 7.2 Xác thực API — ba chế độ

`src/api.py::require_api_key` là dependency của **mọi** endpoint có tác dụng phụ:

| Cấu hình | Hành vi |
|---|---|
| Không đặt gì | Mở — dev cục bộ (graceful fallback, cố ý) |
| `MEP_AGENTS_API_KEY` | Bắt buộc `X-API-Key` header hoặc `?api_key=` query |
| `JWT_SECRET` | Bắt buộc `Authorization: Bearer <JWT>` |
| Đặt cả hai | Chấp nhận **một trong hai** — plugin cũ chỉ biết API key vẫn chạy |

Query `?api_key=` tồn tại vì trình duyệt điều hướng trực tiếp (tải file) và WebSocket
không đặt được header tùy ý. WebSocket nhận `?api_key=` hoặc `?token=` (JWT).

> **Luật bắt buộc:** logic xác thực phải nằm **ngay trong `src/api.py`**. FastAPI chốt
> `Depends(require_api_key)` vào route ngay lúc định nghĩa route; gán đè
> `api.require_api_key` từ module khác sau đó **không đổi được route nào**. Đó chính là
> lỗ hổng đã tồn tại cho tới đợt rà soát này: bật JWT mà không đặt API key thì mọi endpoint
> mở toang cho khách nặc danh, trong khi đọc code lại tưởng đã có xác thực JWT. Xem
> [`RA_SOAT_LO_HONG.md`](RA_SOAT_LO_HONG.md) mục 1. Bộ test `tests/test_api_auth.py` gửi
> **request thật** qua `TestClient` chứ không gọi hàm — vì lỗ hổng thuộc loại "hàm đúng
> nhưng route không dùng nó".

### 7.3 Giới hạn còn lại — nói rõ để không ai hiểu nhầm

- **Chưa có đa người dùng thật.** JWT hiện chỉ có một tài khoản bootstrap từ biến môi
  trường (`verify_bootstrap_user`), không có CSDL người dùng, không phân quyền, không thu
  hồi token.
- **Chưa có quyền sở hữu tài nguyên.** Ai xác thực được là tải được BOQ của **bất kỳ**
  `task_id` nào. Tham số `user_id` của `parse_cad_to_db_task` được nhận rồi bỏ đi.
- **Chưa giới hạn tần suất** trên endpoint nào.

Ba điều này là cùng một việc chưa làm: đa người dùng (mục 6 của `TECH_DEBT.md`).

---

## 8. Bề mặt cấu hình

Toàn bộ cấu hình qua `src/config.py` (pydantic-settings, đọc `.env`) hoặc biến môi
trường. Nguyên tắc xuyên suốt: **thiếu cấu hình thì rơi về đường cục bộ kèm log cảnh báo,
không sập**.

| Nhóm | Biến chính | Thiếu thì sao |
|---|---|---|
| LLM | `LLM_PROVIDER`, `MODEL_NAME`, `<VAI_TRÒ>_LLM_PROVIDER`, `*_API_KEY` | Client dựng với `dummy_key`, lỗi hiện ra ở lượt gọi, không phải lúc import |
| LLM cục bộ | `OLLAMA_BASE_URL`, `VLLM_BASE_URL` | `localhost` mặc định; tự chuẩn hóa đuôi `/v1` |
| Xác thực | `MEP_AGENTS_API_KEY`, `JWT_SECRET`, `JWT_BOOTSTRAP_*` | Mở (dev cục bộ) |
| CORS | `CORS_ALLOWED_ORIGINS` | Chỉ `localhost:5173` — không mở `*` |
| Hàng đợi | `CELERY_BROKER_URL`, `REDIS_URL`, `REDIS_HOST` | `redis://localhost:6379/0` |
| CSDL | `DATABASE_URL`, `USE_PGVECTOR` | SQLite checkpointer → RAM |
| Lưu trữ | `S3_*` | Đĩa cục bộ (`LocalStorage`) |
| RAG | `FAISS_INDEX_PATH`, `EMBEDDING_BACKEND`, `HYBRID_SEARCH` | Tra cứu offline bằng từ khóa trên `data/standards/*.txt` |
| Chi phí token | `AGENT_MESSAGE_WINDOW` (24), `MAX_TOOL_RESULT_CHARS` (6000) | Mặc định như trong ngoặc |
| Vòng lặp | `MAX_REVIEW_RETRIES` (2), `RECURSION_LIMIT` (25), `MAX_CAD_REVISIONS` (3) | Mặc định như trong ngoặc |
| Bảo mật đường dẫn | `MEP_AGENTS_STRICT_PATHS` | Tắt — giữ kịch bản plugin cùng máy |
| Beta Anthropic | `ANTHROPIC_TOOL_SEARCH` | Tắt |

**Ràng buộc:** một cấu hình đọc từ hai nơi bằng hai tên khác nhau là lỗi. `OLLAMA_BASE_URL`
từng bị đúng lỗi này — embedding đọc biến môi trường còn LLM hardcode `localhost`, nên
chạy Ollama ở máy khác thì một nửa hệ thống trỏ đúng, nửa kia gọi vào chính container của
mình.

---

## 9. Tối ưu chi phí và tốc độ

| Cơ chế | Ở đâu | Tiết kiệm gì |
|---|---|---|
| Thu gọn tool theo vai trò | `tools.py::TOOLS_BY_ROLE` | 90 → 14-33 schema mỗi request |
| Cắt cửa sổ message | `perf_tuning.py::trim_messages_for_llm` | Giữ 24 message gần nhất |
| Cắt bớt kết quả tool dài | `perf_tuning.py` | Cắt giữa, giữ đầu-đuôi, trần 6000 ký tự |
| Cache client LLM | `agents.py::_build_llm` (`lru_cache`) | Không dựng lại client mỗi lượt |
| Prompt caching Anthropic | `agents.py::build_system_message` | Prefix cố định được đánh dấu `cache_control`; cảnh báo lỗi (đổi mỗi lượt) tách thành block SAU — nhét chung thì prefix đổi và cache không bao giờ trúng |
| Cache DXF | `cad_cache.py` | Không đọc lại cùng một file |
| Cache bảng đơn giá | `unit_price_cache.py` | Không đọc lại CSV |
| Chạy song song M/E/P/F | `supervisor_parallel.py` + LangGraph `Send` | Bốn bộ phận độc lập chạy cùng lúc |

Prompt caching chỉ bật khi prompt ≥ 4000 ký tự (`ANTHROPIC_CACHE_MIN_CHARS`): dưới ngưỡng
Anthropic bỏ qua cache **trong im lặng**, bật lên chỉ tạo cảm giác đã tiết kiệm.

---

## 10. Bản đồ kiểm thử

617 test trong 59 file. Nhóm theo thứ nó bảo vệ:

| Nhóm | File tiêu biểu | Bảo vệ điều gì |
|---|---|---|
| Bất biến bóc khối lượng | `test_takeoff_invariants.py`, `test_takeoff_*.py` (7 file) | Con số bóc ra không đổi ngoài ý muốn |
| Công thức kỹ thuật | `test_hvac_tools.py`, `test_elec_tools.py`, `test_plumb_tools.py`, `test_ff_tools.py`, `test_voltage_drop.py`, `test_fire_pump_head.py` | Công thức đúng chuẩn |
| An toàn đường dẫn | `test_workspace.py`, `test_file_tools_path_safety.py` | Không thoát khỏi workspace |
| Sandbox | `test_execute_python_code_sandbox.py` | Code LLM sinh không thoát ra được |
| Xác thực API | `test_api_auth.py`, `test_api.py` | 401 khi phải 401 — **qua request thật** |
| Chốt chặn bảo mật | `test_hardening.py` | Pickle, dò đường dẫn, phạm vi tool theo vai trò |
| Kiến trúc | `test_no_import_cycles.py`, `test_registry_consolidation.py`, `test_supervisor_pipeline.py`, `test_standards_backend.py` | Điểm nối không bị lách |
| Vòng lặp điều phối | `test_review_retry_loop.py`, `test_routing.py`, `test_graph.py` | Không lặp vô tận, không auto-pass |
| E2E | `test_e2e_takeoff.py` + `web/tests-ui/` (Playwright) | Luồng thật đầu-cuối |

**Ràng buộc:** chạy `uv run pytest -q` đủ bộ sau **mỗi** thay đổi. Chạy riêng file test của
phần đang sửa không bao giờ lộ ra lỗi ghép module — đó chính là cách lỗi XREF lọt vào.

---

## 11. Bất biến — danh sách kiểm tra khi review

Một thay đổi vi phạm bất kỳ dòng nào dưới đây thì phải bị chặn, kể cả khi test xanh:

1. LLM không sinh số kỹ thuật. Công thức nằm trong Python xác định.
2. Dữ liệu thiếu phải nêu ra trong kết quả trả về khách.
3. Mọi thao tác file qua `resolve_safe_path`.
4. Sửa CAD phải snapshot trước khi ghi đè.
5. Thiếu cấu hình → fallback cục bộ + log cảnh báo, không sập.
6. Không gán đè hàm/tool của module khác. Mở rộng qua đúng ba điểm nối.
7. Logic xác thực nằm trong `src/api.py`, không gắn từ ngoài vào.
8. Vai trò có node trong graph phải có entry trong `TOOLS_BY_ROLE`.
9. Reviewer không fail-open, không auto-pass.
10. `mepf_spec.py` không import module nào của dự án.
11. Chạy đủ bộ test, không chỉ test của phần đang sửa.
12. Không tự nhận là xong khi chưa chạy thử được — ghi rõ là chưa chạy.

Điều 12 là văn hóa của [`TECH_DEBT.md`](../TECH_DEBT.md) và là lý do đặc tả này có mục
"phần chưa đạt" ngay giữa mục 4 thay vì giấu xuống cuối.

---

## 12. Đọc tiếp

- [`RA_SOAT_LO_HONG.md`](RA_SOAT_LO_HONG.md) — lỗ hổng và thiếu sót tìm được, lộ trình nâng cấp
- [`TIEN_DO_DU_AN.md`](TIEN_DO_DU_AN.md) — trạng thái thực tế, cái gì đã chạy thật
- [`../TECH_DEBT.md`](../TECH_DEBT.md) — nợ kỹ thuật và **vì sao chưa trả**
- [`E2E.md`](E2E.md) — kịch bản end-to-end
- [`../AI_MODEL_SETUP.md`](../AI_MODEL_SETUP.md) — chọn model cho từng vai trò

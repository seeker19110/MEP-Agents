# MEP-Agents — PROJECT PROGRESS & ENGINEERING OS MASTER PLAN

> **Document status:** Master progress ledger + product north star + implementation specification
>
> **Updated:** 2026-08-14 (mục 3.2–3.8 gộp từ `docs/TIEN_DO_DU_AN.md`, nay đã xóa — file
> này là nguồn duy nhất cho cả tầm nhìn chiến lược lẫn nhật ký tiến độ thực tế)
>
> **Repository:** `seeker19110/MEP-Agents`
>
> **Current product position:** Advanced Multi-Agent MEPF Engineering Prototype → **Engineering Intelligence Platform Foundation**
>
> **Next strategic milestone:** **Engineering OS**

---

# 0. Quyết định chiến lược đã chốt

MEP-Agents **không còn được định nghĩa là một chatbot MEP hoặc một tập hợp agent gọi LLM**.

Định nghĩa chính thức từ thời điểm này:

> **MEP-Agents là nền tảng Engineering Intelligence có Digital Twin, Engineering Knowledge Graph, deterministic engineering engines, CAD/BIM intelligence, evidence/audit và AI orchestration; mục tiêu dài hạn là Engineering Operating System cho AEC.**

MEP là vertical đầu tiên và là proving ground. Kiến trúc phải cho phép mở rộng sang Architecture, Structural, Fire, ELV, QS, Construction và Facility Management mà không phải viết lại core.

---

# 1. Product Vision

## 1.1 Từ AI Agent → Engineering OS

Lộ trình sản phẩm được chốt thành 5 tầng:

```text
LEVEL 1 — AI Engineering Assistant
    ↓
LEVEL 2 — AI Engineering Agents                 [ĐÃ ĐẠT]
    ↓
LEVEL 3 — Engineering Digital Twin
    ↓
LEVEL 4 — Generative + Optimization Engineering
    ↓
LEVEL 5 — AEC Engineering Operating System      [NORTH STAR]
```

## 1.2 Ý tưởng cuối cùng

Kỹ sư không còn phải làm thủ công từng thao tác:

```text
mở bản vẽ → đọc → đo → tính → vẽ → check → bóc → Excel → sửa → check lại
```

Thay vào đó:

```text
Engineering Intent
        ↓
Requirements + Constraints
        ↓
Engineering OS
        ↓
Understand project
        ↓
Calculate
        ↓
Generate alternatives
        ↓
Coordinate
        ↓
Validate
        ↓
Optimize
        ↓
Human approval
        ↓
CAD / BIM / BOQ / Estimate / Reports
```

---

# 2. Current Repository Assessment

Đánh giá trạng thái dựa trên code và tài liệu hiện có trong repository, không đánh đồng “có code” với “production-ready”.

## 2.1 Những năng lực hiện đã tồn tại

### Multi-Agent orchestration — DONE

Repository hiện có kiến trúc LangGraph với:

- Supervisor;
- Mechanical;
- Electrical;
- Plumbing;
- Firefighting;
- QS;
- CAD;
- BIM;
- QS Auditor;
- Reviewer;
- ToolNode;
- conditional routing;
- recursion limit;
- checkpoint support.

### Deterministic engineering tools — DONE

Đã có các nhóm tính toán bằng code Python thay vì để LLM tự đoán số:

- HVAC cooling load;
- duct pressure loss;
- NC/noise;
- cable sizing;
- voltage drop;
- electrical load;
- short circuit;
- cable tray;
- lightning protection;
- panel schedule;
- water pipe;
- plumbing pump;
- sprinkler hydraulics;
- fire pump;
- standpipe;
- smoke control;
- fire detector quantity;
- quantity takeoff;
- BOQ cost;
- Vietnamese BOQ export;
- unit price lookup.

### CAD capability — DONE at prototype level

Đã có:

- edit CAD;
- optimization;
- standardization;
- color legend;
- block replacement;
- snapshot;
- revision diff;
- restore;
- Overkill/Purge pipeline;
- layer/block normalization;
- geometric clash checks;
- dimension-aware clash checks where source dimensions are available.

### BIM / coordination — DONE at prototype level

Đã có clash detection và BIM-related tooling.

### Persistence — PARTIAL / FOUNDATION

Đã có:

- LangGraph checkpoint;
- SQLite option;
- PostgreSQL checkpointer integration/fallback path;
- persistent conversation state.

Chưa có Digital Twin canonical database.

### Model routing — DONE at prototype level

Đã có:

- role-specific provider/model configuration;
- OpenAI;
- Anthropic;
- Gemini;
- Groq;
- Ollama;
- vLLM;
- local LLM endpoint support;
- prompt trimming;
- Anthropic prompt caching support;
- optional Anthropic tool search;
- usage/cost tracking.

### Workspace safety — PARTIAL / FOUNDATION

Đã có session workspace isolation và path traversal protection.

### Reviewer / Guardrail — DONE at prototype level

Reviewer có vai trò kiểm duyệt và giới hạn retry.

### Standards retrieval — PARTIAL

Đã có standards ingestion / search / offline fallback theo kiến trúc RAG hiện tại.

Nhưng **chưa được coi là Standards Engine production-grade** vì chưa chuyển hoàn toàn từ text retrieval sang versioned structured rules + deterministic compliance.

---

# 3. Giai đoạn hiện tại

## 3.1 Trạng thái chính thức

### ✅ PHASE A — Multi-Agent Engineering Prototype — HOÀN THÀNH

Mục tiêu phase này:

- xây multi-agent architecture;
- có Supervisor;
- có domain agents;
- có Reviewer;
- có tool calling;
- có deterministic engineering tools;
- có CAD/BIM/QS capability;
- có persistence cơ bản;
- có model/provider flexibility;
- có guardrails cơ bản.

**Đã đạt.**

---

### ⚠️ PHASE B — Engineering Intelligence Foundation — ĐANG CHUYỂN TIẾP

Các mảnh đã có nhưng chưa được hợp nhất thành canonical platform:

- CAD intelligence;
- BIM intelligence;
- engineering calculations;
- standards retrieval;
- revision;
- usage;
- workspace;
- agent orchestration.

Điểm thiếu lớn nhất là **Project State / Digital Twin / Engineering Graph**.

Vì vậy Phase B chưa đánh dấu hoàn thành toàn bộ.

---

## 3.2 Số liệu hiện trạng

**Cập nhật lần cuối của nhật ký này:** 2026-08-13 — sau đợt quét sâu viết lại đặc tả. Đặc
tả đầy đủ nay nằm ở [`docs/DAC_TA_HE_THONG.md`](docs/DAC_TA_HE_THONG.md); lỗ hổng tìm được ở
[`docs/RA_SOAT_LO_HONG.md`](docs/RA_SOAT_LO_HONG.md) (nặng nhất: xác thực JWT chưa từng có hiệu
lực — API mở toang ở chế độ JWT, nay đã bịt). Sau đó đã trả **toàn bộ** nợ kỹ thuật sửa
được bằng code: xóa hết module patch, thêm quyền sở hữu tài nguyên, hạn mức upload/tần
suất, mật khẩu Redis, và đẩy tiến độ thật qua Redis Pub/Sub. Phần còn lại đều cần tài
nguyên thật (Docker daemon, GPU, hạ tầng Postgres/S3, Revit/AutoCAD) — xem bảng cuối
[`docs/RA_SOAT_LO_HONG.md`](docs/RA_SOAT_LO_HONG.md).

**Đợt tiếp theo** bổ sung CSDL người dùng (3 vai trò, thu hồi token), workspace riêng từng
người trong Worker, và rà soát sâu tầng CAD/QS — đợt rà soát này tìm ra **hai lỗi bóc khối
lượng sai**, loại nguy hiểm nhất về nghiệp vụ: cảnh báo "tuyến vẽ 2 nét bị tính đôi" im
lặng không nổ trên bản vẽ vẽ tay, và ngã ba ống bị đếm thành co thay vì tê.

| Chỉ số | Giá trị | Ghi chú |
|---|---:|---|
| Mã nguồn Python (`src/`) | ~13.900 dòng | 62 module |
| Test Python | **756 đạt / 0 lỗi** | 67 file trong `tests/` (đã xác minh lại 2026-08-14) |
| Test giao diện | **7 đạt / 0 lỗi** | Playwright, Chromium thật (`web/tests-ui/`) |
| Số PR đã hợp nhất | 32+ | tính tới `c44e3b3`, nhiều PR sau đó tiếp tục hợp nhất |
| Phase đã hợp nhất | A, B, C, D | xem mục 3.3 |

Cách kiểm chứng lại số liệu:

```bash
uv run pytest -q
uv run python -m py_compile app.py main.py src/*.py
```

## 3.3 Các Phase đã hợp nhất

| Phase | Nội dung | Tài liệu | Trạng thái |
|---|---|---|---|
| **A** | 5 skill CAD/QS gộp pipeline (`batch_edit_pipes`, `batch_replace_text`, `update_title_block`, `prepare_drawing`, `full_boq`) | [`README_PHASE_A.md`](README_PHASE_A.md) | ✅ Có test, chạy được offline |
| **B** | Checklist QS chấm điểm 0–100, `compare_boq`, chốt chặn Human-in-the-loop, hàng đợi đa ý định | [`README_PHASE_B.md`](README_PHASE_B.md) | ✅ Có test |
| **C** | Postgres/pgvector, S3, JWT, scaffold YOLO MEPF | [`README_PHASE_C.md`](README_PHASE_C.md) | ⚠️ Code + test đủ, **chưa chạy với hạ tầng thật** |
| **D** | Tìm kiếm lai (vector + từ khóa RRF), embedding cục bộ, LangGraph `Send` chạy song song M/E/P/F, cache tool theo vai trò | [`README_PHASE_D.md`](README_PHASE_D.md) | ✅ Có test |

Bốn Phase **từng** nối vào hệ thống bằng patch lúc import (gán đè hàm/tool của module
khác). Kiểu nối đó đã sinh ra lỗi thật (xem mục 3.5) và nay đã được thay hết bằng ba điểm
nối tường minh: registry tool (`src/tools.py`), backend tra cứu
(`src/standards_backend.py`), middleware điều phối (`src/supervisor_pipeline.py`).

## 3.4 Đợt rà soát 2026-08-13 (PR #32)

Chạy đủ bộ test trên `main` ra **13 test đỏ**. Không phải test hỏng vặt: 3 lỗi thật lọt
vào khi patch Phase C/D ghi đè code cũ, cộng 1 nhóm test lạc hậu.

| Lỗi | Mức độ | Hệ quả nếu không sửa |
|---|---|---|
| Đệ quy vô hạn khi đọc XREF (`src/cad_cache.py`) | 🔴 Nặng | **Mọi XREF thất bại im lặng** — nội dung xref bị loại khỏi khối lượng, chỉ để lại một dòng note khó hiểu. Đúng kịch bản "bóc thiếu mà không cảnh báo" mà `cad_loader.py` ghi rõ là phải tránh |
| `detect_cad_symbols_yolo` mất `resolve_safe_path` (`src/vision_tools.py`) | 🟠 Cao | Tool đọc được file ngoài workspace của phiên; `predict` ném lỗi thì tool vỡ thay vì báo |
| `ingest` ném `FileNotFoundError` lần chạy đầu (`src/ingest.py`) | 🟡 Vừa | Người dùng mới chạy `python -m src.ingest` là gặp traceback |
| `JWT_BOOTSTRAP_USER` qua env bị nuốt (`src/auth_jwt.py`) | 🟡 Vừa | Đổi user bootstrap bằng biến môi trường im lặng vô tác dụng |
| `uv.lock` lệch `pyproject.toml` từ Phase C | 🟡 Vừa | `uv sync --extra phase-c` không tái lập được đúng môi trường |

**Thay đổi hành vi cần biết:** sau khi sửa lỗi XREF, khối lượng bóc từ bản vẽ **có xref sẽ
tăng** so với trước. Đó là con số đúng — trước đây phần xref bị bỏ qua hoàn toàn.

## 3.5 Bài học rút ra: rủi ro của kiểu "patch lúc import"

Lỗi XREF nói trên là hệ quả trực tiếp của kiến trúc patch: `cad_loader_perf_patch` gán tạm
`ezdxf.readfile = readfile_cached`, còn `readfile_cached` lại gọi ngược `ezdxf.readfile` ở
nhánh cache-miss → tự gọi chính mình. Từng module đứng riêng đều đúng; chỉ sai khi ghép.

Hệ quả cho cách làm việc về sau:

1. **Luôn chạy đủ bộ test, không chỉ test của Phase mình làm.** Cả 13 lỗi đều lộ ra ở lần
   chạy `pytest` toàn bộ; chạy riêng `tests/test_phase_d.py` thì xanh hết.
2. Module bị patch nên giữ tham chiếu hàm gốc **ngay lúc import**, không gọi lại qua tên
   module (tên đó có thể đã bị người khác thay).
3. Khi một Phase đổi hành vi có chủ đích, sửa luôn test cũ trong cùng PR — đừng để test
   đỏ tồn tại như "nhiễu nền", vì lỗi thật sẽ lẫn vào đó (đúng như đã xảy ra ở đây).

## 3.6 Lịch sử các đợt xử lý tiếp theo

### Đợt 2 (cùng ngày PR #32)

Làm theo đúng 3 việc đề ở mục 3.8 mà môi trường hiện tại cho phép:

- **Rà hết tầng patch còn lại** — không có ca đệ quy thứ hai. Nhưng lộ ra một lỗi khác
  cùng gốc: `cad_loader_perf_patch` gán đè biến toàn cục `ezdxf.readfile` quanh mỗi lần
  gộp xref. Phase D chạy song song bằng thread nên hai lời gọi chồng nhau khôi phục nhầm
  của nhau → `ezdxf.readfile` kẹt vĩnh viễn ở bản cache, mọi chỗ đọc DXF sau đó dùng chung
  một doc có thể bị sửa đổi. Đã sửa bằng cách truyền hàm đọc qua tham số.
- **Gộp 8 skill Phase A/B vào registry chính** `src/tools.py`. Tầng patch giữ lại làm mạng
  lưới an toàn. Bộ tool từng vai trò không đổi (đã đối chiếu số lượng trước/sau).
- **Chạy thử Docker / E2E**: vẫn chưa làm được — môi trường này không có Docker daemon.

### Đợt 3

- **Thêm điểm mở rộng `src/standards_backend.py`** — Phase C/D thôi tráo đối tượng tool
  `search_standards`, chuyển sang đăng ký backend theo mức ưu tiên. Tool giữ nguyên danh
  tính suốt vòng đời tiến trình.
- **Nguồn embedding vào thẳng `vectorstore.get_embeddings`** — sửa kèm một lỗi thật:
  `python -m src.ingest` không import `graph` nên patch Phase D không chạy, cộng với việc
  `ingest` chặn cứng ở `OPENAI_API_KEY` → **chạy offline không nạp được index**, hybrid
  mất hẳn nhánh vector mà không có dấu hiệu gì.
- **Xóa hàm chết** `get_tools_for_role_cached()`.
- **Sửa hardcode địa chỉ LLM cục bộ** — `src/agents.py` hardcode `localhost:11434`
  (Ollama) và `localhost:8000` (vLLM), trong khi phía embedding lại đọc `OLLAMA_BASE_URL`.
  Hai nửa của cùng một cấu hình đi hai đường: embedding trỏ đúng máy, LLM gọi vào chính
  container của nó. Chỉ lộ ra khi thật sự dựng cấu hình lai. Nay đọc env, dùng chung biến
  với embedding, tự chuẩn hóa đuôi `/v1`.
- **Ghi nợ, chưa làm:** phần patch bọc node của graph (HIL, hàng đợi, fan-out song song)
  không dùng được kiểu registry này — cần tái cấu trúc `agents.py`/`graph.py` thành các
  bước có điểm nối sẵn. Việc lớn, để riêng một PR. Xem `TECH_DEBT.md` mục 10.

### Đợt 4 — Kịch bản E2E

Thêm hai tầng kiểm thử E2E, xem [`docs/E2E.md`](docs/E2E.md):

- **Tầng 1** `tests/test_e2e_takeoff.py` — chạy trong CI, đi trọn đường bản vẽ `.dxf` thật
  → bóc khối lượng thật → Excel thật → tải về qua FastAPI, chỉ thay broker bằng gọi đồng
  bộ. Đã kiểm chứng sức bắt lỗi: làm hỏng luồng gộp XREF thì 3/4 test chuyển đỏ.
- **Tầng 2** `scripts/e2e_smoke.py` — không giả lập gì. **Đã chạy đạt** với Redis thật,
  worker Celery ở tiến trình riêng, FastAPI thật: tải lên → worker nhặt task qua Redis →
  Excel 5.582 byte → tải về, tổng chiều dài khớp hình học đã dựng. Đường xác thực
  `MEP_AGENTS_API_KEY` cũng đã kiểm (thiếu khóa → 401, có khóa → đạt).

Đây là lần đầu dự án có bằng chứng luồng phân tán chạy thật đầu-cuối. **Vẫn chưa** chạy
qua `docker compose up --build` — môi trường viết code không có Docker daemon, và lớp
container còn có thể sinh lỗi riêng (quyền volume, biến môi trường, healthcheck).

### Đợt 5 — Gỡ nốt phần patch bọc node

Đây là phần cuối của mục 10 `TECH_DEBT.md`, trước đó cố ý để lại vì nó nằm giữa luồng
điều phối.

- **`src/supervisor_pipeline.py`** — điểm nối kiểu middleware. Phase B (chốt chặn HIL +
  hàng đợi) và Phase D (fan-out song song) đăng ký lớp theo mức ưu tiên thay vì gán đè
  `agents.supervisor_node`. Hàm điều phối nay giữ nguyên danh tính suốt vòng đời tiến
  trình, nên `src/graph.py` không còn phải đọc lại nó sau các dòng import patch.
- **`DELIVERABLE_TOOLS`** khai báo thẳng trong `src/agents.py`.
- **Kiểm chứng tương đương:** chạy cùng 10 tình huống định tuyến đại diện trên bản trước
  và sau, kết quả **giống hệt từng trường**. E2E hạ tầng thật chạy lại cũng đạt.

Sau đợt này **không còn chỗ nào gán đè hàm hay tráo đối tượng của module khác.** Hai
patch còn lại (`agents_perf_patch`, `qs_perf_patch`) là bọc thuần túy quanh một hàm, không
dính lớp lỗi đã gặp — để lại có chủ đích.

### Đợt 6 — Triển khai theo khuyến nghị

- **Test giao diện `web/`** — 7 kịch bản Playwright trên Chromium thật, gồm **trọn đường
  qua trình duyệt**: thả bản vẽ → bấm phân tích → WebSocket đẩy trạng thái → tải Excel về.
  Đây là mảng trước đó không có lớp kiểm thử nào. Test bắt ngay một lỗi giao diện thật:
  vùng kéo-thả mời "hoặc click để chọn file" nhưng **không có `<input type="file">`** — cú
  bấm rơi vào hư không. Đã sửa, và lời mời nay là nút thật (bàn phím dùng được).
- **Cảnh báo bảng đơn giá cũ** — rủi ro nghiệp vụ lớn nhất còn lại: con số tiền đi vào hồ
  sơ thầu dựa trên `data/unit_prices.csv` mà không ai biết bảng giá cũ chưa. Nay có
  `data/unit_prices.meta.json` khai báo ngày hiệu lực, quá ngưỡng thì chính báo cáo dự
  toán mang theo cảnh báo. Xem `TECH_DEBT.md` mục 11.
- **Chưa làm được:** chạy Docker Compose (không có Docker daemon) và dựng Ollama thật
  (chưa cài). Hai việc này vẫn cần máy khác.

### Đợt 7 — Tái cấu trúc module: cắt vòng import

`tools.py` và `qs_tools.py` import ngược nhau ở mức module, khiến `import src.qs_tools`
trực tiếp bị vỡ và buộc cả hai file phải dồn import xuống giữa/cuối file kèm `# noqa: E402`.

- Tách hàm dùng chung sang **`src/mepf_spec.py`** — module nền, không import module nào
  của dự án. Vòng lặp đứt hẳn.
- Toàn bộ import của hai file về đầu file; **không còn `# noqa: E402`** nào.
- `src/api.py` nạp thẳng từ `src.qs_tools` thay vì đi vòng qua `src.tools`.
- Mã nguồn **giảm ròng ~14 dòng** trong ba file, dù thêm một module mới.
- `tests/test_no_import_cycles.py` nạp từng module lõi trong **tiến trình sạch** để vòng
  lặp quay lại là đỏ ngay; đã thử tái lập vòng cũ để xác nhận test bắt được.

## 3.7 Việc còn nợ

Chi tiết đầy đủ ở [`TECH_DEBT.md`](TECH_DEBT.md). Tóm tắt mức ưu tiên:

| Việc | Mức | Vướng ở đâu |
|---|---|---|
| Chạy thử `docker compose up --build` thật | 🟠 Cao | Cần máy có Docker daemon |
| Migrate Postgres/pgvector/S3 với hạ tầng thật | 🟠 Cao | Cần instance thật + người duyệt schema |
| Kiểm thử plugin trong Revit/AutoCAD thật | 🟡 Vừa | Cần máy Windows có 2 phần mềm đó |
| Fine-tune YOLO trên ký hiệu MEPF | 🟡 Vừa | Cần bộ ảnh gán nhãn thật |
| Real-time đúng nghĩa (Redis Pub/Sub) | 🟡 Vừa | Server vẫn polling Celery backend 1s |
| Local LLM / air-gapped | 🟢 Thấp | Cần GPU 16–24GB VRAM |
| Billing + xác thực đa người dùng | 🟢 Thấp | Cần tài khoản cổng thanh toán thật |

Điểm chung của nhóm còn nợ: **không phải việc sửa code**, mà là việc cần hạ tầng, phần
cứng, dữ liệu thật hoặc quyết định kinh doanh. Viết code đoán trước cho chúng rủi ro cao
hơn lợi ích.

## 3.8 Đề xuất việc tiếp theo (thực dụng, ngắn hạn)

Khác với lộ trình chiến lược "Engineering OS" ở mục 5 trở đi (dài hạn, kiến trúc lớn), đây
là các việc **ngắn hạn** xếp theo tỉ lệ lợi ích / công sức, cao xuống thấp:

1. **Chạy thử Docker Compose thật** — việc còn lại rẻ nhất. Kịch bản E2E đã sẵn sàng:
   `docker compose up --build -d` rồi `uv run python scripts/e2e_smoke.py` là biết ngay
   lớp container có vấn đề gì.
2. **Dựng thử cấu hình lai với Ollama thật** — phần sửa địa chỉ server mới chỉ được kiểm ở
   mức "dựng đúng địa chỉ", chưa hề gọi tới server thật.
3. **Đối chiếu `data/unit_prices.csv` với công bố giá thật của Sở Xây dựng**, và phân theo
   vùng. Cơ chế cảnh báo đã có, nhưng số liệu vẫn là giá tham khảo nội bộ.

---

# 4. Definition of Done của Phase B

Phase B chỉ được đánh dấu `[x]` khi toàn bộ các điều kiện sau đạt:

- [ ] Canonical Project model
- [ ] Stable IDs cho engineering objects
- [ ] Digital Twin hierarchy
- [ ] Source references từ object → drawing/BIM/PDF
- [ ] Revision graph
- [ ] Engineering Knowledge Graph
- [ ] Calculation result schema thống nhất
- [ ] Evidence model
- [ ] Standards versioning
- [ ] Structured Rule Engine
- [ ] Job/event architecture
- [ ] deterministic tool registry chuẩn hóa
- [ ] tenant/project isolation foundation
- [ ] golden regression suite
- [ ] integration test baseline

---

# 5. ENGINEERING OS — Giai đoạn tiếp theo

## 5.1 Mục tiêu

Engineering OS là lớp nền tảng biến MEP-Agents từ một hệ multi-agent thành **hệ điều hành kỹ thuật cho một project**.

Nguyên tắc:

> **Project State là source of truth. LLM không phải source of truth.**

LLM chỉ:

- hiểu intent;
- lập kế hoạch;
- chọn tool;
- phân rã task;
- suy luận;
- giải thích.

Engineering OS chịu trách nhiệm:

- giữ trạng thái dự án;
- lưu object;
- quan hệ giữa object;
- geometry;
- calculations;
- standards;
- revisions;
- evidence;
- jobs;
- approvals;
- deliverables.

---

# 6. Engineering OS Architecture

```text
                         USER / ENGINEER
                                │
                                ▼
                         PROJECT WORKSPACE
                                │
                                ▼
                         INTENT INTERFACE
                                │
                                ▼
                       AI ORCHESTRATOR
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
        Planner/Reasoner    Model Router      Policy Engine
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ▼
                           TOOL BUS
                                │
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
    CAD/BIM                 Engineering              QS/Cost
    Services                Services                 Services
        │                       │                        │
        └───────────────────────┼────────────────────────┘
                                ▼
                       ENGINEERING CORE
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
     Digital Twin         Knowledge Graph       Rule/Standards
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
                    Evidence / Audit / Revision
                                │
                                ▼
                       REVIEW / APPROVAL
                                │
                                ▼
                         DELIVERABLES
```

---

# 7. Engineering OS Core Components

## 7.1 Project Kernel

> **Đặc tả chi tiết (schema, stable ID, module surface, kế hoạch triển khai theo giai
> đoạn, câu hỏi mở cần duyệt):** [`docs/DAC_TA_PROJECT_KERNEL.md`](../docs/DAC_TA_PROJECT_KERNEL.md).
> Đây là bước 2 trong "Immediate implementation order" (mục 44) — đã có đặc tả, **chưa có
> code**. Mục 13 của đặc tả đó liệt kê các câu hỏi cần người phụ trách duyệt trước khi bắt
> đầu code.

Project Kernel là “kernel” của Engineering OS.

Chức năng:

- project identity;
- building identity;
- discipline registry;
- revision state;
- object registry;
- source registry;
- job registry;
- approval registry;
- policy registry.

Không được để các agent tự định nghĩa project state riêng.

---

## 7.2 Digital Twin

### Hierarchy

```text
Organization
└── Project
    └── Site
        └── Building
            └── Level
                └── Zone
                    └── Space
                        └── System
                            └── Equipment
                                └── Component
                                    └── Connection
```

### Object identity

Mỗi object có:

```json
{
  "id": "equipment:AHU-003",
  "type": "AHU",
  "project_id": "P001",
  "revision_id": "R004",
  "discipline": "mechanical",
  "source_refs": [],
  "geometry_ref": null,
  "properties": {},
  "status": "active"
}
```

### Object lifecycle

```text
DISCOVERED
  ↓
NORMALIZED
  ↓
VALIDATED
  ↓
ACTIVE
  ↓
MODIFIED
  ↓
SUPERSEDED
  ↓
ARCHIVED
```

---

# 8. Source-of-Truth Model

Engineering OS phải phân biệt:

```text
SOURCE
  ├── DWG
  ├── DXF
  ├── IFC
  ├── PDF
  ├── XLSX
  ├── Specification
  └── Standard

DERIVED
  ├── parsed object
  ├── geometry
  ├── quantity
  ├── calculation
  ├── rule result
  └── report
```

Derived data phải có `derived_from` reference.

Không được ghi đè source.

---

# 9. Engineering Knowledge Graph

Graph là bộ nhớ quan hệ của công trình.

## 9.1 Relationship vocabulary

Tối thiểu:

```text
contains
located_in
serves
connects_to
powered_by
supplied_by
drains_to
controls
depends_on
feeds
returns_to
intersects
near
clearance_to
replaces
derived_from
belongs_to_system
```

## 9.2 Ví dụ

```text
AHU-003
 ├── serves → ZONE-03
 ├── supplies → DUCT-003
 ├── powered_by → DB-04
 ├── controlled_by → BMS-03
 └── drains_to → DRAIN-08
```

Graph phải cho phép impact traversal:

```text
AHU-003 changed
       ↓
DUCT-003
       ↓
Diffusers
       ↓
Room loads
       ↓
Electrical load
       ↓
DB-04
       ↓
BOQ
       ↓
Estimate
```

---

# 10. Canonical Engineering Object Model

> Đặc tả cụ thể hóa thành schema SQLite (bảng `engineering_objects`, phân biệt `object_id`
> bất biến với `tag` nghiệp vụ) nằm ở [`docs/DAC_TA_PROJECT_KERNEL.md`](../docs/DAC_TA_PROJECT_KERNEL.md) mục 6.4 và 7.

Mọi discipline dùng chung object contract.

```json
{
  "id": "string",
  "type": "string",
  "discipline": "string",
  "project_id": "string",
  "revision_id": "string",
  "geometry": {},
  "properties": {},
  "relations": [],
  "source_refs": [],
  "status": "string",
  "confidence": 0.0,
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

Các domain-specific fields nằm trong `properties` nhưng phải có schema.

---

# 11. Calculation Platform

Mọi calculation phải có canonical envelope:

```json
{
  "calculation_id": "CALC-001",
  "type": "voltage_drop",
  "discipline": "electrical",
  "engine_version": "1.0.0",
  "inputs": {},
  "assumptions": [],
  "formula_refs": [],
  "standards_refs": [],
  "results": {},
  "warnings": [],
  "validation": {},
  "evidence_refs": []
}
```

Calculation engine phải deterministic và testable độc lập khỏi LLM.

---

# 12. Standards Engine

RAG hiện tại được nâng thành 3 lớp:

```text
DOCUMENT LAYER
    ↓
SEMANTIC RETRIEVAL
    ↓
STRUCTURED RULES
    ↓
DETERMINISTIC COMPLIANCE
```

Mỗi rule phải có:

- standard ID;
- version;
- jurisdiction;
- section;
- effective date;
- rule type;
- applicability;
- expression;
- evidence source.

Không cho phép hệ thống nói “compliant” chỉ vì LLM tìm thấy đoạn văn phù hợp.

---

# 13. Rule Engine

Rule engine hỗ trợ:

- hard constraints;
- soft constraints;
- warnings;
- exceptions;
- project overrides;
- jurisdiction rules;
- discipline rules.

Ví dụ:

```text
IF clearance < required_clearance
THEN violation(CRITICAL)
```

Rule result:

```json
{
  "rule_id": "RULE-001",
  "status": "FAIL",
  "severity": "HIGH",
  "object_refs": ["DUCT-03", "PIPE-22"],
  "evidence_refs": ["..."],
  "remediation": []
}
```

---

# 14. Evidence Engine

Mục tiêu: **mọi kết luận quan trọng đều giải thích được**.

Evidence chain:

```text
Answer
 ↓
Decision
 ↓
Calculation / Rule
 ↓
Inputs
 ↓
Objects
 ↓
Source
 ↓
Revision
```

Ví dụ:

> “DB-05 quá tải.”

Phải truy ngược được:

```text
DB-05
 ↓
Load schedule
 ↓
Connected equipment
 ↓
Equipment revisions
 ↓
Calculation CALC-xxxx
 ↓
Formula
 ↓
Source drawing
```

---

# 15. Revision Engine

Revision phải immutable.

```text
R001
 ↓
R002
 ↓
R003
 ↓
R004
```

Mỗi revision chứa:

- added objects;
- removed objects;
- changed objects;
- changed calculations;
- changed rules;
- changed BOQ;
- changed cost;
- changed clashes.

Không sửa lịch sử revision.

---

# 16. Engineering Diff

Diff không chỉ là file diff.

Phải có 4 lớp:

```text
FILE DIFF
GEOMETRY DIFF
SEMANTIC DIFF
ENGINEERING IMPACT DIFF
```

Ví dụ:

```text
Semantic:
AHU-03 capacity 18,000 → 20,000 CMH

Engineering:
Cooling load +7%
Electrical load +4.2 kW

Quantity:
Duct +32m
Cable +18m

Cost:
+84,000,000 VND
```

---

# 17. Job Engine

Mọi tác vụ nặng phải asynchronous.

```text
QUEUED
 ↓
RUNNING
 ↓
WAITING_REVIEW
 ↓
SUCCEEDED
```

Hoặc:

```text
FAILED
CANCELLED
```

Job phải hỗ trợ:

- retry;
- idempotency;
- timeout;
- cancellation;
- progress;
- logs;
- result references.

---

# 18. Event Bus

Event chuẩn:

```text
PROJECT_CREATED
SOURCE_UPLOADED
SOURCE_PARSED
OBJECT_DISCOVERED
OBJECT_NORMALIZED
GRAPH_UPDATED
CALCULATION_REQUESTED
CALCULATION_COMPLETED
RULE_EVALUATED
CLASH_DETECTED
QUANTITY_UPDATED
BOQ_UPDATED
ESTIMATE_UPDATED
REVISION_CREATED
APPROVAL_REQUESTED
APPROVED
REJECTED
DELIVERABLE_GENERATED
```

Agent không tự gọi agent khác bằng hard-coded function chain khi event-driven orchestration phù hợp.

---

# 19. Tool Bus

Tool phải có metadata:

```json
{
  "name": "calc_voltage_drop",
  "domain": "electrical",
  "risk": "medium",
  "read_only": true,
  "requires_approval": false,
  "idempotent": true,
  "version": "1.0.0"
}
```

Mutation tool:

```json
{
  "name": "edit_cad",
  "risk": "high",
  "read_only": false,
  "requires_approval": true
}
```

Policy engine quyết định agent nào được gọi tool nào.

---

# 20. AI Orchestrator V2

## 20.1 Planner

Planner biến yêu cầu thành DAG/task plan.

Ví dụ:

```text
User:
"Kiểm tra tầng 5 và tối ưu HVAC giảm chi phí"

Plan:
1. Load project state
2. Identify Level 5
3. Validate source completeness
4. Extract HVAC objects
5. Calculate loads
6. Detect constraints
7. Generate alternatives
8. Calculate alternatives
9. Coordinate
10. Estimate cost
11. Rank options
12. Review
13. Ask approval
```

## 20.2 Planner không được tự ý bỏ validation

Mọi task critical phải có preconditions.

---

# 21. Model Router V2

Router quyết định model theo:

```text
Task
+ modality
+ complexity
+ risk
+ latency budget
+ cost budget
+ context size
+ availability
```

Ví dụ:

```text
OCR/simple classification → cheap model
Engineering explanation → mid/high model
Complex planning → reasoning model
Vision drawing → vision model
Code generation → coding model
Safety review → stronger model + deterministic rules
```

Model provider là replaceable infrastructure.

---

# 22. Confidence & Risk Engine

Không chỉ có confidence của model.

Hệ thống phải có:

```text
Model confidence
Data completeness
Calculation confidence
Rule confidence
Source quality
Risk level
```

Final decision confidence phải tổng hợp các thành phần.

Nếu:

```text
data completeness < threshold
```

→ không được tự động phát hành.

---

# 23. Human Approval System

Approval levels:

```text
AUTO
REVIEW_REQUIRED
ENGINEER_APPROVAL
LEAD_APPROVAL
PUBLISH_APPROVAL
```

Safety-critical và publish-ready deliverable phải có approval policy rõ.

Approval record:

```json
{
  "approval_id": "APR-001",
  "target": "REV-004",
  "decision": "approved",
  "actor": "engineer-id",
  "timestamp": "...",
  "evidence_refs": []
}
```

---

# 24. Ask the Building

Đây là flagship UX của Engineering OS.

Người dùng có thể hỏi:

- “Tầng 3 có bao nhiêu FCU?”
- “FCU nào chưa có nguồn?”
- “Tổng tải điện tầng 5?”
- “Clash critical nào chưa xử lý?”
- “Tại sao BOQ R04 tăng?”
- “Nếu chuyển AHU-03 2 m về phía đông thì ảnh hưởng gì?”
- “Phương án HVAC nào rẻ nhất nhưng vẫn đạt constraints?”

Query pipeline:

```text
Natural Language
 ↓
Intent parser
 ↓
Project context resolver
 ↓
Graph query / calculation / rule / document retrieval
 ↓
Evidence aggregation
 ↓
Answer
```

Không trả lời bằng chat memory nếu project state đã có dữ liệu chính xác hơn.

---

# 25. What-if / Impact Simulation

Đây là tính năng tạo khác biệt lớn.

Input:

```text
Change:
AHU-03 capacity 18,000 → 20,000 CMH
```

System:

```text
Find dependents
 ↓
Recalculate affected systems
 ↓
Re-run rules
 ↓
Re-run clash checks
 ↓
Update quantities
 ↓
Update cost
 ↓
Generate impact report
```

Output:

```text
Affected objects: 47
Affected calculations: 13
New clashes: 2
BOQ delta: +37 items
Cost delta: +84M VND
Compliance: PASS with 1 warning
```

---

# 26. Generative Engineering

Engineering OS sau khi có Digital Twin mới được phép tiến tới generative design.

Input:

```text
Requirements
Constraints
Objectives
Available equipment
Space
Budget
```

Output:

```text
Option A
Option B
Option C
```

Mỗi option phải chạy qua:

```text
Calculation
Rules
Coordination
Cost
Performance
Maintainability
```

AI không được tạo geometry “đẹp” nhưng không được kiểm chứng.

---

# 27. Optimization Engine

Objective có thể là:

- minimize CAPEX;
- minimize OPEX;
- minimize energy;
- minimize duct length;
- minimize shaft size;
- maximize maintainability;
- maximize redundancy.

Constraints:

- code;
- safety;
- geometry;
- capacity;
- project requirements;
- procurement;
- constructability.

Hard constraints không được optimizer phá vỡ.

---

# 28. Engineering Compiler

Đây là long-term R&D của Engineering OS.

Thay vì:

```text
Engineer draws every component
```

sẽ có:

```text
Engineering Intent
 ↓
Constraint Model
 ↓
Design Graph
 ↓
Engineering Compiler
 ↓
Calculations
 ↓
Geometry
 ↓
BIM/CAD
 ↓
BOQ
```

Ví dụ:

```text
Room R301
Occupants = 25
Ventilation = 10 L/s/person
Temperature = 24°C
Ceiling = 3.2m
Maintenance clearance >= X
```

Compiler sinh candidate engineering solution.

Đây là mục tiêu R&D dài hạn, chưa coi là production requirement của Phase B.

---

# 29. Engineering Version Control

Engineering OS phải tiến tới mô hình giống Git:

```text
commit
branch
merge
diff
rollback
blame
```

Nhưng semantic theo engineering.

Ví dụ:

```text
Who changed AHU-03?
Why?
Which requirement caused it?
Which calculation changed?
Who approved it?
Which BOQ lines changed?
```

---

# 30. Engineering Memory

Sau nhiều project, hệ thống có thể xây:

```text
Validated patterns
Engineering playbooks
Typical configurations
Failure patterns
Cost patterns
Coordination patterns
```

Nhưng memory phải có provenance.

Không được học một lỗi thành “best practice”.

Mỗi pattern cần:

- source projects;
- validation status;
- confidence;
- date;
- domain;
- applicability.

---

# 31. AEC Expansion

Sau khi Engineering OS core ổn định:

```text
MEP
 ↓
Architecture
 ↓
Structural
 ↓
Fire
 ↓
ELV
 ↓
Construction
 ↓
Facility Management
```

Core không được chứa hard-coded logic chỉ dành cho MEP.

MEP là plugin/domain package của Engineering OS.

---

# 32. Live Building / Operational Twin

Long-term:

```text
Design Twin
 ↓
As-built Twin
 ↓
IoT / BMS / Metering
 ↓
Live Building Twin
```

Use cases:

- anomaly detection;
- predictive maintenance;
- energy optimization;
- equipment health;
- operational simulation.

Đây là post-construction roadmap, không làm trước khi Design Twin ổn định.

---

# 33. Engineering OS Data Architecture

## PostgreSQL

Canonical transactional data:

- organizations;
- projects;
- buildings;
- levels;
- spaces;
- systems;
- objects;
- revisions;
- calculations;
- rules;
- approvals;
- jobs;
- audit.

## Object Storage

Binary/source artifacts:

- DWG;
- DXF;
- IFC;
- PDF;
- XLSX;
- reports;
- snapshots.

## Graph layer

Ban đầu có thể dùng PostgreSQL relational graph patterns nếu đủ; chỉ tách graph database khi workload thực tế chứng minh cần thiết.

**Không được dùng graph database chỉ vì nghe “AI architecture” hay hơn.**

## Queue

Redis/worker queue hoặc message broker tùy scale.

---

# 34. API Contract

Canonical API:

```text
/api/v1/projects
/api/v1/projects/{id}/sources
/api/v1/projects/{id}/objects
/api/v1/projects/{id}/graph
/api/v1/projects/{id}/revisions
/api/v1/calculations
/api/v1/rules
/api/v1/standards
/api/v1/jobs
/api/v1/approvals
/api/v1/evidence
/api/v1/quantities
/api/v1/boq
/api/v1/estimates
/api/v1/ai/query
```

Long-running task:

```json
{
  "job_id": "JOB-001",
  "status": "QUEUED"
}
```

---

# 35. Security Model

Engineering OS phải coi file và agent output là untrusted input.

Bắt buộc:

- authentication;
- RBAC;
- project-level authorization;
- tenant isolation;
- signed uploads;
- malware scanning;
- path traversal protection;
- tool authorization;
- prompt injection defense;
- audit logs;
- secret management;
- encryption;
- rate limiting.

Agent không được tự ý:

- delete project data;
- publish deliverables;
- mutate safety-critical design;
- cross-tenant query;
- export private source data.

---

# 36. Testing & Evaluation

## Engineering tests

Golden cases cho:

- HVAC;
- electrical;
- plumbing;
- fire;
- QS.

## CAD tests

Golden DWG/DXF.

## BIM tests

Golden IFC.

## Agent tests

Đo:

- tool selection;
- plan correctness;
- hallucination;
- evidence completeness;
- reviewer acceptance.

## System tests

```text
Upload
 → Parse
 → Twin
 → Calculate
 → Rule
 → BOQ
 → Revision
 → Export
```

Phải có end-to-end fixture.

---

# 37. Quality Gates

Không feature nào được coi là production-ready nếu thiếu:

- [ ] typed contract;
- [ ] unit tests;
- [ ] integration tests;
- [ ] error handling;
- [ ] logging;
- [ ] audit nếu liên quan state;
- [ ] authorization;
- [ ] documentation;
- [ ] migration;
- [ ] rollback strategy;
- [ ] AI evaluation nếu có model behavior;
- [ ] deterministic validation nếu là engineering result.

---

# 38. Engineering OS Roadmap

## PHASE OS-0 — Foundation Hardening

Status: **NEXT**

- [ ] Freeze current behavior bằng regression suite
- [ ] Chuẩn hóa config
- [ ] Chuẩn hóa domain contracts
- [ ] Chuẩn hóa errors
- [ ] Chuẩn hóa logging
- [ ] CI quality gates
- [ ] Security baseline

## PHASE OS-1 — Project Kernel

- [ ] Project schema
- [ ] Building/level/space schema
- [ ] Object registry
- [ ] Source registry
- [ ] Revision registry
- [ ] Job registry
- [ ] Approval registry

## PHASE OS-2 — Digital Twin

- [ ] Stable IDs
- [ ] Object lifecycle
- [ ] Geometry references
- [ ] Source references
- [ ] System hierarchy
- [ ] Cross-discipline relations

## PHASE OS-3 — Engineering Graph

- [ ] Relation model
- [ ] Traversal API
- [ ] Impact analysis
- [ ] Spatial relationships
- [ ] Dependency graph

## PHASE OS-4 — Engineering Core

- [ ] Calculation envelope
- [ ] Engine registry
- [ ] Rule engine
- [ ] Standards versioning
- [ ] Evidence engine

## PHASE OS-5 — Revision & Impact

- [ ] Immutable revisions
- [ ] Semantic diff
- [ ] Engineering diff
- [ ] Change propagation
- [ ] What-if analysis

## PHASE OS-6 — AI Orchestrator V2

- [ ] Planner
- [ ] DAG execution
- [ ] Policy engine
- [ ] Model router
- [ ] Confidence/risk engine
- [ ] Tool authorization

## PHASE OS-7 — Ask the Building

- [ ] Natural language query
- [ ] Graph query translation
- [ ] Calculation query
- [ ] Evidence aggregation
- [ ] Explainable answer

## PHASE OS-8 — Generative Engineering

- [ ] Alternative generation
- [ ] Candidate scoring
- [ ] Constraint solving
- [ ] Optimization
- [ ] Approval workflow

## PHASE OS-9 — Engineering Compiler

- [ ] Intent schema
- [ ] Constraint DSL
- [ ] Design graph compiler
- [ ] Geometry generation
- [ ] BIM/CAD generation

## PHASE OS-10 — AEC OS

- [ ] Architecture
- [ ] Structural
- [ ] Construction
- [ ] FM
- [ ] Live Building Twin

---

# 39. P0 / P1 / P2 Priority

## P0 — Must build first

1. Project Kernel
2. Digital Twin
3. Stable IDs
4. Source references
5. Revision model
6. Calculation envelope
7. Evidence
8. Rule engine
9. Job engine
10. Tool authorization
11. Regression tests

## P1 — Product moat

1. Engineering Knowledge Graph
2. Semantic CAD
3. BIM semantic model
4. Change impact
5. Ask the Building
6. Model Router V2
7. Review Board
8. Quantity traceability

## P2 — Advanced intelligence

1. What-if simulation
2. Design alternatives
3. Optimization
4. Engineering Memory
5. Engineering Compiler
6. Live Building Twin

---

# 40. What NOT to do

Không được:

1. Rewrite toàn bộ repository chỉ vì muốn “kiến trúc đẹp”.
2. Đổi Streamlit/technology trước khi Project Kernel ổn định.
3. Cho LLM làm calculation engine.
4. Cho LLM tự quyết compliance.
5. Tạo graph database nếu PostgreSQL chưa đủ.
6. Tạo microservices hàng loạt khi chưa có workload cần thiết.
7. Chạy tất cả agent cho mọi câu hỏi.
8. Gửi toàn bộ project context vào mỗi LLM request.
9. Đưa toàn bộ CAD binary vào prompt.
10. Sử dụng RAG như source of truth.
11. Auto-publish CAD/BIM thay đổi safety-critical.
12. Để agent có quyền vô hạn.
13. Học từ dữ liệu chưa được validate.
14. Đánh giá AI chỉ bằng “câu trả lời nghe hay”.

---

# 41. North Star Workflow

```text
USER UPLOADS PROJECT
        ↓
INGESTION
        ↓
SOURCE VALIDATION
        ↓
CAD / BIM / PDF / XLSX PARSING
        ↓
SEMANTIC OBJECT EXTRACTION
        ↓
DIGITAL TWIN
        ↓
ENGINEERING GRAPH
        ↓
REQUIREMENT MODEL
        ↓
AI PLAN
        ↓
DETERMINISTIC CALCULATIONS
        ↓
RULE / STANDARDS CHECK
        ↓
COORDINATION
        ↓
QUANTITY TAKEOFF
        ↓
BOQ / COST
        ↓
ALTERNATIVES
        ↓
OPTIMIZATION
        ↓
REVIEW BOARD
        ↓
HUMAN APPROVAL
        ↓
CAD / BIM MUTATION
        ↓
NEW REVISION
        ↓
IMPACT ANALYSIS
        ↓
REPORTS / DELIVERABLES
```

---

# 42. Final Product Definition

MEP-Agents đạt mục tiêu Engineering OS khi một kỹ sư có thể đưa dữ liệu dự án vào hệ thống và yêu cầu:

> **“Hiểu dự án, tìm vấn đề, tính toán, đề xuất phương án, kiểm tra tiêu chuẩn, phối hợp, bóc khối lượng, dự toán, tối ưu, cho tôi xem tác động, sau đó chờ tôi phê duyệt trước khi sửa hồ sơ.”**

Hệ thống phải thực hiện được toàn bộ workflow trên bằng state machine + deterministic engines + AI orchestration + evidence, thay vì một chuỗi prompt.

---

# 43. Project Status Board

| Area | Status | Ghi chú |
|---|---|---|
| Multi-Agent | ✅ DONE | LangGraph + Supervisor + domain agents |
| Deterministic MEP calculations | ✅ DONE | Prototype/engineering-tool level |
| CAD tools | ✅ DONE | Prototype level, có revision/safety primitives |
| BIM/clash | ✅ DONE | Prototype level |
| QS/BOQ | ✅ DONE | Prototype level |
| Reviewer/guardrail | ✅ DONE | Cơ chế reviewer hiện có |
| Model/provider routing | ✅ DONE | Prototype level |
| Usage/cost tracking | ✅ DONE | Có trong current architecture |
| Persistent checkpoint | 🟡 PARTIAL | Có SQLite/Postgres path, chưa phải project kernel |
| Standards RAG | 🟡 PARTIAL | Có retrieval, chưa phải structured compliance engine |
| Digital Twin | ⬜ TODO | Core next milestone |
| Engineering Graph | ⬜ TODO | Core next milestone |
| Project Kernel + Canonical object model | 🟡 ĐẶC TẢ XONG | [`docs/DAC_TA_PROJECT_KERNEL.md`](../docs/DAC_TA_PROJECT_KERNEL.md) — schema + module surface đã chốt, chưa code, chờ duyệt mục 13 |
| Evidence engine | ⬜ TODO | Core next milestone |
| Revision semantic model | 🟡 PARTIAL | CAD revision có, project-wide semantic revision chưa có |
| Job/event platform | 🟡 PARTIAL | Có graph execution, chưa có platform job/event model |
| Multi-tenancy | ⬜ TODO | Engineering OS requirement |
| Production API | ⬜ TODO | Engineering OS requirement |
| Ask the Building | ⬜ TODO | Flagship OS feature |
| What-if simulation | ⬜ TODO | Advanced |
| Generative engineering | ⬜ TODO | Advanced |
| Optimization engine | ⬜ TODO | Advanced |
| Engineering Compiler | ⬜ TODO | Long-term R&D |
| AEC OS | ⬜ TODO | North Star |

---

# 44. Immediate implementation order

Không nhảy thẳng vào Generative AI.

Thứ tự bắt buộc:

```text
1. Regression baseline
        ↓
2. Project Kernel
        ↓
3. Canonical Object Model
        ↓
4. Digital Twin
        ↓
5. Source / Evidence
        ↓
6. Engineering Graph
        ↓
7. Calculation / Rule contracts
        ↓
8. Revision / Impact
        ↓
9. Job/Event platform
        ↓
10. AI Orchestrator V2
        ↓
11. Ask the Building
        ↓
12. What-if
        ↓
13. Generative Engineering
        ↓
14. Optimization
        ↓
15. Engineering Compiler
        ↓
16. AEC Engineering OS
```

---

# 45. Acceptance Criteria — Engineering OS MVP

Engineering OS MVP chỉ được đánh dấu hoàn thành khi có thể chứng minh end-to-end:

### Input

- [ ] Upload một project có nhiều file.
- [ ] Parse ít nhất CAD/BIM/PDF/XLSX phù hợp.

### State

- [ ] Project có canonical state.
- [ ] Objects có stable IDs.
- [ ] Objects có source refs.
- [ ] Objects có relationships.

### Engineering

- [ ] Gọi calculation engine độc lập.
- [ ] Gọi rule engine.
- [ ] Truy xuất standard/evidence.

### Revision

- [ ] Tạo revision mới.
- [ ] Semantic diff.
- [ ] Impact analysis.

### AI

- [ ] Planner tạo task plan.
- [ ] Router chọn tool/model.
- [ ] Tool policy kiểm soát quyền.
- [ ] AI trả evidence.

### Safety

- [ ] Mutation yêu cầu approval theo risk policy.
- [ ] Có rollback.
- [ ] Có audit trail.

### Deliverable

- [ ] Xuất report.
- [ ] Xuất BOQ/estimate.
- [ ] Có traceability về source/revision.

---

# 46. Definition of “Super Pro”

“Super Pro” không có nghĩa:

> nhiều agent hơn + prompt dài hơn + model đắt hơn.

Super Pro nghĩa:

```text
SOURCE OF TRUTH
      +
DIGITAL TWIN
      +
ENGINEERING GRAPH
      +
DETERMINISTIC ENGINES
      +
RULES / STANDARDS
      +
EVIDENCE
      +
REVISION CONTROL
      +
AI ORCHESTRATION
      +
HUMAN GOVERNANCE
      +
GENERATION / OPTIMIZATION
```

Đây là moat kỹ thuật thực sự.

---

# 47. Guiding principles — khóa kiến trúc

1. **LLM is not the source of truth.**
2. **Engineering calculations are deterministic.**
3. **Every important result has evidence.**
4. **Every mutation has revision lineage.**
5. **Every high-risk action has policy/approval.**
6. **Every AI behavior is measurable.**
7. **Models are replaceable.**
8. **Project state is canonical.**
9. **Domain engines must work without an LLM.**
10. **Do not over-engineer infrastructure before workload requires it.**
11. **MEP is the first domain, not the architectural limit.**
12. **Build the Engineering OS before attempting full autonomy.**

---

# 48. Long-term North Star

```text
                         AEC ENGINEERING OS
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
          DESIGN              CONSTRUCTION         OPERATION
              │                   │                   │
       ┌──────┼──────┐      ┌─────┼─────┐       ┌────┼────┐
       ▼      ▼      ▼      ▼     ▼     ▼       ▼    ▼    ▼
      MEP    BIM   CAD     QS    PM    QA      BMS   IoT  FM
       │      │      │      │     │     │       │    │    │
       └──────┴──────┴──────┴─────┴─────┴───────┴────┴────┘
                                  │
                                  ▼
                           DIGITAL TWIN
                                  │
                                  ▼
                       ENGINEERING KNOWLEDGE
                                  │
                                  ▼
                         AI ENGINEERING OS
```

**Final strategic statement:**

> **Build the source of truth first. Put intelligence on top of it. Then let intelligence generate and optimize engineering — under evidence, rules, revision control and human governance.**

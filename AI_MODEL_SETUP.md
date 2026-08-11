# Hướng dẫn chọn & cấu hình model AI theo từng vai trò (Role-based Model Setup)

Tài liệu này trả lời câu hỏi: **"Từng phòng ban (Supervisor, Reviewer, Cơ khí, Điện,
Nước, PCCC, QS, CAD, BIM) nên dùng model AI nào để đạt hiệu quả tối ưu?"** — và
hướng dẫn cách cấu hình để mỗi vai trò thực sự dùng đúng model đó.

## 1. Vì sao cần chọn model riêng theo vai trò?

Trước đây (`src/agents.py` bản gốc), **toàn bộ hệ thống chỉ dùng 1 model duy nhất**
(`LLM_PROVIDER`/`MODEL_NAME` trong `.env`) cho cả 9 vai trò — từ việc định tuyến đơn
giản của Supervisor đến việc CAD Agent phải đọc ảnh bản vẽ + tự viết code Python vẽ
block mới. Đây là lãng phí hai chiều:
- Dùng model mạnh (đắt) cho việc đơn giản (định tuyến) → tốn tiền không cần thiết.
- Dùng model yếu (rẻ) cho việc phức tạp (sinh code ezdxf, đọc ảnh CAD, tuân thủ quy
  tắc nghiêm ngặt của QS) → dễ sai, dễ "trả lời suông" (đúng như các bug đã từng gặp
  trong lịch sử commit của dự án).

Bản cập nhật này (`src/agents.py`) cho phép **mỗi vai trò dùng provider/model riêng**
qua biến môi trường `<ROLE>_LLM_PROVIDER` / `<ROLE>_MODEL_NAME`, nếu không đặt sẽ rơi
về `LLM_PROVIDER`/`MODEL_NAME` toàn cục như cũ (tương thích ngược 100%).

## 2. Bảng khuyến nghị model theo vai trò

Dựa trên độ phức tạp thực tế của từng vai trò trong `src/agents.py`:

| Vai trò | Biến môi trường | Độ phức tạp công việc | Model khuyến nghị | Lý do |
|---|---|---|---|---|
| **Supervisor** (Giám đốc dự án) | `SUPERVISOR_*` | Phân loại yêu cầu → định tuyến 1 trong 8 lựa chọn. Chạy ở **mọi** lượt hội thoại → tần suất gọi cao nhất hệ thống. | **Claude Sonnet 5** (cân bằng) hoặc **Haiku 4.5** (tối ưu chi phí) | Nhiệm vụ phân loại đơn giản nhưng định tuyến sai sẽ kéo cả luồng đi sai hướng — Sonnet 5 an toàn hơn Haiku nếu ngân sách cho phép; Haiku 4.5 phù hợp nếu traffic lớn và cần tốc độ. |
| **Reviewer** (Kỹ sư trưởng) | `REVIEWER_*` | Vai trò kiểm duyệt: đánh giá tính đúng đắn kỹ thuật, bắt lỗi "trả lời suông", yêu cầu trích dẫn tiêu chuẩn. Đây là **cổng chất lượng cuối cùng** của cả hệ thống. | **Claude Sonnet 5**, nâng lên **Opus 5** nếu cần độ tin cậy cao nhất | Reviewer sai sót nghĩa là kết quả lỗi lọt ra ngoài cho khách hàng — đáng đầu tư model mạnh hơn mức trung bình. |
| **Mechanical (HVAC)** | `MECHANICAL_*` | Tính tải lạnh chi tiết, tổn thất áp suất, chọn Chiller/AHU, phối hợp nhiều tool tính toán liên tiếp. | **Claude Sonnet 5** | Nhóm việc "agentic tool-use" nhiều bước — Sonnet 5 đạt chất lượng gần Opus với chi phí thấp hơn, đúng thế mạnh được công bố cho coding/agentic workload. |
| **Electrical (Điện)** | `ELECTRICAL_*` | Tính cáp, aptomat, chiếu sáng — công thức đơn giản hơn HVAC. | **Claude Sonnet 5** (hoặc Haiku 4.5 nếu chỉ cần các phép tính cơ bản hiện có) | |
| **Plumbing (Cấp thoát nước)** | `PLUMBING_*` | Cấp nước, thoát nước, bể tự hoại, nước nóng — nhiều tool tính toán tương tự Mechanical. | **Claude Sonnet 5** | |
| **Firefighting (PCCC)** | `FIREFIGHTING_*` | Sprinkler, bơm PCCC, bình chữa cháy — phải tuân thủ nghiêm ngặt tiêu chuẩn (an toàn cháy nổ, sai số ảnh hưởng an toàn con người). | **Claude Sonnet 5**, cân nhắc **Opus 5** cho công trình có yêu cầu PCCC phức tạp | Hậu quả sai sót cao hơn các hệ khác về mặt an toàn — nên ưu tiên chất lượng hơn chi phí. |
| **QS** (Bóc tách khối lượng) | `QS_*` | Bắt buộc gọi đúng chuỗi tool (`read_cad` → `analyze_cad_spatial_context` → `write_excel`), tuân thủ quy tắc chuẩn hóa ký hiệu, suy luận không gian từ dữ liệu text CAD. Lịch sử commit cho thấy đây là vai trò **hay bị lỗi "trả lời lý thuyết suông"** nhất. | **Claude Opus 5** | Vai trò này cần tuân thủ instruction nghiêm ngặt nhất hệ thống (nhiều `BẮT BUỘC`, `KHÔNG ĐƯỢC` trong prompt) — model càng mạnh càng bám sát quy tắc, giảm rủi ro lặp lại bug cũ. |
| **CAD** (Họa viên) | `CAD_*` | Đọc ảnh bản vẽ CAD (Computer Vision qua `render_cad_image`), tự viết code Python (ezdxf) để vẽ block mới khi thư viện thiếu, chỉnh sửa file DXF. Đòi hỏi **cả khả năng thị giác lẫn sinh code chính xác**. | **Claude Opus 5** | Đây là vai trò kỹ thuật nặng nhất: kết hợp vision + code generation. Opus 5 có độ phân giải ảnh cao nhất trong dòng Claude (tọa độ ánh xạ 1:1 pixel) và mạnh nhất về agentic coding — đúng hồ sơ năng lực CAD Agent cần. |
| **BIM** (Điều phối 3D) | `BIM_*` | Quản lý mô hình, bóc khối lượng qua CAD (hiện dùng chung tool với QS). | **Claude Sonnet 5** | Tương tự QS nhưng phạm vi hiện tại còn hẹp hơn (xem `MEPF_BACKLOG.md` — clash detection thật sự chưa có); nâng lên Opus 5 khi bổ sung tool clash detection. |

**Tóm tắt theo cấp độ**:
- 🔴 **Opus 5** — chỉ cho vai trò đòi hỏi tuân thủ quy tắc nghiêm ngặt nhất hoặc năng lực kỹ thuật cao nhất: **QS, CAD**.
- 🟡 **Sonnet 5** — mặc định hợp lý cho phần lớn vai trò: **Supervisor, Reviewer, Mechanical, Electrical, Plumbing, Firefighting, BIM**.
- 🟢 **Haiku 4.5** — chỉ cân nhắc cho Supervisor khi traffic rất lớn và cần tối ưu chi phí/tốc độ tối đa.

## 3. Ba chiến lược cấu hình dựng sẵn

### 3.1. Chiến lược "Cân bằng" (khuyến nghị mặc định)

Toàn bộ vai trò dùng Claude Sonnet 5, riêng QS và CAD nâng lên Opus 5:

```env
LLM_PROVIDER=anthropic
MODEL_NAME=claude-sonnet-5
ANTHROPIC_API_KEY=sk-ant-xxxxxx

QS_MODEL_NAME=claude-opus-5
CAD_MODEL_NAME=claude-opus-5
```

*(Không cần đặt `QS_LLM_PROVIDER`/`CAD_LLM_PROVIDER` vì đã cùng provider `anthropic`
với biến toàn cục — chỉ cần ghi đè `MODEL_NAME` riêng.)*

### 3.2. Chiến lược "Tối ưu chi phí" (mix nhiều provider)

Dùng Groq (miễn phí/giá rẻ) cho các vai trò tần suất cao, chỉ dùng Claude cho các vai
trò đòi hỏi độ chính xác cao nhất:

```env
LLM_PROVIDER=groq
MODEL_NAME=llama-3.3-70b-versatile
GROQ_API_KEY=gsk_xxxxxx

ANTHROPIC_API_KEY=sk-ant-xxxxxx
QS_LLM_PROVIDER=anthropic
QS_MODEL_NAME=claude-opus-5
CAD_LLM_PROVIDER=anthropic
CAD_MODEL_NAME=claude-opus-5
REVIEWER_LLM_PROVIDER=anthropic
REVIEWER_MODEL_NAME=claude-sonnet-5
```

### 3.3. Chiến lược "Chất lượng tối đa" (dự án quan trọng/có tính pháp lý cao)

```env
LLM_PROVIDER=anthropic
MODEL_NAME=claude-sonnet-5
ANTHROPIC_API_KEY=sk-ant-xxxxxx

QS_MODEL_NAME=claude-opus-5
CAD_MODEL_NAME=claude-opus-5
REVIEWER_MODEL_NAME=claude-opus-5
FIREFIGHTING_MODEL_NAME=claude-opus-5
```

## 4. Hướng dẫn setup chi tiết

### Bước 1 — Cài đặt dependency

Đã có sẵn trong `pyproject.toml` (`langchain-anthropic`), chỉ cần đồng bộ môi trường:

```bash
uv sync
```

### Bước 2 — Lấy API Key

- **Claude (Anthropic)**: đăng ký tại [console.anthropic.com](https://console.anthropic.com),
  tạo API key dạng `sk-ant-...`.
- Các provider khác (OpenAI/Groq/Gemini) giữ nguyên cách lấy key như trước.

### Bước 3 — Cấu hình `.env`

```bash
cp .env.example .env
```

Mở `.env`, điền `ANTHROPIC_API_KEY`, rồi chọn 1 trong 3 chiến lược ở Mục 3 (hoặc tự
phối theo bảng khuyến nghị ở Mục 2). File `.env.example` đã có sẵn khối chú thích mẫu
cho từng vai trò — chỉ cần bỏ dấu `#` và điền giá trị.

### Bước 4 — Kiểm tra cấu hình đã áp dụng đúng

```bash
uv run python -c "
from src.agents import get_llm
for role in ['Supervisor', 'Reviewer', 'Mechanical', 'Electrical', 'Plumbing', 'Firefighting', 'QS', 'CAD', 'BIM']:
    llm = get_llm(role)
    model = getattr(llm, 'model', getattr(llm, 'model_name', '?'))
    print(f'{role:12s} -> {type(llm).__name__:20s} {model}')
"
```

Kết quả mong đợi (theo chiến lược "Cân bằng" ở Mục 3.1) phải cho thấy QS và CAD dùng
`claude-opus-5`, các vai trò còn lại dùng `claude-sonnet-5`.

### Bước 5 — Chạy thử ứng dụng

```bash
uv run streamlit run app.py
```

Thử một yêu cầu cần nhiều phòng ban phối hợp (ví dụ: "Đọc bản vẽ CAD, bóc khối lượng
và xuất Excel dự toán") để xác nhận từng agent hoạt động đúng với model đã cấu hình —
theo dõi qua LangSmith (nếu đã bật `LANGCHAIN_TRACING_V2=true`) để xem model nào thực
sự được gọi ở mỗi bước.

## 5. Chạy test tự động

```bash
uv run pytest tests/test_agents_llm_selection.py -v
```

Bộ test này xác nhận: (a) mặc định không cấu hình gì vẫn chạy được (OpenAI
`gpt-4o-mini`), (b) biến toàn cục áp dụng cho mọi vai trò, (c) biến riêng theo vai trò
ghi đè đúng biến toàn cục, (d) API key riêng theo vai trò hoạt động, (e) tên vai trò
được suy ra đúng từ tên agent (`"MechanicalAgent"` → `"Mechanical"`).

## 6. Lưu ý về chi phí

Giá tham khảo (USD / 1 triệu token, tại thời điểm viết tài liệu):

| Model | Input | Output |
|---|---|---|
| Claude Haiku 4.5 | $1.00 | $5.00 |
| Claude Sonnet 5 | $3.00 (ưu đãi $2.00 đến 2026-08-31) | $15.00 (ưu đãi $10.00) |
| Claude Opus 5 | $5.00 | $25.00 |

### Ước tính chi phí theo kịch bản thực tế (đo trực tiếp từ code, không phải phỏng đoán)

Đo bằng cách đếm ký tự thực tế của system prompt (`src/agents.py`) + tool schema JSON
(`src/tools.py` → `get_tools_for_role`) cho từng vai trò, quy đổi ~4 ký tự/token (cùng
heuristic `app.py` đang dùng để hiển thị tốc độ sinh AI real-time). Đây là ước tính sơ
bộ (không phải `count_tokens` API chính xác), đủ để so sánh tương đối giữa các lựa
chọn cấu hình.

**Kịch bản 1 — Yêu cầu đơn giản 1 phòng ban** (VD: "Tính tải lạnh phòng 30m², 6 người"):
Supervisor định tuyến → Mechanical gọi tool → Mechanical trả lời → Reviewer duyệt →
Supervisor kết thúc (5 lượt gọi LLM, ~6.800 input + ~380 output token):

| Model | Chi phí / yêu cầu | Chi phí / 1.000 yêu cầu |
|---|---|---|
| Claude Haiku 4.5 | ~$0.0087 | ~$8.70 |
| Claude Sonnet 5 (giá ưu đãi) | ~$0.0174 | ~$17.40 |
| Claude Sonnet 5 (giá chuẩn) | ~$0.0261 | ~$26.10 |
| Claude Opus 5 | ~$0.0435 | ~$43.50 |

**Kịch bản 2 — Yêu cầu phức tạp QS** (đọc bản vẽ CAD + phân tích không gian + xuất
Excel dự toán): Supervisor → QS gọi `read_cad` → QS gọi `analyze_cad_spatial_context`
→ QS gọi `write_excel` → QS trả lời → Reviewer → Supervisor (7 lượt gọi LLM, ~11.900
input + ~640 output token — nặng hơn do dữ liệu CAD ~4KB được đọc vào context):

| Model | Chi phí / yêu cầu | Chi phí / 1.000 yêu cầu |
|---|---|---|
| Claude Haiku 4.5 | ~$0.0151 | ~$15.10 |
| Claude Sonnet 5 (giá ưu đãi) | ~$0.0303 | ~$30.30 |
| Claude Sonnet 5 (giá chuẩn) | ~$0.0454 | ~$45.40 |
| Claude Opus 5 | ~$0.0757 | ~$75.70 |

### Tác động thực tế của việc tách tool schema theo vai trò

So sánh Kịch bản 1 (HVAC) trên cùng Sonnet 5, **trước và sau** khi tách tool schema
theo vai trò (Mục "Đã tối ưu" bên dưới):

| | Chi phí / 1.000 yêu cầu |
|---|---|
| Trước (bind cả 39 tool cho mọi agent) | ~$668.80 |
| Sau (Mechanical chỉ nhận 17 tool liên quan) | ~$417.70 |
| **Tiết kiệm** | **~37.5%** |

### Dự phóng chi phí hàng tháng theo 3 chiến lược (Mục 3)

Giả định 50 yêu cầu/ngày, tỉ lệ 70% đơn giản (HVAC/Điện/Nước/PCCC) : 30% phức tạp
(QS/CAD) — mức dùng thử của một văn phòng tư vấn nhỏ:

| Chiến lược | Cấu hình | Chi phí ước tính/tháng |
|---|---|---|
| 3.1 Cân bằng | Sonnet 5 mặc định + Opus 5 cho QS/CAD | **~$52** |
| 3.2 Tối ưu chi phí | Groq (free tier) cho phần lớn + Opus 5 chỉ cho QS/CAD | **~$34** + Groq free tier |
| 3.3 Chất lượng tối đa | Toàn bộ Opus 5 | **~$80** |

Ở quy mô nhỏ (dưới ~1.500 yêu cầu/tháng), chênh lệch tuyệt đối giữa 3 chiến lược chỉ
vài chục USD — nên ưu tiên **Chiến lược 3.1 (Cân bằng)** làm mặc định, chỉ chuyển sang
3.2 khi traffic đủ lớn để phần chênh lệch có ý nghĩa, hoặc 3.3 khi dự án có yêu cầu độ
chính xác/pháp lý cao hơn mức tiết kiệm chi phí.

### Đã tối ưu: tool schema theo từng vai trò (giảm token)

Trước đây mỗi lượt gọi agent gửi kèm **toàn bộ 30+ tool schema** (`src/tools.py` →
`tools`) cho mọi vai trò, kể cả tool hoàn toàn không liên quan (VD: ElectricalAgent
vẫn nhận schema đọc/ghi CAD, tính PCCC...). `src/tools.py` giờ có `TOOLS_BY_ROLE` +
`get_tools_for_role(role)` để mỗi agent chỉ nhận đúng tool nó cần:

| Vai trò | Số tool trước | Số tool sau |
|---|---|---|
| Electrical / Firefighting / BIM | 39 | 10 |
| QS | 39 | 11 |
| Plumbing / CAD | 39 | 14 |
| Mechanical | 39 | 17 |

Cắt trực tiếp phần lớn input token của mỗi request đến LLM, áp dụng cho **mọi
provider** (không riêng Claude) vì đây là số lượng JSON schema gửi kèm request, không
phải tính năng riêng của Anthropic API. Supervisor/Reviewer không bị ảnh hưởng — hai
vai trò này vốn không bind tool nào (`with_structured_output` thuần túy).

*Trong lúc viết test cho thay đổi này, phát hiện thêm một bug: `search_standards` và
`calculate` được định nghĩa bằng `@tool` nhưng chưa từng có trong danh sách `tools`
toàn cục — nghĩa là dù mọi prompt phòng ban đều ghi "Luôn gọi tool `search_standards`",
LLM chưa bao giờ thực sự có tool đó trong tay để gọi. Đã bổ sung vào `tools` để tính
năng RAG tra cứu tiêu chuẩn hoạt động đúng như thiết kế.*

### Các tính năng giảm token khác (đặc thù Anthropic, chưa áp dụng)

Anthropic API còn có **prompt caching** (cache system prompt lặp lại giữa các lượt,
giảm ~90% chi phí phần được cache) và **tool search** (chỉ nạp schema tool khi cần thay
vì nạp hết ngay từ đầu). Hai tính năng này gắn với Anthropic API/SDK trực tiếp, còn dự
án dùng LangChain đa provider (openai/groq/gemini/anthropic/ollama) nên chưa tích hợp
để tránh làm phức tạp lớp trừu tượng provider hiện có — cân nhắc triển khai riêng nếu
sau này chuyển hẳn sang Claude làm provider chính. Đã ghi vào `MEPF_BACKLOG.md`.

## 7. Chế độ Offline hoàn toàn / Model AI yếu (Ollama, model nhỏ)

Mục tiêu của mục này: cho phép chạy **toàn bộ hệ thống không cần internet** (LLM cục bộ
qua Ollama) hoặc dùng **model AI yếu/nhỏ** (Groq free tier, `llama3.1:8b`,...) mà vẫn bóc
tách khối lượng và tối ưu bản vẽ đúng — bằng cách chuyển gánh nặng suy luận (đếm số, cộng
chiều dài, soạn JSON) từ LLM sang code Python xác định (deterministic), LLM chỉ cần biết
gọi đúng 1 tool.

### 7.1. Bóc tách khối lượng bằng 1 tool duy nhất: `auto_quantity_takeoff`

Trước đây, QS/BIM Agent phải tự: gọi `read_cad` → đọc kết quả text → tự đếm/tự cộng số
trong "đầu" → tự soạn chuỗi JSON đúng cú pháp cho `write_excel`. Đây chính là bước model
yếu hay sai nhất (soạn sai JSON, đếm nhầm, quên gọi `write_excel`).

`src/tools.py` → `auto_quantity_takeoff(file_path, output_excel_path)` gộp toàn bộ quy
trình đó thành **một lần gọi tool**, xử lý thuần bằng `ezdxf`/`math`/`pandas` (không dùng
LLM ở bước tính toán):
1. Audit làm sạch file CAD.
2. Đếm số lượng từng Block (thiết bị) theo tên + thuộc tính.
3. Cộng dồn chiều dài từng tuyến ống/dây theo Layer.
4. Liên kết Ghi chú văn bản (TEXT/MTEXT) với tuyến ống gần nhất (Spatial Matching) để đặt
   tên hạng mục đúng theo bản vẽ (ví dụ "Ống uPVC Ø110" thay vì tên layer kỹ thuật thô).
5. Ghi thẳng ra file Excel (STT, Hạng mục, Đơn vị, Khối lượng, Ghi chú).

QS/BIM Agent hiện được yêu cầu ưu tiên gọi tool này trước tiên (xem `src/agents.py`).

### 7.2. Tối ưu bản vẽ bằng 1 tool duy nhất: `optimize_cad_drawing`

Tương tự, `optimize_cad_drawing(file_path, output_path)` tự động dọn dẹp bản vẽ mà không
cần LLM tự phán đoán lỗi nào cần sửa: audit, xóa đối tượng chiều dài bằng 0, xóa Block
trùng lặp (cùng tên + cùng vị trí), xóa Layer rỗng. CAD Agent được yêu cầu gọi tool này khi
khách yêu cầu "tối ưu"/"dọn dẹp" bản vẽ.

### 7.3. Tra cứu tiêu chuẩn offline hoàn toàn (không cần OPENAI_API_KEY)

`search_standards` trước đây **luôn cần `OPENAI_API_KEY`** (dùng cho `OpenAIEmbeddings`
của FAISS), nên dù chọn `LLM_PROVIDER=ollama` để chạy offline, tool tra cứu tiêu chuẩn vẫn
gọi ra internet/API OpenAI. Giờ đây, nếu chưa cấu hình `OPENAI_API_KEY` hợp lệ hoặc chưa
chạy `ingest`, `search_standards` tự động rơi về `_offline_keyword_search` — so khớp từ
khóa (Jaccard, có bỏ dấu tiếng Việt) trên toàn bộ nội dung `data/standards/*.txt`, không
gọi mạng, không cần model embedding nào. Kết quả kém chính xác hơn vector search ngữ
nghĩa nhưng đảm bảo tính năng vẫn hoạt động ở chế độ 100% offline.

### 7.4. Cấu hình khuyến nghị cho offline hoàn toàn (Ollama)

```env
LLM_PROVIDER=ollama
MODEL_NAME=llama3.1:8b
```

Không cần đặt bất kỳ `*_API_KEY` nào. Chạy Ollama cục bộ (`ollama serve`, đã `ollama pull
llama3.1:8b`), sau đó `uv run streamlit run app.py` — mọi bước LLM (định tuyến, sinh câu
trả lời, review) lẫn tra cứu tiêu chuẩn, bóc khối lượng, tối ưu bản vẽ đều chạy được
không cần internet. Cân nhắc nâng riêng vai trò `QS`/`CAD`/`REVIEWER` lên provider cloud
(xem Mục 3.2) nếu model local quá yếu để tuân thủ chuỗi tool-calling ổn định.

## 8. Câu hỏi thường gặp

**Q: Nếu chỉ đặt `QS_MODEL_NAME` mà không đặt `QS_LLM_PROVIDER` thì sao?**
A: `QS_LLM_PROVIDER` sẽ rơi về `LLM_PROVIDER` toàn cục. Chỉ cần đặt provider riêng khi
vai trò đó dùng **provider khác** với mặc định toàn cục.

**Q: Có thể dùng model Claude khác (Fable 5, Opus 4.8...) không?**
A: Có — chỉ cần đặt đúng model ID vào biến `MODEL_NAME`/`<ROLE>_MODEL_NAME`
(ví dụ `claude-fable-5`). Hệ thống không giới hạn danh sách model, chỉ tự động chọn
`claude-sonnet-5` làm mặc định khi bỏ trống.

**Q: Đổi model có cần khởi động lại server không?**
A: Không — `.env` được nạp lại (`load_dotenv(override=True)`) ở đầu mỗi lượt gọi
`get_llm()`, nên chỉ cần sửa `.env` và gửi tin nhắn mới trong Streamlit.

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

Vì mỗi lượt gọi agent hiện đang gửi kèm **toàn bộ 30+ tool schema** (`src/tools.py` →
`tools`) cho mọi vai trò — kể cả những agent không dùng đến phần lớn tool đó — chi phí
input token sẽ cao hơn mức tối thiểu cần thiết. Đây là khoản tối ưu tiềm năng cho đợt
sau (tách tool set theo từng agent thay vì dùng chung danh sách `tools` toàn cục),
chưa nằm trong phạm vi tài liệu này — đã ghi vào `MEPF_BACKLOG.md`.

## 7. Câu hỏi thường gặp

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

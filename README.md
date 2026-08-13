# MEP-Agents — Văn phòng Tư vấn Thiết kế MEPF tự động (Multi-Agent)

Hệ thống Multi-Agent mô phỏng một **văn phòng tư vấn thiết kế MEPF** hoàn chỉnh: Giám đốc
Dự án điều phối 7 bộ phận chuyên môn, Kỹ sư trưởng kiểm duyệt đầu ra, và toàn bộ phép tính
kỹ thuật được thực hiện bằng **code Python xác định** thay vì để LLM tự suy đoán con số.

Xây dựng bằng **LangGraph**, giao diện **Streamlit**, theo nguyên tắc
[12-Factor Agents](https://github.com/humanlayer/12-factor-agents).

## Các bộ phận (Agents)

| Bộ phận | Vai trò | Tool tiêu biểu |
|---|---|---|
| **Supervisor** | Giám đốc Dự án — phân việc, điều phối nhiều bước | (định tuyến) |
| **Mechanical** | HVAC: tải lạnh, ống gió, chiller/AHU, thông gió, **tiếng ồn NC** | `calc_cooling_load_detailed`, `calc_duct_total_pressure_loss`, `calc_nc_level` |
| **Electrical** | Điện: cáp (**có kiểm tra sụt áp**), aptomat, chiếu sáng, **phụ tải, ngắn mạch, máng cáp, chống sét, bảng tủ điện** | `calc_cable_size`, `calc_voltage_drop`, `calc_total_load`, `calc_short_circuit`, `calc_cable_tray_size`, `calc_lightning_protection`, `generate_panel_schedule` |
| **Plumbing** | Cấp thoát nước, bể, bơm, nước nóng | `calc_water_pipe`, `calc_plumbing_pump_head` |
| **Firefighting** | PCCC: **thủy lực sprinkler**, bơm chữa cháy (Q và H), **họng nước, kiểm soát khói, đầu báo cháy** | `calc_sprinkler_hydraulics`, `calc_fire_pump`, `calc_standpipe`, `calc_smoke_control`, `calc_fire_detector_qty` |
| **QS** | Bóc khối lượng + **lập dự toán có giá trị tiền + BOQ mẫu Việt Nam** | `auto_quantity_takeoff`, `calc_boq_cost`, `export_boq_vietnam`, `lookup_unit_price` |
| **CAD** | Đọc/sửa/tối ưu (**Overkill + Purge**)/**chuẩn hóa** bản vẽ, **chú thích quy chuẩn màu**, phục hồi Block, render ảnh, **theo dõi revision** | `edit_cad`, `optimize_cad_drawing`, `standardize_cad_drawing`, `add_color_legend`, `snapshot_cad`, `diff_cad_revisions`, `restore_cad_revision` |
| **BIM** | Mô hình 3D và **kiểm tra xung đột giữa các hệ (kể cả theo bề dày ống/gió)** | `detect_clashes`, `auto_quantity_takeoff` |
| **Reviewer** | Kỹ sư trưởng — kiểm duyệt, bắt làm lại nếu chưa đạt | (guardrail) |

## Đặc điểm thiết kế

- 🧮 **Tính toán xác định, không để LLM đoán số**: mọi công thức kỹ thuật nằm trong
  `src/hvac_tools.py`, `elec_tools.py`, `plumb_tools.py`, `ff_tools.py`, `qs_tools.py`,
  `bim_tools.py`. Model AI chỉ chọn tool và diễn giải kết quả.
- 🤖 **Chạy được với model yếu / offline**: các tác vụ nặng (`auto_quantity_takeoff`,
  `optimize_cad_drawing`, `detect_clashes`) gom cả pipeline vào **một lần gọi tool duy
  nhất**, không đòi LLM tự đếm hay tự soạn JSON. `search_standards` có fallback tra cứu
  từ khóa offline khi không có API key. Xem `AI_MODEL_SETUP.md`.
- 🛡️ **Guardrail có hạn mức**: Reviewer kiểm duyệt thật ở **mọi** lần thử; hết
  `MAX_REVIEW_RETRIES` thì dừng và nói rõ "CHƯA ĐẠT" thay vì giả vờ phê duyệt.
- 💾 **Bộ nhớ bền vững**: checkpoint hội thoại ghi xuống SQLite (`CHECKPOINT_DB`), sống
  sót qua restart. Đặt rỗng để quay về RAM.
- 🔒 **Cô lập theo phiên**: mỗi phiên Streamlit có workspace riêng, mọi thao tác file bị
  chặn path traversal (`src/workspace.py`).
- 💰 **Đo token & chi phí thật** theo từng vai trò, lấy từ `usage_metadata` của nhà cung
  cấp (`src/usage.py`) — không phải ước lượng.
- 🎛️ **Mỗi vai trò một model riêng**: `CAD_MODEL_NAME`, `REVIEWER_LLM_PROVIDER`, ... để
  cân đối chất lượng/chi phí. Tool schema cũng được cắt theo vai trò để giảm token.
- 💸 **Tối ưu chi phí Anthropic**: prompt caching tự động cho phần system prompt cố định
  (phần thay đổi mỗi lượt được tách ra sau để không phá cache); tool search beta bật được
  bằng `ANTHROPIC_TOOL_SEARCH=true`.
- 🕓 **Không mất bản gốc bản vẽ**: mọi tool sửa CAD tự lưu revision trước khi ghi đè, có
  `diff_cad_revisions` và `restore_cad_revision` để xem thay đổi và quay lui. Mặc định giữ
  **3 phiên bản gần nhất** cho mỗi bản vẽ (`MAX_CAD_REVISIONS`, đặt 0 để giữ tất cả) —
  mỗi phiên bản là một bản sao `.dxf` đầy đủ nên không giới hạn sẽ phình workspace.
- 🧭 **Chuẩn hóa Layer/Block bản vẽ khách đẩy vào**: `standardize_cad_drawing` đối chiếu
  với bảng tiêu chuẩn nội bộ (`src/cad_standards.py`) để tự đổi tên Layer (kèm sửa màu),
  đổi tên Block, và gắn thuộc tính MA_HIEU/MO_TA — chỉ sửa đặt tên/thuộc tính, không đụng
  hình học. Bảng tiêu chuẩn theo quy ước tên `<HỆ>-<NHÓM>[-<PHÂN LOẠI>]`, phủ đủ đường
  ống LẪN thiết bị của 4 hệ: **Mechanical** (ống gió SAD/RAD/FAD/EAD/KEAD/PAD/SEAD, ống
  đồng gas lạnh, ống nước ngưng, ống nước lạnh Chiller cấp/hồi CHWS/CHWR, thiết bị
  AHU/FCU/VRV/Chiller/Tháp giải nhiệt/Bơm/Quạt), **Electrical** (đèn thường/đèn sự cố, ổ
  cắm, máng cáp/trunking, ống luồn dây, tủ điện, máy phát điện+ATS, máy biến áp, tủ bù
  công suất, chống sét, ELV data/CCTV/kiểm soát vào ra), **Plumbing** (cấp nước lạnh/nóng
  sinh hoạt, hồi nước nóng, thoát nước thải/thông hơi/nước mưa, thiết bị Bơm/Bể/Bình nóng
  lạnh/Trạm xử lý nước thải), **Firefighting** (Sprinkler, họng nước vách tường/trụ cứu
  hỏa, đầu báo/chuông còi báo cháy, chữa cháy khí, bình chữa cháy, thiết bị Bơm chữa
  cháy/Bể nước chữa cháy/Van điều khiển). Mỗi hệ M/E/P/F có MỘT dải màu (hue) riêng biệt
  không trùng với hệ khác — Mechanical=xanh lá, Electrical=cam/vàng, Plumbing=xanh dương,
  Firefighting=đỏ — để nhìn màu là đoán ngay ra hệ, không còn kiểu mượn màu chéo hệ như
  trước (VD "nóng = đỏ" từng dùng chung cho cả ống nước nóng Plumbing lẫn PCCC). Toàn bộ
  mã màu được xác minh bằng `ezdxf.colors.aci2rgb()` để đảm bảo không có 2 mã ACI khác
  nhau nhưng ra cùng 1 màu RGB thật. Thiết bị chính của cả 3 hệ M/P/F dùng chung màu xám
  trung tính (ngoại lệ có chủ đích, vì thiết bị đã có Block/nhãn riêng để nhận diện).
  Lưu ý: đây KHÔNG phải "Block động" (Dynamic Block) kiểu AutoCAD Block Editor —
  Visibility State/Parameter/Action là định dạng nhị phân độc quyền của Autodesk mà thư
  viện `ezdxf` không hỗ trợ ghi; muốn dùng Block động thật sự phải vẽ tay 1 lần trong
  AutoCAD/BricsCAD rồi đưa vào `data/blocks/mepf_library.dxf`, hệ thống sẽ tự copy/chèn
  lại (giữ nguyên tính năng động) chứ không tự tạo mới được.
- 🎨 **Chú thích quy chuẩn màu ngay trên bản vẽ**: `add_color_legend` vẽ trực tiếp một
  bảng legend (ô màu SOLID + tên Layer + mô tả + tên màu) liệt kê toàn bộ quy chuẩn màu
  của `src/cad_standards.py` lên layer riêng `G-LEGEND`, tự đặt bên phải vùng vẽ hiện có
  để không đè hình học gốc — dùng sau `standardize_cad_drawing` để hồ sơ nộp có ghi chú
  quy chuẩn ngay trên bản vẽ, không cần tra tài liệu rời. Chỉ 9 màu ACI cơ bản (1-9) có
  tên tiếng Việt chuẩn hóa (`cad_standards.color_name`); màu mở rộng (>9, dùng cho các
  hệ ELV/báo cháy cần nhiều màu phân biệt) ghi rõ "ACI \<n\>" thay vì đoán tên màu sai.
- ⚡ **Clash detection xét cả bề dày ống/gió, không chỉ đường tâm**: `detect_clashes`
  trước đây chỉ báo xung đột khi đường TÂM hai tuyến cắt nhau — bỏ sót trường hợp phổ
  biến nhất trong thực tế: hai tuyến chạy song song sát nhau, đường tâm không hề giao
  nhau nhưng đường kính/kích thước thật (ống Ø, ống gió WxH) khiến chúng chồng lấn vật
  lý. Nay tool suy bán kính/nửa bề rộng mỗi tuyến từ ghi chú kích thước gần nhất trên
  bản vẽ (TEXT/MTEXT dạng "Ø110", "DN100", "600x400") và báo thêm loại xung đột
  "Chồng lấn theo bề dày ống/gió" khi khoảng cách đường tâm nhỏ hơn tổng bán kính hai
  bên — vẫn tôn trọng cao độ Z thật nếu có khai báo. Tuyến không có ghi chú kích thước
  gần đó CHỈ được xét theo đường tâm (không đoán bừa kích thước để tránh báo động giả);
  số lượng đoạn thiếu dữ liệu này được liệt kê rõ trong báo cáo.
- 🧹 **Overkill + Purge tự động**: `optimize_cad_drawing` nay còn xóa LINE/LWPOLYLINE
  trùng lặp/chồng đè hình học hoàn toàn (Overkill — lỗi thường gặp khi trace lại nét cũ)
  và xóa Block định nghĩa/text style/linetype không còn được tham chiếu (Purge, tương
  đương lệnh PURGE của AutoCAD), bên cạnh audit lỗi + xóa entity chiều dài 0 + Block
  trùng vị trí đã có trước đó — tất cả trong một lần gọi tool duy nhất.

## Cấu trúc thư mục

```
app.py                  # Giao diện Streamlit (chat, xem Excel, render CAD, bảng token)
main.py                 # Chạy CLI tương tác
src/
  graph.py              # Đồ thị LangGraph + checkpointer + recursion limit
  agents.py             # Supervisor, 7 agent chuyên môn, Reviewer
  state.py              # AgentState và các reducer
  config.py             # Cấu hình tập trung (pydantic-settings)
  tools.py              # Registry tool + tool CAD/file/RAG dùng chung
  hvac_tools.py         # Tính toán HVAC
  elec_tools.py         # Tính toán Điện (kèm kiểm tra sụt áp)
  plumb_tools.py        # Tính toán Cấp thoát nước
  ff_tools.py           # Tính toán PCCC (Q và H bơm chữa cháy)
  qs_tools.py           # Tra đơn giá, lập dự toán BOQ, xuất mẫu BOQ Việt Nam
  panel_schedule.py     # Bảng tủ điện (Excel) + sơ đồ nguyên lý một sợi (DXF)
  bim_tools.py          # Clash detection
  cad_revision.py       # Snapshot / diff / restore phiên bản bản vẽ CAD
  usage.py              # Đo token/chi phí theo vai trò
  workspace.py          # Cô lập workspace theo phiên + chống path traversal
  ingest.py             # Nạp tiêu chuẩn vào FAISS cho RAG
data/
  standards/            # Kho tiêu chuẩn cho RAG (TCVN Điện/PCCC/Cấp thoát nước, ASHRAE)
  unit_prices.csv       # CSDL đơn giá vật tư/nhân công/máy — SỬA GIÁ Ở ĐÂY
  blocks/               # Thư viện Block MEPF chuẩn
tests/                  # Test suite (pytest) — 551 test
```

## Cài đặt và chạy

Dự án dùng `uv`.

```bash
# 1. Cấu hình
cp .env.example .env      # rồi điền API key

# 2. (Tùy chọn) Nạp tiêu chuẩn cho RAG — cần OPENAI_API_KEY
uv run python -m src.ingest

# 3. Chạy giao diện web
uv run streamlit run app.py

# Hoặc chạy CLI
uv run main.py

# Chạy test
uv run pytest -q
```

## Lập dự toán (BOQ)

Quy trình đầy đủ từ bản vẽ tới con số tiền:

1. Tải file `.dxf` lên qua sidebar.
2. Giao việc: *"Bóc khối lượng và lập dự toán bản vẽ tang1.dxf"*.
3. QS Agent chạy `auto_quantity_takeoff` → file Excel khối lượng, rồi `calc_boq_cost` →
   file Excel dự toán gồm chi phí trực tiếp, chi phí chung, thu nhập chịu thuế tính
   trước, VAT và tổng giá trị (cấu trúc theo Thông tư 11/2021/TT-BXD).
4. Cần bảng nộp thầu: `export_boq_vietnam` định dạng lại thành bảng tiên lượng — dự toán
   gom theo chương mục từng hệ (A. HVAC, B. Điện, C. Cấp thoát nước, D. PCCC), có tiểu
   tổng từng chương và trang bìa công trình.

**Đơn giá nằm ở `data/unit_prices.csv`** — hãy cập nhật theo thời điểm và theo vùng trước
khi dùng cho hồ sơ thật. Hạng mục không tra được đơn giá sẽ được liệt kê kèm cảnh báo
"CHƯA CÓ ĐƠN GIÁ" chứ không bị bỏ qua âm thầm.

## Giám sát bằng LangSmith (Observability)

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxx
LANGCHAIN_PROJECT=x_agents_project
```

Toàn bộ "suy nghĩ", thời gian thực thi và lỗi của từng tác nhân sẽ được vẽ trực quan tại
[smith.langchain.com](https://smith.langchain.com/).

## Tài liệu khác

- [`docs/TIEN_DO_DU_AN.md`](docs/TIEN_DO_DU_AN.md) — **trạng thái dự án hiện tại**: số
  liệu, các Phase đã hợp nhất, việc còn nợ, đề xuất việc tiếp theo. Đọc file này trước.
- [`AI_MODEL_SETUP.md`](AI_MODEL_SETUP.md) — chọn model theo vai trò, chế độ offline, chi phí.
- [`TECH_DEBT.md`](TECH_DEBT.md) — nợ kỹ thuật: cái gì chưa làm và **vì sao chưa làm được**.
- Tài liệu từng Phase: [`README_PHASE_A.md`](README_PHASE_A.md) (skill CAD/QS),
  [`README_PHASE_B.md`](README_PHASE_B.md) (workflow, HIL),
  [`README_PHASE_C.md`](README_PHASE_C.md) (Postgres/S3/JWT),
  [`README_PHASE_D.md`](README_PHASE_D.md) (tìm kiếm lai, song song hóa).
- [`docs/E2E.md`](docs/E2E.md) — kiểm thử end-to-end: tầng chạy trong CI và tầng chạy với hạ tầng thật (Redis + worker + API).
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — Docker, docker-compose kèm Ollama, systemd VPS, Streamlit Cloud.
- [`MEPF_BACKLOG.md`](MEPF_BACKLOG.md) — lịch sử backlog tính năng (đã xử lý hết) và tool tương ứng.
- [`docs/AUDIT_BOC_KHOI_LUONG.md`](docs/AUDIT_BOC_KHOI_LUONG.md) — hồ sơ rà soát sai lệch bản vẽ → khối lượng: 19 nguồn đã xử lý, chỗ đã rà sạch, chỗ cố ý không sửa, kiểm kê hằng số.
- [`docs/PROMPT_RA_SOAT_SAI_LECH.md`](docs/PROMPT_RA_SOAT_SAI_LECH.md) — quy trình/prompt rà soát sai lệch dữ liệu, dùng lại được cho dự án khác.
- [`Agentic.md`](Agentic.md) — lộ trình phát triển hệ thống Agentic.

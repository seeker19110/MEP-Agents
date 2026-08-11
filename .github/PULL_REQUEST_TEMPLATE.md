## Tóm tắt

<!-- Mô tả ngắn gọn PR này làm gì và tại sao cần thay đổi này. -->

## Thay đổi chính

<!-- Liệt kê các thay đổi quan trọng, nhóm theo chủ đề nếu PR lớn. Ví dụ: -->
- [ ] Sửa lỗi: ...
- [ ] Tính năng mới: ...
- [ ] Refactor / dọn dẹp: ...
- [ ] Cập nhật tài liệu: ...

## Ảnh hưởng / Rủi ro

<!-- PR này có ảnh hưởng tới luồng agent (Supervisor/Reviewer), file tools (đọc/ghi
Excel, CAD, Word...), hay cấu hình (.env, provider LLM) không? Có thay đổi hành vi
mà người dùng hiện tại cần biết không? -->

## Test plan

<!-- Cách đã kiểm tra thay đổi này. Đánh dấu các mục đã thực hiện. -->
- [ ] `uv run pytest -q`
- [ ] `python -m py_compile app.py main.py src/*.py`
- [ ] Chạy thử `streamlit run app.py` và kiểm tra luồng chat/tool liên quan
- [ ] Test thủ công với ít nhất 1 provider LLM thật (OpenAI/Groq/Gemini/Ollama)

## Ghi chú khác

<!-- Bất kỳ thông tin nào khác người review cần biết (breaking change, cần chạy
migration, cần thêm biến môi trường mới trong .env, v.v.) -->

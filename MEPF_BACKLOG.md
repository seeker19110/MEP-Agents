# Backlog tính năng MEPF (chưa triển khai)

Ghi lại các đề xuất tối ưu đã thảo luận nhưng **chưa** đưa vào vòng triển khai hiện tại
(vòng hiện tại: 4 tool HVAC + 4 tool Cấp thoát nước, xem `src/hvac_tools.py` /
`src/plumb_tools.py`). Giữ danh sách này để không thất lạc, ưu tiên xử lý ở các đợt sau.

## HVAC (Cơ khí)
- [ ] **Kiểm tra tiếng ồn (NC level)** cho miệng gió/quạt — chưa có tool, cần cho phòng
  yêu cầu yên tĩnh (phòng họp, phòng ngủ, studio...).

## Điện
- [ ] **Kiểm tra sụt áp (voltage drop)** theo chiều dài cáp — `calc_cable_size` hiện chỉ
  tính theo dòng điện, bỏ qua chiều dài dây, trong khi TCVN yêu cầu kiểm tra %sụt áp.
- [ ] **Chống sét & tiếp địa** (lightning protection / grounding) — chưa có tool nào dù
  đây là hạng mục phổ biến trong scope Điện MEPF.
- [ ] **Tổng hợp phụ tải & hệ số đồng thời** để chọn máy biến áp/máy phát.
- [ ] **Dòng ngắn mạch & phối hợp bảo vệ** (short-circuit + selectivity giữa các cấp
  aptomat).
- [ ] **Xuất bảng tủ điện / sơ đồ nguyên lý** (panel schedule / single-line diagram).
- [ ] **Tính máng cáp / ống luồn dây** (cable tray & conduit sizing).

## PCCC
- [ ] **Tính thủy lực mạng đầu phun sprinkler** (pressure/flow tại từng đầu phun theo
  mạng đường ống) — hiện `calc_sprinkler_qty` chỉ ước tính theo diện tích bao phủ, chưa
  phải tính thủy lực thật.
- [ ] **Họng nước vách tường / standpipe**.
- [ ] **Cột áp bơm PCCC (H)** — `calc_fire_pump` hiện chỉ trả về lưu lượng (Q), thiếu cột
  áp nên chưa đủ dữ liệu để chọn bơm thực tế (cần cả Q và H, tương tự
  `calc_plumbing_pump_head` bên Nước).
- [ ] **Quạt tăng áp / hút khói theo QCVN 06** — có thể tái dùng `calc_ventilation_rate`
  nhưng cần logic riêng theo quy chuẩn PCCC (áp suất dương cầu thang, tốc độ hút khói...).
- [ ] **Số lượng đầu báo khói/nhiệt** (fire alarm detector spacing).

## QS (Lập dự toán)
- [ ] **CSDL đơn giá vật tư/nhân công + tool tính giá trị dự toán** (khối lượng × đơn
  giá) — gap lớn nhất: hiện QS chỉ đếm khối lượng, chưa phải "dự toán" đúng nghĩa.
- [ ] **Xuất BOQ theo mẫu chuẩn Việt Nam** (định dạng bảng tổng hợp khối lượng quen
  thuộc với hồ sơ thầu).

## BIM
- [ ] **Clash detection** — kiểm tra xung đột hình học giữa các hệ thống (ống, gió,
  cáp...) trong file CAD/DXF. Prompt của `bim_agent_node` đã nói "kiểm tra xung đột"
  nhưng chưa có tool thực hiện việc này.

## Khác (cross-cutting)
- [ ] Mở rộng CSDL tiêu chuẩn cho RAG — hiện `data/standards/` chỉ có 2 file mẫu
  (`ashrae_hvac.txt`, `tcvn_mau.txt`), tra cứu tiêu chuẩn còn rất mỏng.
- [ ] Theo dõi phiên bản/revision bản vẽ CAD giữa các lần chỉnh sửa.

# Hồ sơ rà soát sai lệch: bản vẽ → bóc khối lượng

Ghi lại kết quả đợt rà soát tại PR #22 (6 đợt, 19 nguồn) và bộ test bất biến bổ sung sau đó (thêm 3 nguồn). Mục đích của file này
là để **lần rà sau không phải làm lại từ đầu**: biết chỗ nào đã rà sạch, chỗ nào cố ý
không sửa và vì sao, chỗ nào còn nợ.

Quy trình dùng cho đợt này: [`PROMPT_RA_SOAT_SAI_LECH.md`](PROMPT_RA_SOAT_SAI_LECH.md).

## Nguyên tắc đã chốt (áp dụng cho mọi thay đổi sau này)

1. **Không tự đổi con số dựa trên phỏng đoán.** Nếu phép tự sửa có mặt trái đối xứng —
   sửa đúng thì lợi, sửa nhầm thì gây sai lệch ngược lại và âm thầm — thì chỉ CẢNH BÁO
   và đưa quyền quyết định cho kỹ sư qua một tham số tùy chọn.
2. **Mặc định giữ nguyên hành vi cũ.** Tham số mới (`drawing_unit`, `mep_only`) đều tùy
   chọn.
3. **Mọi thay đổi làm đổi con số phải được nêu trong chính báo cáo của tool**, không đổi
   lặng lẽ.
4. **Bóc thiếu âm thầm nguy hiểm hơn bóc thừa có cảnh báo.** Khi phải chọn, giữ lại dòng
   và đánh dấu, chứ không tự loại.

## 22 nguồn sai lệch đã xử lý

| # | Nguồn sai lệch | Hậu quả | Nơi sửa |
|---|---|---|---|
| 1 | Đơn vị bản vẽ chỉ cảnh báo, không quy đổi | Bản vẽ mét: sai 1000 lần | `cad_units.py` |
| 2 | Ống/dây vẽ trong Block bị bỏ qua | Thiếu 100% phần trong block | `cad_geometry.explode_insert` |
| 3 | MINSERT đếm là 1 thiết bị | Thiếu cả dàn đèn/đầu phun | `cad_geometry.insert_repeat_count` |
| 4 | SPLINE/ELLIPSE không đo được | Thiếu trọn vẹn tuyến cong | `cad_geometry._curve_segments` |
| 5 | Lưới 3D đếm thành ống | Thừa con số vô nghĩa | `cad_geometry.entity_segments` |
| 6 | Tọa độ OCS đọc như WCS | Tuyến sai vị trí → gán nhầm ghi chú | `cad_geometry._to_wcs` |
| 7 | Block động ra tên `*U12` | Một chủng loại xé nhiều dòng | `cad_geometry.effective_block_name` |
| 8 | Nền kiến trúc vào dự toán | Thừa tường, trục, đường kích thước | cột `Hệ` trong `qs_tools` |
| 9 | Tuyến vẽ 2 nét song song | Chiều dài tính đôi | `cad_geometry.detect_double_line_runs` |
| 10 | Mỗi mắt đường cong = một cái co | Một spline ra 1654 cái co | `cad_geometry._curve_segments` |
| 11 | Măng sông chỉ đếm đoạn > 1 cây ống | Tuyến 100 m ra 0 mối nối | `cad_geometry._connected_run_lengths` |
| 12 | Thiết bị khác mã hiệu tách từng dòng | 500 đèn ra 500 dòng "1 Bộ" | `qs_tools.aggregate_block_attributes` |
| 13 | MTEXT/TEXT giữ mã định dạng CAD | Tên rác + mất đơn giá | `cad_geometry.plain_entity_text` |
| 14 | Nhãn kích thước trong thuộc tính Block bị bỏ | Hạng mục giữ tên layer thô | `qs_tools.auto_quantity_takeoff` |
| 15 | Layer khác tên cùng một loại tuyến | Khối lượng xé nhiều dòng | cảnh báo trong `qs_tools` |
| 16 | BOQ xếp nhầm chương mục | Ống gió vào "HẠNG MỤC KHÁC" | `qs_tools.classify_boq_group` |
| 17 | 4 chỗ tạo DXF khai sai đơn vị | File tự ghi đọc lại sai 1000 lần | `tools.py`, `panel_schedule.py`, `create_library.py` |
| 18 | Thư viện block khai 600×600 **mét** | Sai lan sang mọi bản vẽ dùng nó | `data/blocks/mepf_library.dxf` |
| 19 | Luồng Revit thiếu cột `Hệ` | Hai luồng hết đối chiếu được | `qs_tools._revit_system` |
| 20 | ELLIPSE nằm nghiêng đo ra 0 m | Thiếu trọn vẹn tuyến ellipse | `cad_geometry._curve_span` |
| 21 | Ngưỡng lọc nét ký hiệu không áp cho block lồng | Thừa nét ký hiệu trong block lồng | `cad_geometry.explode_insert` |
| 22 | SPLINE định nghĩa bằng fit points ra kích thước 0 | Thiếu (chỉ lộ khi refactor) | `cad_geometry._curve_span` |

Test tương ứng: `tests/test_takeoff_units_and_blocks.py`,
`test_takeoff_curve_and_block_naming.py`, `test_takeoff_system_and_double_line.py`,
`test_takeoff_fittings_and_labels.py`, `test_takeoff_invariants.py`.

## Đã rà, KHÔNG có lỗi — lần sau khỏi rà lại

- **Entity không đo được**: HATCH, SOLID, 3DFACE, POINT, DIMENSION đều đóng góp đúng
  0 m, không gây bóc thừa. (DIMENSION dựng hình trong block ẩn danh `*D…` nhưng block đó
  không được chèn ở modelspace nên không lọt vào phép đo.)
- **Luồng Revit**: plugin quy đổi feet → mm (×304.8) và `build_revit_boq_excel` chia
  1000 — khớp nhau, không có lỗi đơn vị.
- **Downstream đọc Excel**: `calc_boq_cost` và `export_boq_vietnam` đều dò cột theo TÊN
  nên việc thêm cột `Hệ` không làm vỡ chúng.
- **Chuỗi đầy đủ** `auto_quantity_takeoff` → `calc_boq_cost` → `export_boq_vietnam` đã
  chạy thông trên bản vẽ có đủ ống nước, ống gió, máng cáp, đèn và nền kiến trúc.

## Bài học: bất biến và test theo ca là hai lưới khác nhau, cần cả hai

Khi sửa nguồn #20, tôi refactor `_curve_span` và vô tình làm SPLINE dạng fit points ra
kích thước 0 (nguồn #22). **Toàn bộ 10 test bất biến vẫn pass** — vì spline đo 0 m ở cả
bản vẽ gốc lẫn bản vẽ đã xoay, nên bất biến "xoay không đổi kết quả" vẫn đúng. Thứ bắt
được lỗi là test theo ca cụ thể (`test_spline_route_is_measured`, kỳ vọng đúng 8.0 m).

Bất biến kiểm tra tính NHẤT QUÁN, không kiểm tra tính ĐÚNG: một cài đặt sai đều nhau ở
mọi phía vẫn thoả mãn mọi bất biến. Test theo ca neo kết quả vào một con số tính tay
được. Bỏ loại nào cũng để lọt một lớp lỗi.

## Cân nhắc nhưng KHÔNG làm — kèm lý do

Bốn chỗ có thể "sửa cho gọn" bằng máy. Cả bốn đều bị bác vì cùng một lý do: phép tự sửa
có mặt trái đối xứng, sửa nhầm sẽ gây bóc thiếu âm thầm.

| Đề xuất | Vì sao không làm |
|---|---|
| Tự chia đôi tuyến 2 nét song song | Hai tuyến riêng biệt chạy song song sát nhau (cấp và hồi cùng trục) trông y hệt hai mép một ống — trừ nhầm là bóc thiếu đúng một nửa |
| Tự gộp layer cùng tên chuẩn | `match_layer` quy cả `ONG_CAP_NUOC_NONG` về cùng khóa với nước lạnh — gộp máy móc là trộn hai loại ống khác hẳn nhau |
| Tự đoán đơn vị bản vẽ Unitless | Suy đoán sai sẽ nhân/chia khối lượng cả nghìn lần, nguy hiểm hơn con số cũ mà kỹ sư đã quen kiểm tra |
| Cảnh báo hình học trong paperspace | Khung tên của mọi hồ sơ thật đều là LINE ở paperspace → kêu trên gần như mọi bản vẽ, nhiễu nhiều hơn giá trị |

## Kiểm kê hằng số — mỗi con số là một giả định

Rà lại bảng này mỗi khi đổi logic hình học. Cột cuối là điều kiện làm giả định vỡ.

| Hằng số | Giá trị | Ở đâu | Giả định / vỡ khi nào |
|---|---|---|---|
| `JOINT_TOLERANCE` | 1.0 | `cad_geometry` | Sai số coi như trùng điểm; đã đổi theo đơn vị bản vẽ khi dùng trong takeoff |
| `ELBOW_MIN_ANGLE_DEG` | 15.0 | `cad_geometry` | Dưới ngưỡng là vertex chia nhỏ, không phải co. Tuyến uốn thoải nhiều đoạn có thể bị bỏ sót co |
| `DEFAULT_PIPE_STOCK_LENGTH` | 6000 | `cad_geometry` | Cây ống 6 m. Ống cỡ lớn/vật liệu khác bán theo cây khác |
| `_CURVE_FLATTENING_RATIO` | 0.001 | `cad_geometry` | Sai số phình 0.1% kích thước bao đường cong |
| `DEFAULT_DOUBLE_LINE_MAX_WIDTH` | 2000 | `cad_geometry` | Bề rộng ống gió tối đa; ống lớn hơn sẽ không bị bắt là 2 nét |
| `_DOUBLE_LINE_MIN_OVERLAP_RATIO` | 0.6 | `cad_geometry` | Tỷ lệ chồng nhau tối thiểu của hai mép ống |
| `_PARALLEL_ANGLE_TOLERANCE_DEG` | 2.0 | `cad_geometry` | Sai lệch góc coi là song song |
| `max_depth` (explode_insert) | 8 | `cad_geometry` | Chặn block tự tham chiếu vòng; block lồng sâu hơn 8 tầng bị bỏ |
| `_PLAUSIBLE_EXTENT_M` | (2, 5000) | `cad_units` | Kích thước bao hợp lý của một mặt bằng, dùng để GỢI Ý đơn vị (không tự áp) |
| `_AMBIGUITY_RATIO` | 1.3 | `qs_tools` | Ghi chú nằm giữa hai hệ thì coi là mơ hồ |
| ngưỡng tuyến trong block | 1000 mm | `qs_tools` | Dưới ngưỡng coi là nét vẽ ký hiệu, không phải tuyến |

## Còn nợ — việc nên làm ở đợt sau

1. ~~**Bộ test bất biến**~~ — ĐÃ LÀM: `tests/test_takeoff_invariants.py` (10 test phủ 5
   nhóm bất biến: đơn vị, phép dời hình, lồng/phẳng, cộng tính, lũy đẳng). Ngay lần chạy
   đầu đã bắt được **nguồn #20 và #21** — cả hai đều là lỗi "sai âm thầm" mà 6 đợt rà thủ
   công trước đó không thấy.
2. **Đo coverage** phần `cad_geometry` / `qs_tools` để tìm nhánh chưa bao giờ chạy.
3. **Chạy trên hồ sơ thật của khách** (đợt này mới chỉ chạy dữ liệu tổng hợp và file
   thư viện block của chính dự án).
4. **Mở rộng `BLOCK_STANDARD`**: nhiều tên block thông dụng chưa khớp (VD `DEN_LED_600`),
   nên bị đánh `CHƯA XÁC ĐỊNH HỆ` dù rõ ràng là thiết bị điện.
5. **Category `Pipes` và `Mechanical Equipment` của Revit** hiện để `CHƯA XÁC ĐỊNH HỆ` —
   đúng về mặt trung thực (Revit không phân biệt được), nhưng nếu payload có thêm trường
   hệ thống thì nên dùng.

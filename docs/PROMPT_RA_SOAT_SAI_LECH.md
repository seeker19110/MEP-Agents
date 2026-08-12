# Prompt rà soát sai lệch dữ liệu (dùng lại cho dự án khác)

Prompt này được rút ra từ đợt rà soát luồng **bản vẽ CAD → bảng bóc khối lượng** của
MEP-Agents (PR #22, 19 nguồn sai lệch qua 6 đợt). Nó viết theo cách trung lập với lĩnh
vực, dùng được cho bất kỳ dự án nào có **một luồng biến đổi dữ liệu qua nhiều tầng mà
kết quả khó kiểm chứng bằng mắt**: bóc khối lượng, ETL/data pipeline, chuyển đổi định
dạng, tính toán tài chính, xử lý ảnh/tín hiệu.

## Vì sao cần một prompt riêng cho việc này

Loại lỗi nguy hiểm nhất trong các luồng đó không phải lỗi làm chương trình chết, mà là
lỗi **sai âm thầm**: đầu ra vẫn đủ dòng, đúng định dạng, đúng kiểu dữ liệu — chỉ có con
số là sai. Không có exception, không có log đỏ, không có gì để người dùng nghi ngờ. Ví
dụ có thật từ đợt rà soát này:

- Bản vẽ vẽ bằng mét bị chia cứng cho 1000 → khối lượng nhỏ hơn thực tế **1000 lần**,
  bảng Excel vẫn ra đầy đủ.
- Ống vẽ bên trong Block → bóc **thiếu 100%** phần đó, không một dòng cảnh báo.
- Một đường cong spline → **1654 cái co** trong bảng dự toán.

Rà soát kiểu "nghĩ ra được gì thì kiểm cái đó" bắt được kha khá, nhưng không có gì bảo
đảm những thứ chưa nghĩ ra sẽ lộ diện. Prompt dưới đây thay việc đó bằng **danh sách
phải tick hết** và **bất biến tự bắt lỗi**.

## Prompt

```
Rà soát triệt để các nguồn SAI LỆCH trong <luồng: từ <đầu vào> tới <đầu ra>>.

=== GIAI ĐOẠN 1: LẬP DANH SÁCH TRƯỚC KHI RÀ (bắt buộc, làm xong mới được sửa gì) ===

Không đi tìm lỗi bằng cảm hứng. Lập trước 4 danh sách, rồi rà theo danh sách:

A. KHÔNG GIAN ĐẦU VÀO: liệt kê ĐẦY ĐỦ mọi biến thể mà định dạng/nguồn dữ liệu cho
   phép (mọi kiểu entity, mọi trường header, mọi biến thể cấu trúc). Lấy từ đặc tả
   chính thức hoặc từ API của thư viện đang dùng, KHÔNG lấy từ trí nhớ.
B. CÁC TẦNG BIẾN ĐỔI: liệt kê từng bước dữ liệu bị đọc / đổi đơn vị / gộp / suy diễn
   / ghi ra.
C. MỌI HẰNG SỐ VÀ NGƯỠNG trong code liên quan: mỗi con số là một giả định được chôn
   sẵn. Ghi rõ từng cái giả định điều gì và vỡ khi nào.
D. CÁC LUỒNG SONG SONG cùng mục đích (đường nhập liệu khác, plugin, API khác) — chúng
   phải cho cùng kết quả trên cùng dữ liệu.

Lập ma trận A × B. Mỗi ô phải được tick: đã kiểm chứng thực nghiệm, kết quả đúng/sai.
Ô "đúng, không có lỗi" cũng phải ghi lại — kết quả âm tính là bằng chứng đã rà, không
phải là chỗ bỏ trống.

=== GIAI ĐOẠN 2: KIỂM CHỨNG ===

1. THỰC NGHIỆM, không suy luận: mỗi ô trong ma trận phải dựng dữ liệu thử và chạy
   thật. Không tin docstring và comment — chúng có thể mô tả sai chính code bên dưới.
2. BẤT BIẾN (quan trọng nhất — đây là thứ bắt được lỗi mà bạn CHƯA nghĩ tới):
   viết test kiểm tra các tính chất phải luôn đúng, ví dụ:
   - Bất biến hình học/đơn vị: đổi đơn vị + nhân tọa độ tương ứng → kết quả không đổi.
   - Bất biến phép biến đổi: xoay/tịnh tiến/lật toàn bộ đầu vào → đại lượng đo không đổi.
   - Bất biến tương đương: dữ liệu đóng gói (nhóm/lồng nhau) phải cho cùng kết quả
     với dữ liệu trải phẳng tương đương.
   - Bất biến cộng tính: chia đầu vào làm hai rồi cộng kết quả = xử lý một lần.
   - Bất biến lũy đẳng: chạy hai lần cho cùng kết quả.
   - Bất biến khép kín: dữ liệu do chính hệ thống ghi ra, đọc lại phải ra đúng số cũ.
3. ĐỐI CHIẾU ĐỘC LẬP: với vài mẫu, tính tay hoặc bằng một công cụ/thư viện khác, so
   với kết quả chương trình. Một cài đặt tự đối chiếu với chính nó không chứng minh
   được gì.
4. GIÁ TRỊ BIÊN: rỗng, một phần tử, độ dài 0, trùng điểm, số âm, số cực lớn/cực nhỏ,
   giá trị thiếu, dữ liệu dị dạng. Với mỗi hằng số ở danh sách C: thử ngay dưới, ngay
   trên, và đúng bằng ngưỡng.
5. ĐO ĐỘ PHỦ: chạy coverage trên phần code liên quan. Nhánh nào chưa bao giờ chạy là
   nhánh chưa ai kiểm chứng — rà từng nhánh đó.

=== GIAI ĐOẠN 3: SỬA ===

- Mỗi lỗi phải có test tái hiện: FAIL trước khi sửa, PASS sau khi sửa. Chưa thấy nó
  fail thì chưa chắc test đang kiểm tra đúng thứ cần kiểm tra.
- KHÔNG tự đổi con số dựa trên phỏng đoán. Nếu phép tự sửa có mặt trái đối xứng (sửa
  đúng thì lợi, sửa nhầm thì gây sai lệch ngược lại và âm thầm) → chỉ CẢNH BÁO, đưa
  quyền quyết định cho người dùng qua tham số tùy chọn, mặc định giữ hành vi cũ.
- Mọi thay đổi làm đổi con số phải được nêu trong chính đầu ra của chương trình.
- Sau mỗi lần sửa: chạy lại TOÀN BỘ test + lint (ghi rõ baseline để biết có phát sinh
  lỗi mới). Sửa xong phải rà lại chính phần vừa sửa — nó là dữ liệu đầu vào mới của
  các bước sau.

=== GIAI ĐOẠN 4: ĐIỀU KIỆN DỪNG (dừng theo bằng chứng, không theo cảm giác) ===

Chỉ được dừng khi ĐỒNG THỜI:
  [ ] Ma trận A × B đã tick hết, không còn ô trống.
  [ ] Mọi hằng số ở danh sách C đã có test biên.
  [ ] Bộ test bất biến ở mục 2 chạy pass.
  [ ] Các luồng song song ở D cho cùng kết quả trên cùng dữ liệu.
  [ ] HAI vòng rà liên tiếp không phát hiện thêm lỗi mới nào.
  [ ] Đã chạy thử trên dữ liệu THẬT, không chỉ dữ liệu tổng hợp.

=== BÁO CÁO ===

- Bảng nguồn sai lệch: hậu quả (thiếu/thừa/sai vị trí/sai tên) + cách xử lý.
- Danh sách đã rà và KHÔNG có lỗi (để lần sau khỏi rà lại).
- Danh sách "cân nhắc nhưng không làm" kèm lý do.
- Nếu phát hiện lỗi do chính bạn gây ra ở đợt trước: nói thẳng.
```

## Ba mệnh đề có sức nặng nhất

**Bất biến (Giai đoạn 2, mục 2)** là thứ duy nhất bắt được lỗi mà người rà *chưa nghĩ
tới*. Chiếu vào đợt rà soát MEP-Agents:

| Bất biến | Lỗi nó bắt được |
|---|---|
| Đổi đơn vị + nhân tọa độ → kết quả không đổi | Nguồn #1 (sai 1000 lần) |
| Xoay/lật toàn bộ → chiều dài không đổi | Nguồn #6 (tọa độ OCS) |
| Dữ liệu lồng nhau = dữ liệu trải phẳng | Nguồn #2 và #3 cùng lúc |
| Ghi ra rồi đọc lại phải ra số cũ | Nguồn #17 và #18 (4 chỗ khai sai đơn vị) |

Bốn đợt rà thủ công gộp lại thành mấy chục dòng test.

**Danh sách không gian đầu vào (A)** lấy từ API thư viện chứ không từ trí nhớ. Nếu đợt
đầu đã liệt kê hết các kiểu entity mà `ezdxf` hỗ trợ thì SPLINE/ELLIPSE/polyface mesh
lộ ngay, thay vì đợi tới đợt 2.

**Kiểm kê hằng số (C)**: trong MEP-Agents mỗi ngưỡng đều chôn một giả định "bản vẽ vẽ
bằng mm" — dung sai nối tuyến, chiều dài cây ống, bán kính gán ghi chú. Chúng được phát
hiện nhờ tình cờ đang sửa đúng chỗ đó; danh sách C biến việc này thành có hệ thống.

## Điều cần nói thẳng

Không prompt nào bảo đảm **"không bỏ sót một sai sót nào"** — đó là bài toán không
quyết định được nói chung. Cái prompt này thật sự mua được là chuyển từ *"tôi có nghĩ
ra không?"* sang *"checklist đã tick chưa, bất biến có pass không, coverage còn nhánh
trống không"*. Sót vẫn có thể sót, nhưng sót vì **danh sách chưa đủ** — mà danh sách thì
kiểm tra và bổ sung được, còn trí nhớ thì không.

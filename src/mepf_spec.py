"""Chuẩn hóa ký hiệu thông số kỹ thuật MEPF đọc từ bản vẽ CAD.

Tách riêng khỏi `src/tools.py` để cắt vòng import: `qs_tools` cần đúng hàm này, còn
`tools` lại import ngược một loạt tool từ `qs_tools`. Vòng đó khiến `import src.qs_tools`
**trực tiếp** vỡ với `partially initialized module`, và buộc `tools.py` phải dồn một khối
import xuống cuối file kèm `# noqa: E402` — một chỗ khó hiểu cho người đọc sau.

Module này cố ý **không import bất kỳ module nào khác của dự án**: đó là điều kiện để nó
làm nền chung cho cả hai bên mà không tạo vòng mới.
"""
from __future__ import annotations

import re


def normalize_mepf_parameter_spec(text: str) -> str:
    """Chuẩn hóa toàn bộ các ký hiệu thông số kỹ thuật MEPF trong CAD về định dạng đồng nhất cho AI:
    1. Đường kính ống: %%c, Φ, Ø, D, d, DN, OD -> Ø110 (D110)
    2. Kích thước ống gió: 600*400, 600X400, W600xH400 -> 600x400
    3. Độ dốc thoát nước: i=1%, s=1%, i=1.5% -> i=1%
    4. Tiết diện dây điện: 3x2.5mm2, 3x2.5sqmm -> 3x2.5mm²
    5. Điện áp / Pha: 220V/1P, 220V 1 Phase -> 220V-1P
    6. Lưu lượng: CMH, m3/h -> m³/h
    """
    if not text:
        return text
    text = text.replace('%%c', 'Ø').replace('%%C', 'Ø').replace('Φ', 'Ø')
    text = re.sub(r'(?i)\b(Ø|DN|D|d|OD)\s*(\d+)\b', r'Ø\2 (D\2)', text)
    text = re.sub(r'(?i)(?:W)?(\d+)\s*[\*xX]\s*(?:H)?(\d+)', r'\1x\2', text)
    text = re.sub(r'(?i)\b[is]\s*=\s*(\d+(?:\.\d+)?)\s*%', r'i=\1%', text)
    text = re.sub(r'(?i)\b(\d+x\d+(?:\.\d+)?)\s*(?:mm2|sqmm|mm²)\b', r'\1mm²', text)
    text = re.sub(r'(?i)\b(220|230|380|400)\s*V?\s*[\/\-]?\s*([13])\s*(?:P|Phase|Pha)\b', r'\1V-\2P', text)
    text = re.sub(r'(?i)\b(?:CMH|m3\/h|m3h)\b', r'm³/h', text)
    return text


#: Tên cũ, giữ lại vì code sẵn có còn dùng.
normalize_pipe_diameter_spec = normalize_mepf_parameter_spec

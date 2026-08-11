from langchain_core.tools import tool
import pandas as pd
from docx import Document
import os
import json
from pypdf import PdfReader
import ezdxf
from ezdxf import audit
import math
import re
import ast
import operator as op
import logging
from functools import lru_cache
from src.workspace import resolve_safe_path, get_project_root

logger = logging.getLogger(__name__)

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

normalize_pipe_diameter_spec = normalize_mepf_parameter_spec

@lru_cache(maxsize=4)
def _load_vectorstore(api_key: str, index_path: str):
    """Load (and cache) the FAISS index once per api_key/index_path instead of on every call."""
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS

    embeddings = OpenAIEmbeddings(api_key=api_key)
    return FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)

@tool
def search_standards(query: str) -> str:
    """Tra cứu Tiêu chuẩn thiết kế MEPF (TCVN, ASHRAE, NFPA...) từ cơ sở dữ liệu nội bộ."""
    logger.info("Tra cứu tiêu chuẩn thực: %s", query)
    try:
        from src.config import settings

        api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "dummy_key_to_prevent_crash_on_import")

        index_path = "faiss_index"
        if not os.path.exists(index_path):
            return "Hệ thống RAG chưa được khởi tạo. Vui lòng thêm tài liệu vào 'data/standards/' và chạy 'uv run python src/ingest.py'."

        vectorstore = _load_vectorstore(api_key, index_path)
        docs = vectorstore.similarity_search(query, k=3)

        if not docs:
            return "Không tìm thấy thông tin tiêu chuẩn nào khớp với yêu cầu."

        result = f"Kết quả RAG Tiêu chuẩn cho '{query}':\n"
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get('source', 'Unknown')
            result += f"\n--- Trích đoạn {i} (Nguồn: {source}) ---\n"
            result += doc.page_content + "\n"

        return result
    except Exception as e:
        return f"Lỗi tra cứu tiêu chuẩn RAG: {e}"

@tool
def search_web(query: str) -> str:
    """Tìm kiếm thông tin trên internet."""
    logger.info("Searching web for: %s", query)
    return f"Kết quả mô phỏng cho '{query}': Tìm thấy nhiều tài liệu liên quan."

# Chỉ cho phép các toán tử số học thuần túy - không có tên biến, thuộc tính hay lời gọi hàm,
# nên không thể escape sandbox như với eval() (kể cả khi đã tắt __builtins__).
_SAFE_OPERATORS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Pow: op.pow, ast.Mod: op.mod, ast.FloorDiv: op.floordiv,
    ast.USub: op.neg, ast.UAdd: op.pos,
}

def _safe_eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPERATORS:
        return _SAFE_OPERATORS[type(node.op)](_safe_eval_node(node.left), _safe_eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPERATORS:
        return _SAFE_OPERATORS[type(node.op)](_safe_eval_node(node.operand))
    raise ValueError("Biểu thức chứa cú pháp không được phép (chỉ hỗ trợ số và các phép toán +-*/%**).")

@tool
def calculate(expression: str) -> str:
    """Thực hiện tính toán toán học cơ bản (ví dụ: '25 * 4')."""
    logger.info("Calculating: %s", expression)
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval_node(tree.body)
        return f"Kết quả: {result}"
    except Exception as e:
        return f"Lỗi tính toán: {e}"

@tool
def list_directory(path: str = ".") -> str:
    """Liệt kê danh sách các file trong thư mục để xem có file nào tồn tại."""
    logger.info("Listing directory: %s", path)
    try:
        safe_path = resolve_safe_path(path)
        files = os.listdir(safe_path)
        return f"Files trong '{path}': {', '.join(files)}"
    except Exception as e:
        return f"Lỗi đọc thư mục: {e}"

@tool
def read_excel(file_path: str) -> str:
    """Đọc nội dung từ file Excel (.xlsx)."""
    logger.info("Reading Excel: %s", file_path)
    try:
        df = pd.read_excel(resolve_safe_path(file_path))
        return f"Dữ liệu Excel:\n{df.to_string(index=False)}"
    except Exception as e:
        return f"Lỗi đọc Excel: {e}"

@tool
def write_excel(file_path: str, json_data: str) -> str:
    """Tạo hoặc ghi file Excel (.xlsx). json_data là danh sách các object dưới dạng chuỗi JSON đại diện cho các dòng. Ví dụ: '[{"STT": 1, "Vật tư": "Ống", "KL": 10}]'"""
    logger.info("Writing Excel: %s", file_path)
    try:
        if not file_path.endswith('.xlsx'):
            file_path += '.xlsx'

        safe_path = resolve_safe_path(file_path)
        dir_name = os.path.dirname(safe_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        data = json.loads(json_data)
        df = pd.DataFrame(data)
        df.to_excel(safe_path, index=False)
        return f"Đã ghi đè/tạo thành công file Excel tại: {file_path}"
    except Exception as e:
        return f"Lỗi ghi Excel: {e}"

@tool
def read_word(file_path: str) -> str:
    """Đọc nội dung từ file Word (.docx)."""
    logger.info("Reading Word: %s", file_path)
    try:
        doc = Document(resolve_safe_path(file_path))
        full_text = [para.text for para in doc.paragraphs]
        return "\n".join(full_text)
    except Exception as e:
        return f"Lỗi đọc Word: {e}"

@tool
def write_word(file_path: str, content: str, font_name: str = 'Arial') -> str:
    """Tạo hoặc ghi file Word (.docx) với nội dung được truyền vào. Tham số font_name hỗ trợ 'Arial' hoặc 'Times New Roman'."""
    logger.info("Writing Word: %s", file_path)
    try:
        from docx.shared import Pt
        safe_path = resolve_safe_path(file_path)
        doc = Document()
        # Thiết lập Font chữ chuẩn Unicode (Arial / Times New Roman) cho tiếng Việt
        style = doc.styles['Normal']
        font = style.font
        if font_name not in ['Arial', 'Times New Roman']:
            font_name = 'Arial'
        font.name = font_name
        font.size = Pt(12)

        doc.add_paragraph(content)
        doc.save(safe_path)
        return f"Đã lưu nội dung vào file Word tại: {file_path} (Font: {font_name})"
    except Exception as e:
        return f"Lỗi ghi Word: {e}"

@tool
def read_pdf(file_path: str) -> str:
    """Đọc và trích xuất toàn bộ văn bản từ file PDF."""
    logger.info("Reading PDF: %s", file_path)
    try:
        reader = PdfReader(resolve_safe_path(file_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return f"Nội dung PDF ({len(reader.pages)} trang):\n{text[:5000]}..."
    except Exception as e:
        return f"Lỗi đọc PDF: {e}"

@tool
def read_cad(file_path: str) -> str:
    """Đọc file CAD (.dxf) và trả về thống kê thư viện block, block attributes, chiều dài, và layer sau khi đã làm sạch."""
    logger.info("Reading, Cleaning & Extracting CAD: %s", file_path)
    try:
        doc = ezdxf.readfile(resolve_safe_path(file_path))
        
        auditor = audit.Auditor(doc)
        auditor.run()
        audit_fixes = len(auditor.fixes)
        
        block_defs = []
        for block in doc.blocks:
            is_layout = getattr(block, 'is_layout_block', False) or getattr(block, 'is_any_layout', False)
            if not is_layout and not block.name.startswith('*'):
                block_defs.append(block.name)
                
        msp = doc.modelspace()
        layer_counts = {}
        block_instances = []
        layer_lengths = {}
        
        for entity in msp:
            layer = entity.dxf.layer
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
            dxftype = entity.dxftype()
            
            if dxftype in ('LINE', 'LWPOLYLINE', 'POLYLINE'):
                try:
                    dist = 0.0
                    if dxftype == 'LINE':
                        start = entity.dxf.start
                        end = entity.dxf.end
                        dist = math.hypot(end.x - start.x, end.y - start.y)
                    elif dxftype == 'LWPOLYLINE':
                        pts = entity.get_points(format='xy')
                        dist = sum(math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]) for i in range(1, len(pts)))
                    elif dxftype == 'POLYLINE':
                        pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                        dist = sum(math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]) for i in range(1, len(pts)))
                    layer_lengths[layer] = layer_lengths.get(layer, 0.0) + dist
                except Exception:
                    pass
            
            if dxftype == 'INSERT':
                b_name = entity.dxf.name
                attribs = {}
                if hasattr(entity, 'attribs') and entity.attribs:
                    for attrib in entity.attribs:
                        if hasattr(attrib, 'dxf') and hasattr(attrib.dxf, 'tag'):
                            attribs[attrib.dxf.tag] = getattr(attrib.dxf, 'text', '')
                block_instances.append({"name": b_name, "attribs": attribs})
                
        block_summary = {}
        for b in block_instances:
            b_name = b['name']
            attr_str = json.dumps(b['attribs'], ensure_ascii=False) if b['attribs'] else "No Attributes"
            key = f"{b_name} | Thuộc tính: {attr_str}"
            block_summary[key] = block_summary.get(key, 0) + 1
            
        result = f"Đã làm sạch (Audit). Sửa {audit_fixes} lỗi.\n\n"
        
        if len(block_defs) > 25:
            defs_str = ", ".join(block_defs[:25]) + f"... (và {len(block_defs) - 25} block khác)"
        else:
            defs_str = ", ".join(block_defs) if block_defs else "Không có"
        result += f"THƯ VIỆN BLOCK CÓ SẴN (Definitions): {defs_str}\n\n"
        
        result += "THỐNG KÊ LAYER TRÊN MODELSPACE:\n"
        for k, v in layer_counts.items():
            l_info = f"- Layer '{k}': {v} đối tượng"
            if k in layer_lengths and layer_lengths[k] > 0:
                l_info += f" (Tổng chiều dài nắn nét: {layer_lengths[k]:.2f}m)"
            result += l_info + "\n"
            
        result += "\nTHỐNG KÊ BLOCK THỰC TẾ & THUỘC TÍNH (Attributes):\n"
        if not block_summary:
            result += "(Không có block nào)\n"
        else:
            sorted_blocks = sorted(block_summary.items(), key=lambda x: x[1], reverse=True)
            display_blocks = sorted_blocks[:40]
            for k, v in display_blocks:
                result += f"- Block: {k} -> Số lượng: {v}\n"
            if len(sorted_blocks) > 40:
                result += f"... (và {len(sorted_blocks) - 40} nhóm block khác)\n"
                
        return result
    except Exception as e:
        return f"Lỗi xử lý CAD (.dxf): {e}"

@tool
def write_cad(file_path: str, layers: str) -> str:
    """Tạo một file CAD mới (.dxf) sạch sẽ với các layer định trước. Tham số layers: chuỗi ngăn cách bởi dấu phẩy."""
    logger.info("Writing CAD: %s", file_path)
    try:
        safe_path = resolve_safe_path(file_path)
        doc = ezdxf.new('R2010')
        layer_list = [l.strip() for l in layers.split(',') if l.strip()]
        for layer in layer_list:
            doc.layers.add(name=layer)

        doc.saveas(safe_path)
        return f"Đã tạo thành công bản vẽ CAD tại {file_path} với các layers: {', '.join(layer_list)}"
    except Exception as e:
        return f"Lỗi tạo CAD (.dxf): {e}"

import sys
from io import StringIO
import builtins

# Sandbox cho execute_python_code: chỉ cho phép các builtin an toàn (không có open/eval/exec/input)
# và chỉ cho phép import các module cần thiết cho việc dựng Block ezdxf (ezdxf, math, json).
# Đây KHÔNG phải cô lập tuyệt đối (không thay thế container/subprocess sandbox thật sự),
# nhưng chặn được các vector tấn công rõ ràng nhất: đọc/ghi file tùy ý, exec chuỗi động, os/subprocess.
_ALLOWED_MODULES = {"ezdxf", "math", "json"}

def _sandboxed_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in _ALLOWED_MODULES:
        raise ImportError(f"Module '{name}' không được phép sử dụng trong execute_python_code.")
    return builtins.__import__(name, globals, locals, fromlist, level)

_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list",
    "max", "min", "print", "range", "round", "set", "sorted", "str", "sum", "tuple",
    "zip", "True", "False", "None", "isinstance",
)
_SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}
_SAFE_BUILTINS["__import__"] = _sandboxed_import

@tool
def execute_python_code(code: str) -> str:
    """
    Thực thi mã Python động trong môi trường giới hạn (sandbox).
    Được dùng để Họa viên CAD tự viết code ezdxf vẽ Block mới và lưu vào 'data/blocks/mepf_library.dxf'.
    Chỉ cho phép import ezdxf/math/json và không có quyền truy cập file/network trực tiếp qua builtin open().
    """
    logger.info("Executing Custom Python Code (sandboxed)")
    old_stdout = sys.stdout
    try:
        redirected_output = sys.stdout = StringIO()

        safe_globals = {"__builtins__": _SAFE_BUILTINS}
        local_env = {}
        exec(code, safe_globals, local_env)

        return f"Thực thi Python thành công. Output:\n{redirected_output.getvalue()}"
    except Exception as e:
        return f"Lỗi quá trình thực thi Python: {e}"
    finally:
        sys.stdout = old_stdout

@tool
def ai_block_recovery(file_path: str, layer: str, shape: str, dimensions: str, replacement_block: str) -> str:
    """Khôi phục các thiết bị bị phá vỡ (exploded) thành Block chuẩn.
    - layer: Tên layer chứa các nét vẽ rời rạc.
    - shape: 'circle' (hình tròn) hoặc 'rectangle' (hình chữ nhật).
    - dimensions: Với circle là 'bán kính' (ví dụ: '100'). Với rectangle là 'dài,rộng' (ví dụ '600,600').
    - replacement_block: Tên Block mới sẽ được chèn vào.
    """
    logger.info("AI Block Recovery: %s, Layer=%s, Shape=%s", file_path, layer, shape)
    try:
        from ezdxf.addons import importer

        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Lỗi: Không tìm thấy file {file_path}"

        doc = ezdxf.readfile(safe_path)
        msp = doc.modelspace()

        library_path = os.path.join(get_project_root(), "data", "blocks", "mepf_library.dxf")
        lib_doc = None
        if os.path.exists(library_path):
            lib_doc = ezdxf.readfile(library_path)
            
        if replacement_block not in doc.blocks and lib_doc and replacement_block in lib_doc.blocks:
            imp = importer.Importer(lib_doc, doc)
            imp.import_block(replacement_block)
            imp.finalize()
            
        if replacement_block not in doc.blocks:
            return f"Lỗi: Block '{replacement_block}' không tồn tại trong Thư viện Tổng kho."
            
        centers = []
        entities_to_delete = []
        max_dim = 0
        
        if shape.lower() == "circle":
            target_r = float(dimensions)
            max_dim = target_r * 2
            for entity in msp.query(f'CIRCLE[layer=="{layer}"]'):
                r = entity.dxf.radius
                if abs(r - target_r) / target_r <= 0.05:
                    centers.append((entity.dxf.center.x, entity.dxf.center.y))
                    
        elif shape.lower() == "rectangle":
            dims = dimensions.split(",")
            if len(dims) == 2:
                target_w, target_h = float(dims[0]), float(dims[1])
                max_dim = max(target_w, target_h)
                target_area = target_w * target_h
                for entity in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
                    if entity.closed or len(entity) >= 4:
                        points = entity.get_points()
                        xs = [p[0] for p in points]
                        ys = [p[1] for p in points]
                        w = max(xs) - min(xs)
                        h = max(ys) - min(ys)
                        area = w * h
                        if area > 0 and abs(area - target_area) / target_area <= 0.1:
                            cx = (max(xs) + min(xs)) / 2
                            cy = (max(ys) + min(ys)) / 2
                            centers.append((cx, cy))
                            
        # Dọn rác chuyên sâu: Quét và xóa MỌI nét vẽ (LINE, PLINE, TEXT) nằm lọt thỏm trong vùng Block
        if max_dim > 0 and centers:
            tolerance = max_dim * 0.6  # Phạm vi dọn rác (Bao trùm block + 10% an toàn)
            for entity in msp.query(f'*[layer=="{layer}"]'):
                px, py = None, None
                if hasattr(entity.dxf, 'start'):
                    px, py = entity.dxf.start.x, entity.dxf.start.y
                elif hasattr(entity.dxf, 'center'):
                    px, py = entity.dxf.center.x, entity.dxf.center.y
                elif hasattr(entity.dxf, 'insert'):
                    px, py = entity.dxf.insert.x, entity.dxf.insert.y
                elif entity.dxftype() == 'LWPOLYLINE':
                    try:
                        pts = entity.get_points()
                        px, py = pts[0][0], pts[0][1]
                    except:
                        pass
                
                if px is not None and py is not None:
                    for cx, cy in centers:
                        if abs(px - cx) <= tolerance and abs(py - cy) <= tolerance:
                            entities_to_delete.append(entity)
                            break
                            
        for e in set(entities_to_delete):
            try:
                msp.delete_entity(e)
            except:
                pass
            
        for cx, cy in centers:
            msp.add_blockref(replacement_block, (cx, cy), dxfattribs={'layer': layer})
            
        doc.saveas(safe_path)
        return f"AI Recovery thành công: Đã tìm thấy và phục hồi {len(centers)} đối tượng '{shape}' thành Block '{replacement_block}'."
    except Exception as e:
        return f"Lỗi phục hồi Block: {e}"

@tool
def edit_cad(file_path: str, actions_json: str) -> str:
    """Chỉnh sửa file CAD (.dxf) hiện tại. Luôn Audit làm sạch file trước.
    actions_json là danh sách các dict. Ví dụ:
    - Thêm layer: {"action": "add_layer", "name": "MEP_DIEN"}
    - Thêm text: {"action": "add_text", "text": "Phong Khach", "x": 0, "y": 0, "layer": "MEP_DIEN", "font_name": "Times New Roman"}
    - Chèn block: {"action": "insert_block", "name": "TU_DIEN", "x": 10, "y": 10, "layer": "MEP_DIEN", "scale": 1.0, "rotation": 0}
    - Đồng bộ font (chống lỗi tiếng Việt): {"action": "fix_fonts", "font_name": "Arial"}
    """
    logger.info("Editing CAD: %s", file_path)
    try:
        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Lỗi: Không tìm thấy file {file_path}"

        doc = ezdxf.readfile(safe_path)
        msp = doc.modelspace()

        auditor = audit.Auditor(doc)
        auditor.run()
        audit_fixes = len(auditor.fixes)

        actions = json.loads(actions_json)
        results = []

        # Tải Master Library (Tổng kho Block)
        from ezdxf.addons import importer
        library_path = os.path.join(get_project_root(), "data", "blocks", "mepf_library.dxf")
        lib_doc = None
        if os.path.exists(library_path):
            lib_doc = ezdxf.readfile(library_path)
            
        # Khởi tạo Style chữ chuẩn Unicode để tránh lỗi font tiếng Việt trong CAD
        if 'VIETNAMESE_ARIAL' not in doc.styles:
            doc.styles.new('VIETNAMESE_ARIAL', dxfattribs={'font': 'arial.ttf'})
        if 'VIETNAMESE_TIMES' not in doc.styles:
            doc.styles.new('VIETNAMESE_TIMES', dxfattribs={'font': 'times.ttf'})
            
        for act in actions:
            action_type = act.get("action")
            if action_type == "fix_fonts":
                font_name = act.get("font_name", "Arial")
                ttf_file = "times.ttf" if font_name == "Times New Roman" else "arial.ttf"
                # Đổi font của toàn bộ Text Styles có trong bản vẽ
                count = 0
                for style in doc.styles:
                    style.dxf.font = ttf_file
                    count += 1
                results.append(f"Đã đồng bộ {count} Text Styles trong file sang chuẩn Unicode ({font_name}) để sửa lỗi tiếng Việt.")
            elif action_type == "add_layer":
                lname = act.get("name", "NEW_LAYER")
                if lname not in doc.layers:
                    doc.layers.add(name=lname)
                    results.append(f"Thêm layer {lname}")
            elif action_type == "add_text":
                txt = act.get("text", "Text")
                x = act.get("x", 0)
                y = act.get("y", 0)
                layer = act.get("layer", "0")
                font_name = act.get("font_name", "Arial")
                
                if layer not in doc.layers:
                    doc.layers.add(name=layer)
                
                # Áp dụng style VIETNAMESE tương ứng cho Text
                style_name = 'VIETNAMESE_TIMES' if font_name == 'Times New Roman' else 'VIETNAMESE_ARIAL'
                msp.add_text(txt, dxfattribs={'layer': layer, 'style': style_name}).set_placement((x, y))
                results.append(f"Thêm text '{txt}' tại tọa độ ({x},{y}) trên layer {layer} (Font: {font_name})")
            elif action_type == "insert_block":
                b_name = act.get("name")
                x = act.get("x", 0)
                y = act.get("y", 0)
                layer = act.get("layer", "0")
                scale = act.get("scale", 1.0)
                rotation = act.get("rotation", 0.0)
                
                # Auto-Import Block từ Thư viện Trung tâm nếu bản vẽ thiếu
                if b_name not in doc.blocks and lib_doc and b_name in lib_doc.blocks:
                    imp = importer.Importer(lib_doc, doc)
                    imp.import_block(b_name)
                    imp.finalize()
                    results.append(f"Auto-Import thành công Block '{b_name}' từ Thư viện Trung tâm.")
                
                if b_name in doc.blocks:
                    if layer not in doc.layers:
                        doc.layers.add(name=layer)
                    msp.add_blockref(b_name, (x, y), dxfattribs={
                        'layer': layer,
                        'xscale': scale,
                        'yscale': scale,
                        'rotation': rotation
                    })
                    results.append(f"Chèn Block '{b_name}' tại ({x},{y}) layer {layer}")
                else:
                    results.append(f"Lỗi: Block '{b_name}' không tồn tại trong bản vẽ và cả Thư viện Trung tâm.")
                    
        doc.saveas(safe_path)
        return f"Đã làm sạch ({audit_fixes} lỗi rác được xóa) và chỉnh sửa thành công {file_path}:\n- " + "\n- ".join(results)
    except Exception as e:
        return f"Lỗi sửa CAD (.dxf): {e}"

@tool
def render_cad_image(file_path: str, output_png_path: str = "cad_preview.png") -> str:
    """Chuyển đổi file bản vẽ CAD (.dxf) thành hình ảnh PNG sắc nét để hiển thị trực quan (Computer Vision) lên giao diện Web."""
    logger.info("Rendering CAD to Image: %s -> %s", file_path, output_png_path)
    try:
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib.pyplot as plt

        doc = ezdxf.readfile(resolve_safe_path(file_path))
        msp = doc.modelspace()

        fig = plt.figure(figsize=(12, 8), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)
        fig.savefig(resolve_safe_path(output_png_path), dpi=150, bbox_inches='tight')
        plt.close(fig)
        return f"Đã xuất hình ảnh bản vẽ CAD (Computer Vision) thành công tại: {output_png_path}"
    except Exception as e:
        return f"Lỗi xuất ảnh CAD: {e}"

@tool
def analyze_cad_spatial_context(file_path: str, max_distance: float = 2000.0) -> str:
    """Phân tích Ngữ cảnh Hình học & Mũi tên Chỉ dẫn (Leaders, Text Annotations, Spatial Matching) để hiểu bản vẽ CAD như con người: tự động liên kết Ghi chú văn bản (ví dụ: 'Ống uPVC Ø110', 'Ống gió 600x400') và Mũi tên chỉ hướng với đúng nét vẽ đường ống kề cận."""
    logger.info("Analyzing CAD Spatial Context & Arrows: %s", file_path)
    try:
        doc = ezdxf.readfile(resolve_safe_path(file_path))
        msp = doc.modelspace()
        
        texts = []
        leaders = []
        pipe_segments = []
        
        def point_to_seg_dist(px, py, ax, ay, bx, by):
            l2 = (bx - ax)**2 + (by - ay)**2
            if l2 == 0:
                return math.hypot(px - ax, py - ay)
            t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2))
            proj_x = ax + t * (bx - ax)
            proj_y = ay + t * (by - ay)
            return math.hypot(px - proj_x, py - proj_y)

        for entity in msp:
            dxftype = entity.dxftype()
            layer = entity.dxf.layer
            
            if dxftype == 'TEXT':
                t_str = normalize_pipe_diameter_spec(entity.dxf.text.strip())
                pos = entity.dxf.insert
                if t_str:
                    texts.append({"text": t_str, "pos": (pos.x, pos.y), "layer": layer})
            elif dxftype == 'MTEXT':
                t_str = normalize_pipe_diameter_spec(entity.text.strip())
                pos = entity.dxf.insert
                if t_str:
                    texts.append({"text": t_str, "pos": (pos.x, pos.y), "layer": layer})
            elif dxftype in ('LEADER', 'MULTILEADER'):
                try:
                    if hasattr(entity, 'vertices') and entity.vertices:
                        vertices = [(v.x, v.y) for v in entity.vertices]
                        leaders.append({"tip": vertices[0], "tail": vertices[-1], "layer": layer})
                except Exception:
                    pass
            elif dxftype == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                length = math.hypot(e.x - s.x, e.y - s.y)
                pipe_segments.append({"layer": layer, "seg": (s.x, s.y, e.x, e.y), "length": length})
            elif dxftype in ('LWPOLYLINE', 'POLYLINE'):
                try:
                    if dxftype == 'LWPOLYLINE':
                        pts = entity.get_points(format='xy')
                    else:
                        pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                    for i in range(1, len(pts)):
                        ax, ay = pts[i-1][0], pts[i-1][1]
                        bx, by = pts[i][0], pts[i][1]
                        length = math.hypot(bx - ax, by - ay)
                        pipe_segments.append({"layer": layer, "seg": (ax, ay, bx, by), "length": length})
                except Exception:
                    pass

        associations = {}
        for text_item in texts:
            tx, ty = text_item["pos"]
            txt = text_item["text"]
            
            min_dist = float('inf')
            best_pipe = None
            
            for p in pipe_segments:
                ax, ay, bx, by = p["seg"]
                d = point_to_seg_dist(tx, ty, ax, ay, bx, by)
                if d < min_dist:
                    min_dist = d
                    best_pipe = p
                    
            if best_pipe and min_dist <= max_distance:
                p_layer = best_pipe["layer"]
                key = f"Ghi chú: '{txt}' <---> Layer ống: '{p_layer}'"
                if key not in associations:
                    associations[key] = {"count": 0, "total_length": 0.0, "text": txt, "layer": p_layer, "min_dist": min_dist}
                associations[key]["count"] += 1
                associations[key]["total_length"] += best_pipe["length"]

        report = f"PHÂN TÍCH NGỮ CẢNH HÌNH HỌC & MŨI TÊN CHỈ DẪN (Spatial Intelligence):\n"
        report += f"- Tìm thấy {len(texts)} văn bản ghi chú (TEXT/MTEXT), {len(leaders)} mũi tên chỉ dẫn (LEADER), và {len(pipe_segments)} đoạn đường ống.\n\n"
        
        report += "📌 THỐNG KÊ GHI CHÚ VĂN BẢN VÀ MŨI TÊN (Tối đa 20 ghi chú tiêu biểu):\n"
        for t in texts[:20]:
            report += f"  • Ghi chú: \"{t['text']}\" (Layer: {t['layer']}) tại tọa độ ({t['pos'][0]:.1f}, {t['pos'][1]:.1f})\n"
        if len(texts) > 20:
            report += f"  ... và {len(texts) - 20} ghi chú khác.\n"
            
        report += "\n🔗 LIÊN KẾT HÌNH HỌC KHÔNG GIANG (Text Annotation <-> Pipe Segment): \n"
        if not associations:
            report += "  (Không tìm thấy liên kết kề cận trong bán kính khoảng cách quy định)\n"
        else:
            for k, v in list(associations.items())[:25]:
                report += f"  • [{v['text']}] liên kết trực tiếp với tuyến ống Layer '{v['layer']}' (Khoảng cách kề cận: {v['min_dist']:.1f}mm) -> Tổng chiều dài suy luận: {v['total_length']:.2f}m\n"
                
        return report
    except Exception as e:
        return f"Lỗi phân tích ngữ cảnh không gian CAD: {e}"

from src.hvac_tools import (
    calc_psychrometrics, calc_duct_size, calc_cooling_load, calc_chw_pipe_size, calc_pump_fan_power, calc_ventilation_rate,
    calc_cooling_load_detailed, calc_duct_total_pressure_loss, calc_chiller_ahu_selection, calc_refrigerant_pipe_size,
)
from src.elec_tools import calc_cable_size, calc_breaker_size, calc_lighting_qty
from src.plumb_tools import (
    calc_water_pipe, calc_water_tank, calc_plumbing_pump_head,
    calc_drainage_pipe, calc_rainwater_drainage, calc_septic_tank, calc_hot_water_system,
)
from src.ff_tools import calc_sprinkler_qty, calc_fire_pump, calc_extinguisher_qty

tools = [
    search_web, execute_python_code, list_directory,
    read_excel, write_excel, read_word, write_word, read_pdf,
    read_cad, write_cad, edit_cad, ai_block_recovery, render_cad_image, analyze_cad_spatial_context,
    calc_psychrometrics, calc_duct_size, calc_cooling_load, calc_chw_pipe_size, calc_pump_fan_power, calc_ventilation_rate,
    calc_cooling_load_detailed, calc_duct_total_pressure_loss, calc_chiller_ahu_selection, calc_refrigerant_pipe_size,
    calc_cable_size, calc_breaker_size, calc_lighting_qty,
    calc_water_pipe, calc_water_tank, calc_plumbing_pump_head,
    calc_drainage_pipe, calc_rainwater_drainage, calc_septic_tank, calc_hot_water_system,
    calc_sprinkler_qty, calc_fire_pump, calc_extinguisher_qty
]

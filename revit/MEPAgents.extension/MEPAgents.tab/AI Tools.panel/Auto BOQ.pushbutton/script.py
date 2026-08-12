#! python3
# -*- coding: utf-8 -*-
"""
Gửi dữ liệu MEP từ Revit sang FastAPI Cloud để phân tích bằng Bầy đàn AI.
"""
import json
import os
import urllib.error
import urllib.request  # Shebang "#! python3" buộc pyRevit chạy bằng CPython3
                       # (không phải IronPython 2.7) → phải dùng urllib.request / urllib.error
                       # của Python 3. urllib2 không tồn tại ở Python 3 và sẽ crash
                       # ngay khi import nếu chạy thật trong Revit.
from pyrevit import revit, DB, UI, forms

# --- Cấu hình máy chủ AI ------------------------------------------------
# Ưu tiên biến môi trường MEP_AGENTS_API_BASE (đặt sẵn trên máy trạm) rồi mới
# tới file config.json cạnh script này, cuối cùng mới rơi về localhost mặc
# định. Trước đây URL bị hardcode "http://localhost:8083" nên plugin không
# dùng được với server chạy trên máy khác/cloud mà không sửa trực tiếp code.
_SCRIPT_DIR = os.path.dirname(__file__)
_CONFIG_PATH = os.path.join(_SCRIPT_DIR, "config.json")
_DEFAULT_API_BASE = "http://localhost:8083"
_REQUEST_TIMEOUT_SEC = 30


def _load_config():
    cfg = {}
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass  # config hỏng -> rơi về mặc định thay vì chặn cả plugin
    return cfg


def _load_api_base(cfg):
    env_value = os.environ.get("MEP_AGENTS_API_BASE")
    if env_value:
        return env_value.rstrip("/")
    base = cfg.get("api_base")
    if base:
        return base.rstrip("/")
    return _DEFAULT_API_BASE


def _load_api_key(cfg):
    # Chỉ cần đặt khi server bật MEP_AGENTS_API_KEY (xem TECH_DEBT.md mục 7) — máy dev
    # cục bộ mặc định không cấu hình gì thì server vẫn mở, giá trị này để rỗng cũng được.
    return os.environ.get("MEP_AGENTS_API_KEY") or cfg.get("api_key") or ""


_CONFIG = _load_config()
API_BASE = _load_api_base(_CONFIG)
API_KEY = _load_api_key(_CONFIG)
ANALYZE_URL = API_BASE + "/api/v1/revit/analyze"

doc = revit.doc

# Thu thập đủ 4 hệ MEP thay vì chỉ Cơ (Duct/Pipe) như trước, để BOQ Revit bao
# quát cả Điện (ống luồn dây/máng cáp/thiết bị điện) và PCCC (đầu phun/báo cháy).
CATEGORIES = [
    DB.BuiltInCategory.OST_DuctCurves,
    DB.BuiltInCategory.OST_DuctFitting,
    DB.BuiltInCategory.OST_DuctAccessory,
    DB.BuiltInCategory.OST_FlexDuctCurves,
    DB.BuiltInCategory.OST_PipeCurves,
    DB.BuiltInCategory.OST_PipeFitting,
    DB.BuiltInCategory.OST_PipeAccessory,
    DB.BuiltInCategory.OST_FlexPipeCurves,
    DB.BuiltInCategory.OST_MechanicalEquipment,
    DB.BuiltInCategory.OST_Conduit,
    DB.BuiltInCategory.OST_ConduitFitting,
    DB.BuiltInCategory.OST_CableTray,
    DB.BuiltInCategory.OST_CableTrayFitting,
    DB.BuiltInCategory.OST_ElectricalEquipment,
    DB.BuiltInCategory.OST_ElectricalFixtures,
    DB.BuiltInCategory.OST_LightingFixtures,
    DB.BuiltInCategory.OST_PlumbingFixtures,
    DB.BuiltInCategory.OST_Sprinklers,
    DB.BuiltInCategory.OST_FireAlarmDevices,
]


def get_mep_elements():
    elements_data = []

    for cat in CATEGORIES:
        try:
            collector = DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType()
        except Exception:
            # Category không tồn tại trong phiên bản Revit/template hiện tại -> bỏ qua.
            continue

        for el in collector:
            try:
                el_dict = {
                    "id": el.Id.IntegerValue,
                    "category": el.Category.Name if el.Category else "Unknown",
                    "name": el.Name,
                }
                # Lấy chiều dài (nếu có) và đổi sang mm (Revit dùng feet)
                param_length = el.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)
                if param_length:
                    el_dict["length_mm"] = param_length.AsDouble() * 304.8

                elements_data.append(el_dict)
            except Exception:
                # Một cấu kiện lỗi (VD Category null) không được làm hỏng cả lượt thu thập.
                continue

    return elements_data


def _post_json(url, payload_dict):
    payload = json.dumps(payload_dict).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(url, data=payload, headers=headers)
    response = urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SEC)
    return json.loads(response.read().decode("utf-8"))


def main():
    data = get_mep_elements()
    if not data:
        forms.alert("Không tìm thấy cấu kiện MEP nào trong mô hình này!", title="MEP-Agents")
        return

    forms.alert("Đã trích xuất {} cấu kiện MEP. Bắt đầu gửi cho AI Swarm...".format(len(data)), title="MEP-Agents")

    try:
        result_json = _post_json(ANALYZE_URL, {
            "elements": data,
            "project_name": doc.Title,
        })
    except urllib.error.HTTPError as e:
        if e.code == 401:
            forms.alert(
                "Server yêu cầu API Key (401 Unauthorized) nhưng plugin chưa có key đúng.\n\n"
                "Đặt biến môi trường MEP_AGENTS_API_KEY hoặc thêm \"api_key\" vào config.json "
                "cạnh script, khớp với MEP_AGENTS_API_KEY phía server.",
                title="Chưa xác thực",
            )
        else:
            forms.alert("Server trả lỗi HTTP {}: {}".format(e.code, e), title="Lỗi API")
        return
    except urllib.error.URLError as e:
        forms.alert(
            "Không kết nối được tới MEP-Agents Cloud tại {}.\n\n"
            "Kiểm tra server đã chạy chưa, hoặc đặt biến môi trường "
            "MEP_AGENTS_API_BASE / sửa file config.json cạnh script "
            "nếu server chạy ở máy/địa chỉ khác.\n\nChi tiết: {}".format(API_BASE, e),
            title="Lỗi kết nối",
        )
        return
    except Exception as e:
        forms.alert("Lỗi không xác định khi gửi dữ liệu: " + str(e), title="Lỗi API")
        return

    message = result_json.get("message", "")
    boq_filename = result_json.get("boq_filename")
    if boq_filename:
        message += "\n\nLink tải BOQ: {}/api/v1/revit/download/{}".format(API_BASE, boq_filename)
    forms.alert("Phân tích thành công!\n\n" + message, title="Swarm AI Report")


if __name__ == "__main__":
    main()

#! python3
# -*- coding: utf-8 -*-
"""
Gửi dữ liệu MEP từ Revit sang FastAPI Cloud để phân tích bằng Bầy đàn AI.
"""
import json
import urllib.request  # Shebang "#! python3" ở trên buộc pyRevit chạy script này bằng
                        # engine CPython3 (không phải IronPython 2.7.7) -> phải dùng
                        # urllib.request của Python 3, KHÔNG PHẢI urllib2 (module này
                        # không tồn tại ở Python 3, từng khiến script lỗi ngay khi chạy
                        # thật trong Revit dù mọi test offline đều pass).
from pyrevit import revit, DB, UI, forms

# Cấu hình máy chủ AI
API_URL = "http://localhost:8083/api/v1/revit/analyze"

doc = revit.doc

def get_mep_elements():
    # Thu thập Ống gió (Ducts), Ống nước (Pipes), Phụ kiện, Thiết bị Cơ điện
    categories = [
        DB.BuiltInCategory.OST_DuctCurves,
        DB.BuiltInCategory.OST_DuctFitting,
        DB.BuiltInCategory.OST_PipeCurves,
        DB.BuiltInCategory.OST_PipeFitting,
        DB.BuiltInCategory.OST_MechanicalEquipment,
    ]
    
    elements_data = []
    
    for cat in categories:
        collector = DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType()
        for el in collector:
            el_dict = {
                "id": el.Id.IntegerValue,
                "category": el.Category.Name if el.Category else "Unknown",
                "name": el.Name
            }
            # Lấy chiều dài (nếu có) và đổi sang mm (Revit dùng feet)
            param_length = el.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)
            if param_length:
                el_dict["length_mm"] = param_length.AsDouble() * 304.8
                
            elements_data.append(el_dict)
            
    return elements_data

def main():
    data = get_mep_elements()
    if not data:
        forms.alert("Không tìm thấy cấu kiện MEP nào trong mô hình này!", title="MEP-Agents")
        return
        
    payload = json.dumps({"elements": data, "project_name": doc.Title})
    
    forms.alert("Đã trích xuất {} cấu kiện MEP. Bắt đầu gửi cho AI Swarm...".format(len(data)), title="MEP-Agents")
    
    # Gửi HTTP POST request sang FastAPI
    try:
        req = urllib.request.Request(API_URL, data=payload.encode('utf-8'),
                                      headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        result_json = json.loads(response.read().decode('utf-8'))
        
        # Báo cáo kết quả bằng cửa sổ Revit (bao gồm đường dẫn tải file BOQ Excel thật,
        # nếu server đã lập được — xem build_revit_boq_excel trong src/qs_tools.py)
        forms.alert("Phân tích thành công!\n\n" + result_json.get("message", ""), title="Swarm AI Report")
    except Exception as e:
        forms.alert("Lỗi kết nối tới MEP-Agents Cloud: " + str(e), title="Lỗi API")

if __name__ == '__main__':
    main()

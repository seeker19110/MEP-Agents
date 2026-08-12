import json
import os
import urllib.error
import urllib.request

import win32com.client

# Truoc day URL bi hardcode "http://localhost:8083", nen script khong dung duoc
# voi server chay tren may/dia chi khac ma khong sua truc tiep code. Nay uu tien
# bien moi truong MEP_AGENTS_API_BASE, roi moi roi ve localhost mac dinh.
API_BASE = os.environ.get("MEP_AGENTS_API_BASE", "http://localhost:8083").rstrip("/")
API_URL = f"{API_BASE}/api/v1/autocad/analyze"
REQUEST_TIMEOUT_SEC = 30


def get_acad_document_path():
    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        doc = acad.ActiveDocument

        file_path = doc.FullName
        if not file_path:
            return None, "Bản vẽ chưa được lưu. Hãy lưu file (.dwg) trước khi chạy lệnh."

        return {"project_name": doc.Name, "file_path": file_path}, None

    except Exception as e:
        return None, f"Lỗi khi kết nối AutoCAD: {str(e)}"


def main():
    print("Đang kết nối với AutoCAD...")
    payload_dict, err = get_acad_document_path()

    if err:
        print(err)
        input("\nNhấn Enter để thoát...")
        return

    print(f"Đã xác nhận bản vẽ hiện tại: {payload_dict['file_path']}")
    print(f"Đang gửi lệnh xử lý siêu tốc lên MEP-Agents FastAPI ({API_BASE})...")

    payload = json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(API_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC)
        result = json.loads(response.read().decode("utf-8"))
        print("\n=== KẾT QUẢ TỪ SWARM AI ===")
        print(result.get("message", ""))
    except urllib.error.URLError as e:
        print(f"\nKhông kết nối được tới MEP-Agents Cloud tại {API_BASE}.")
        print("Kiểm tra server đã chạy chưa, hoặc đặt biến môi trường MEP_AGENTS_API_BASE")
        print("nếu server chạy ở máy/địa chỉ khác.")
        print(f"Chi tiết lỗi: {e}")
    except Exception as e:
        print("Lỗi không xác định:", str(e))

    input("\nNhấn Enter để thoát...")


if __name__ == "__main__":
    main()

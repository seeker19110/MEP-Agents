import json
import urllib.request
import win32com.client
import sys

API_URL = "http://localhost:8083/api/v1/autocad/analyze"

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
    print("Đang gửi lệnh xử lý siêu tốc lên MEP-Agents FastAPI...")
    
    payload = json.dumps(payload_dict).encode('utf-8')
    
    req = urllib.request.Request(API_URL, data=payload, headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        print("\n=== KẾT QUẢ TỪ SWARM AI ===")
        print(result.get("message", ""))
    except Exception as e:
        print("Lỗi API FastAPI:", str(e))
        
    input("\nNhấn Enter để thoát...")

if __name__ == "__main__":
    main()

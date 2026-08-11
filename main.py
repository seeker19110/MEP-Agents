import sys
from langchain_core.messages import HumanMessage
from src.graph import app
from src.config import settings
from src.logging_config import setup_logging

setup_logging()

def print_stream(stream):
    for s in stream:
        if "__end__" not in s:
            node_name = list(s.keys())[0]
            print(f"\n--- {node_name.upper()} ---")
            
            state = s[node_name]
            
            if "messages" in state and len(state["messages"]) > 0:
                last_msg = state["messages"][-1]
                print(f"Output: {last_msg.content}")
            
            if "next" in state:
                print(f"Điều hướng tới: {state['next']}")
                
            if "errors" in state and len(state["errors"]) > 0:
                print(f"CẢNH BÁO / LỖI: {state['errors'][-1]}")

def interactive_loop():
    print(f"=== KHỞI CHẠY HỆ SINH THÁI TƯ VẤN THIẾT KẾ MEPF TOÀN DIỆN ===")
    print(f"Mô hình đang sử dụng: {settings.model_name}")
    print("Các bộ phận trực: Mechanical (Cơ khí), Electrical (Điện), Plumbing (Nước), Firefighting (PCCC).")
    print("Các bộ phận hỗ trợ: QS (Bóc tách khối lượng), CAD (Triển khai bản vẽ), BIM (Quản lý 3D).")
    print("Kỹ sư trưởng (Reviewer) sẽ duyệt tất cả đầu ra.")
    print("Gõ 'quit' hoặc 'exit' để thoát.\n")
    
    config = {"configurable": {"thread_id": "mepf_full_room_session_1"}, "recursion_limit": 20}
    
    while True:
        try:
            user_input = input("\n[Khách hàng]: ")
            if user_input.lower() in ["quit", "exit"]:
                print("Đóng hệ thống MEPF...")
                break
            if not user_input.strip():
                continue
            
            initial_state = {"messages": [HumanMessage(content=user_input)]}
            
            # Chạy graph
            stream = app.stream(initial_state, config=config, stream_mode="updates")
            print_stream(stream)
            
            # Kiểm tra xem có bị ngắt (interrupt) để gọi tool không
            state = app.get_state(config)
            if state.next and state.next[0] == "tools":
                print("\n[HỆ THỐNG] Kỹ sư đang muốn sử dụng công cụ (Tool) để đọc/ghi file.")
                approval = input("Bạn có cho phép thực thi không? (y/n): ")
                if approval.lower() == 'y':
                    print("\n[HỆ THỐNG] Đã phê duyệt. Đang thực thi công cụ...")
                    stream = app.stream(None, config=config, stream_mode="updates")
                    print_stream(stream)
                else:
                    print("\n[HỆ THỐNG] Đã hủy yêu cầu gọi công cụ.")
            
            print("\n" + "="*60)
            
        except KeyboardInterrupt:
            print("\nĐóng hệ thống...")
            break
        except Exception as e:
            print(f"\nĐã có lỗi xảy ra: {e}")

if __name__ == "__main__":
    if not settings.openai_api_key:
        print("LỖI: Chưa cấu hình OPENAI_API_KEY trong file .env")
        sys.exit(1)
        
    interactive_loop()

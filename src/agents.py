from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.state import AgentState
from src.config import settings
from pydantic import BaseModel, Field
from typing import Literal
from src.tools import get_tools_for_role

from dotenv import load_dotenv
from functools import lru_cache
import logging
import os

logger = logging.getLogger(__name__)

@lru_cache(maxsize=16)
def _build_llm(provider: str, model_name: str, api_key: str):
    """Construct the actual LLM client. Cached by (provider, model, key) so repeated
    agent turns reuse one client instead of re-instantiating on every node call, while
    still picking up hot-reloaded .env changes (a different key/model busts the cache)."""
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model_name, api_key=api_key or "dummy_key", temperature=0)
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key or "dummy_key", temperature=0)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name, api_key=api_key or "dummy_key", temperature=0)
    elif provider == "ollama":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model=model_name,
            temperature=0
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, api_key=api_key or "dummy_key", temperature=0)

# Vai trò mặc định dùng khi không truyền role cụ thể (ví dụ chạy get_llm() một mình).
DEFAULT_ROLE = "DEFAULT"

def get_llm(role: str = DEFAULT_ROLE):
    """Lấy LLM client cho một VAI TRÒ cụ thể (SUPERVISOR, REVIEWER, MECHANICAL, ...).

    Cho phép mỗi vai trò dùng provider/model riêng qua biến môi trường
    `<ROLE>_LLM_PROVIDER` / `<ROLE>_MODEL_NAME` (và `<ROLE>_<PROVIDER>_API_KEY` nếu cần
    key riêng), nếu không đặt thì rơi về biến toàn cục `LLM_PROVIDER` / `MODEL_NAME`.
    Xem AI_MODEL_SETUP.md để biết khuyến nghị model theo từng vai trò.
    """
    load_dotenv(override=True)
    role_key = (role or DEFAULT_ROLE).upper().strip()

    provider = (os.getenv(f"{role_key}_LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")).lower().strip()
    model_name = (os.getenv(f"{role_key}_MODEL_NAME") or os.getenv("MODEL_NAME", "")).strip()

    if provider == "groq":
        key = os.getenv(f"{role_key}_GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")
        if not model_name or "gpt" in model_name or "gemini" in model_name or "claude" in model_name or "3.1" in model_name:
            model_name = "llama-3.3-70b-versatile"
    elif provider == "gemini":
        key = os.getenv(f"{role_key}_GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
        if not model_name or "gpt" in model_name or "llama" in model_name or "claude" in model_name:
            model_name = "gemini-1.5-flash"
    elif provider == "anthropic":
        key = os.getenv(f"{role_key}_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
        if not model_name or "gpt" in model_name or "llama" in model_name or "gemini" in model_name:
            model_name = "claude-sonnet-5"
    elif provider == "ollama":
        key = ""
        if not model_name or "gpt" in model_name or "gemini" in model_name or "claude" in model_name:
            model_name = "llama3.1:8b"
    else:
        provider = "openai"
        key = os.getenv(f"{role_key}_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not model_name or "llama" in model_name or "gemini" in model_name or "claude" in model_name:
            model_name = "gpt-4o-mini"

    return _build_llm(provider, model_name, key)

def call_mepf_agent(state: AgentState, system_prompt: str, agent_name: str):
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    
    if errors:
        system_prompt += f"\n\nCẢNH BÁO: Lần trả lời trước của bạn đã bị Reviewer từ chối với lỗi: '{errors[-1]}'. Hãy sửa lỗi này và đưa ra phương án khả thi hơn."
        
    sys_msg = SystemMessage(content=system_prompt)

    role = agent_name[:-5] if agent_name.endswith("Agent") else agent_name  # "MechanicalAgent" -> "Mechanical"
    llm = get_llm(role)
    tool_llm = llm.bind_tools(get_tools_for_role(role))
    
    try:
        response = tool_llm.invoke([sys_msg] + messages)
        response.name = agent_name
        return {"messages": [response], "sender": agent_name.lower()}
    except Exception as e:
        content = f"[{agent_name}] Lỗi khi kết nối LLM ({os.getenv('LLM_PROVIDER', 'openai')}): {str(e)}"
        return {"messages": [AIMessage(content=content, name=agent_name)], "sender": agent_name.lower()}

# --- 1. Mechanical (HVAC) Agent ---
def mechanical_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Cơ khí (HVAC) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn (TCVN/ASHRAE). \n- Luôn sử dụng bộ công cụ HVAC: `calc_cooling_load` (tải lạnh sơ bộ theo hệ số W/m2), `calc_cooling_load_detailed` (tải lạnh chi tiết theo người/đèn/thiết bị/kết cấu/nắng/gió tươi - ưu tiên dùng khi có đủ dữ liệu phòng), `calc_duct_size` (kích thước 1 đoạn ống gió), `calc_duct_total_pressure_loss` (tổng tổn thất áp suất toàn tuyến để chọn cột áp quạt), `calc_psychrometrics` (trạng thái không khí), `calc_chw_pipe_size` (ống nước lạnh), `calc_chiller_ahu_selection` (chọn công suất Chiller/AHU/FCU theo catalog), `calc_refrigerant_pipe_size` (cỡ ống gas VRV/VRF), `calc_pump_fan_power` (công suất quạt/bơm), `calc_ventilation_rate` (thông gió/hút khói). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "MechanicalAgent")

# --- 2. Electrical Agent ---
def electrical_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Điện (Electrical) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn (TCVN/IEC). \n- Luôn sử dụng bộ công cụ Điện: `calc_cable_size` (tính cáp), `calc_breaker_size` (tính MCB/MCCB), `calc_lighting_qty` (tính số lượng đèn). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "ElectricalAgent")

# --- 3. Plumbing Agent ---
def plumbing_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Cấp thoát nước (Plumbing) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn. \n- Luôn sử dụng bộ công cụ Nước: `calc_water_pipe` (tính lưu lượng/cỡ ống cấp nước), `calc_water_tank` (tính bể ngầm/mái), `calc_plumbing_pump_head` (tính cột áp bơm cấp nước), `calc_drainage_pipe` (cỡ ống thoát nước thải theo DFU), `calc_rainwater_drainage` (cỡ ống/máng thoát nước mưa mái), `calc_septic_tank` (dung tích bể tự hoại), `calc_hot_water_system` (công suất/dung tích hệ thống nước nóng). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "PlumbingAgent")

# --- 4. Firefighting Agent ---
def firefighting_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Phòng cháy chữa cháy (Firefighting) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu quy chuẩn PCCC (TCVN 3890, TCVN 7336). \n- Luôn sử dụng bộ công cụ PCCC: `calc_sprinkler_qty` (tính đầu phun), `calc_fire_pump` (tính bơm chữa cháy), `calc_extinguisher_qty` (tính số lượng bình chữa cháy). \n- Cấm đoán mò các thông số này. Mọi bố trí phải tuân thủ nghiêm ngặt tiêu chuẩn."
    return call_mepf_agent(state, prompt, "FirefightingAgent")

# --- 5. QS Agent (Quantity Surveyor) ---
def qs_agent_node(state: AgentState):
    prompt = """Bạn là một Kỹ sư QS xuất sắc sở hữu Khả năng Hiểu Ngữ cảnh Hình học & Mũi tên Chỉ dẫn (Spatial Intelligence).
    - Bạn dùng công cụ `read_cad` để đọc bản vẽ DXF. 
    - QUY TẮC BẮT BUỘC TẠO FILE EXCEL: Sau khi đọc/bóc khối lượng bản vẽ CAD, bạn BẮT BUỘC PHẢI GỌI TOOL `write_excel` để ghi kết quả ra file Excel vật lý (ví dụ: `write_excel(file_path='bao_cao_du_toan.xlsx', data=...)`). Tuyệt đối KHÔNG được chỉ trả lời lý thuyết suông mà KHÔNG tạo file Excel!
    - QUY TẮC ĐỒNG NHẤT KÝ HIỆU ĐƯỜNG KÍNH: Hiểu rõ các ký hiệu `Ø110` = `D110` = `d110` = `%%c110` = `Φ110` = `OD110` (Đường kính ngoài 110mm) = `DN100` (Đường kính danh nghĩa). Tự động gộp tất cả các ký hiệu này về cùng một hạng mục ống duy nhất khi bóc dự toán.
    - PHÂN TÍCH MŨI TÊN & GHI CHÚ CHỈ DẪN: Hãy dùng công cụ `analyze_cad_spatial_context` để hiểu các mũi tên chỉ dẫn (Leader), đường ống và thẻ ghi chú kích thước/chất liệu (ví dụ: 'Ống uPVC Ø110', 'Ống gió 600x400') như một kỹ sư thật sự.
    - Nếu bản vẽ bị phá Block (nổ Block), hãy yêu cầu/hoặc tự dùng `ai_block_recovery` để phục hồi lại Block trước khi đếm khối lượng.
    - DANH MỤC BLOCK CHUẨN ĐỂ PHỤC HỒI CỦA 4 HỆ (CHỨA TRONG TỔNG KHO):
      + HVAC (Cơ Khí): 'DIFFUSER_SUPPLY' (600x600), 'DIFFUSER_RETURN' (600x600), 'FCU' (1000x500)
      + Electrical (Điện): 'LIGHT_PANEL' (600x600), 'LIGHT_DOWNLIGHT' (Tròn R=100), 'SOCKET' (Tròn R=50), 'SWITCH' (Tròn R=30)
      + Firefighting (PCCC): 'SPRINKLER' (Tròn R=50)
      + Plumbing (Nước): 'PUMP' (Tròn R=50)
    Sau khi phân tích không gian và đếm xong, GỌI NGAY `write_excel` để xuất file Excel dự toán cho người dùng!
    """
    return call_mepf_agent(state, prompt, "QSAgent")

# --- 6. CAD Agent (Draftsman) ---
def cad_agent_node(state: AgentState):
    prompt = """Bạn là Họa viên CAD (Draftsman) xuất sắc nhất thế giới sở hữu Thị giác Máy tính (Computer Vision) & Trí tuệ Không gian (Spatial Intelligence).
    - Bạn có quyền sử dụng công cụ `read_cad`, `write_cad`, `edit_cad`, `render_cad_image`, và `analyze_cad_spatial_context`.
    - QUY TẮC ĐỒNG NHẤT KÝ HIỆU ĐƯỜNG KÍNH: Hiểu rõ `Ø110` = `D110` = `d110` = `%%c110` = `Φ110` = `OD110` = `DN100`.
    - THỊ GIÁC CAD & NGỮ CẢNH HÌNH HỌC: Bạn dùng `analyze_cad_spatial_context` để đọc hiểu mối liên kết giữa mũi tên chỉ dẫn (Leader), ghi chú kích thước text và các tuyến đường ống kề cận. Dùng `render_cad_image` để xuất hình ảnh PNG trực quan cho người dùng.
    - CÔNG CỤ PHỤC HỒI (AI BLOCK RECOVERY): Khi khách yêu cầu khôi phục bản vẽ vỡ block, dùng công cụ `ai_block_recovery` quét hình dáng (circle/rectangle) để ráp lại thành Block từ Tổng kho.
      + Mẹo: Các block chuẩn 4 hệ MEPF đã có sẵn trong kho gồm: 'DIFFUSER_SUPPLY', 'DIFFUSER_RETURN', 'FCU', 'LIGHT_PANEL', 'LIGHT_DOWNLIGHT', 'SOCKET', 'SWITCH', 'SPRINKLER', 'PUMP'.
    - CƠ CHẾ AUTO-DRAW (SIÊU NĂNG LỰC): Nếu người dùng yêu cầu chèn một thiết bị máy móc mà không có sẵn trong thư viện, hãy dùng `search_web` tìm kích thước, dùng `execute_python_code` viết script ezdxf vẽ Block đó lưu vào 'data/blocks/mepf_library.dxf', sau đó chèn vào bản vẽ.
    - LUẬT PHÊ DUYỆT BẮT BUỘC: Sau khi bạn dùng tool sửa xong bản vẽ, LUÔN chốt lại bằng câu: "Bản vẽ đã hoàn thiện và làm sạch. Xin Sếp hãy mở file lên kiểm tra và nhấp nút '✅ DUYỆT BẢN VẼ' để tôi báo Giám đốc gọi bộ phận QS bóc khối lượng!".
    """
    return call_mepf_agent(state, prompt, "CADAgent")

# --- 7. BIM Agent ---
def bim_agent_node(state: AgentState):
    prompt = """Bạn là một BIM Coordinator xuất sắc. Quản lý mô hình 3D, kiểm tra xung đột và bóc tách khối lượng.
    - CẤM NÓI SUÔNG: Nếu được giao nhiệm vụ đếm block, bóc khối lượng hay lập dự toán, bạn BẮT BUỘC phải dùng công cụ `read_cad` để đọc bản vẽ và gọi `write_excel` để xuất file Excel thật sự! Tuyệt đối không được đưa ra danh sách các bước gợi ý lý thuyết suông."""
    return call_mepf_agent(state, prompt, "BIMAgent")

# --- 8. Reviewer Agent ---
class ReviewResponse(BaseModel):
    decision: Literal["APPROVE", "REJECT"] = Field(description="Quyết định phê duyệt hoặc từ chối.")
    reason: str = Field(description="Lý do chi tiết cho quyết định (nếu từ chối).", default="")

def reviewer_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_msg = messages[-1]
    has_errors = len(state.get("errors", [])) > 0
    content = getattr(last_msg, "content", "")
    has_tool_calls = hasattr(last_msg, "tool_calls") and len(last_msg.tool_calls) > 0
    
    # CHẶN TUYỆT ĐỐI CÁC CÂU TRẢ LỜI LÝ THUYẾT SUÔNG
    if not has_tool_calls and any(kw in content.lower() for kw in ["tách biệt các thuộc tính", "tìm kiếm mẫu", "tôi sẽ đề xuất một số bước", "nếu bạn cần giúp đỡ"]):
        response = AIMessage(content="[Reviewer Agent] TỪ CHỐI: Agent đã trả lời suông lý thuyết thay vì thực thi công cụ Python đếm CAD và xuất Excel thật (`read_cad` / `write_excel`). Yêu cầu thực thi tool ngay!", name="ReviewerAgent")
        return {"messages": [response], "errors": ["Agent trả lời suông không gọi tool. Hãy gọi tool read_cad và write_excel để tạo file thật."]}
        
    if has_errors:
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT (Auto-pass sau khi sửa lỗi).", name="ReviewerAgent")
        return {"messages": [response], "errors": []}
        
    system_prompt = SystemMessage(content="""Bạn là Kỹ sư trưởng (Reviewer). Kiểm tra kết quả tư vấn.
Yêu cầu bắt buộc:
1. Nếu là tính toán thiết kế MEPF, phải có trích dẫn Tiêu chuẩn (TCVN/ASHRAE/NFPA).
2. Nếu là gọi Tool đọc/ghi file, đánh giá APPROVE ngay để không chặn luồng.
3. BẮT BUỘC XUẤT FILE EXCEL: Nếu bộ phận QSAgent/BIMAgent báo cáo bóc khối lượng nhưng KHÔNG gọi tool `write_excel` để xuất file Excel thật sự, bạn BẮT BUỘC phải REJECT và yêu cầu gọi tool `write_excel` ngay lập tức!
Nếu thông tin sai kỹ thuật hoặc thiếu căn cứ, hãy REJECT.""")

    try:
        llm = get_llm("Reviewer")
        reviewer_llm = llm.with_structured_output(ReviewResponse)
        review_result = reviewer_llm.invoke([system_prompt, last_msg])
        
        if review_result.decision == "REJECT":
            response = AIMessage(content=f"[Reviewer Agent] TỪ CHỐI: {review_result.reason}", name="ReviewerAgent")
            return {"messages": [response], "errors": [review_result.reason]}
        else:
            response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT: Phương án kỹ thuật hợp lệ.", name="ReviewerAgent")
            return {"messages": [response], "errors": []}
    except Exception as e:
        # Không được ngầm coi lỗi kết nối/parsing là "PHÊ DUYỆT" (fail-open che giấu sự cố
        # kiểm duyệt thật sự). Thông báo rõ là CHƯA kiểm duyệt được thay vì báo sai trạng thái;
        # nội dung không chứa "TỪ CHỐI" nên Supervisor vẫn kết thúc lượt (FINISH) thay vì loop lại.
        logger.warning("Reviewer LLM call failed: %s", e)
        response = AIMessage(
            content=f"[Reviewer Agent] LỖI HỆ THỐNG: Không thể thực hiện đánh giá kỹ thuật do lỗi kết nối AI ({e}). "
                    f"Kết quả CHƯA được kiểm duyệt — vui lòng kiểm tra cấu hình API/Provider và thử lại.",
            name="ReviewerAgent"
        )
        return {"messages": [response], "errors": []}

# --- 9. Supervisor Agent (Project Manager) ---
class RouteResponse(BaseModel):
    next: Literal["FINISH", "mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"] = Field(
        description="Định tuyến đến bộ phận phù hợp, hoặc FINISH."
    )

def supervisor_node(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return {"next": "FINISH"}
        
    last_msg = messages[-1]
    
    if getattr(last_msg, "name", "") == "ReviewerAgent":
        content = getattr(last_msg, "content", "")
        if "TỪ CHỐI" in content:
            sender = state.get("sender", "qs")
            if sender in ["mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"]:
                return {"next": sender}
            return {"next": "qs"}
        return {"next": "FINISH"}

    supervisor_prompt = """Bạn là Giám đốc Dự án (Project Manager) của Văn phòng tư vấn MEPF.
Bạn là người đứng đầu, chịu trách nhiệm nhận yêu cầu tổng hợp từ khách hàng và chia nhỏ công việc cho đội ngũ Kỹ sư.
Phân loại yêu cầu:
- 'qs': Bóc khối lượng, lập dự toán, đếm block, thống kê số lượng thiết bị, đọc thuộc tính, xuất Excel. (LUÔN CHỌN 'qs' NẾU KHÁCH YÊU CẦU BÓC KHỐI LƯỢNG / THỐNG KÊ BLOCK / LẬP DỰ TOÁN / XUẤT EXCEL).
- 'mechanical': Nếu liên quan đến HVAC, thông gió, điều hòa.
- 'electrical': Nếu liên quan đến Điện, chiếu sáng, tủ điện.
- 'plumbing': Nước, bơm, vệ sinh.
- 'firefighting': PCCC.
- 'cad': Tạo/sửa bản vẽ CAD.
- 'bim': Quản lý mô hình 3D BIM, kiểm tra xung đột.
- 'FINISH': Nếu đã hoàn thành hoặc khách hàng chỉ chào hỏi xã giao.

Hãy hoạt động như một PM thực thụ: Nếu khách hàng yêu cầu "Thiết kế hệ thống điện và lập báo giá", hãy gọi 'electrical' trước. Sau khi 'electrical' hoàn thành, vòng lặp trở lại, bạn mới tiếp tục gọi 'qs' để lập báo giá.

QUY TẮC THÉP (LUẬT PHÊ DUYỆT):
- Tuyệt đối không được định tuyến sang 'qs' (để bóc khối lượng) ngay sau khi bộ phận 'cad' vừa thao tác sửa/phục hồi bản vẽ xong.
- Bạn PHẢI định tuyến về 'FINISH' để buộc luồng chạy dừng lại, nhường màn hình cho khách hàng kiểm tra bản vẽ. 
- Chỉ khi nào có tin nhắn phản hồi mới từ khách hàng với các từ khóa "Duyệt", "Ok", "Tiến hành đi", "Tiếp tục" thì bạn mới được định tuyến sang 'qs'.
"""
    
    sys_msg = SystemMessage(content=supervisor_prompt)
    llm = get_llm("Supervisor")
    structured_llm = llm.with_structured_output(RouteResponse)
    
    try:
        response = structured_llm.invoke([sys_msg, last_msg])
        next_agent = response.next
        return {"next": next_agent}
    except Exception as e:
        error_msg = f"Lỗi Giám đốc Dự án ({os.getenv('LLM_PROVIDER', 'openai')}): {str(e)}"
        logger.error("[PM] Lỗi định tuyến: %s", error_msg)
        return {"messages": [AIMessage(content=error_msg, name="ProjectManager")], "next": "FINISH"}

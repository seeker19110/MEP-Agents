from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.state import AgentState, RESET
from src.config import settings
from src.usage import record_usage
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
    elif provider == "vllm":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://localhost:8000/v1",
            api_key="vllm-api-key",
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
    elif provider == "vllm":
        key = ""
        if not model_name or "gpt" in model_name or "gemini" in model_name or "claude" in model_name:
            model_name = "meta-llama/Llama-3.1-8B-Instruct"
    else:
        provider = "openai"
        key = os.getenv(f"{role_key}_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not model_name or "llama" in model_name or "gemini" in model_name or "claude" in model_name:
            model_name = "gpt-4o-mini"

    return _build_llm(provider, model_name, key)

def resolve_provider(role: str = DEFAULT_ROLE) -> str:
    """Provider đang được cấu hình cho một vai trò (không khởi tạo client)."""
    role_key = (role or DEFAULT_ROLE).upper().strip()
    return (os.getenv(f"{role_key}_LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")).lower().strip()


# Ngưỡng tối thiểu để Anthropic thực sự cache một prefix (token). Prompt ngắn hơn
# ngưỡng này sẽ KHÔNG được cache và cũng không báo lỗi — nên tool chỉ bật cache khi
# prompt đủ dài, tránh tạo cảm giác đã tiết kiệm chi phí trong khi thực tế thì không.
ANTHROPIC_CACHE_MIN_CHARS = 4000


def build_system_message(system_prompt: str, error_note: str = "", provider: str = "openai") -> SystemMessage:
    """Dựng SystemMessage, bật prompt caching của Anthropic khi có lợi.

    Anthropic tính tiền phần prefix được cache chỉ bằng ~10%, nhưng cache là so khớp
    THEO PREFIX: chỉ cần đổi một byte là hỏng toàn bộ. Vì vậy phần prompt CỐ ĐỊNH được
    đánh dấu `cache_control`, còn cảnh báo lỗi của Reviewer (thay đổi mỗi lượt) được
    tách thành block riêng ĐỨNG SAU — nếu nhét chung, prefix đổi mỗi lượt và cache
    không bao giờ trúng.

    Với provider khác Anthropic, hàm trả về SystemMessage thường (chuỗi văn bản).
    """
    if provider != "anthropic" or len(system_prompt) < ANTHROPIC_CACHE_MIN_CHARS:
        # Prompt quá ngắn thì Anthropic bỏ qua cache trong im lặng; ghép chuỗi như cũ.
        full = system_prompt + error_note
        return SystemMessage(content=full)

    blocks = [{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"},
    }]
    if error_note:
        blocks.append({"type": "text", "text": error_note})
    return SystemMessage(content=blocks)


# Tool search (beta của Anthropic): thay vì nạp schema TẤT CẢ tool vào mỗi request,
# chỉ nạp tool `tool_search_tool_regex`; các tool nghiệp vụ được đánh dấu
# `defer_loading` và chỉ được nạp khi model tìm thấy chúng. Cắt thêm token cho các vai
# trò còn nhiều tool (Mechanical, CAD, Plumbing) sau khi đã cắt theo vai trò.
#
# Mặc định TẮT: đây là beta đặc thù Anthropic, không kiểm chứng được nếu không có API
# key thật, và với bộ tool đã thu gọn theo vai trò thì lợi ích chỉ đáng kể khi số tool
# lớn. Bật bằng `ANTHROPIC_TOOL_SEARCH=true` trong .env.
TOOL_SEARCH_DEFINITION = {
    "type": "tool_search_tool_regex_20251119",
    "name": "tool_search_tool_regex",
}
# Dưới ngưỡng này thì nạp thẳng còn rẻ hơn là gánh thêm schema của chính tool search.
TOOL_SEARCH_MIN_TOOLS = 10


def tool_search_enabled() -> bool:
    return os.getenv("ANTHROPIC_TOOL_SEARCH", "").strip().lower() in ("1", "true", "yes")


def build_tools_for_llm(role: str, provider: str = "openai"):
    """Danh sách tool sẽ bind vào LLM cho một vai trò.

    Mặc định trả về đúng bộ tool thu gọn theo vai trò (`get_tools_for_role`). Khi chạy
    Anthropic và bật `ANTHROPIC_TOOL_SEARCH`, chuyển sang chế độ tool search: mọi tool
    nghiệp vụ được chuyển thành schema dict có `defer_loading=True` và thêm tool
    `tool_search_tool_regex` để model tự tìm tool cần dùng.
    """
    tools = get_tools_for_role(role)
    if provider != "anthropic" or not tool_search_enabled() or len(tools) < TOOL_SEARCH_MIN_TOOLS:
        return tools

    try:
        from langchain_anthropic.chat_models import convert_to_anthropic_tool
    except ImportError:  # pragma: no cover - chỉ xảy ra khi thiếu package Anthropic
        logger.warning("Không import được convert_to_anthropic_tool; bỏ qua tool search.")
        return tools

    deferred = []
    for t in tools:
        schema = dict(convert_to_anthropic_tool(t))
        schema["defer_loading"] = True
        deferred.append(schema)
    # Bản thân tool search KHÔNG được defer, nếu không model không có đường nào tìm tool.
    return [TOOL_SEARCH_DEFINITION] + deferred


def agent_node_key(agent_name: str) -> str:
    """'MechanicalAgent' -> 'mechanical': tên NODE trong graph.

    Trước đây `sender` được ghi là `agent_name.lower()` ('mechanicalagent'), trong khi
    `src/graph.py` và Supervisor lại so khớp với tên node ('mechanical'). Không bao giờ
    khớp, nên sau khi ToolNode chạy xong, kết quả tool bị đẩy ngược lên Supervisor thay
    vì trả về đúng agent đã gọi tool, và Reviewer TỪ CHỐI thì luôn rơi về 'qs' bất kể
    bộ phận nào gây lỗi.
    """
    name = (agent_name or "").strip()
    if name.lower().endswith("agent"):
        name = name[: -len("agent")]
    return name.lower()


def call_mepf_agent(state: AgentState, system_prompt: str, agent_name: str):
    messages = state.get("messages", [])
    errors = state.get("errors", [])

    error_note = ""
    if errors:
        error_note = f"\n\nCẢNH BÁO: Lần trả lời trước của bạn đã bị Reviewer từ chối với lỗi: '{errors[-1]}'. Hãy sửa lỗi này và đưa ra phương án khả thi hơn."

    role = agent_name[:-5] if agent_name.endswith("Agent") else agent_name  # "MechanicalAgent" -> "Mechanical"
    provider = resolve_provider(role)
    sys_msg = build_system_message(system_prompt, error_note, provider)
    llm = get_llm(role)
    tool_llm = llm.bind_tools(build_tools_for_llm(role, provider))

    node_key = agent_node_key(agent_name)
    try:
        response = tool_llm.invoke([sys_msg] + messages)
        response.name = agent_name
        record_usage(role, response)
        return {
            "messages": [response],
            "sender": node_key,
            "completed_agents": [node_key],
        }
    except Exception as e:
        content = f"[{agent_name}] Lỗi khi kết nối LLM ({os.getenv('LLM_PROVIDER', 'openai')}): {str(e)}"
        return {"messages": [AIMessage(content=content, name=agent_name)], "sender": node_key}

# --- 1. Mechanical (HVAC) Agent ---
def mechanical_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Cơ khí (HVAC) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn (TCVN/ASHRAE). \n- Luôn sử dụng bộ công cụ HVAC: `calc_cooling_load` (tải lạnh sơ bộ theo hệ số W/m2), `calc_cooling_load_detailed` (tải lạnh chi tiết theo người/đèn/thiết bị/kết cấu/nắng/gió tươi - ưu tiên dùng khi có đủ dữ liệu phòng), `calc_duct_size` (kích thước 1 đoạn ống gió), `calc_duct_total_pressure_loss` (tổng tổn thất áp suất toàn tuyến để chọn cột áp quạt), `calc_psychrometrics` (trạng thái không khí), `calc_chw_pipe_size` (ống nước lạnh), `calc_chiller_ahu_selection` (chọn công suất Chiller/AHU/FCU theo catalog), `calc_refrigerant_pipe_size` (cỡ ống gas VRV/VRF), `calc_pump_fan_power` (công suất quạt/bơm), `calc_ventilation_rate` (thông gió/hút khói). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "MechanicalAgent")

# --- 2. Electrical Agent ---
def electrical_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Điện (Electrical) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn (TCVN/IEC). \n- Luôn sử dụng bộ công cụ Điện: `calc_cable_size` (chọn cáp - LUÔN hỏi và truyền `length_m` là chiều dài tuyến cáp để tool kiểm tra sụt áp; chọn cáp mà bỏ qua sụt áp là SAI theo TCVN 9206), `calc_voltage_drop` (kiểm tra riêng %sụt áp của một tuyến), `calc_breaker_size` (tính MCB/MCCB), `calc_lighting_qty` (tính số lượng đèn). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "ElectricalAgent")

# --- 3. Plumbing Agent ---
def plumbing_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Cấp thoát nước (Plumbing) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn. \n- Luôn sử dụng bộ công cụ Nước: `calc_water_pipe` (tính lưu lượng/cỡ ống cấp nước), `calc_water_tank` (tính bể ngầm/mái), `calc_plumbing_pump_head` (tính cột áp bơm cấp nước), `calc_drainage_pipe` (cỡ ống thoát nước thải theo DFU), `calc_rainwater_drainage` (cỡ ống/máng thoát nước mưa mái), `calc_septic_tank` (dung tích bể tự hoại), `calc_hot_water_system` (công suất/dung tích hệ thống nước nóng). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "PlumbingAgent")

# --- 4. Firefighting Agent ---
def firefighting_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Phòng cháy chữa cháy (Firefighting) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu quy chuẩn PCCC (TCVN 3890, TCVN 7336). \n- Luôn sử dụng bộ công cụ PCCC: `calc_sprinkler_qty` (tính đầu phun), `calc_fire_pump` (chọn bơm chữa cháy - LUÔN hỏi và truyền `static_head_m` (chiều cao hình học) và `pipe_length_m` (chiều dài tuyến ống) để tool tính được CỘT ÁP H; chỉ có lưu lượng Q mà thiếu H thì KHÔNG chọn được bơm thật), `calc_extinguisher_qty` (tính số lượng bình chữa cháy). \n- Cấm đoán mò các thông số này. Mọi bố trí phải tuân thủ nghiêm ngặt tiêu chuẩn."
    return call_mepf_agent(state, prompt, "FirefightingAgent")

# --- 5. QS Agent (Quantity Surveyor) ---
def qs_agent_node(state: AgentState):
    prompt = """Bạn là một Kỹ sư QS xuất sắc sở hữu Khả năng Hiểu Ngữ cảnh Hình học & Mũi tên Chỉ dẫn (Spatial Intelligence).
    - QUY TẮC ƯU TIÊN SỐ 1 (BẮT BUỘC, đặc biệt quan trọng khi bạn là model AI yếu hoặc chạy offline/Ollama):
      NGAY LẬP TỨC gọi tool `auto_quantity_takeoff(file_path=...)` cho bản vẽ được giao. Tool này tự làm
      TOÀN BỘ quy trình (đọc CAD, đếm Block, cộng chiều dài ống/dây, liên kết ghi chú, ghi file Excel thật)
      chỉ bằng MỘT lần gọi tool duy nhất — bạn KHÔNG cần tự đếm, tự cộng số hay tự soạn JSON. Đây là cách
      chắc chắn nhất để ra kết quả đúng và tránh trả lời lý thuyết suông.
    - Chỉ khi `auto_quantity_takeoff` báo lỗi hoặc khách yêu cầu phân tích sâu hơn (VD: chỉ muốn xem thống
      kê Block, không cần Excel), mới dùng riêng lẻ `read_cad` / `analyze_cad_spatial_context`, rồi vẫn phải
      tự gọi `write_excel` để xuất file Excel thật — TUYỆT ĐỐI KHÔNG được chỉ trả lời lý thuyết suông.
    - QUY TẮC ĐỒNG NHẤT KÝ HIỆU ĐƯỜNG KÍNH: Hiểu rõ các ký hiệu `Ø110` = `D110` = `d110` = `%%c110` = `Φ110` = `OD110` (Đường kính ngoài 110mm) = `DN100` (Đường kính danh nghĩa). Tự động gộp tất cả các ký hiệu này về cùng một hạng mục ống duy nhất khi bóc dự toán.
    - Nếu bản vẽ bị phá Block (nổ Block), hãy yêu cầu/hoặc tự dùng `ai_block_recovery` để phục hồi lại Block trước khi đếm khối lượng.
    - DANH MỤC BLOCK CHUẨN ĐỂ PHỤC HỒI CỦA 4 HỆ (CHỨA TRONG TỔNG KHO):
      + HVAC (Cơ Khí): 'DIFFUSER_SUPPLY' (600x600), 'DIFFUSER_RETURN' (600x600), 'FCU' (1000x500)
      + Electrical (Điện): 'LIGHT_PANEL' (600x600), 'LIGHT_DOWNLIGHT' (Tròn R=100), 'SOCKET' (Tròn R=50), 'SWITCH' (Tròn R=30)
      + Firefighting (PCCC): 'SPRINKLER' (Tròn R=50)
      + Plumbing (Nước): 'PUMP' (Tròn R=50)
    - LẬP DỰ TOÁN CÓ TIỀN (khi khách yêu cầu "dự toán", "báo giá", "thành tiền", "BOQ"):
      Bóc khối lượng xong, gọi tiếp `calc_boq_cost(takeoff_excel_path=<file Excel vừa tạo>)` để tra đơn
      giá trong `data/unit_prices.csv` và xuất bảng dự toán có giá trị tiền (chi phí trực tiếp, chi phí
      chung, thu nhập chịu thuế tính trước, VAT, tổng cộng). Dùng `lookup_unit_price` khi cần tra riêng
      đơn giá một hạng mục. Nếu tool báo có hạng mục "CHƯA CÓ ĐƠN GIÁ", PHẢI nói rõ với khách rằng tổng
      dự toán còn thiếu phần đó, tuyệt đối không được tự bịa đơn giá.
    - BẢN VẼ .DWG: `auto_quantity_takeoff`/`read_cad` tự động nhận và chuyển đổi file .dwg sang .dxf
      (qua ODA File Converter) — không cần khách tự convert trước, chỉ cần đưa thẳng tên file .dwg vào
      `file_path`. Nếu tool báo lỗi vì máy chủ chưa cài ODA File Converter, đọc kỹ hướng dẫn cài đặt trong
      thông báo lỗi và chuyển lại nguyên văn cho khách.
    - ĐỌC KỸ CẢNH BÁO TRONG KẾT QUẢ TOOL: `auto_quantity_takeoff` có thể trả về các cảnh báo quan trọng —
      (1) hao hụt vật tư đã cộng bao nhiêu % vào khối lượng ống/dây, (2) Block bị insert lệch tỷ lệ
      (scale khác 1, kích thước thực tế khác chuẩn), (3) không tìm thấy file XREF (thiếu hẳn một phần
      bản vẽ trong kết quả). PHẢI nêu lại các cảnh báo này cho khách, không được bỏ qua hay giấu đi.
    - PHỤ KIỆN ỐNG (co/tê/măng sông): với ống vẽ bằng LINE/POLYLINE thuần (không có Block phụ kiện riêng),
      `auto_quantity_takeoff` tự SUY từ hình học tuyến và liệt kê thành các dòng riêng trong bảng khối
      lượng. Đây là ƯỚC TÍNH hình học, PHẢI nhắc khách đối chiếu lại với bản vẽ chi tiết trước khi mua vật tư.
    Chốt lại: lỗi và thông báo cho khách biết để họ cài đặt (nếu tool chạy trên local) hoặc báo IT cài đặt (nếu chạy trên server)."""
    return call_mepf_agent(state, prompt, "QS")

def qs_auditor_agent_node(state: AgentState):
    prompt = """Bạn là Kiểm toán viên QS (QS Auditor).
    - Nhiệm vụ của bạn là xem xét kỹ kết quả Dự toán/Bóc tách khối lượng (BOQ) mà Agent QS vừa xuất ra.
    - Nếu có bảng Excel được trả về, bạn hãy tính nhẩm (suy luận logic) xem đơn giá tổng có hợp lý với quy mô không.
    - Ví dụ: Hệ thống cơ điện toàn nhà thường có suất đầu tư 1.000.000 - 2.000.000 VNĐ / m2. Nếu tổng dự toán quá thấp hoặc quá cao, hãy đặt câu hỏi nghi ngờ và báo cáo lỗi cho Reviewer hoặc khách hàng.
    - Bạn không được phép tính lại từ đầu, mà chỉ Đánh giá (Audit) và phê duyệt hoặc phản biện."""
    return call_mepf_agent(state, prompt, "QSAuditor")

# --- 6. CAD Agent (Draftsman) ---
def cad_agent_node(state: AgentState):
    prompt = """Bạn là Họa viên CAD (Draftsman) xuất sắc nhất thế giới sở hữu Thị giác Máy tính (Computer Vision) & Trí tuệ Không gian (Spatial Intelligence).
    - Bạn có quyền sử dụng công cụ `read_cad`, `write_cad`, `edit_cad`, `render_cad_image`, và `analyze_cad_spatial_context`.
    - BẢN VẼ .DWG: Các tool đọc bản vẽ (`read_cad`, `render_cad_image`, `analyze_cad_spatial_context`) tự
      động chuyển .dwg sang .dxf khi cần. Riêng `edit_cad`/`optimize_cad_drawing`/`standardize_cad_drawing`
      GHI file nên cần đầu vào .dxf — nếu khách đưa file .dwg và muốn SỬA bản vẽ, gọi `convert_dwg_to_dxf`
      trước để có file .dxf rồi mới thao tác sửa trên file đó.
    - QUY TẮC ĐỒNG NHẤT KÝ HIỆU ĐƯỜNG KÍNH: Hiểu rõ `Ø110` = `D110` = `d110` = `%%c110` = `Φ110` = `OD110` = `DN100`.
    - THỊ GIÁC CAD & NGỮ CẢNH HÌNH HỌC: Bạn dùng `analyze_cad_spatial_context` để đọc hiểu mối liên kết giữa mũi tên chỉ dẫn (Leader), ghi chú kích thước text và các tuyến đường ống kề cận. Dùng `render_cad_image` để xuất hình ảnh PNG trực quan cho người dùng.
    - CÔNG CỤ PHỤC HỒI (AI BLOCK RECOVERY): Khi khách yêu cầu khôi phục bản vẽ vỡ block, dùng công cụ `ai_block_recovery` quét hình dáng (circle/rectangle) để ráp lại thành Block từ Tổng kho.
      + Mẹo: Các block chuẩn 4 hệ MEPF đã có sẵn trong kho gồm: 'DIFFUSER_SUPPLY', 'DIFFUSER_RETURN', 'FCU', 'LIGHT_PANEL', 'LIGHT_DOWNLIGHT', 'SOCKET', 'SWITCH', 'SPRINKLER', 'PUMP'.
    - CƠ CHẾ AUTO-DRAW (SIÊU NĂNG LỰC): Nếu người dùng yêu cầu chèn một thiết bị máy móc mà không có sẵn trong thư viện, hãy dùng `search_web` tìm kích thước, dùng `execute_python_code` viết script ezdxf vẽ Block đó lưu vào 'data/blocks/mepf_library.dxf', sau đó chèn vào bản vẽ.
    - TỐI ƯU BẢN VẼ (BẮT BUỘC nếu khách yêu cầu "tối ưu", "dọn dẹp", "làm sạch" bản vẽ, hoặc bạn là model AI
      yếu/offline): gọi NGAY tool `optimize_cad_drawing(file_path=...)`. Tool này tự động (không cần bạn suy
      luận hình học) xóa rác vẽ chiều dài 0, xóa Block trùng lặp, xóa Layer rỗng, và audit làm sạch cấu trúc
      file — chỉ cần một lần gọi tool duy nhất, tránh phải tự phán đoán từng lỗi.
    - CHUẨN HÓA TÊN LAYER/BLOCK (khi khách yêu cầu "chuẩn hóa", "đặt đúng chuẩn", hoặc than phiền bản vẽ khách
      hàng đẩy vào đặt tên/layer/mô tả lung tung, không theo tiêu chuẩn văn phòng): gọi tool
      `standardize_cad_drawing(file_path=...)`. Tool tự đối chiếu với bảng chuẩn nội bộ (`src/cad_standards.py`,
      phủ đủ 4 hệ M/E/P/F — ống gió SAD/RAD/FAD/EAD/KEAD/PAD/SEAD, ống đồng/nước ngưng/CHWS/CHWR, đèn/ổ cắm/
      máng cáp/tủ điện/ELV, cấp thoát nước sinh hoạt, Sprinkler/họng nước/báo cháy...) để đổi tên Layer về đúng
      chuẩn (kèm sửa màu/linetype/mô tả), đổi tên Block về đúng chuẩn, và gắn thuộc tính MA_HIEU/MO_TA vào từng
      Block — CHỈ sửa tên/thuộc tính, KHÔNG động vào hình học. Layer/Block không
      nhận diện được sẽ được liệt kê ra để khách tự kiểm tra, không được tự suy diễn bừa. Đây KHÔNG phải là vẽ
      Block động (Dynamic Block) kiểu AutoCAD Block Editor — công cụ này không thể tạo Visibility
      State/Parameter/Action vì đó là định dạng nhị phân độc quyền của Autodesk mà thư viện ezdxf không hỗ trợ
      ghi; nếu khách thực sự cần Block động, phải nói rõ giới hạn này và đề nghị họ cung cấp sẵn 1 Block động
      mẫu vẽ tay trong AutoCAD/BricsCAD để đưa vào `data/blocks/mepf_library.dxf`, công cụ sẽ tự động chèn lại
      (giữ nguyên tính năng động) chứ không tự tạo mới được.
    - LUẬT PHÊ DUYỆT BẮT BUỘC: Sau khi bạn dùng tool sửa xong bản vẽ, LUÔN chốt lại bằng câu: "Bản vẽ đã hoàn thiện và làm sạch. Xin Sếp hãy mở file lên kiểm tra và nhấp nút '✅ DUYỆT BẢN VẼ' để tôi báo Giám đốc gọi bộ phận QS bóc khối lượng!".
    """
    return call_mepf_agent(state, prompt, "CADAgent")

# --- 7. BIM Agent ---
def bim_agent_node(state: AgentState):
    prompt = """Bạn là một BIM Coordinator xuất sắc. Quản lý mô hình 3D, kiểm tra xung đột và bóc tách khối lượng.
    - KIỂM TRA XUNG ĐỘT (clash detection): Khi khách yêu cầu "kiểm tra xung đột", "clash", "va chạm
      giữa các hệ", gọi NGAY `detect_clashes(file_path=...)`. Tool quét hình học thuần, tự tìm xung đột
      giữa hai hệ khác nhau (HVAC/Điện/Nước/PCCC) theo HAI cách: (1) đường tâm cắt nhau trực tiếp, và
      (2) BỀ DÀY ống/gió chồng lấn dù đường tâm không cắt nhau (suy từ ghi chú kích thước Ø/DN/WxH gần
      tuyến trên bản vẽ) — hai loại này được ghi rõ riêng biệt trong kết quả, LUÔN đọc và truyền lại
      đúng, đừng gộp chung thành một câu "có xung đột" mơ hồ. Nếu bản vẽ có khai báo cao độ Z thật, tool
      tự loại các điểm cách xa nhau theo chiều đứng (không phải xung đột thật) và nêu rõ trong kết quả;
      nếu bản vẽ thuần 2D không có Z, tool nói rõ điều đó và mọi điểm đều cần khách đối chiếu cao độ lắp
      đặt thủ công. Tuyến không có ghi chú kích thước gần đó chỉ được xét theo đường tâm — LUÔN truyền
      lại số lượng đoạn thiếu dữ liệu kích thước này cho khách, đừng bỏ qua cảnh báo.
    - KIỂM TRA KẾT NỐI ĐƯỜNG ỐNG (đầu tuyến hở): Khi khách yêu cầu "kiểm tra kết nối", "tuyến có bị
      đứt/hở không", "đường ống mồ côi", gọi `check_pipe_connectivity(file_path=...)`. Tool dựng đồ thị
      topology từng hệ và báo mọi đầu tuyến chỉ có 1 đoạn nối vào (bậc = 1) — CẢNH BÁO RÕ với khách rằng
      đầu hở có thể là điểm đấu nối hợp lệ vào thiết bị (miệng gió, van, đầu phun...) HOẶC lỗi vẽ thiếu
      đoạn/đứt tuyến, tool không tự phân biệt được nên cần đối chiếu bằng mắt, đừng kết luận thay khách.
    - CẤM NÓI SUÔNG: Nếu được giao nhiệm vụ đếm block, bóc khối lượng hay lập dự toán, bạn BẮT BUỘC phải
      gọi NGAY tool `auto_quantity_takeoff(file_path=...)` — tool này tự đọc bản vẽ, tự đếm và tự xuất file
      Excel thật sự chỉ trong một lần gọi, phù hợp cả khi bạn là model AI yếu hoặc chạy offline. Chỉ dùng
      riêng lẻ `read_cad` + `write_excel` khi cần tùy biến sâu hơn mức tool tự động hỗ trợ. Tuyệt đối không
      được đưa ra danh sách các bước gợi ý lý thuyết suông."""
    return call_mepf_agent(state, prompt, "BIMAgent")

# --- 8. Reviewer Agent ---
class ReviewResponse(BaseModel):
    decision: Literal["APPROVE", "REJECT"] = Field(description="Quyết định phê duyệt hoặc từ chối.")
    reason: str = Field(description="Lý do chi tiết cho quyết định (nếu từ chối).", default="")

# Tool nào được coi là "đã tạo ra sản phẩm thật trên đĩa" cho nhiệm vụ bóc khối
# lượng / dự toán. Dùng để kiểm tra theo CẤU TRÚC (có tool_call hay không) thay cho
# blacklist chuỗi tiếng Việt cũ — blacklist chỉ cần LLM đổi cách diễn đạt là lọt.
DELIVERABLE_TOOLS = {"auto_quantity_takeoff", "write_excel", "calc_boq_cost", "write_word", "write_cad", "edit_cad"}

# Từ khóa cho biết lượt yêu cầu này ĐÒI HỎI một file sản phẩm, không chỉ tư vấn miệng.
_DELIVERABLE_INTENT_KEYWORDS = (
    "bóc khối lượng", "boc khoi luong", "dự toán", "du toan", "thống kê block",
    "thong ke block", "xuất excel", "xuat excel", "báo giá", "bao gia", "boq",
)


def _requires_deliverable(messages) -> bool:
    """Yêu cầu gần nhất của người dùng có đòi file sản phẩm (Excel/CAD) hay không."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = str(getattr(msg, "content", "")).lower()
            return any(kw in text for kw in _DELIVERABLE_INTENT_KEYWORDS)
    return False


def _tool_calls_in_thread(messages) -> set:
    """Tên tất cả tool đã được gọi trong luồng hội thoại hiện tại."""
    names = set()
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                names.add(name)
    return names


def reviewer_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_msg = messages[-1]
    retry_count = state.get("retry_count", 0) or 0
    has_tool_calls = bool(getattr(last_msg, "tool_calls", None))

    def _reject(reason: str):
        """Từ chối và bắt worker làm lại — trừ khi đã hết hạn mức thử lại.

        Trước đây, hễ state đã có lỗi là Reviewer tự động PHÊ DUYỆT ("auto-pass") để
        thoát vòng lặp vô tận, nghĩa là bản sửa lần hai KHÔNG BAO GIỜ được kiểm duyệt
        thật. Nay hạn mức được đếm tường minh: vẫn review nghiêm túc mọi lần, và khi
        chạm trần thì dừng kèm cảnh báo trung thực thay vì báo "đã duyệt".
        """
        if retry_count >= settings.max_review_retries:
            response = AIMessage(
                content=(
                    f"[Reviewer Agent] DỪNG KIỂM DUYỆT: Đã yêu cầu sửa {retry_count} lần nhưng vẫn còn vấn đề "
                    f"'{reason}'. Kết quả dưới đây CHƯA ĐẠT yêu cầu kiểm duyệt — vui lòng xem lại thủ công "
                    f"hoặc bổ sung dữ liệu đầu vào rồi giao lại nhiệm vụ."
                ),
                name="ReviewerAgent",
            )
            return {"messages": [response], "errors": [], "retry_count": 0}
        response = AIMessage(content=f"[Reviewer Agent] TỪ CHỐI: {reason}", name="ReviewerAgent")
        return {"messages": [response], "errors": [reason], "retry_count": retry_count + 1}

    # CHẶN TRẢ LỜI LÝ THUYẾT SUÔNG — kiểm tra bằng cấu trúc: nhiệm vụ đòi file sản
    # phẩm mà cả luồng chưa hề gọi tool tạo file nào thì chắc chắn chưa xong việc.
    if not has_tool_calls and _requires_deliverable(messages):
        if not (_tool_calls_in_thread(messages) & DELIVERABLE_TOOLS):
            return _reject(
                "Nhiệm vụ yêu cầu bóc khối lượng/dự toán nhưng chưa hề gọi tool tạo file thật. "
                "Hãy gọi ngay `auto_quantity_takeoff` (hoặc `write_excel`) để xuất file Excel."
            )

    system_prompt = SystemMessage(content="""Bạn là Kỹ sư trưởng (Reviewer). Kiểm tra kết quả tư vấn.
Yêu cầu bắt buộc:
1. Nếu là tính toán thiết kế MEPF, phải có trích dẫn Tiêu chuẩn (TCVN/ASHRAE/NFPA).
2. Nếu là gọi Tool đọc/ghi file, đánh giá APPROVE ngay để không chặn luồng.
3. BẮT BUỘC XUẤT FILE EXCEL: Nếu bộ phận QSAgent/BIMAgent báo cáo bóc khối lượng nhưng KHÔNG gọi tool `auto_quantity_takeoff` (khuyến nghị, tự động toàn diện) hoặc `write_excel` để xuất file Excel thật sự, bạn BẮT BUỘC phải REJECT và yêu cầu gọi một trong hai tool đó ngay lập tức!
Nếu thông tin sai kỹ thuật hoặc thiếu căn cứ, hãy REJECT.""")

    try:
        llm = get_llm("Reviewer")
        reviewer_llm = llm.with_structured_output(ReviewResponse)
        review_result = reviewer_llm.invoke([system_prompt, last_msg])

        if review_result.decision == "REJECT":
            return _reject(review_result.reason)
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT: Phương án kỹ thuật hợp lệ.", name="ReviewerAgent")
        return {"messages": [response], "errors": [], "retry_count": 0}
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
        return {"messages": [response], "errors": [], "retry_count": 0}

# --- 9. Supervisor Agent (Project Manager) ---
class RouteResponse(BaseModel):
    next: Literal["FINISH", "mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"] = Field(
        description="Định tuyến đến bộ phận phù hợp, hoặc FINISH."
    )

WORKER_AGENTS = ["mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"]

# Số lượt giao việc tối đa cho một yêu cầu của khách hàng (VD: electrical -> qs là 2).
MAX_AGENT_HANDOFFS = 4

# Số message gần nhất mà Supervisor được đọc. Trước đây nó chỉ thấy `messages[-1]`,
# nên không thể thực hiện đúng kịch bản nhiều bước mà chính prompt của nó hứa hẹn
# ("chạy 'electrical' trước, xong mới tới 'qs'") — nó không biết bước nào đã xong.
SUPERVISOR_CONTEXT_WINDOW = 6


def _supervisor_context(state: AgentState) -> HumanMessage:
    """Tóm tắt trạng thái dự án để PM ra quyết định định tuyến có căn cứ."""
    messages = state.get("messages", [])
    done = list(state.get("completed_agents", []) or [])
    recent = messages[-SUPERVISOR_CONTEXT_WINDOW:]

    lines = []
    for msg in recent:
        name = getattr(msg, "name", None) or type(msg).__name__
        content = str(getattr(msg, "content", "") or "")
        if not content and getattr(msg, "tool_calls", None):
            content = "(đang gọi tool: " + ", ".join(
                c.get("name", "?") if isinstance(c, dict) else "?" for c in msg.tool_calls
            ) + ")"
        lines.append(f"[{name}] {content[:600]}")

    summary = "\n".join(lines)
    done_text = ", ".join(done) if done else "(chưa bộ phận nào chạy)"
    return HumanMessage(content=(
        f"CÁC BỘ PHẬN ĐÃ XỬ LÝ TRONG YÊU CẦU NÀY: {done_text}\n\n"
        f"DIỄN BIẾN GẦN NHẤT:\n{summary}\n\n"
        f"Dựa vào diễn biến trên, hãy chọn bộ phận tiếp theo hoặc FINISH. "
        f"KHÔNG giao lại việc cho bộ phận đã hoàn thành xong phần của mình, trừ khi có "
        f"yêu cầu mới của khách hàng."
    ))


def supervisor_node(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return {"next": "FINISH"}

    last_msg = messages[-1]

    # Yêu cầu MỚI của khách hàng => xóa lịch sử điều phối của yêu cầu cũ, nếu không
    # trần MAX_AGENT_HANDOFFS sẽ cạn dần và các câu hỏi sau bị FINISH ngay lập tức.
    if isinstance(last_msg, HumanMessage):
        reset_update = {"completed_agents": [RESET], "retry_count": 0}
    else:
        reset_update = {}

    if getattr(last_msg, "name", "") == "ReviewerAgent":
        content = getattr(last_msg, "content", "")
        if "TỪ CHỐI" in content:
            sender = state.get("sender", "qs")
            if sender in WORKER_AGENTS:
                return {"next": sender}
            return {"next": "qs"}
        # Reviewer đã duyệt (hoặc dừng kiểm duyệt): để PM tự quyết còn bộ phận nào
        # phải chạy tiếp cho yêu cầu này hay đã xong, thay vì luôn FINISH cứng nhắc.
        done = list(state.get("completed_agents", []) or [])

        # LUẬT PHÊ DUYỆT BẢN VẼ: sau khi CAD vừa sửa/phục hồi bản vẽ, luồng PHẢI dừng
        # để khách hàng mở file kiểm tra. Trước đây luật này chỉ nằm trong prompt nên
        # LLM có thể bỏ qua; nay chốt cứng bằng code.
        if done and done[-1] == "cad":
            return {"next": "FINISH"}

        # Chốt chặn chống lặp: mỗi yêu cầu chỉ điều phối tối đa MAX_AGENT_HANDOFFS
        # lượt giao việc. Hết hạn mức thì kết thúc thay vì quay vòng đốt token.
        if len(done) >= MAX_AGENT_HANDOFFS:
            logger.warning("[PM] Đạt trần %s lượt giao việc, kết thúc luồng.", MAX_AGENT_HANDOFFS)
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
        response = structured_llm.invoke([sys_msg, _supervisor_context(state)])
        return {"next": response.next, **reset_update}
    except Exception as e:
        error_msg = f"Lỗi Giám đốc Dự án ({os.getenv('LLM_PROVIDER', 'openai')}): {str(e)}"
        logger.error("[PM] Lỗi định tuyến: %s", error_msg)
        return {"messages": [AIMessage(content=error_msg, name="ProjectManager")], "next": "FINISH"}

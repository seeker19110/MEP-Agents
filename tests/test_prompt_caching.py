"""Prompt caching của Anthropic: cache phần prompt CỐ ĐỊNH, tách phần thay đổi ra sau."""
import pytest

from src.agents import ANTHROPIC_CACHE_MIN_CHARS, build_system_message, resolve_provider

LONG_PROMPT = "Bạn là Kỹ sư MEPF. " * 400  # đủ dài để vượt ngưỡng cache


def test_non_anthropic_provider_gets_plain_string():
    msg = build_system_message(LONG_PROMPT, "", provider="openai")
    assert isinstance(msg.content, str)


def test_anthropic_long_prompt_is_marked_cacheable():
    msg = build_system_message(LONG_PROMPT, "", provider="anthropic")
    assert isinstance(msg.content, list)
    assert msg.content[0]["cache_control"] == {"type": "ephemeral"}


def test_short_prompt_is_not_marked_since_anthropic_would_skip_it():
    """Prompt dưới ngưỡng KHÔNG được cache và Anthropic cũng không báo lỗi — đánh dấu
    cache_control ở đây chỉ tạo ảo giác tiết kiệm chi phí."""
    short = "Bạn là Kỹ sư Điện."
    assert len(short) < ANTHROPIC_CACHE_MIN_CHARS
    msg = build_system_message(short, "", provider="anthropic")
    assert isinstance(msg.content, str)


def test_volatile_error_note_is_separated_from_the_cached_prefix():
    """Cache là so khớp theo PREFIX: nếu ghép cảnh báo lỗi (đổi mỗi lượt) vào phần được
    cache thì prefix đổi liên tục và cache không bao giờ trúng."""
    msg = build_system_message(LONG_PROMPT, "\n\nCẢNH BÁO: thiếu TCVN.", provider="anthropic")
    assert len(msg.content) == 2
    cached, volatile = msg.content
    assert "cache_control" in cached
    assert "CẢNH BÁO" not in cached["text"]
    assert "cache_control" not in volatile
    assert "CẢNH BÁO" in volatile["text"]


def test_cached_prefix_is_byte_identical_across_turns_with_different_errors():
    """Cùng một prompt gốc phải cho ra prefix y hệt nhau dù lỗi khác nhau."""
    a = build_system_message(LONG_PROMPT, "\n\nlỗi A", provider="anthropic")
    b = build_system_message(LONG_PROMPT, "\n\nlỗi B", provider="anthropic")
    assert a.content[0]["text"] == b.content[0]["text"]


def test_no_error_note_produces_single_cached_block():
    msg = build_system_message(LONG_PROMPT, "", provider="anthropic")
    assert len(msg.content) == 1


@pytest.mark.parametrize("env_value,expected", [("anthropic", "anthropic"), ("GROQ", "groq"), (" Ollama ", "ollama")])
def test_resolve_provider_normalizes_env(monkeypatch, env_value, expected):
    monkeypatch.setenv("LLM_PROVIDER", env_value)
    monkeypatch.delenv("CAD_LLM_PROVIDER", raising=False)
    assert resolve_provider("CAD") == expected


def test_role_specific_provider_wins(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("CAD_LLM_PROVIDER", "anthropic")
    assert resolve_provider("CAD") == "anthropic"
    assert resolve_provider("QS") == "groq"


# --- Tool search (beta Anthropic) ---

def _expected_role_tools(role: str):
    """Bộ tool "không bật tool search" mà build_tools_for_llm phải trả về: tool của vai
    trò cộng thêm replace_blocks_by_mapping cho CAD/QS (xem docstring build_tools_for_llm)."""
    from src import agents
    tools = list(agents.get_tools_for_role(role))
    if role.lower().strip() in ("cad", "qs") and agents.replace_blocks_by_mapping not in tools:
        tools.append(agents.replace_blocks_by_mapping)
    return tools

def test_tool_search_off_by_default(monkeypatch):
    """Beta đặc thù Anthropic, không kiểm chứng được nếu thiếu API key thật => mặc định tắt."""
    monkeypatch.delenv("ANTHROPIC_TOOL_SEARCH", raising=False)
    from src import agents
    # So với bộ tool của vai trò như chính agents nhìn thấy (đã gắn thêm skill Phase A),
    # chứ không phải bản gốc trong tools.py.
    assert agents.build_tools_for_llm("cad", "anthropic") == _expected_role_tools("cad")


def test_tool_search_defers_business_tools_but_not_itself(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_TOOL_SEARCH", "true")
    from src.agents import TOOL_SEARCH_DEFINITION, build_tools_for_llm
    result = build_tools_for_llm("cad", "anthropic")
    assert result[0] == TOOL_SEARCH_DEFINITION
    assert "defer_loading" not in result[0]  # defer cả nó thì model hết đường tìm tool
    assert all(t["defer_loading"] is True for t in result[1:])


def test_tool_search_never_applies_to_other_providers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_TOOL_SEARCH", "true")
    from src import agents
    for provider in ("openai", "groq", "gemini", "ollama"):
        assert agents.build_tools_for_llm("cad", provider) == _expected_role_tools("cad")


def test_tool_search_skipped_when_role_has_few_tools(monkeypatch):
    """Ít tool thì nạp thẳng còn rẻ hơn gánh thêm schema của chính tool search."""
    monkeypatch.setenv("ANTHROPIC_TOOL_SEARCH", "true")
    from src import agents
    monkeypatch.setattr(agents, "TOOL_SEARCH_MIN_TOOLS", 999)
    assert agents.build_tools_for_llm("cad", "anthropic") == _expected_role_tools("cad")

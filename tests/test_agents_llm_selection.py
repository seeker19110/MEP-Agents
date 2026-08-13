import os

import pytest

from src import agents


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    """Isolate each test's env and clear the LLM client cache (lru_cache) so a
    previous test's cached client doesn't leak into this one."""
    for key in list(os.environ):
        if key.endswith(("_LLM_PROVIDER", "_MODEL_NAME", "_API_KEY")) or key in (
            "LLM_PROVIDER", "MODEL_NAME", "OPENAI_API_KEY", "GROQ_API_KEY",
            "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
    agents._build_llm.cache_clear()
    yield
    agents._build_llm.cache_clear()


def test_default_provider_is_openai_when_unset():
    llm = agents.get_llm()
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "gpt-4o-mini"


def test_global_provider_applies_to_every_role(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    llm = agents.get_llm("Mechanical")
    assert type(llm).__name__ == "ChatGroq"


def test_role_specific_provider_overrides_global(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("CAD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CAD_MODEL_NAME", "claude-opus-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    cad_llm = agents.get_llm("CAD")
    other_llm = agents.get_llm("Electrical")

    assert type(cad_llm).__name__ == "ChatAnthropic"
    assert cad_llm.model == "claude-opus-5"
    assert type(other_llm).__name__ == "ChatGroq"


def test_role_specific_api_key_overrides_global(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-global")
    monkeypatch.setenv("QS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("QS_ANTHROPIC_API_KEY", "sk-ant-qs-specific")

    llm = agents.get_llm("QS")
    assert llm.anthropic_api_key.get_secret_value() == "sk-ant-qs-specific"


def test_anthropic_default_model_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    llm = agents.get_llm()
    assert llm.model == "claude-sonnet-5"


@pytest.mark.parametrize("agent_name,expected_role", [
    ("MechanicalAgent", "Mechanical"),
    ("ElectricalAgent", "Electrical"),
    ("PlumbingAgent", "Plumbing"),
    ("FirefightingAgent", "Firefighting"),
    ("QSAgent", "QS"),
    ("CADAgent", "CAD"),
    ("BIMAgent", "BIM"),
])
def test_call_mepf_agent_derives_role_from_agent_name(monkeypatch, agent_name, expected_role):
    """agent_name like 'MechanicalAgent' should resolve to role 'Mechanical' so that
    MECHANICAL_-prefixed env overrides apply. Stub get_llm to avoid a real network call."""
    captured = {}

    class _StubLLM:
        def bind_tools(self, _tools):
            raise RuntimeError("stop before any network call")

    def fake_get_llm(role=agents.DEFAULT_ROLE):
        captured["role"] = role
        return _StubLLM()

    monkeypatch.setattr(agents, "get_llm", fake_get_llm)

    state = {"messages": [], "errors": []}
    with pytest.raises(RuntimeError, match="stop before any network call"):
        agents.call_mepf_agent(state, "system prompt", agent_name)

    assert captured["role"] == expected_role


# --- Địa chỉ server LLM cục bộ (Ollama / vLLM) ---

def test_local_base_url_defaults_to_localhost(monkeypatch):
    from src.agents import resolve_local_base_url
    for var in ("OLLAMA_BASE_URL", "OLLAMA_HOST", "VLLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert resolve_local_base_url("ollama") == "http://localhost:11434/v1"
    assert resolve_local_base_url("vllm") == "http://localhost:8000/v1"


def test_local_base_url_reads_env(monkeypatch):
    """Hồi quy: địa chỉ từng bị hardcode `localhost` nên chạy Ollama ở máy khác hoặc trong
    Docker Compose là LLM không bao giờ kết nối được, dù embedding đã trỏ đúng."""
    from src.agents import resolve_local_base_url
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    assert resolve_local_base_url("ollama") == "http://ollama:11434/v1"

    monkeypatch.setenv("VLLM_BASE_URL", "http://gpu-box:8000")
    assert resolve_local_base_url("vllm") == "http://gpu-box:8000/v1"


def test_local_base_url_shares_variable_with_embeddings(monkeypatch):
    """`OLLAMA_BASE_URL` dùng chung với `src/local_embeddings.py`, nơi nó được viết KHÔNG
    có đuôi `/v1`. Hai nửa cấu hình phải đọc cùng một biến mà vẫn ra địa chỉ đúng."""
    from src.agents import resolve_local_base_url
    from src.local_embeddings import _ollama_embeddings

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    assert resolve_local_base_url("ollama").endswith("/v1")
    assert _ollama_embeddings().base_url.rstrip("/") == "http://ollama:11434"


def test_local_base_url_does_not_double_v1(monkeypatch):
    from src.agents import resolve_local_base_url
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
    assert resolve_local_base_url("ollama") == "http://ollama:11434/v1"


def test_local_base_url_empty_for_cloud_providers(monkeypatch):
    from src.agents import resolve_local_base_url
    for provider in ("openai", "groq", "gemini", "anthropic"):
        assert resolve_local_base_url(provider) == ""


def test_changing_base_url_builds_a_new_client(monkeypatch):
    """`_build_llm` có lru_cache — base_url phải nằm trong khóa cache, nếu không đổi địa
    chỉ trong .env sẽ dùng lại client cũ trỏ về server cũ."""
    from src import agents
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("MODEL_NAME", "llama3.1:8b")

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://box-a:11434")
    first = agents.get_llm("CAD")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://box-b:11434")
    second = agents.get_llm("CAD")

    assert first is not second
    assert "box-b" in str(second.root_client.base_url)

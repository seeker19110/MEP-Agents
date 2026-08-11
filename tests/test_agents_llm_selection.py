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

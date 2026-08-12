"""Cấu hình Settings: giá trị mặc định và khả năng override qua biến môi trường."""
from src.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"
    assert s.model_name == "gpt-4o-mini"
    assert s.max_review_retries == 2
    assert s.recursion_limit == 25
    assert s.max_cad_revisions == 3
    assert s.checkpoint_db == "data/checkpoints.sqlite"
    assert s.langchain_tracing_v2 is False


def test_settings_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("MODEL_NAME", "claude-3")
    monkeypatch.setenv("MAX_REVIEW_RETRIES", "5")
    s = Settings(_env_file=None)
    assert s.llm_provider == "anthropic"
    assert s.model_name == "claude-3"
    assert s.max_review_retries == 5


def test_settings_ignores_unknown_extra_env(monkeypatch):
    monkeypatch.setenv("SOME_UNRELATED_ENV_VAR", "value")
    # extra="ignore" => should not raise even with unrelated env vars present.
    Settings(_env_file=None)

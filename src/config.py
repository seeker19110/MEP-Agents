from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llm_provider: str = "openai"
    openai_api_key: str = ""
    groq_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    model_name: str = "gpt-4o-mini"

    max_review_retries: int = 2
    recursion_limit: int = 25
    max_cad_revisions: int = 3
    checkpoint_db: str = "data/checkpoints.sqlite"

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "x_agents_project"

    database_url: str = ""
    use_pgvector: bool = False

    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-southeast-1"
    s3_prefix: str = "mep-agents/"

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    jwt_bootstrap_user: str = "admin"
    jwt_bootstrap_password: str = ""

    yolo_weights: str = ""
    yolo_confidence: float = 0.25

    agent_message_window: int = 24
    max_tool_result_chars: int = 6000
    cad_cache_max: int = 8

    embedding_backend: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embed_model: str = "nomic-embed-text"
    local_embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hybrid_search: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

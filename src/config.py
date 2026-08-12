from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llm_provider: str = "openai"  # "openai", "groq", "gemini", "anthropic", "ollama"
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

    # --- Phase C: Postgres / pgvector ---
    database_url: str = ""
    use_pgvector: bool = False

    # --- Phase C: S3-compatible object storage ---
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-southeast-1"
    s3_prefix: str = "mep-agents/"

    # --- Phase C: JWT auth ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    jwt_bootstrap_user: str = "admin"
    jwt_bootstrap_password: str = ""

    # --- Phase C: YOLO MEPF ---
    yolo_weights: str = ""
    yolo_confidence: float = 0.25

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

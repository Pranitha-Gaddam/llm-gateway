from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from the environment or a local .env file."""

    REDIS_URL: str = "redis://localhost:6379"
    OPENAI_API_KEY: str = ""

    # Model used to resolve context-dependent follow-ups into standalone
    # questions before embedding. Kept cheap because it runs on the lookup path.
    REWRITE_MODEL: str = "gpt-4o-mini"

    # Set this when exposing the gateway publicly on your own API key. Every
    # limit below is inert while it is False, so local runs and the throughput
    # benchmark are not rate limited.
    PUBLIC_DEMO: bool = False

    # The control that actually protects the budget. Rate limits are bypassed by
    # cycling IPs; a hard ceiling is not. Once crossed, upstream calls stop and
    # only cache hits are served.
    DAILY_BUDGET_USD: float = 5.00

    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 600

    MAX_OUTPUT_TOKENS: int = 150
    MAX_INPUT_CHARS: int = 2000
    MAX_MESSAGES: int = 20

    # Comma separated. Anything off this list is rejected, which stops a visitor
    # from requesting a frontier model at roughly twenty times the cost.
    ALLOWED_MODELS: str = "gpt-4o-mini"

    ENABLE_MODERATION: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

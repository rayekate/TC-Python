from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    SESSIONS_DIR: str = ".sessions"
    NODE_ENV: str = "development"

    model_config = {"env_file": ".env", "case_sensitive": True}

settings = Settings()

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ufc:ufc@localhost:5432/ufc"
    upload_dir: Path = Path("./data/uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    session_ttl_days: int = 30
    cookie_secure: bool = False


settings = Settings()

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Log Analyzer"
    host: str = "0.0.0.0"
    port: int = 8080
    database_url: str = f"sqlite:///{ROOT_DIR / 'private' / 'data' / 'log-analyzer.db'}"
    private_env_file: Path = ROOT_DIR / "private" / ".env"
    frontend_dir: Path = ROOT_DIR / "frontend"

    model_config = SettingsConfigDict(env_file=(ROOT_DIR / ".env", ROOT_DIR / "private" / ".env"), env_prefix="LOG_ANALYZER_", extra="ignore")


settings = Settings()

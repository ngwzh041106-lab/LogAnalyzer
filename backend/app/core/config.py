from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Log Analyzer"
    host: str = "0.0.0.0"
    port: int = 8080
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'log-analyzer.db'}"
    frontend_dir: Path = ROOT_DIR / "frontend"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOG_ANALYZER_")


settings = Settings()

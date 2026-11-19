from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, model_validator


class SummaryRead(BaseModel):
    id: int
    log_source_id: int | None
    status: str
    severity: str | None
    result_json: str | None
    input_preview: str | None
    raw_input: str | None
    raw_output: str | None
    error_message: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class LLMSettingsRead(BaseModel):
    provider: Literal["ollama", "openai"] = "ollama"
    base_url: str
    model: str
    timeout_seconds: int = 180
    temperature: float
    max_input_bytes: int
    system_prompt: str
    analysis_prompt: str
    connection_test_prompt: str
    has_api_key: bool


class LLMSettingsUpdate(BaseModel):
    provider: Literal["ollama", "openai"] = "ollama"
    base_url: str = "http://host.docker.internal:11434"
    model: str = "gemma4:e4b"
    timeout_seconds: int = Field(default=180, ge=10, le=1800)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_input_bytes: int = Field(default=32768, ge=1024, le=10_485_760)
    system_prompt: str = (
        "你是 Linux Log 分析助手。請使用繁體中文，簡潔整理事件、嚴重程度、"
        "可能原因與建議。只回傳有效 JSON。"
    )
    analysis_prompt: str = (
        "請分析以下 Linux Log，回傳 JSON，欄位必須包含：summary（摘要文字）、"
        "severity（info/warning/critical）、key_events（字串陣列）、"
        "possible_causes（字串陣列）、recommendations（字串陣列）、"
        "error_count（整數）。\n\nLOG:\n{log_text}"
    )
    connection_test_prompt: str = '請只回傳 JSON：{"status":"ok"}'
    api_key: str | None = None

    @model_validator(mode="after")
    def validate_prompts(self):
        self.base_url = self.base_url.strip().rstrip("/")
        url = urlsplit(self.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.query or url.fragment or url.username or url.password:
            raise ValueError("base_url 必須是有效的 HTTP(S) API 基底網址")
        self.model = self.model.strip()
        if not self.model:
            raise ValueError("model 不可為空白")
        if "{log_text}" not in self.analysis_prompt:
            raise ValueError("analysis_prompt 必須包含 {log_text}")
        return self

from datetime import datetime

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
    base_url: str
    model: str
    temperature: float
    max_input_bytes: int
    system_prompt: str
    analysis_prompt: str
    connection_test_prompt: str
    has_api_key: bool


class LLMSettingsUpdate(BaseModel):
    base_url: str = "http://host.docker.internal:11434"
    model: str = "gemma4:e4b"
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
        if "{log_text}" not in self.analysis_prompt:
            raise ValueError("analysis_prompt 必須包含 {log_text}")
        return self

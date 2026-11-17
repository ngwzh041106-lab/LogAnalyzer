from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LogSourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: Literal["file", "command"] = "file"
    path: str = Field(default="", max_length=1024)
    command: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    read_mode: Literal["tail_lines", "tail_bytes"] = "tail_lines"
    tail_lines: int = Field(default=500, ge=1)
    tail_bytes: int = Field(default=262144, ge=1)
    include_patterns: str | None = None
    exclude_patterns: str | None = None
    schedule_minutes: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_type == "file" and not self.path:
            raise ValueError("path is required for file sources")
        if self.source_type == "command" and not self.command:
            raise ValueError("command is required for command sources")
        return self


class LogSourceCreate(LogSourceBase):
    pass


class LogSourceRead(LogSourceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

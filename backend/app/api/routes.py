import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import protect_api
from app.core.private_settings import read_private, write_private
from app.models.log_source import LogSource
from app.models.settings import AppSettings
from app.models.summary import Summary
from app.schemas.log_source import LogSourceCreate, LogSourceRead
from app.schemas.summary import LLMSettingsRead, LLMSettingsUpdate, SummaryRead
from app.services.llm_client import LLMClient, LLMError
from app.services.log_reader import LogReadError, LogReader
from app.services.scheduler import AnalysisScheduler
from app.services.email_notifications import EmailSettings, load_settings, public_settings, validate_ready, send_email, notify_summary

router = APIRouter(prefix="/api", dependencies=[Depends(protect_api)])
_scheduler: AnalysisScheduler | None = None


def set_scheduler(scheduler: AnalysisScheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def _llm_config(db: Session) -> dict:
    defaults = {
        "provider": "ollama",
        "base_url": "http://host.docker.internal:11434",
        "model": "gemma4:e4b",
        "temperature": 0.2,
        "timeout_seconds": 180,
        "max_input_bytes": 32768,
        "system_prompt": "你是 Linux Log 分析助手。只做必要分析，使用繁體中文。不要展示推理，只輸出符合要求的 JSON。",
        "analysis_prompt": "分析以下 Linux Log。摘要最多 120 字，key_events、possible_causes、recommendations 各最多 5 項；只輸出 JSON，不要 Markdown 或其他文字。\n\nLOG:\n{log_text}",
        "connection_test_prompt": "請只回傳 JSON：{\"status\":\"ok\"}",
        "api_key": "",
    }
    row = db.scalar(select(AppSettings).where(AppSettings.key == "llm"))
    if row and row.value:
        try:
            stored = json.loads(row.value)
        except json.JSONDecodeError as exc:
            raise LLMError("Stored LLM settings are not valid JSON") from exc
        if not isinstance(stored, dict):
            raise LLMError("Stored LLM settings must be a JSON object")
        defaults.update(stored)
    defaults["api_key"] = read_private().get("LLM_API_KEY") or ""
    return defaults


def _llm_client(db: Session) -> tuple[LLMClient, dict]:
    config = _llm_config(db)
    validated = LLMSettingsUpdate(**config)
    return LLMClient(
        validated.base_url,
        validated.model,
        validated.temperature,
        validated.system_prompt,
        validated.analysis_prompt,
        validated.connection_test_prompt,
        validated.api_key or "",
        provider=validated.provider,
        timeout_seconds=validated.timeout_seconds,
    ), validated.model_dump()


def _create_summary(
    db: Session,
    source_id: int | None,
    content: str,
    result: dict | None,
    raw_input: str,
    raw_output: str,
    status_value: str = "completed",
    error_message: str | None = None,
) -> Summary:
    summary = Summary(
        log_source_id=source_id,
        status=status_value,
        severity=result.get("severity") if result else None,
        result_json=json.dumps(result or {}, ensure_ascii=False),
        input_preview=content,
        raw_input=raw_input,
        raw_output=raw_output,
        error_message=error_message,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    notify_summary(db, summary)
    return summary


def analyze_source(db: Session, source: LogSource) -> Summary:
    content = LogReader().read(source)
    client, config = _llm_client(db)
    content = content.encode("utf-8")[-config["max_input_bytes"] :].decode(
        "utf-8", errors="replace"
    )
    try:
        result = client.summarize(content)
    except LLMError as exc:
        return _create_summary(
            db,
            source.id,
            content,
            None,
            client.last_raw_input,
            client.last_raw_output,
            status_value="failed",
            error_message=str(exc),
        )
    return _create_summary(
        db, source.id, content, result, client.last_raw_input, client.last_raw_output
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "log-analyzer",
        "scheduler": _scheduler.status if _scheduler else "starting",
    }


@router.get("/log-sources", response_model=list[LogSourceRead])
def list_log_sources(db: Session = Depends(get_db)) -> list[LogSource]:
    return list(db.scalars(select(LogSource).order_by(LogSource.id)))


@router.get("/log-sources/{source_id}", response_model=LogSourceRead)
def get_log_source(source_id: int, db: Session = Depends(get_db)) -> LogSource:
    source = db.get(LogSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Log source not found")
    return source


@router.post("/log-sources", response_model=LogSourceRead, status_code=status.HTTP_201_CREATED)
def create_log_source(payload: LogSourceCreate, db: Session = Depends(get_db)) -> LogSource:
    source = LogSource(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.put("/log-sources/{source_id}", response_model=LogSourceRead)
def update_log_source(
    source_id: int, payload: LogSourceCreate, db: Session = Depends(get_db)
) -> LogSource:
    source = db.get(LogSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Log source not found")
    for key, value in payload.model_dump().items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/log-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log_source(source_id: int, db: Session = Depends(get_db)) -> None:
    source = db.get(LogSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Log source not found")
    db.delete(source)
    db.commit()


@router.get("/log-sources/{source_id}/preview")
def preview_log_source(source_id: int, db: Session = Depends(get_db)) -> dict[str, int | str]:
    source = db.get(LogSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Log source not found")
    try:
        content = LogReader().read(source)
    except LogReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"source_id": source.id, "line_count": len(content.splitlines()) if content else 0, "content": content}


@router.post(
    "/log-sources/{source_id}/analyze",
    status_code=status.HTTP_201_CREATED,
    response_model=SummaryRead,
)
def analyze_log_source(source_id: int, db: Session = Depends(get_db)) -> Summary:
    source = db.get(LogSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Log source not found")
    try:
        return analyze_source(db, source)
    except (LogReadError, LLMError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/analyze-all", status_code=status.HTTP_201_CREATED, response_model=SummaryRead)
def analyze_all_sources(db: Session = Depends(get_db)) -> Summary:
    sources = list(
        db.scalars(
            select(LogSource).where(LogSource.enabled.is_(True)).order_by(LogSource.id)
        )
    )
    if not sources:
        raise HTTPException(status_code=422, detail="No enabled log sources configured")

    sections: list[str] = []
    errors: list[str] = []
    for source in sources:
        try:
            content = LogReader().read(source)
        except LogReadError as exc:
            errors.append(f"{source.name}: {exc}")
            continue
        sections.append(f"===== {source.name} =====\n{content}")
    if not sections:
        raise HTTPException(status_code=422, detail="Unable to read any enabled log source")

    client = None
    try:
        client, config = _llm_client(db)
        combined = "\n\n".join(sections)
        combined = combined.encode("utf-8")[-config["max_input_bytes"] :].decode(
            "utf-8", errors="replace"
        )
        result = client.summarize(combined)
    except LLMError as exc:
        return _create_summary(
            db,
            None,
            combined if "combined" in locals() else "\n\n".join(sections),
            None,
            client.last_raw_input if client else "",
            client.last_raw_output if client else "",
            status_value="failed",
            error_message=str(exc),
        )

    if errors:
        result.setdefault("key_events", []).append(f"部分來源讀取失敗：{'; '.join(errors)}")
    return _create_summary(
        db, None, combined, result, client.last_raw_input, client.last_raw_output
    )


@router.get("/summaries", response_model=list[SummaryRead])
def list_summaries(
    keyword: str | None = Query(default=None, max_length=200),
    source_id: int | None = Query(default=None, ge=1),
    all_sources: bool = False,
    severity: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Summary]:
    query = select(Summary).order_by(Summary.created_at.desc()).limit(limit)
    if source_id is not None:
        query = query.where(Summary.log_source_id == source_id)
    elif all_sources:
        query = query.where(Summary.log_source_id.is_(None))
    if severity:
        query = query.where(Summary.severity == severity)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(
            Summary.result_json.ilike(pattern) | Summary.input_preview.ilike(pattern)
        )
    return list(db.scalars(query))


@router.get("/summaries/{summary_id}", response_model=SummaryRead)
def get_summary(summary_id: int, db: Session = Depends(get_db)) -> Summary:
    summary = db.get(Summary, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@router.delete("/summaries/{summary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_summary(summary_id: int, db: Session = Depends(get_db)) -> None:
    summary = db.get(Summary, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    db.delete(summary)
    db.commit()


@router.delete("/summaries", status_code=status.HTTP_204_NO_CONTENT)
def delete_summaries(
    all_sources: bool = False,
    source_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> None:
    query = select(Summary)
    if source_id is not None:
        query = query.where(Summary.log_source_id == source_id)
    elif all_sources:
        query = query.where(Summary.log_source_id.is_(None))
    for summary in db.scalars(query):
        db.delete(summary)
    db.commit()


@router.get("/settings/llm", response_model=LLMSettingsRead)
def get_llm_settings(db: Session = Depends(get_db)) -> LLMSettingsRead:
    config = _llm_config(db)
    return LLMSettingsRead(**{**config, "has_api_key": bool(config["api_key"])})


@router.put("/settings/llm", response_model=LLMSettingsRead)
def update_llm_settings(
    payload: LLMSettingsUpdate, db: Session = Depends(get_db)
) -> LLMSettingsRead:
    current = _llm_config(db)
    values = payload.model_dump()
    if values["api_key"] is None:
        values["api_key"] = current["api_key"]
    row = db.scalar(select(AppSettings).where(AppSettings.key == "llm"))
    if row is None:
        row = AppSettings(key="llm")
        db.add(row)
    write_private({"LLM_API_KEY": values["api_key"]})
    row.value = json.dumps({key: value for key, value in values.items() if key != "api_key"}, ensure_ascii=False)
    db.commit()
    return LLMSettingsRead(**{**values, "has_api_key": bool(values["api_key"])})


@router.post("/settings/llm/test")
def test_llm_settings(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        _llm_client(db)[0].test_connection()
    except LLMError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/settings/email")
def get_email_settings(db: Session = Depends(get_db)):
    return public_settings(load_settings(db))


@router.put("/settings/email")
def update_email_settings(payload: EmailSettings, db: Session = Depends(get_db)):
    current = load_settings(db)
    if payload.password is None:
        payload.password = current.password
    if payload.enabled:
        try:
            validate_ready(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = db.scalar(select(AppSettings).where(AppSettings.key == "email"))
    if row is None:
        row = AppSettings(key="email")
        db.add(row)
    write_private({"GMAIL_SENDER": payload.sender, "GMAIL_RECIPIENT": payload.recipient,
                   "GMAIL_APP_PASSWORD": payload.password or ""})
    row.value = payload.model_dump_json(exclude={"sender", "recipient", "password"})
    db.commit()
    return public_settings(payload)


@router.post("/settings/email/test")
def test_email_settings(db: Session = Depends(get_db)):
    try:
        send_email(load_settings(db), "[LogAnalyzer] 測試通知", "收到這封信代表 Gmail 通知設定成功。")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/settings/{section}")
def get_settings(section: str) -> dict[str, str]:
    if section not in {"llm", "webhook"}:
        raise HTTPException(status_code=404, detail="Unknown settings section")
    return {"section": section, "status": "placeholder"}

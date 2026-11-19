import json
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Literal
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from app.models.settings import AppSettings
from app.core.private_settings import read_private

logger = logging.getLogger(__name__)

class EmailSettings(BaseModel):
    enabled: bool = False
    sender: str = ""
    recipient: str = ""
    password: str | None = None
    minimum_severity: Literal["info", "warning", "critical"] = "warning"

    @field_validator("sender", "recipient")
    @classmethod
    def address(cls, value):
        value = value.strip()
        if value and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
            raise ValueError("請填寫單一有效的電子郵件地址")
        return value

    @field_validator("password")
    @classmethod
    def clean_password(cls, value):
        return "".join(value.split()) if value is not None else None


def load_settings(db):
    row = db.scalar(select(AppSettings).where(AppSettings.key == "email"))
    data = json.loads(row.value) if row and row.value else {}
    private = read_private()
    data.update(sender=private.get("GMAIL_SENDER") or "", recipient=private.get("GMAIL_RECIPIENT") or "",
                password=private.get("GMAIL_APP_PASSWORD") or "")
    return EmailSettings(**data)


def public_settings(config):
    return {**config.model_dump(exclude={"password"}), "has_password": bool(config.password)}


def validate_ready(config):
    if not config.sender or not config.recipient or not config.password:
        raise ValueError("請填寫寄件帳號、收件地址與 Gmail 應用程式密碼，並儲存設定")


def send_email(config, subject, body):
    validate_ready(config)
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = config.recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(config.sender, config.password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise ValueError("Gmail 登入失敗：請確認帳號、兩步驟驗證及應用程式密碼（不是登入密碼）") from None
    except (smtplib.SMTPException, OSError):
        raise ValueError("寄信失敗：請檢查網路、收件地址或 Gmail 寄信限制，稍後重試") from None


def notify_summary(db, summary):
    # Delivery errors must never undo an already saved analysis.
    try:
        config = load_settings(db)
        if not config.enabled or summary.status != "completed":
            return
        levels = {"info": 0, "warning": 1, "critical": 2}
        if levels.get(summary.severity, -1) < levels[config.minimum_severity]:
            return
        result = json.loads(summary.result_json or "{}")
        subject = f"[LogAnalyzer] {summary.severity} 分析通知 #{summary.id}"
        body = f"分析紀錄：{summary.id}\n來源 ID：{summary.log_source_id or '全部來源'}\n嚴重程度：{summary.severity}\n\n" + json.dumps(result, ensure_ascii=False, indent=2)
        send_email(config, subject, body)
    except Exception:
        logger.warning("Email notification failed for summary id=%s; check notification settings and test delivery", summary.id)

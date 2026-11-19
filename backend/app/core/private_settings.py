"""Private values live in a gitignored dotenv file, never in settings JSON."""
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from dotenv import dotenv_values, set_key
from sqlalchemy import select
from app.core.config import settings
from app.models.settings import AppSettings

LOCK = RLock()  # This application runs one Uvicorn worker.
KEYS = {"LLM_API_KEY", "GMAIL_SENDER", "GMAIL_RECIPIENT", "GMAIL_APP_PASSWORD", "JWT_SECRET"}


def read_private():
    with LOCK:
        return dict(dotenv_values(settings.private_env_file, interpolate=False))


def write_private(values):
    if set(values) - KEYS:
        raise ValueError("Unknown private setting")
    with LOCK:
        path = settings.private_env_file
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write a sibling file, then replace atomically; preserve unrelated settings.
        fd, filename = tempfile.mkstemp(prefix=".env-", dir=path.parent)
        os.close(fd)
        temporary = Path(filename)
        try:
            temporary.write_text(path.read_text(encoding="utf-8") if path.exists() else "", encoding="utf-8")
            for key, value in values.items():
                set_key(str(temporary), key, value, quote_mode="always")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def migrate_private(db):
    """Copy first, scrub database second. Safe to run again after interruption."""
    mappings = {"llm": {"api_key": "LLM_API_KEY"},
                "email": {"sender": "GMAIL_SENDER", "recipient": "GMAIL_RECIPIENT", "password": "GMAIL_APP_PASSWORD"}}
    with LOCK:
        existing = read_private()
        changes = {}
        rows = []
        for section, fields in mappings.items():
            row = db.scalar(select(AppSettings).where(AppSettings.key == section))
            if not row or not row.value:
                continue
            data = json.loads(row.value)
            for field, key in fields.items():
                if field in data:
                    value = data.pop(field)
                    if key not in existing and value is not None:
                        changes[key] = value
            rows.append((row, data))
        jwt_row = db.scalar(select(AppSettings).where(AppSettings.key == "jwt_secret"))
        if jwt_row and "JWT_SECRET" not in existing and jwt_row.value:
            changes["JWT_SECRET"] = jwt_row.value
        if changes:
            write_private(changes)
        for row, data in rows:
            row.value = json.dumps(data, ensure_ascii=False)
        if jwt_row:
            db.delete(jwt_row)
        db.commit()

"""Run locally: python -m app.manage_users (Docker: docker compose exec log-analyzer ...)."""
from getpass import getpass
from sqlalchemy import select
from app.api.auth import NewUser
from app.core.auth import password_hash, init_auth
from app.core.database import init_db, SessionLocal
from app.models.user import User


def main():
    init_db()
    init_auth()
    username = input("Admin username: ").strip()
    password = getpass("Password (12+ characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    try:
        payload = NewUser(username=username, password=password, role="admin")
    except ValueError:
        raise SystemExit("Username: 3-64 letters/digits/_.-; password: 12-128 characters") from None
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == payload.username))
        if user:
            if input("Reset this account as an active admin? Type YES: ") != "YES":
                return
            user.password_hash = password_hash.hash(payload.password)
            user.role, user.active = "admin", True
            user.token_version += 1
        else:
            db.add(User(username=payload.username, password_hash=password_hash.hash(payload.password), role="admin"))
        db.commit()
    print("Admin account ready. Sign in through the web page.")


if __name__ == "__main__":
    main()

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A disposable database; tests never use the deployment's users or logs.
_temp = tempfile.TemporaryDirectory()
os.environ["LOG_ANALYZER_PRIVATE_ENV_FILE"] = str(Path(_temp.name) / ".env")
os.environ["LOG_ANALYZER_DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "auth.db")
os.environ["LOG_ANALYZER_FRONTEND_DIR"] = str(Path(__file__).resolve().parents[2] / "frontend")

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.database import SessionLocal, engine
from app.core.auth import password_hash, signing_key
from app.models.user import User


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        engine.dispose()
        _temp.cleanup()

    def setUp(self):
        with SessionLocal() as db:
            for user in db.scalars(select(User)):
                db.delete(user)
            db.commit()
            for name, role in [("admin", "admin"), ("reader", "viewer")]:
                db.add(User(username=name, role=role, password_hash=password_hash.hash("test-password-123")))
            db.commit()

    def login(self, name="admin"):
        response = self.client.post("/api/auth/login", json={"username":name,"password":"test-password-123"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("password_hash", response.text)
        return {"Authorization":"Bearer " + response.json()["access_token"]}

    def test_anonymous_blocked(self):
        for path in ["/api/log-sources", "/api/summaries", "/api/settings/llm", "/api/settings/email", "/api/auth/users"]:
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login", json={"username":"admin","password":"wrong"}).status_code, 401)

    def test_viewer_permissions(self):
        headers = self.login("reader")
        for path in ["/api/log-sources", "/api/summaries", "/api/auth/me"]:
            self.assertEqual(self.client.get(path, headers=headers).status_code, 200)
        for method, path in [("GET","/api/settings/llm"),("GET","/api/settings/email"),("GET","/api/log-sources/1/preview"),("POST","/api/analyze-all"),("DELETE","/api/summaries"),("GET","/api/auth/users"),("PUT","/api/log-sources/1"),("POST","/api/settings/email/test")]:
            self.assertEqual(self.client.request(method,path,headers=headers,json={}).status_code,403,path)
        self.assertEqual(self.client.post("/api/auth/users", headers=headers, json={"username":"evil","password":"test-password-123","role":"admin"}).status_code,403)

    def test_admin_create_and_disable(self):
        headers = self.login()
        body = {"username":"newreader","password":"test-password-123"}
        response = self.client.post("/api/auth/users",headers=headers,json=body)
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()["role"],"viewer")
        self.assertEqual(self.client.post("/api/auth/users",headers=headers,json=body).status_code,409)
        viewer = self.login("newreader")
        uid = response.json()["id"]
        self.assertEqual(self.client.put(f"/api/auth/users/{uid}",headers=headers,json={"active":False,"role":"viewer"}).status_code,200)
        self.assertEqual(self.client.get("/api/auth/me",headers=viewer).status_code,401)
        self.assertEqual(self.client.get("/api/settings/llm",headers=headers).status_code,200)

    def test_logout_and_password_revoke(self):
        headers = self.login()
        self.assertEqual(self.client.post("/api/auth/logout",headers=headers).status_code,200)
        self.assertEqual(self.client.get("/api/auth/me",headers=headers).status_code,401)
        headers = self.login()
        self.assertEqual(self.client.put("/api/auth/password",headers=headers,json={"old_password":"test-password-123","new_password":"replacement-password"}).status_code,200)
        self.assertEqual(self.client.get("/api/auth/me",headers=headers).status_code,401)
        self.assertEqual(self.client.post("/api/auth/login",json={"username":"admin","password":"replacement-password"}).status_code,200)

    def test_invalid_tokens(self):
        with SessionLocal() as db:
            uid = db.scalar(select(User).where(User.username=="admin")).id
            key = signing_key(db)
        now = datetime.now(timezone.utc)
        claims = {"sub":str(uid),"iat":now-timedelta(hours=2),"exp":now-timedelta(hours=1),"ver":0}
        expired = jwt.encode(claims,key,algorithm="HS256")
        claims["exp"] = now+timedelta(hours=1)
        forged = jwt.encode(claims,"wrong-signing-key-that-is-long-enough",algorithm="HS256")
        for token in [expired,forged,"not-a-token"]:
            self.assertEqual(self.client.get("/api/auth/me",headers={"Authorization":"Bearer "+token}).status_code,401)

    def test_cannot_disable_self(self):
        headers=self.login()
        uid=self.client.get("/api/auth/me",headers=headers).json()["id"]
        self.assertEqual(self.client.put(f"/api/auth/users/{uid}",headers=headers,json={"active":False,"role":"viewer"}).status_code,400)

    def test_private_settings_api(self):
        import json
        from app.models.settings import AppSettings
        from app.core.private_settings import read_private
        headers = self.login()
        secret = "test-key-with-$dollar-and-'quote"
        result = self.client.put("/api/settings/llm", headers=headers, json={"api_key":secret})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn(secret, result.text)
        self.assertNotIn("api_key", result.json())
        self.assertEqual(read_private()["LLM_API_KEY"], secret)
        self.assertEqual(self.client.put("/api/settings/llm", headers=headers, json={"api_key":None}).status_code,200)
        self.assertEqual(read_private()["LLM_API_KEY"], secret)
        email = {"enabled":True,"sender":"sender@example.com","recipient":"recipient@example.com","password":"abcd efgh ijkl mnop"}
        result = self.client.put("/api/settings/email",headers=headers,json=email)
        self.assertEqual(result.status_code,200,result.text)
        self.assertNotIn("password",result.json())
        self.assertEqual(read_private()["GMAIL_APP_PASSWORD"],"abcdefghijklmnop")
        with SessionLocal() as db:
            llm = json.loads(db.scalar(select(AppSettings).where(AppSettings.key=="llm")).value)
            mail = json.loads(db.scalar(select(AppSettings).where(AppSettings.key=="email")).value)
            self.assertNotIn("api_key",llm)
            for key in ["sender","recipient","password"]:
                self.assertNotIn(key,mail)
        self.client.put("/api/settings/llm",headers=headers,json={"api_key":""})
        self.assertEqual(read_private()["LLM_API_KEY"],"")

    def test_legacy_migration(self):
        import json
        from unittest.mock import patch
        from app.core.config import settings
        from app.core.private_settings import migrate_private, read_private, write_private
        from app.models.settings import AppSettings
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings,"private_env_file",Path(tmp)/".env"):
            with SessionLocal() as db:
                for row in db.scalars(select(AppSettings)):
                    db.delete(row)
                db.commit()
                db.add_all([AppSettings(key="llm",value=json.dumps({"api_key":"legacy-key","model":"test"})),
                            AppSettings(key="email",value=json.dumps({"sender":"old@example.com","recipient":"to@example.com","password":"legacy-password","enabled":True})),
                            AppSettings(key="jwt_secret",value="legacy-signing-key")])
                db.commit()
                with patch("app.core.private_settings.write_private",side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        migrate_private(db)
                db.expire_all()
                self.assertIn("legacy-key",db.scalar(select(AppSettings).where(AppSettings.key=="llm")).value)
                write_private({"LLM_API_KEY":"newer-key"})
                migrate_private(db)
                self.assertEqual(read_private()["LLM_API_KEY"],"newer-key")
                self.assertEqual(read_private()["GMAIL_APP_PASSWORD"],"legacy-password")
                self.assertEqual(read_private()["JWT_SECRET"],"legacy-signing-key")
                self.assertIsNone(db.scalar(select(AppSettings).where(AppSettings.key=="jwt_secret")))
                self.assertNotIn("api_key",json.loads(db.scalar(select(AppSettings).where(AppSettings.key=="llm")).value))
                migrate_private(db)
                self.assertEqual(read_private()["JWT_SECRET"],"legacy-signing-key")

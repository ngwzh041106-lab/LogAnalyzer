# Log Analyzer

單機、內網使用的 Log 分析工具。服務部署在需要被觀察的主機上，使用 FastAPI 同時提供 REST API 與 Web UI，從檔案或 Shell 指令取得 Log，再交給 Ollama 模型產生結構化摘要。

> 目前版本適合內網或受信任的管理環境。服務已加入 JWT 登入；管理員可修改設定與執行指令，一般使用者僅能查看來源及已保存結果。

## 功能總覽

- 以 Web UI 管理 Log 來源
  - 檔案來源：讀取最後 N 行或最後 N bytes
  - 指令來源：執行 Shell 指令，例如 `docker logs --tail 500 container-name`
  - Include / Exclude 關鍵字過濾
  - 啟用 / 停用來源與每來源分析週期
- 讀取前預覽 Log，或手動分析單一來源
- 將所有啟用來源合併後執行一次「摘要全部」
- 透過 Ollama `/api/chat` 產生 JSON 分析結果
- 保存分析結果、原始請求、模型原始回應與錯誤訊息到 SQLite
- 內建背景排程器，依來源週期自動分析
- 提供摘要搜尋、嚴重程度篩選與刪除功能
- Docker Compose 與 systemd 部署範例

### 尚未完成的功能

- 已提供 Gmail 郵件通知；通用 HTTP Webhook 發送尚未實作。
- 已提供 JWT 登入與管理員／唯讀角色；HTTPS 仍需部署時設定。
- 排程服務重啟後不會補跑離線期間錯過的任務。

## 系統架構

```text
Browser
   │
   ▼
FastAPI (0.0.0.0:8080)
   ├── REST API (/api)
   ├── Static Web UI
   ├── SQLite (data/log-analyzer.db)
   ├── LogReader ── file source / command source
   ├── AnalysisScheduler
   └── LLMClient ── Ollama /api/chat
```

服務啟動時會建立資料表並啟動排程器；服務停止時會停止排程器。排程器每 30 秒檢查一次啟用中的來源，首次啟動後會等待該來源設定的週期才執行。

## 快速開始：Docker Compose

### 前置需求

- Docker Engine
- Docker Compose
- 可連線的 Ollama 服務與已下載的模型

在專案根目錄執行：

```bash
docker compose up -d --build
```

開啟 <http://localhost:8080>。

常用指令：

```bash
docker compose ps
docker compose logs --tail=100 log-analyzer
docker compose logs --tail=100 --follow log-analyzer
docker compose down
```

SQLite 使用 Docker named volume `log-analyzer-data`，不會寫入 `/mnt/d` 等可能有 I/O 相容性問題的掛載路徑。要連同資料一起移除時才使用：

```bash
docker compose down -v
```

### Docker 的主機 Log 路徑

Compose 預設提供以下唯讀掛載：

| 主機內容 | 容器內容 | 用途 |
|---|---|---|
| `/var/log` | `/var/log` | 相容常見 Linux Log 路徑 |
| `/` | `/host` | 將其他主機絕對路徑映射到容器 |
| `/var/run/docker.sock` | `/var/run/docker.sock` | 讓指令來源可執行 Docker CLI |

因此可在 UI 直接填入：

```text
/var/log/auth.log
/home/user/app.log
/opt/my-service/logs/app.log
```

服務會先嘗試原始路徑，再嘗試 `/host/<主機路徑>`。Windows 路徑會轉為 WSL 格式，例如：

```text
D:\logs\app.log
```

會嘗試讀取：

```text
/mnt/d/logs/app.log
/host/mnt/d/logs/app.log
```

若使用其他容器編排方式，請自行提供 `/host` 根目錄唯讀掛載，或把個別 Log 目錄掛載到容器內的相同路徑。

## Ollama 設定

在 Web UI 的「LLM 設定」填入 Ollama Base URL 與模型，預設值為：

```text
Base URL: http://host.docker.internal:11434
Model:    gemma4:e4b
```

Ollama 必須已下載指定模型，例如：

```bash
ollama pull gemma4:e4b
```

如果 Ollama 位於另一個 WSL distro，不能只監聽 `127.0.0.1`。可建立 systemd override：

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo sh -c 'printf "%s\n" "[Service]" "Environment=OLLAMA_HOST=0.0.0.0:11434" > /etc/systemd/system/ollama.service.d/override.conf'
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

接著在 UI 填入該 WSL distro 的 IP，按「測試連線」，成功後即可預覽或開始分析。

### 提示詞規則

- `analysis_prompt` 必須包含 `{log_text}`，服務會將實際 Log 內容代入。
- 客戶端會要求模型只回傳 JSON，且包含：
  - `summary`
  - `severity`：`info`、`warning` 或 `critical`
  - `key_events`
  - `possible_causes`
  - `recommendations`
  - `error_count`
- 所有輸入內容會依 `max_input_bytes` 從尾端截取，避免單次請求過大。
- 服務會嘗試解析模型回應中的 JSON，並將常見欄位名稱正規化。
- 若填寫 API Key，服務會以 `Authorization: Bearer <key>` 標頭送出；Ollama 原生部署通常不需要 API Key。

## 本機執行

需要 Python 3.12 或相容版本：

```bash
cd LogAnalyzer
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt
```

啟動服務：

```bash
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8080
```

開啟 <http://localhost:8080>。SQLite 預設位置為 `data/log-analyzer.db`；`data/` 不存在時會由應用程式建立資料表，但請先確保資料夾可寫入。

也可以使用環境變數覆寫設定：

```text
LOG_ANALYZER_APP_NAME=Log Analyzer
LOG_ANALYZER_HOST=0.0.0.0
LOG_ANALYZER_PORT=8080
LOG_ANALYZER_DATABASE_URL=sqlite:///D:/path/to/log-analyzer.db
LOG_ANALYZER_FRONTEND_DIR=D:/path/to/LogAnalyzer/frontend
```

設定模型使用 `LOG_ANALYZER_` 前綴；目前 LLM 連線設定是保存於 SQLite 的應用程式設定，不是環境變數。

## REST API

Swagger/OpenAPI 文件由 FastAPI 提供：

- <http://localhost:8080/docs>
- <http://localhost:8080/redoc>

### 健康檢查

```http
GET /api/health
```

回應包含 `status`、`service` 與 `scheduler`。`scheduler` 可能是 `running`、`stopped` 或 `failed`。

### Log 來源

| Method | Path | 說明 |
|---|---|---|
| `GET` | `/api/log-sources` | 列出所有來源 |
| `POST` | `/api/log-sources` | 建立來源 |
| `GET` | `/api/log-sources/{id}` | 取得單一來源 |
| `PUT` | `/api/log-sources/{id}` | 更新來源 |
| `DELETE` | `/api/log-sources/{id}` | 刪除來源 |
| `GET` | `/api/log-sources/{id}/preview` | 讀取並預覽符合條件的 Log |
| `POST` | `/api/log-sources/{id}/analyze` | 分析單一來源並保存摘要 |

來源的 `source_type` 為 `file` 或 `command`。檔案來源需要 `path`，指令來源需要 `command`。`read_mode` 為 `tail_lines` 或 `tail_bytes`。

### 分析結果

| Method | Path | 說明 |
|---|---|---|
| `POST` | `/api/analyze-all` | 合併所有啟用來源並產生一份摘要 |
| `GET` | `/api/summaries` | 列出摘要 |
| `GET` | `/api/summaries/{id}` | 取得單筆摘要 |
| `DELETE` | `/api/summaries/{id}` | 刪除單筆摘要 |
| `DELETE` | `/api/summaries` | 依條件刪除摘要 |

`GET /api/summaries` 支援：

```text
keyword=<文字>
source_id=<來源 ID>
all_sources=true
severity=info|warning|critical
limit=1..500
```

`all_sources=true` 代表只篩選「摘要全部」產生的結果；它不等同於所有來源。

### LLM 設定

| Method | Path | 說明 |
|---|---|---|
| `GET` | `/api/settings/llm` | 取得設定 |
| `PUT` | `/api/settings/llm` | 儲存設定 |
| `POST` | `/api/settings/llm/test` | 測試 Ollama 連線 |

### 預留設定 API

```http
GET /api/settings/webhook
```

目前只會回傳 `{"section":"webhook","status":"placeholder"}`；實際 Webhook 發送尚未支援。

## 資料與錯誤處理

主要 SQLite 資料表：

- `log_sources`：來源設定與排程週期
- `app_settings`：目前保存 Ollama / LLM 設定
- `summaries`：分析結果、輸入預覽、原始 LLM 請求與回應

讀取檔案失敗、指令逾時或回傳非零狀態碼，以及 LLM 請求失敗，都會回傳明確錯誤。排程單次失敗會記錄服務日誌，並繼續處理其他來源。

指令來源由 Python `subprocess` 以 Shell 執行，且沒有額外沙箱。請只讓受信任的管理者修改來源，避免把未驗證的輸入寫入 `command`。

## systemd 部署

`deploy/log-analyzer.service` 是 systemd 範例，預期專案安裝於 `/opt/log-analyzer`，並已在該目錄建立 `.venv`：

```bash
sudo cp deploy/log-analyzer.service /etc/systemd/system/log-analyzer.service
sudo systemctl daemon-reload
sudo systemctl enable --now log-analyzer
sudo systemctl status log-analyzer
```

本機部署時，請確認：

- `/opt/log-analyzer/data` 可由服務帳號寫入
- 服務帳號能讀取要分析的 Log
- 若使用 command source，服務帳號能執行所需指令
- `WorkingDirectory`、`PYTHONPATH` 與 `.venv` 路徑符合實際安裝位置

## 專案結構

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routes.py             REST API 與分析流程
│   │   ├── core/config.py            環境設定
│   │   ├── core/database.py          SQLAlchemy engine 與資料表初始化
│   │   ├── models/                   SQLite ORM 模型
│   │   ├── schemas/                  Pydantic request / response schema
│   │   └── services/
│   │       ├── log_reader.py         檔案 / 指令 Log 讀取與過濾
│   │       ├── llm_client.py         Ollama HTTP client
│   │       ├── scheduler.py          背景分析排程器
│   │       └── webhook.py            尚未實作的 Webhook 介面
│   └── requirements.txt
├── frontend/
│   ├── index.html                    Web UI 入口
│   └── assets/                       JavaScript、CSS、favicon
├── deploy/log-analyzer.service       systemd 範例
├── Dockerfile
└── docker-compose.yml
```

## 疑難排解

### `/api/health` 顯示無法連線

確認容器是否啟動，以及查看：

```bash
docker compose ps
docker compose logs --tail=100 log-analyzer
```

### 預覽找不到檔案

確認容器內掛載是否存在。Compose 預設只允許透過 `/var/log` 或 `/host` 讀取主機檔案，且使用唯讀模式。

### LLM 測試失敗

確認 Ollama 可從 Log Analyzer 執行環境連線、模型名稱正確，並檢查 Ollama 是否只綁定在 `127.0.0.1`。也可查看服務日誌中的 HTTP 錯誤。

### 排程沒有立即執行

來源建立後，排程器會先等待設定的 `schedule_minutes`；背景迴圈每 30 秒檢查一次。需要立即驗證時，請使用來源卡片上的「開始分析」。

## 外部模型 API

在「LLM 設定」將模型服務選為「OpenAI 相容 API」，填入供應商的 Base URL（包含版本路徑，例如 https://api.openai.com/v1，不要加入 /chat/completions）、模型 ID 與 API Key。先儲存設定，再按「測試連線」。手動分析、摘要全部與背景排程均使用這份設定；外部模式會將 Log 傳送到指定服務。

設定 API 新增 provider：ollama（預設）或 openai（OpenAI 相容 Chat Completions）。舊設定不需遷移。外部模式呼叫 Base URL 加上 /chat/completions，解析 choices[0].message.content，以提示詞要求 JSON。Temperature 僅適用 Ollama。非 Chat Completions 格式尚不支援。API Key 留空保留原值；透過設定 API 傳入空字串可清除。

## Gmail 通知（簡單版）

原理：分析成功 → 檢查嚴重程度 → 透過 Gmail SMTP 寄信。不需要 Webhook URL 或另一台接收伺服器；這是郵件通知，不是 HTTP Webhook。

1. 在 Google 帳號啟用兩步驟驗證，再到 https://myaccount.google.com/apppasswords 建立應用程式密碼。部分組織帳號可能不提供此功能，請參考 https://support.google.com/mail/answer/185833 。
2. 開啟「Gmail 通知」，填寄件 Gmail、收件信箱（可填自己）、應用程式密碼，先儲存設定。
3. 按「寄送測試信」，確認收件匣或垃圾郵件有收到。
4. 選擇通知程度、勾選啟用，再儲存。預設關閉，預設門檻為 warning。

使用 smtp.gmail.com:587 與 STARTTLS，不需要新增套件。手動、摘要全部與排程分析成功後，每次符合條件寄一封；不通知分析失敗，也沒有去重、自動重試或寄信佇列。寄信最多等待每次網路操作 20 秒，因此分析回應可能稍慢。寄信失敗記錄於服務日誌，不影響分析結果。信件包含分析結果，不包含原始 Log。

設定儲存在 SQLite app_settings 的 email 項目；應用程式密碼以明文保存，讀取 API 不回傳密碼。密碼欄留空保留；設定 API 傳入空字串可清除。通知設定僅管理員可操作，適用受信任內網。

API：GET /api/settings/email、PUT /api/settings/email、POST /api/settings/email/test（使用已儲存設定，即使未啟用也會寄測試信）。

### 模型讀取逾時

若出現 read operation timed out，表示網路讀取超過等待時間，不代表 API Key 錯誤。LLM 設定的 timeout_seconds 預設 180 秒，可設為 10～1800 秒；較慢模型可嘗試 600 秒。這是個別 socket 操作的逾時，不是整次分析的總時限。先用 50～100 行測試；若小量 Log 仍逾時，檢查服務負載、模型載入與網路。逾時不會自動重送請求。

## 登入與基礎權限（JWT）

原理：帳號密碼驗證成功 → 取得 1 小時有效的 JWT → 前端每次呼叫 API 帶上 Bearer Token → 後端驗證簽章、到期時間及資料庫中的角色。使用 PyJWT 與 pwdlib/Argon2；不自行實作加密。

### 第一次建立管理員

更新服務後，在專案目錄執行：

```powershell
 docker compose up -d --build
 docker compose exec log-analyzer python -m app.manage_users
```

依提示輸入帳號及至少 12 字元的密碼；輸入密碼時不顯示字元是正常的。沒有預設帳密，也沒有公開註冊。若本機執行，先設定 PYTHONPATH=backend，再執行 python -m app.manage_users。此指令也能重設既有帳號為管理員，需輸入 YES 確認。請在備份資料庫後更新部署。

登入後在「帳號管理」新增帳號、停用帳號或切換角色。所有使用者都能修改自己的密碼；管理員不能降級或停用自己。

| 操作 | 一般使用者 viewer | 管理員 admin |
|---|---|---|
| 查看來源、已保存摘要（含原始請求／回應） | 可以 | 可以 |
| 預覽 Log、手動分析、來源增刪改、刪除結果 | 不可以 | 可以 |
| LLM、Gmail 設定與測試 | 不可以 | 可以 |
| 建立帳號、變更角色與停用 | 不可以 | 可以 |

預覽可能執行 Shell 指令，所以也限定管理員。所有業務 API（含健康檢查）都需登入；靜態登入頁公開，背景排程在服務內運作。權限在後端檢查，前端隱藏按鈕僅為操作引導。

JWT 簽署金鑰首次啟動隨機產生並保存於 app_settings，不會透過設定 API 回傳。帳號密碼只存 Argon2 雜湊。Token 存於瀏覽器 sessionStorage；登出／改密碼會撤銷該帳號全部 Token，停用及角色變更亦會撤銷。資料庫包含簽署金鑰與服務密碼，請保護備份。跨網路使用請部署 HTTPS；此簡易版本沒有 MFA、忘記密碼郵件或多租戶資料隔離。

API：POST /api/auth/login、GET /api/auth/me、POST /api/auth/logout、PUT /api/auth/password、GET/POST /api/auth/users、PUT /api/auth/users/{id}。登入傳 JSON username/password，其餘攜帶 Authorization: Bearer <token>。

測試：安裝 requirements.txt 與 httpx，設定 PYTHONPATH=backend，執行 python -m unittest discover -s backend/tests -v。登入測試使用獨立暫存 SQLite。

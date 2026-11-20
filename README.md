# Log Analyzer

單機、內網使用的 Log 分析工具。透過網頁讀取檔案或 Shell 指令的 Log，交給本地 Ollama 或 OpenAI 相容 API 產生摘要，並可用 Gmail 寄送通知。

支援 JWT 登入與管理員／一般使用者權限。請部署於受信任的管理環境；透過網路使用時應配置 HTTPS。

## 功能

- 檔案與指令來源，支援最後 N 行／N bytes、Include／Exclude 過濾。
- 預覽可展開與收合；手動分析、合併所有啟用來源產生摘要。
- 來源各自設定分析週期，背景排程每 30 秒檢查一次。
- Ollama 與 OpenAI 相容 Chat Completions API，可調整模型等待秒數。
- 摘要搜尋、嚴重程度篩選、原始模型請求／回應與錯誤紀錄。
- Gmail 通知，依 info、warning、critical 門檻寄信。
- JWT 登入、帳號管理、角色切換、停用及修改密碼。
- 私密設定由網頁寫入 private/.env，排除於 Git 和 Docker 建置內容。

## 快速開始：Docker Compose

需要 Docker Compose，以及可用的 Ollama 模型或外部 API 帳號。以下指令皆在專案根目錄執行。

### 1. 啟動服務

```powershell
# 第一次使用可先建立私人資料夾
New-Item -ItemType Directory -Force private/logs

docker compose up -d --build
```

Linux／macOS 可用 mkdir -p private/logs 建立目錄。服務會自動建立 private/.env，不需要先複製範例檔。

### 2. 建立管理員

```powershell
docker compose exec log-analyzer python -m app.manage_users
```

依提示輸入帳號及至少 12 字元的密碼。密碼輸入時不顯示字元是正常的。沒有預設帳密，也沒有公開註冊。

開啟 [登入頁](http://localhost:8080)，登入後可在「帳號管理」新增一般使用者。

### 3. 設定模型

在「LLM 設定」選擇服務、填入連線資訊，先儲存，再按「測試連線」。詳見下方模型設定。

### 4. 新增 Log 來源

將檔案放入專案的 private/logs/，例如：

```text
主機：D:\LogAnalyzer\private\logs\Linux_2k.log
網頁來源路徑：/logs/Linux_2k.log
```

先設定最後 50～100 行，儲存後按「預覽」，確認可讀取再分析。預覽再次點擊即可收合。

分析期間，該來源的編輯、刪除與重複分析按鈕會停用；摘要全部時停用所有來源的這些按鈕。這是目前瀏覽器頁面的手動分析狀態，不是跨瀏覽器的任務鎖。

## 模型設定

| 欄位 | Ollama | OpenAI 相容 API |
|---|---|---|
| 模型服務 | Ollama（本地模型） | OpenAI 相容 API |
| Base URL | 預設 http://host.docker.internal:11434 | 供應商基底網址，例如 https://api.openai.com/v1 |
| 模型 | 預設 gemma4:e4b，需已下載 | 供應商提供的模型 ID |
| API Key | 原生 Ollama 通常不需要 | 填入供應商金鑰，不加 Bearer 前綴 |

外部 API 的 Base URL 應包含供應商需要的版本路徑，不要加 /chat/completions。程式會自動附加該路徑；目前不支援其他 API 協定。外部模式會將選取的 Log 傳送到指定服務。

- Temperature 僅適用 Ollama。
- 模型等待秒數預設 180，可設 10～1800；慢速模型可試 600。這是每次連線／讀取操作的等待上限，不是整次分析總時限。
- 最大輸入預設 32768 bytes；超過時保留尾端內容。
- 分析提示詞必須包含 {log_text}。
- 模型輸出包含 summary、severity、key_events、possible_causes、recommendations、error_count。
- API Key 在網頁留空會保留原值；透過設定 API 傳入空字串可清除。

若 Ollama 在另一台主機或 WSL 環境，請確認服務監聽地址與網路可達性，不能只監聽該環境的 127.0.0.1。

## Gmail 通知

原理：分析成功 → 達到嚴重程度門檻 → 經 Gmail SMTP 寄信。這是直接寄信，通用 HTTP Webhook 尚未實作。

1. 在 Google 帳號啟用兩步驟驗證。
2. 前往 [應用程式密碼](https://myaccount.google.com/apppasswords) 建立 LogAnalyzer 專用密碼；可參考 [Google 說明](https://support.google.com/mail/answer/185833)。
3. 在「Gmail 通知」填寄件帳號、收件地址（可填自己）及應用程式密碼。
4. 儲存後按「寄送測試信」，確認收件匣或垃圾郵件收到。
5. 選擇通知門檻、啟用自動寄信，再儲存。

請填應用程式密碼，不是一般登入密碼或一次性驗證碼。密碼留空保留原值。

SMTP 使用 smtp.gmail.com:587 與 STARTTLS。預設通知關閉、門檻 warning；手動、摘要全部與排程分析皆適用。每次符合條件寄一封，不通知分析失敗，目前沒有去重、重試或郵件佇列。信件含分析結果、不附原始 Log；分析結果仍可能包含從 Log 摘錄的私人資訊。

寄信失敗會記錄服務日誌，不會取消已保存的分析。測試寄信即使未啟用自動通知也會寄出。

## 登入與權限

登入成功取得 1 小時有效的 JWT，前端每次呼叫 API 帶上 Token，後端驗證簽章、期限及資料庫中的角色。密碼使用 Argon2 雜湊，JWT 使用 PyJWT。

| 操作 | 一般使用者 viewer | 管理員 admin |
|---|---|---|
| 查看來源與已保存結果，包含原始請求／回應 | 可以 | 可以 |
| 預覽 Log、手動分析、來源增刪改、刪除結果 | 不可以 | 可以 |
| 修改／測試模型與 Gmail 設定 | 不可以 | 可以 |
| 新增帳號、變更角色、停用帳號 | 不可以 | 可以 |
| 修改自己的密碼 | 可以 | 可以 |

預覽可能執行 Shell 指令，因此也需要管理員。指令來源沒有額外沙箱，只應交由受信任管理員設定。

Token 存於 sessionStorage；登出、改密碼、角色變更或停用會讓該帳號舊 Token 失效。管理員不能降級或停用自己。沒有 MFA、忘記密碼郵件或多租戶資料隔離。

忘記管理員密碼時，重新執行建立管理員指令，輸入既有帳號、新密碼並輸入 YES；該帳號將恢復為啟用中的管理員。

## 私人資料與 GitHub

| 位置 | 保存內容 | 上傳 GitHub？ |
|---|---|---|
| private/.env | API Key、Gmail 地址／應用程式密碼、JWT 簽署金鑰 | 不可以 |
| private/data/ | 本機 SQLite，包含使用者密碼雜湊、來源與分析結果 | 不可以 |
| private/logs/、private/backups/、private/secrets/ | Log、備份與其他私人設定 | 不可以 |
| Docker named volume | Docker 部署的 SQLite | 不可以匯出後上傳 |
| .env.example | 不含真實秘密的設定範例 | 可以 |
| backend/、frontend/、部署檔與文件 | 公開程式碼與說明 | 可以，但不能硬寫真實秘密 |

網頁儲存後，LLM_API_KEY、GMAIL_SENDER、GMAIL_RECIPIENT、GMAIL_APP_PASSWORD、JWT_SECRET 存入 private/.env。這是明文私人檔案，不是加密。設定 API 不回傳 API Key 或密碼；管理員可讀取 Gmail 地址。使用者登入密碼只存資料庫雜湊。

.gitignore 排除私人檔案，.dockerignore 排除建置內容；Docker 運行時另外掛載 private/。一般 git add . 不會加入 private/.env，但 git add -f 可以強制加入。已追蹤的檔案不會因新增忽略規則自動停止追蹤。

上傳前檢查：

```powershell
git status --short
git diff --cached --name-only
```

在自己電腦檢查暫存差異，確認沒有真實秘密再提交。commit 保存到本機 Git；push 才上傳 GitHub。Git 姓名與 Email 也會寫入提交紀錄，需要隱私時使用 GitHub noreply Email。

若曾誤傳金鑰，先撤銷／更換，再另行清理歷史；revert 不會移除歷史內容。更多規則見 [PRIVATE_DATA.md](PRIVATE_DATA.md)。

## Docker 掛載與升級

| 主機內容 | 容器位置 | 存取 |
|---|---|---|
| log-analyzer-data named volume | /app/data | 可讀寫，保留既有資料庫 |
| ./private | /app/private | 可讀寫，讓設定頁保存 .env |
| ./private/logs | /logs | 此掛載唯讀 |
| /var/log | /var/log | 唯讀 |
| / | /host | 唯讀，實際內容取決於 Docker 主機環境 |
| /var/run/docker.sock | 同一路徑 | Docker CLI 使用，不是唯讀限制 |

容器不會自動看見 Windows 所有磁碟。Windows 路徑雖會轉成 /mnt/磁碟代號/... 並嘗試 /host/...，仍需對應掛載；建議使用 /logs/檔名。private/logs 也位於可寫的 private/ 掛載中，所以 /logs 的唯讀標記不代表全面檔案隔離。

升級前先備份資料庫和 private/。資料庫備份應在停止寫入時進行；SQLite 的 -wal／-shm 等附屬檔也可能包含資料。

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 log-analyzer
```

新版本啟動時，先將舊資料庫中的 API／Gmail 私密設定與 JWT 金鑰寫入 .env，成功後才移除舊欄位；既有 .env 值優先。寫入失敗會阻止啟動，保留舊設定。既有帳號及分析資料不會因此刪除。

舊備份與 SQLite 已釋放頁面不保證被安全抹除，仍須保管。不要用 docker compose down -v 更新服務，因為它會刪除資料 volume。私人檔案會在每次操作讀取，網頁儲存後不需重啟；目前只支援單一 Uvicorn worker。

## 本機執行與 systemd

需要 Python 3.12 或相容版本。在專案根目錄建立並啟用虛擬環境後執行：

```powershell
pip install -r backend/requirements.txt
$env:PYTHONPATH = "backend"
python -m app.manage_users
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8080
```

Linux／macOS 使用 export PYTHONPATH=backend。服務會建立 private/.env 及 private/data/log-analyzer.db。若需要自訂本機環境設定，可將 .env.example 複製到 private/.env，但不要覆蓋已有的秘密檔案。

| 設定 | 用途 |
|---|---|
| LOG_ANALYZER_DATABASE_URL | 指定資料庫，例如 sqlite:///D:/path/to/log-analyzer.db |
| LOG_ANALYZER_FRONTEND_DIR | 指定前端資料夾 |
| LOG_ANALYZER_PRIVATE_ENV_FILE | 指定私人秘密檔案位置 |

應用程式環境設定會讀取根目錄 .env 與 private/.env；秘密值由 private_env_file 所指檔案直接讀寫。Docker Compose 已明確指定資料庫在 /app/data，與本機預設不同。Uvicorn 的監聽地址及埠以啟動指令的 --host／--port 為準。

若舊本機資料庫在 data/log-analyzer.db，請先停服務再搬到 private/data/，或指定原資料庫路徑，避免誤建空資料庫。

systemd 範例為 deploy/log-analyzer.service，預設專案位於 /opt/log-analyzer。請確認虛擬環境、工作目錄、服務帳號讀取 Log 的權限，以及 /opt/log-analyzer/private 可寫入；首次使用也要建立管理員。

## REST API

除登入 API 外，業務 API（包含健康檢查）都需要 Authorization: Bearer <token>；管理操作另需 admin。Swagger/OpenAPI 文件由 FastAPI 提供：

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
| `POST` | `/api/settings/llm/test` | 測試已儲存的模型連線 |

### 預留設定 API

```http
GET /api/settings/webhook
```

目前只會回傳 `{"section":"webhook","status":"placeholder"}`；實際 Webhook 發送尚未支援。

### 登入與通知 API

| Method | Path | 說明 |
|---|---|---|
| POST | /api/auth/login | JSON 帳號密碼登入 |
| GET | /api/auth/me | 目前使用者 |
| POST | /api/auth/logout | 撤銷目前帳號舊 Token |
| PUT | /api/auth/password | 修改自己的密碼 |
| GET / POST | /api/auth/users | 管理員列出／新增帳號 |
| PUT | /api/auth/users/{id} | 管理員修改角色與啟用狀態 |
| GET / PUT | /api/settings/email | 管理員讀取／儲存通知設定 |
| POST | /api/settings/email/test | 使用已儲存設定寄送測試信 |

## 架構與程式位置

```text
瀏覽器 → JWT 驗證與權限檢查 → FastAPI
  ├─ LogReader：檔案／Shell 指令 → 過濾與截取
  ├─ LLMClient：Ollama／外部 API → 結構化摘要
  ├─ SQLite：來源、一般設定、帳號雜湊、分析結果
  ├─ private/.env：API／Gmail／JWT 秘密
  ├─ Gmail SMTP：分析成功且符合門檻時通知
  └─ AnalysisScheduler：每 30 秒檢查來源週期
```

| 檔案 | 職責 |
|---|---|
| backend/app/api/routes.py | 來源、分析、模型與通知設定 API |
| backend/app/api/auth.py、core/auth.py | 登入、帳號、JWT 與權限 |
| backend/app/core/private_settings.py | 私人檔案讀寫、舊設定搬移 |
| backend/app/core/database.py、models/ | 資料庫與資料表 |
| backend/app/services/ | Log 讀取、模型呼叫、通知與排程 |
| backend/app/manage_users.py | 本機建立／重設管理員 |
| frontend/assets/app.js | 網頁互動 |
| backend/tests/ | 登入權限、秘密儲存／搬移及模型呼叫測試 |

## 疑難排解

| 現象 | 檢查方式 |
|---|---|
| 登入失敗 | 確認帳號大小寫、密碼及啟用狀態；Docker 帳號需在同一容器資料庫建立 |
| API 回傳 401 | 登入 Token 缺少或過期；模型服務的 401 則檢查供應商 API Key |
| API 回傳 403 | 目前角色無權執行，請使用管理員 |
| Log 找不到 | 確認 private/logs/ 內檔案存在，網頁使用 /logs/檔名，掛載變更後更新容器 |
| 模型逾時 | 先改成 50～100 行，等待時間可試 600 秒，再檢查服務與網路 |
| Gmail 登入失敗 | 確認使用應用程式密碼，且先儲存再測試 |
| .env 無法儲存／升級無法啟動 | 檢查 private/ 掛載、資料夾寫入權限與可用空間 |
| 排程沒有立即執行 | 初次會等待來源設定週期；重啟不補跑離線任務，可先手動分析 |

## 測試

```powershell
pip install -r backend/requirements.txt httpx
$env:PYTHONPATH = "backend"
python -m unittest discover -s backend/tests -v
```

測試使用暫存資料庫與私人檔案，模型請求使用模擬回應，不需要真實金鑰，也不寄出 Gmail 通知。

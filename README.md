# Log Analyzer

單機、內網使用的 Log 分析工具。服務部署在需要被觀察的主機上，使用 FastAPI 同時提供 REST API 與 Web UI，從檔案或 Shell 指令取得 Log，再交給 Ollama 模型產生結構化摘要。

> 目前版本適合內網或受信任的管理環境。服務沒有登入驗證；任何可以連線到服務的人都能查看 Log、修改設定並執行已設定的指令。

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

- Webhook 發送尚未實作；UI 中的 Webhook 頁面目前是預留畫面。
- 沒有使用者登入、權限控管或 HTTPS 設定。
- 排程服務重啟後不會補跑離線期間錯過的任務。

## 系統架構

```text
Browser
   │
   ▼
FastAPI (0.0.0.0:8080)
   ├── REST API (/api)
   ├── Static Web UI
   ├── SQLite（本機 private/data/log-analyzer.db；Docker 使用獨立 volume）
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

開啟 <http://localhost:8080>。本機 SQLite 預設位置為 `private/data/log-analyzer.db`；`data/` 不存在時會由應用程式建立資料表，但請先確保資料夾可寫入。

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

- `/opt/log-analyzer/private/data` 可由服務帳號寫入
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

## 公開程式與私人資料分離

GitHub 只放程式、部署設定與不含真實密碼的 .env.example。私人資料統一放 private/；此目錄不進 Git，也不進 Docker build context。詳細規則見 [PRIVATE_DATA.md](PRIVATE_DATA.md)。

本機執行：將 .env.example 複製到 private/.env，再填自己的設定；SQLite 預設在 private/data/log-analyzer.db。舊版若有 data/log-analyzer.db，請先停止服務，將資料庫及同名 -wal/-shm 檔一起備份及移到 private/data/，或設定 LOG_ANALYZER_DATABASE_URL 繼續使用舊檔，避免誤建空資料庫。舊根目錄 .env 仍相容，但建議移至 private/.env。

Docker：資料庫繼續使用原有 log-analyzer-data volume（容器 /app/data），不需搬移，也不會加入 Git。private/.env 僅供本機使用，Docker 不會自動載入此檔。Log 檔放 private/logs/，UI 填 /logs/檔名，例如 /logs/Linux_2k.log；修改掛載後執行 docker compose up -d --build。不要執行 docker compose down -v，以免刪除資料。

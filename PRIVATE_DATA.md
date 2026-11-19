# 哪些可以上傳 GitHub？

可以上傳：backend/、frontend/、deploy/、Dockerfile、docker-compose.yml、README 與沒有真實秘密值的 .env.example。

私人資料使用以下目錄：

| 位置 | 用途 |
|---|---|
| private/.env | 環境設定、API Key、Gmail 地址與應用程式密碼、JWT 簽署金鑰 |
| private/data/ | 本機 SQLite（帳號雜湊與分析內容；舊資料庫及備份仍可能含金鑰） |
| private/logs/ | 原始 Log、測試資料；Docker 映射為 /logs |
| private/backups/ | 資料庫備份、分析匯出、壓縮備份 |
| private/secrets/ | 金鑰與其他私人設定 |

Docker 的資料庫保留在獨立 named volume，不在 Git 專案裡。這是另一個私人儲存位置；備份或匯出時放 private/backups/。

.gitignore 防止一般 git add 加入私人資料；.dockerignore 防止它們被傳到映像檔建置環境。這些規則不是加密，也無法阻止 git add -f。不要把秘密硬寫進 Python、JavaScript、README 或範例設定。

上傳前執行 git diff --cached --name-only，確認沒有 private/、.env、資料庫、私鑰或真實 Log；再在自己電腦查看 git diff --cached，確認程式內沒有真實金鑰。不要將含秘密的 diff 貼到公開聊天室。

已追蹤的檔案不會因 .gitignore 自動消失。若曾誤傳，先撤銷金鑰，再另行清理 Git 歷史；revert 及新增忽略規則都不會刪除歷史版本。Git 提交者姓名與 Email 也屬公開提交資訊，需要隱私時改用 GitHub noreply Email。

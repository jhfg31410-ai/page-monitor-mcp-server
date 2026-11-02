# page-monitor-mcp-server — Dockerfile（本地備妥，映像尚未發布）
# 用途：供 Glama 提交核准後之自動化安全與品質檢查，及 Official MCP Registry OCI 映像發布使用。
# 本伺服器僅用 Python 3 標準函式庫，零第三方依賴；以 stdio 提供 MCP JSON-RPC 2.0 服務。
FROM python:3.12-slim

# Official MCP Registry OCI 所有權驗證：LABEL 值須與 server.json 之 name 一致（GitHub 帳號 jhfg31410-ai 已填入）
LABEL io.modelcontextprotocol.server.name="io.github.jhfg31410-ai/page-monitor-mcp-server"

# 避免產生 .pyc，並關閉輸出緩衝，利於 stdio 即時通訊
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 只複製執行所需檔案（不含本機測試快取 __pycache__）
COPY server.py engine.py requirements.txt ./
COPY fixtures ./fixtures
COPY README.md claude_desktop_config.example.json ./

# 正式 Key 為選填環境變數；未設定亦可免費使用 cat1_diff_page
ENV CAT1_API_KEY=""

ENTRYPOINT ["python3", "server.py"]

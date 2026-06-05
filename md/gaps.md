# 项目待完善项 — LectureCrewLLM

[English](../README.md) | [中文](../README_CN.md) | [BUG_REPORT](BUG_REPORT.md) ｜ [架构图](diagrams.md) ｜ [未来设想图](feture.md) | [项目缺陷](gaps.md)

> 最后更新：2026年6月 | 测试：151/151

---

## 总览

| 优先级 | 分类 | 待完善项数量 |
|--------|------|------------|
| 🔴 高 | 安全 | 4 |
| 🔴 高 | 运维 | 4 |
| 🔴 高 | 测试 | 2 |
| 🟡 中 | 性能 | 4 |
| 🟡 中 | 配置 | 22+ |
| 🟡 中 | 代码质量 | 3 |
| 🟢 低 | 监控 | 4 |
| 🟢 低 | 功能 | 5 |
| 🟢 低 | 文档 | 4 |
| 🟢 低 | 错误处理 | 4 |

---

## 1. 安全 🔴

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 1.1 | **无 CSRF 保护** — 所有 POST 端点未配置 `flask_wtf.CSRFProtect` | `web_ui.py` | 添加 `flask_wtf.CSRFProtect(app)` |
| 1.2 | **无速率限制** — `/api/chat` 可被无限调用，消耗 API 额度 | `web_ui.py:184` | 使用 `flask-limiter` 限制 `/api/chat` 为 10次/分钟 |
| 1.3 | **无文件上传大小限制** — Flask 默认无上限，可上传超大文件 | `web_ui.py` | 设置 `app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024` |
| 1.4 | **XSS 风险** — 服务端 Markdown 渲染后 `innerHTML` 直接注入，`escapeHtml()` 未覆盖所有路径 | `script.js` | 使用 `markdown` 库的 `safe_mode` 或添加 HTML sanitizer |

---

## 2. 运维 🔴

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 2.1 | **无 Docker 支持** — 无 `Dockerfile` 或 `docker-compose.yml` | 根目录 | 添加 `Dockerfile` + `docker-compose.yml` (Flask + ChromaDB) |
| 2.2 | **无健康检查端点** — 负载均衡器无法探测服务状态 | `web_ui.py` | 添加 `GET /health` 返回 `{"status": "ok", "db": "connected"}` |
| 2.3 | **无优雅关闭** — SIGTERM 时正在保存的会话可能损坏 | `web_ui.py` | 添加 `signal.signal(SIGTERM, shutdown_handler)` |
| 2.4 | **使用 Flask 开发服务器** — 不适合生产环境 | `web_ui.py:556` | 替换为 `waitress` 或 `gunicorn`，已在 `requirements.txt` 中但未配置 |

---

## 3. 测试 🔴

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 3.1 | **前端 JS 零测试** — 1441 行 `script.js` 无任何自动化测试 | `static/script.js` | 引入 Cypress 或 Playwright 做 E2E 测试 |
| 3.2 | **`run_crew()` 无集成测试** — 307 行核心编排函数靠 mock 间接覆盖 | `main.py:425` | 编写端到端集成测试（真实 ChromaDB + mock LLM） |

---

## 4. 性能 🟡

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 4.1 | **`search_all_sessions` N+1 读取** — 每个会话文件独立读取 | `tools/session_manager.py:94-96` | 使用批量读取或 SQLite 替代 JSON 文件 |
| 4.2 | **SHA256 全文件读入内存** — 大文件消耗大量 RAM | `tools/rag_store.py:328` | 改为分块哈希（`hashlib.sha256` 支持 `update()`） |
| 4.3 | **无 API 分页** — `/api/history` 返回全部消息 | `web_ui.py` | 添加 `?page=1&limit=20` 分页参数 |
| 4.4 | **BM25 索引每次全量重建** — dirty flag 触发后重建整个索引 | `tools/rag_store.py:679-688` | 改为增量更新或 LRU 缓存 |

---

## 5. 硬编码配置 🟡

以下值应改为环境变量或配置文件：

| 文件 | 行 | 值 | 建议变量名 |
|------|-----|-----|-----------|
| `main.py` | 26 | `temperature=0.7` | `LLM_TEMPERATURE` |
| `main.py` | 39 | `temperature=0.1` | `ROUTER_TEMPERATURE` |
| `main.py` | 27 | `max_tokens=4000` | `LLM_MAX_TOKENS` |
| `main.py` | 93 | `_SEARCH_CACHE_TTL = 3600` | `SEARCH_CACHE_TTL` |
| `main.py` | 468 | `RAG_K = 3` | `RAG_TOP_K` |
| `main.py` | 469 | `MAX_RAG_CHARS = 2000` | `MAX_RAG_CHARS` |
| `main.py` | 165 | `max_results=5` | `TAVILY_MAX_RESULTS` |
| `main.py` | 25 | `base_url="https://api.deepseek.com"` | `LLM_BASE_URL` |
| `tools/rag_store.py` | 239 | `model_name="paraphrase-multilingual-MiniLM-L12-v2"` | `EMBEDDING_MODEL` |
| `tools/rag_store.py` | 774 | `0.7 / 0.3` (embedding/BM25 fusion) | `EMBEDDING_WEIGHT` / `BM25_WEIGHT` |
| `tools/rag_store.py` | 83 | `_MAX_ENTRIES = 100` | `RETRIEVAL_CACHE_SIZE` |
| `tools/answer_cache.py` | 118 | `_SIMILARITY_THRESHOLD = 0.65` | `CACHE_SIMILARITY_THRESHOLD` |
| `tools/document_processor.py` | 48 | `min_size=100, max_size=1200` | `CHUNK_MIN_SIZE` / `CHUNK_MAX_SIZE` |
| `tools/image_captioner.py` | 68 | `conf >= 0.3` | `OCR_CONFIDENCE_THRESHOLD` |
| `web_ui.py` | 557 | `host='127.0.0.1'` | `FLASK_HOST` |

---

## 6. 代码质量 🟡

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 6.1 | **`run_crew()` 307 行** — 巨型函数混合了路由、检索、门控、生成、指标计算 | `main.py:425-732` | 拆分为 5-6 个小函数：`_do_retrieval()`, `_apply_gate()`, `_execute_visual()`, `_execute_lecture()`, `_execute_web()` |
| 6.2 | **Web 搜索结果索引代码重复** — 两处完全相同的 `json.loads + index_web_search` | `main.py:570-578` 和 `main.py:688-696` | 提取为 `_persist_web_results(search_context)` 函数 |
| 6.3 | **`tenacity` 库已安装但从未使用** — 可用于 LLM API 重试 | `requirements.txt` | 在 `tavily_direct_search()` 和 `crew.kickoff()` 添加 `@retry` 装饰器 |

---

## 7. 监控 🟢

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 7.1 | **日志无结构化格式 + 无请求 ID** | `main.py:14`, `web_ui.py` | 添加请求级 `request_id`（Flask `g`），使用 `python-json-logger` |
| 7.2 | **OpenTelemetry 包已安装但未使用** | `requirements.txt:98-104` | 初始化 OTel SDK，追踪 LLM 调用和 RAG 检索延迟 |
| 7.3 | **无应用指标** — 无请求计数、延迟、缓存命中率 | 全局 | 添加 `prometheus_client` 导出 `/metrics` 端点 |
| 7.4 | **日志无文件输出** — 仅 stdout，进程退出后日志丢失 | `main.py:14` | 添加 `RotatingFileHandler` |

---

## 8. 功能缺失 🟢

| # | 问题 | 修复建议 |
|---|------|---------|
| 8.1 | **无暗色模式** — 1443 行 CSS 无 `prefers-color-scheme: dark` | 添加媒体查询 + CSS 变量切换 |
| 8.2 | **移动端适配不足** — 侧边栏+主内容区布局不适合小屏幕 | 添加汉堡菜单、可折叠侧边栏 |
| 8.3 | **仅支持 Markdown 导出** — 无 PDF/HTML/JSON 导出 | 添加 `python-pdfkit` 或 `weasyprint` 支持 PDF 导出 |
| 8.4 | **无用户认证** — 所有用户共享同一会话空间 | 添加 Flask-Login 或简单的 API Key 认证 |
| 8.5 | **无批量操作** — 文件只能逐个上传/删除 | 支持多文件上传和批量删除 |

---

## 9. 文档 🟢

| # | 问题 | 修复建议 |
|---|------|---------|
| 9.1 | **无 API 文档** — README 表格仅列出端点名称，无请求/响应示例 | 添加 OpenAPI/Swagger 规范或 `flasgger` |
| 9.2 | **部分函数缺少 docstring** — `_build_llm()`, `tavily_direct_search()`, `get_conversation_manager_from_session()` 等 | 补充 Google-style docstrings |
| 9.3 | **无 CONTRIBUTING 指南** | 添加 `md/CONTRIBUTING.md` |
| 9.4 | **无 CI/CD 配置** | 添加 `.github/workflows/test.yml`（pytest + linting） |

---

## 10. 错误处理 🟢

| # | 问题 | 位置 | 修复建议 |
|---|------|------|---------|
| 10.1 | **`crew.kickoff()` 无重试** — LLM API 限流时直接失败 | `main.py:301` | 添加 `@retry(stop=stop_after_attempt(3))` |
| 10.2 | **`cannot_answer` 路径重复添加 user 消息** | `web_ui.py:247` | 移除重复的 `add_message("user", ...)` 调用 |
| 10.3 | **错误信息泄漏内部路径** — `str(e)` 直接返回给用户 | `web_ui.py:237` | 仅返回通用错误信息，详细错误记录到日志 |
| 10.4 | **`tavily_direct_search()` 无网络重试** | `main.py:162` | 添加 `@retry` 处理临时网络故障 |

---

## 优先级路线图

### 第一阶段：安全 + 运维基础（2-3 天）

```
Dockerfile + docker-compose.yml → /health 端点 → waitress 生产服务器
→ CSRF 保护 → 速率限制 → 文件上传大小限制
```

### 第二阶段：测试 + 代码质量（3-5 天）

```
Cypress/Playwright E2E 测试 → run_crew() 拆分 → 消除重复代码
→ 集成测试覆盖核心链路
```

### 第三阶段：性能 + 配置（2-3 天）

```
API 分页 → SHA256 分块读取 → 硬编码值移至 .env
→ BM25 增量更新 → ETag 缓存
```

### 第四阶段：监控 + 功能增强（3-5 天）

```
结构化日志 + 请求 ID → Prometheus 指标 → OpenTelemetry 追踪
→ 暗色模式 → 移动端适配 → PDF 导出
```

---

*此文件描述当前项目的已知差距和改进方向，非 Bug 报告。Bug 报告见 [BUG_REPORT.md](BUG_REPORT.md)。*

# LectureCrewLLM

> [English](README.md) | [中文](README_CN.md)

**多智能体讲座分析系统** — 多模态 RAG（文本+图片+表格）+ 联网搜索 + 交互式 Web UI

基于 CrewAI、ChromaDB 和 Flask 构建。使用 DeepSeek 作为 LLM，sentence-transformers 实现跨语言嵌入，BLIP 实现图片描述生成。

---

## 功能特性

- **多智能体协作** — 意图路由 → RAG 检索 → 相关性验证 → 分析师，智能编排流程
- **多模态 RAG** — 从 PDF/PPTX/DOCX 中提取文本（语义分块）、图片（BLIP 描述）、表格（Markdown）
- **联网搜索** — Tavily API 实时搜索，支持手动开关，自动缓存（1h TTL）
- **智能缓存** — 答案缓存（30 天 TTL）+ 检索缓存 + 搜索缓存，三级缓存避免冗余调用
- **SSE 实时进度** — 4 步进度条 + 计时器 + 轮播提示
- **文件管理** — 上传、删除、重建索引，增量索引仅处理变更文件
- **多会话管理** — 持久化对话历史，支持切换、新建、删除
- **优雅降级** — 搜索失败时自动回退到仅讲座内容

---

## 系统架构

```
用户提问
    │
    ▼
┌─ 缓存检查 ──────────────────────────────────┐
│  命中 → 直接返回（零 LLM 调用）               │
│  未命中 → 继续                               │
└──────────────────────────────────────────────┘
    │
    ▼
┌─ 规则路由器（关键词匹配，零 LLM）─────────────┐
│  → web 意图直接走搜索，无需 LLM               │
│  → 不匹配 → 交 LLM Router                    │
└──────────────────────────────────────────────┘
    │
    ▼
┌─ LLM Router ────────────────────────────────┐
│  分类: lecture / web / hybrid / unknown      │
└──────────────────────────────────────────────┘
    │
    ├── "lecture" ──→ RAG → 相似度门控
    │                       ├─ ≥0.82 → 直接使用（免 Guard）
    │                       ├─ 0.55~0.82 → Grounding Check
    │                       └─ ≤0.55 → 跳过
    │                       │
    │                       ▼
    │                  Analyst 生成答案
    │
    ├── "web" ────────→ Tavily 搜索 → Analyst
    │
    └── "hybrid" ─────→ RAG + 搜索 → Analyst
```

### Agent 角色

| Agent | 职责 | Token |
|-------|------|-------|
| **🎯 意图路由器** | 判断问题类别 lecture/web/hybrid/unknown | ~50 |
| **✅ 相关性验证员** | 边界案例判断 RAG 结果是否语义相关 | ~200 |
| **📝 讲座分析师** | 综合 RAG + 搜索信息，生成中文 Markdown 回答 | ~1000-2000 |

### 多模态 RAG 管道

```
knowledge/*.pdf / *.pptx / *.docx
    │
    ├── DocumentProcessor
    │   ├── extract_text()    → 语义分块（段落/标题边界，100-1200 字符）
    │   ├── extract_images()  → PIL Image → BLIP 描述
    │   └── extract_tables()  → Markdown 表格
    │
    └── ChromaDB（384 维嵌入，paraphrase-multilingual-MiniLM-L12-v2）
            │
            余弦相似度 ANN → BM25 混合重排序 → Top-K
            │
            相似度阈值三档门控（≥0.82 / 0.55~0.82 / ≤0.55）
```

---

## 快速开始

### 环境要求

- Python 3.11+
- DeepSeek API Key — [platform.deepseek.com](https://platform.deepseek.com/api_keys)
- Tavily API Key — [app.tavily.com](https://app.tavily.com)（联网搜索需要）

### 安装

```bash
cd lecture_crewLLM
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY、TAVILY_API_KEY、FLASK_SECRET_KEY
pip install -r requirements.txt
mkdir -p knowledge
```

### 启动

```bash
python web_ui.py     # Web UI（推荐），访问 http://localhost:7860
python main.py       # CLI 模式
```

### 运行测试

```bash
python -m pytest tests/ -v    # 83 个测试，全部通过
```

---

## 项目结构

```
lecture_crewLLM/
├── main.py                          # CLI 入口 + Agent 编排
├── web_ui.py                        # Flask Web UI + REST API + SSE
├── requirements.txt                 # 依赖锁定
├── .env.example                     # 环境变量模板
│
├── tools/
│   ├── rag_store.py                 # ChromaDB + BM25 混合检索
│   ├── document_processor.py        # 文档解析 + 语义分块
│   ├── image_captioner.py           # BLIP 图片描述
│   ├── conversation_manager.py      # 对话历史（≤300 tokens 摘要）
│   ├── session_manager.py           # 多会话管理
│   ├── answer_cache.py              # 答案缓存（30 天 TTL）
│   ├── google_search_tool.py        # Google 搜索集成
│   ├── local_file_tool.py           # 文件读取（CrewAI Tool）
│   └── status_tracker.py            # SSE 进度追踪
│
├── tests/                           # 83 个测试
├── templates/index.html             # Web UI 模板
├── static/                          # CSS + JS
│
├── knowledge/                       # 讲座文件
├── images/                          # 提取的图片
├── chroma_db/                       # 向量数据库
├── conversations/sessions/          # 对话数据
├── cache/                           # 缓存
└── output/                          # 答案导出
```

---

## 配置

| 变量 | 必填 | 说明 | 默认 |
|------|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 | — |
| `TAVILY_API_KEY` | 否 | Tavily 搜索密钥 | — |
| `FLASK_SECRET_KEY` | 是* | Flask 会话密钥 | — |
| `WEB_UI_PORT` | 否 | Web UI 端口 | `7860` |
| `FLASK_DEBUG` | 否 | 调试模式 | `0` |

\* Web UI 必需

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 系统状态 |
| GET/POST | `/api/sessions` | 会话列表/创建 |
| POST/DELETE | `/api/sessions/<path>` | 切换/删除会话 |
| GET | `/api/chat/task` | SSE task ID |
| POST | `/api/chat` | 发送消息 |
| GET | `/api/chat/stream` | SSE 进度流 |
| GET/DELETE | `/api/history` | 对话历史 |
| GET/POST/DELETE | `/api/knowledge/*` | 文件管理 |
| GET/DELETE | `/api/cache` | 缓存 |
| GET | `/images/<filename>` | 图片文件 |

---

## 关键设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **Sequential 替代 Hierarchical** | Pipeline 路由→验证→分析 | Hierarchical 多 3 次 Manager 调用（~24s），Sequential 仅 2-3 次（~8s） |
| **图片存为文字描述** | BLIP 描述 → 向量化 | 避免多模态嵌入模型，384 维即可检索 |
| **语义分块** | 段落/标题边界，100-1200 字符 | 尊重文档结构而非固定长度切割 |
| **移除 CrossEncoder** | BM25 + 嵌入相似度融合（70/30） | 省 1-2s/次查询，BM25 补充统计匹配已足够 |
| **阈值门控** | ≥0.82 直接用 / 0.55-0.82 Guard / ≤0.55 跳过 | 减少不必要的 Guard LLM 调用 |
| **双路由** | 规则匹配（关键词）→ LLM 兜底 | 天气/新闻等明确问题零 LLM 路由成本 |
| **缓存归一化** | 去标点+排序+停用词过滤 | "什么是 BERT" ≡ "BERT 是什么" |

---

## 测试覆盖（83 个）

| 模块 | 数量 |
|------|------|
| `test_rag.py` | 31 |
| `test_answer_cache.py` | 12 |
| `test_conversation_manager.py` | 11 |
| `test_session_manager.py` | 10 |
| `test_web_api.py` | 11 |
| `test_status_tracker.py` | 6 |
| `test_local_file_tool.py` | 3 |

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 向量库错误 | `rm -rf chroma_db/` 后重启重建索引 |
| API Key 错误 | 检查 `.env` 中的密钥 |
| 端口占用 | 修改 `WEB_UI_PORT` |
| BLIP 模型问题 | 回退为 `[图片：WxH 像素]` 占位符 |
| 对话文件损坏 | 删除 `conversations/` 目录 |

---

## 开发历程

| 阶段 | 内容 |
|------|------|
| **基础架构** | CrewAI + ChromaDB + DeepSeek + Flask + CLI |
| **RAG 增强** | 语义分块、BLIP 图片描述、表格 MD、DOCX 支持 |
| **性能优化** | Sequential 取代 Hierarchical、移除 CrossEncoder（省 1-2s/次）、RAG 上下文减半（4000→2000 字）、多级缓存 |
| **体验优化** | 中文界面、SSE 4 步进度、实时计时器、轮播提示 |
| **智能路由** | 规则 + LLM 双路由、Grounding Check 语义验证、三档阈值门控 |
| **稳定性** | 图片 URL 编码、路径穿越防护、缓存自动清理 |

---

*最后更新：2026年5月*

# LectureCrewLLM

> [English](README.md) | [中文](README_CN.md)

Multi-agent lecture analysis system with **multi-modal RAG** (text + images + tables), web search, and interactive Web UI.

Built with [CrewAI](https://github.com/crewAIInc/crewAI), ChromaDB, and Flask. Uses DeepSeek as the LLM, sentence-transformers for cross-lingual embeddings, and BLIP for image captioning.

## Features

- **Multi-Agent Architecture** — Internet Researcher, Lecture Analyst, and Manager coordinated via CrewAI hierarchical process
- **Multi-Modal RAG Pipeline** — Extracts text, images (BLIP-captioned), and tables (Markdown) from PDF/PPTX/DOCX files with semantic chunking
- **Web Search Integration** — Google Programmable Search for supplementary information
- **Real-Time Progress** — SSE streaming shows agent execution status in the Web UI
- **Knowledge Management** — Upload, list, delete, and reindex lecture files via Web UI
- **Multi-Session Conversations** — Persistent conversation history with session switching and deletion
- **Answer Caching** — TTL-based cache (30-day default) avoids redundant LLM calls
- **Graceful Degradation** — Web search failures don't block answer generation; falls back to lecture content only

## Quick Start

### Prerequisites

- Python 3.11+
- DeepSeek API key — [platform.deepseek.com](https://platform.deepseek.com/api_keys)
- Google Programmable Search Engine — [programmablesearchengine.google.com](https://programmablesearchengine.google.com)
  - Create a search engine, get the **API Key** and **Search Engine ID (CSE ID)**

### Setup

```bash
# 1. Clone and enter the project
cd lecture_crewLLM

# 2. Create your environment config
cp .env.example .env
# Edit .env with your API keys:
#   DEEPSEEK_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID, FLASK_SECRET_KEY

# 3. Install dependencies
pip install -r requirements.txt       # exact versions (recommended)
# or: pip install -e .                # from pyproject.toml

# 4. Install optional test dependencies
pip install -e ".[test]"              # adds pytest

# 5. Place lecture files (PDF/PPTX/DOCX) in the knowledge/ folder
mkdir -p knowledge
```

### Run

```bash
# Web UI (recommended)
python web_ui.py
# Open http://localhost:7860

# CLI mode
python main.py
```

### Run Tests

```bash
python -m pytest tests/ -v
# 70 tests across 7 modules
```

## Usage

### Web UI

1. Place lecture files (`.pdf` / `.pptx` / `.docx`) in `knowledge/` or upload via the Web UI
2. Start the server and open `http://localhost:7860`
3. Ask questions about your lectures
4. Watch real-time agent progress: "Searching web..." → "Synthesizing answer..." → "Complete!"
5. Manage files via the Knowledge panel: upload, delete, reindex
6. Switch between conversation sessions via the sidebar

### CLI Commands

| Command | Purpose |
|---------|---------|
| `<question>` | Ask a question about your lectures |
| `sessions` | Switch or create conversation sessions |
| `clear` | Start a new conversation |
| `history` | Show conversation history |
| `cache` | Show cache statistics |
| `cache clear` | Delete all cached answers |
| `exit` / `quit` | Quit |

## Project Structure

```
lecture_crewLLM/
├── main.py                      # CLI entry point + crew orchestration
├── web_ui.py                    # Flask Web UI + REST API + SSE + Knowledge API
├── pyproject.toml               # Project metadata & dependencies
├── requirements.txt             # Locked dependency versions
├── .env.example                 # Environment variable template
│
├── tools/
│   ├── __init__.py
│   ├── local_file_tool.py       # Basic PDF/PPTX text extraction
│   ├── document_processor.py    # Multi-format processor (PDF/PPTX/DOCX)
│   │                            #   + semantic chunking + image & table extraction
│   ├── image_captioner.py       # BLIP-based image description
│   ├── rag_store.py             # Multi-modal ChromaDB vector store
│   ├── conversation_manager.py  # Conversation history persistence
│   ├── session_manager.py       # Multi-session creation & switching
│   ├── answer_cache.py          # Question-answer cache with TTL
│   ├── google_search_tool.py    # Google Programmable Search integration
│   └── status_tracker.py        # In-memory SSE progress tracker
│
├── tests/
│   ├── test_answer_cache.py     # Cache unit tests (12 tests)
│   ├── test_conversation_manager.py  # Conversation tests (11 tests)
│   ├── test_session_manager.py  # Session management tests (10 tests)
│   ├── test_status_tracker.py   # SSE tracker tests (6 tests)
│   ├── test_local_file_tool.py  # File reader tests (3 tests)
│   ├── test_rag.py              # RAG + document processor tests (20 tests)
│   └── test_web_api.py          # Flask API tests (11 tests)
│
├── templates/index.html         # Web UI template
├── static/
│   ├── style.css                # Stylesheet
│   └── script.js                # Client-side JavaScript + EventSource SSE
│
├── knowledge/                   # ← Place lecture files here (PDF, PPTX, DOCX)
├── images/                      # Extracted images (auto-created)
├── conversations/sessions/      # Session JSON files (auto-created)
├── cache/                       # Answer cache (auto-created)
├── chroma_db/                   # Vector database (auto-created)
└── output/                      # Timestamped answer exports (auto-created)
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `DEEPSEEK_API_KEY` | Yes | DeepSeek API key |
| `GOOGLE_API_KEY` | Yes | Google Cloud API key |
| `GOOGLE_CSE_ID` | Yes | Google Custom Search Engine ID |
| `FLASK_SECRET_KEY` | Yes* | Flask session signing key. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `WEB_UI_PORT` | No | Web UI port (default: `7860`) |
| `FLASK_DEBUG` | No | Enable debug mode — set to `1` for development only (default: `0`) |

\* Required for Web UI. The server will refuse to start without it.

## Architecture

### System Flow

```
用户提问
    │
    ▼
┌─ Cache Check ────────────────────────┐
│  命中 → 直接返回缓存答案             │
│  未命中 → 继续                       │
└──────────────────────────────────────┘
    │
    ▼
┌─ Router Agent (意图路由) ────────────┐
│  分类: lecture / web / hybrid        │
│  → 决定走哪条 pipeline               │
└──────────────────────────────────────┘
    │
    ├── "lecture" ────→ RAG → Grounding Check → Analyst
    │                    ↑ 向量检索 + 相关性验证
    ├── "web" ────────→ Web Search → Analyst
    │                    ↑ Google Programmable Search
    └── "hybrid" ──────→ RAG + Web Search → Grounding → Analyst
                              │
                              ▼
                         SSE 实时进度推送 (4步: 路由→检索→搜索→生成)
                              │
                              ▼
                       前端显示 Markdown 答案
```

### Multi-Agent Architecture

```
┌──────────────────────────────────────────────────┐
│                   CrewAI                          │
│              Sequential Process                   │
│                                                   │
│  ┌──────────────┐   ┌──────────────┐             │
│  │ 意图路由器    │   │ 相关性验证员  │             │
│  │ (Router)     │   │ (Grounding)  │             │
│  │ LLM, 0.1 temp│   │ LLM, 0.1 temp│             │
│  │ ~50 tokens   │   │ ~100 tokens  │             │
│  └──────────────┘   └──────────────┘             │
│                                                   │
│  ┌──────────────┐   ┌──────────────┐             │
│  │ 网络研究员    │   │ 讲座分析师    │             │
│  │ (Searcher)   │   │ (Analyst)    │             │
│  │ Google Search│   │ RAG + Web →  │             │
│  │ Tool         │   │ Markdown回答  │             │
│  └──────────────┘   └──────────────┘             │
└──────────────────────────────────────────────────┘
```

### Multi-Modal RAG Pipeline

```
knowledge/*.pdf / *.pptx / *.docx
    │
    ├── DocumentProcessor
    │   ├── extract_text()    → 语义分块（段落/标题/句子边界）
    │   ├── extract_images()  → PIL Image → BLIP描述 → 存文件
    │   └── extract_tables()  → 转为 Markdown 表格字符串
    │
    └── ChromaDB PersistentClient
        ├── document: 文本内容 / 图片描述 / 表格 Markdown
        ├── metadata:
        │   ├── type:       "text" | "image" | "table"
        │   ├── source:     来源文件名
        │   ├── indexed_at: 索引时间戳
        │   └── image_path: 图片路径（仅 image 类型）
        └── vector: 384维嵌入（paraphrase-multilingual-MiniLM-L12-v2）
                │
                ▼
        用户提问 → 同一模型嵌入
                │
                ▼
        余弦相似度 ANN 搜索 → Top-K 结果
                │
                ▼
        Grounding Check: RELEVANT / IRRELEVANT
                │
                ▼
        注入 Analyst Agent prompt
```

### Data Storage Structure

每个 ChromaDB 条目：

```
{
  id:        "lecture1_text_3"           # {stem}_{type}_{index}
  document:  "Transformer 的核心是自注意力机制..."
  metadata: {
    type:        "text"                  # text | image | table
    source:      "knowledge/lecture1.pptx"
    chunk_index: 3
    indexed_at:  "2026-05-26T10:30:00"
  }
  vector:    [0.123, 0.456, ...]         # 384 维 float
}
```

图片类型额外包含 `image_path` 和 `image_filename` 字段，图片二进制文件存储在 `images/` 目录下。

### SSE Progress Flow

```
Browser                          Flask Server
  │                                  │
  ├─ GET /api/chat/task ────────────→│  (获取 task_id)
  │←──────── {task_id: "abc123"} ────┤
  │                                  │
  ├─ GET /api/chat/stream?task_id=   │  (EventSource)
  │                                  │
  ├─ POST /api/chat {message, task_id}──┤
  │                                  ├── Router: 分析问题意图
  │←──── SSE: {"step":"routing"} ─────┤
  │                                  ├── RAG: 检索知识库
  │←──── SSE: {"step":"rag"} ────────┤
  │                                  ├── Web Search / Grounding
  │←──── SSE: {"step":"searching"} ───┤
  │                                  ├── Analyst: 生成答案
  │←──── SSE: {"step":"generating"} ──┤
  │                                  │
  │←── SSE: {"step":"complete"} ─────┤
  │←──────── {response: "..."} ──────┤
```

### REST API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/status` | System status |
| `GET` | `/api/sessions` | List all sessions |
| `POST` | `/api/sessions` | Create new session |
| `POST` | `/api/sessions/<path>` | Switch to session |
| `DELETE` | `/api/sessions/<path>` | Delete session |
| `GET` | `/api/chat/task` | Get SSE task ID |
| `POST` | `/api/chat` | Send message |
| `GET` | `/api/chat/stream` | SSE progress stream |
| `GET` | `/api/history` | Conversation history |
| `DELETE` | `/api/history` | Clear history |
| `GET` | `/api/knowledge` | List files |
| `POST` | `/api/knowledge/upload` | Upload file |
| `DELETE` | `/api/knowledge/<filename>` | Delete file |
| `POST` | `/api/knowledge/reindex` | Force reindex |
| `GET` | `/api/cache` | Cache stats |
| `DELETE` | `/api/cache` | Clear cache |
| `GET` | `/images/<filename>` | Serve extracted images |

### Web UI Layout

```
┌──────────────┬──────────────────────────────────┐
│  侧边栏       │  主聊天区                        │
│              │  ┌──────────────────────────┐    │
│  📚 对话      │  │ 历史消息自动显示在主界面  │    │
│  ├ 当前会话   │  │ 📝 用户消息              │    │
│  └ 切换/创建  │  │ 🤖 助手消息 [+ 导出按钮]  │    │
│              │  └──────────────────────────┘    │
│  📁 讲座文件   │                                  │
│  ├ 文件列表   │  ┌────────────────────────┐     │
│  ├ 上传/删除  │  │ 输入框     [发送] [🌐联网] │   │
│  └ 重建索引   │  │ Shift+Enter 发送         │    │
│              │  └────────────────────────┘     │
│  ⚡ 缓存      │                                  │
│  🎛️ 控制      │  加载时: 4步进度 + 计时器 + 提示  │
│  └ 导出对话   │                                  │
└──────────────┴──────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Sequential over Hierarchical** | Hierarchical calls Manager 3 extra times (~24s). Sequential uses 2 LLM calls (~12s). |
| **Image as text description** | Images are BLIP-captioned, description is vectorized. Avoids multi-modal embedding model. |
| **Semantic chunking** | Paragraph/heading boundaries instead of fixed 500-char split. Respects document structure. |
| **Grounding Check** | LLM verifies RAG results relevance before passing to Analyst. Prevents irrelevant context leakage. |
| **Router Agent** | Classifies intent before processing. Weather questions skip RAG entirely (avoid "temperature" ambiguity). |
| **Cache normalization** | MD5 hash after removing punctuation + stop words + sorting tokens. "What is BERT?" ≡ "BERT" |

See [ARCHITECTURE.md](ARCHITECTURE.md) for more detailed technical documentation.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Vector DB errors | `rm -rf chroma_db/` and restart to reindex |
| API key errors | Verify all four keys in `.env` are set and valid |
| Port already in use | Change `WEB_UI_PORT` in `.env` |
| Corrupted sessions | Delete `conversations/` directory |
| Module import errors | Run `pip install -r requirements.txt` |
| BLIP model issues | Image captions fall back to `[图片：WxH 像素]` placeholder |

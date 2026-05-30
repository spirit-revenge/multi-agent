# LectureCrewLLM

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

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation including:
- Agent design and data flow
- Multi-modal RAG pipeline (text + images + tables)
- SSE progress flow
- API endpoint reference
- Error handling strategy
- Caching design

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Vector DB errors | `rm -rf chroma_db/` and restart to reindex |
| API key errors | Verify all four keys in `.env` are set and valid |
| Port already in use | Change `WEB_UI_PORT` in `.env` |
| Corrupted sessions | Delete `conversations/` directory |
| Module import errors | Run `pip install -r requirements.txt` |
| BLIP model issues | Image captions fall back to `[图片：WxH 像素]` placeholder |

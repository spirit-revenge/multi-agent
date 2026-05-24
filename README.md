# LectureCrewLLM

Multi-agent lecture analysis system with RAG retrieval, web search, and interactive Web UI. Built with [CrewAI](https://github.com/crewAIInc/crewAI), ChromaDB, and Flask.

## Features

- **Multi-Agent Architecture** — Internet Researcher + Lecture Analyst + Manager, coordinated via CrewAI hierarchical process
- **RAG Pipeline** — Semantic retrieval from lecture files (PDF/PPTX) using sentence-transformers and ChromaDB
- **Web Search Integration** — Google Programmable Search for supplementary information
- **Web UI with SSE** — Real-time progress streaming showing agent execution status
- **Multi-Session Conversations** — Persistent conversation history with session switching
- **Answer Caching** — Avoid redundant LLM calls with TTL-based cache (30-day default)
- **Incremental Indexing** — Only re-processes changed lecture files

## Quick Start

### Prerequisites

- Python 3.13+
- DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com))
- Google Programmable Search Engine ([programmablesearchengine.google.com](https://programmablesearchengine.google.com))

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Run Web UI

```bash
python web_ui.py
# Open http://localhost:7860
```

### Run CLI

```bash
python main.py
```

## Usage

### Web UI

1. Place lecture files (`.pdf` / `.pptx`) in the `knowledge/` folder
2. Start the server, open `http://localhost:7860`
3. Type questions about your lectures — the system retrieves relevant excerpts, searches the web, and synthesizes an answer
4. Switch between conversation sessions via the sidebar

### CLI Commands

| Command | Purpose |
|---------|---------|
| `<question>` | Ask a question about your lectures |
| `sessions` | Switch or create conversation sessions |
| `clear` | Start a new conversation |
| `history` | Show conversation history |
| `cache` | Show cache statistics |
| `cache clear` | Delete all cached answers |
| `exit` | Quit |

## Project Structure

```
lecture_crewLLM/
├── main.py                      # CLI entry point + crew orchestration
├── web_ui.py                    # Flask Web UI + REST API + SSE
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
│
├── tools/
│   ├── local_file_tool.py       # PDF/PPTX text extraction
│   ├── rag_store.py             # ChromaDB vector store + RAG retrieval
│   ├── conversation_manager.py  # Conversation history persistence
│   ├── session_manager.py       # Multi-session discovery and creation
│   ├── answer_cache.py          # Question-answer cache with TTL
│   ├── google_search_tool.py    # Google Programmable Search integration
│   └── status_tracker.py        # In-memory SSE progress tracker
│
├── templates/index.html         # Web UI template
├── static/
│   ├── style.css                # Stylesheet
│   └── script.js                # Client-side JavaScript + SSE
│
├── knowledge/                   # Place lecture files here (PDF, PPTX)
├── conversations/sessions/      # Session JSON files (auto-created)
├── cache/                       # Answer cache (auto-created)
├── chroma_db/                   # Vector database (auto-created)
└── output/                      # Timestamped answer exports (auto-created)
```

## Configuration

All configuration is in `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `DEEPSEEK_API_KEY` | Yes | DeepSeek API key |
| `GOOGLE_API_KEY` | Yes | Google Cloud API key |
| `GOOGLE_CSE_ID` | Yes | Google Custom Search Engine ID |
| `FLASK_SECRET_KEY` | Yes* | Flask session signing key (*required for Web UI) |
| `WEB_UI_PORT` | No | Web UI port (default: `7860`) |
| `FLASK_DEBUG` | No | Enable debug mode (default: `0`) |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation including agent design, data flow, RAG pipeline, and API reference.

## Troubleshooting

**Vector DB issues:** `rm -rf chroma_db/` and restart to reindex all files.

**API errors:** Verify `.env` contains valid `DEEPSEEK_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`.

**Port in use:** Set `WEB_UI_PORT` to a different port in `.env`.

**Session errors:** Delete `conversations/` to start with fresh sessions.

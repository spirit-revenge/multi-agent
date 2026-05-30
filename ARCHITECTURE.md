# Architecture

## Agent Design

The system uses a 3-agent hierarchical CrewAI setup:

```
Manager Agent (Educational Manager)
├── Delegates: web search → Internet Researcher
└── Delegates: answer synthesis → Lecture Analyst
```

### Internet Researcher
- **Tool:** Google Programmable Search Engine
- **Goal:** Find definitions, examples, and recent developments related to the user's question
- **Output:** Bullet list of findings with source URLs

### Lecture Analyst
- **Goal:** Synthesize multi-modal lecture excerpts (text + image descriptions + tables) with web research into a polished English Markdown answer
- **Input:** RAG retrieval results (pre-fetched) + Internet Researcher output + conversation history
- **Output:** Well-structured English Markdown with citations

### Manager
- **Role:** Orchestrates task delegation in hierarchical process
- **Decision:** Routes tasks to the appropriate agent based on task descriptions

## Data Flow

```
User Question
    │
    ├──→ Cache Check ──→ Hit? ──→ Return cached answer
    │
    └──→ Multi-Modal RAG Retrieval (ChromaDB)
    │       │
    │       ├── Text chunks (semantic)
    │       ├── Image descriptions (BLIP-captioned)
    │       └── Tables (Markdown)
    │
    └──→ Multi-Agent Crew
            │
            ├── 1. Internet Researcher (web search)
            │
            └── 2. Lecture Analyst (synthesis)
                    │
                    └──→ Save to:
                         • Conversation history (JSON)
                         • Answer cache (JSON)
                         • Output file (Markdown)
```

## Multi-Modal RAG Pipeline

### Document Ingestion

```
knowledge/*.pdf, *.pptx, *.docx
    │
    ├── File hash check (SHA256, skip unchanged)
    │
    ├── document_processor.py
    │   ├── PDF:   PyMuPDF (text + images) + pdfplumber (tables)
    │   ├── PPTX:  python-pptx (text + images + tables + group shapes)
    │   └── DOCX:  python-docx (text + heading detection + images + tables)
    │
    ├── Semantic chunking
    │   ├── Split at heading boundaries (##, ###)
    │   ├── Split at paragraph boundaries (double newline)
    │   ├── Force-split oversize chunks at sentence boundaries (。！？.!?)
    │   └── Merge sub-minimum chunks below 100 chars
    │
    ├── Image captioning (BLIP)
    │   └── image_captioner.py: Salesforce/blip-image-captioning-base
    │
    ├── Table → Markdown conversion
    │   └── GitHub-flavored Markdown table format
    │
    └── ChromaDB storage (cosine similarity)
        ├── type: "text"    — semantically chunked paragraphs
        ├── type: "image"   — BLIP descriptions + saved image files
        └── type: "table"   — Markdown table strings
```

### Embedding Model

`paraphrase-multilingual-MiniLM-L12-v2` — enables cross-lingual retrieval (Chinese lecture content → English queries).

### Content Types in Retrieval

| Type | Icon | Storage |
|------|------|---------|
| `text` | 📝 | Vectorized text chunk |
| `image` | 🖼️ | BLIP caption text + image saved to `images/` |
| `table` | 📊 | Markdown table string |

Retrieval supports filtering by `content_type` parameter.

## Web UI Architecture

### REST API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/status` | System status |
| `GET` | `/api/sessions` | List sessions |
| `POST` | `/api/sessions` | Create session |
| `POST` | `/api/sessions/<path>` | Switch session |
| `DELETE` | `/api/sessions/<path>` | Delete session |
| `GET` | `/api/chat/task` | Get task ID for SSE |
| `POST` | `/api/chat` | Send message, trigger crew |
| `GET` | `/api/chat/stream?task_id=` | SSE progress stream |
| `GET` | `/api/history` | Get conversation history |
| `DELETE` | `/api/history` | Clear history |
| `GET` | `/api/cache` | Cache statistics |
| `DELETE` | `/api/cache` | Clear cache |
| `GET` | `/api/knowledge` | List knowledge files |
| `POST` | `/api/knowledge/upload` | Upload a document |
| `DELETE` | `/api/knowledge/<filename>` | Delete a document + its index |
| `POST` | `/api/knowledge/reindex` | Force reindex all files |

### SSE Progress Flow

```
Browser                          Flask Server
  │                                  │
  ├─ GET /api/chat/task ────────────→│  (get task_id)
  │←────────── {task_id: "abc123"} ──┤
  │                                  │
  ├─ GET /api/chat/stream?task_id=abc123 (EventSource, long-lived)
  │                                  │
  ├─ POST /api/chat {message, task_id}
  │                                  ├── run_crew() updates status_tracker
  │                                  │   → "starting": Searching web...
  │←──── SSE: {"step":"starting"} ───┤
  │                                  │   → "generating": Synthesizing...
  │←──── SSE: {"step":"generating"} ──┤
  │                                  │   → "complete": Answer ready!
  │←──── SSE: {"step":"complete"} ────┤
  │←────────── {response: "..."} ────┤  (chat response)
```

## Document Processing Pipeline

### Supported Formats

| Format | Text | Images | Tables | Tool |
|--------|------|--------|--------|------|
| PDF | PyMuPDF | PyMuPDF extraction | pdfplumber | `_process_pdf()` |
| PPTX | python-pptx | Shape images + group shapes | Shape tables | `_process_pptx()` |
| DOCX | python-docx + heading detection | Inline images via relationships | Document tables | `_process_docx()` |

### Semantic Chunking Rules

1. Normalize line endings (`\r\n` → `\n`)
2. Split at double newlines (paragraph boundaries)
3. Treat `##`, `###` headings as hard boundaries
4. Force-split paragraphs over 1200 chars at sentence boundaries (`。！？.!?`)
5. Merge consecutive short paragraphs below 100 chars

## Image Captioning

Uses `Salesforce/blip-image-captioning-base` from Hugging Face transformers. Lazy-loaded on first use.

- **Success:** `"[图片描述] a diagram of transformer architecture"`
- **Fallback (model unavailable):** `"[图片：1920x1080 像素]"`

Caption text is stored as a searchable document in ChromaDB (type: `image`). The original image is saved to `images/` and referenced via `image_path` metadata.

## Caching Strategy

- **Key:** MD5 hash of normalized question (lowercase, stripped)
- **TTL:** 30 days (configurable)
- **Storage:** JSON file (`cache/answer_cache.json`)
- **Expiration:** Checked on read; expired entries removed lazily

## Error Handling

| Failure Mode | Behavior |
|-------------|----------|
| RAG retrieval fails | Warning logged; Analyst works with empty lecture context |
| Web search fails | Google Search Tool returns error string; Analyst prompted to ignore errors and use lectures only |
| DeepSeek API fails | Exception propagated to Web UI; user sees error toast; failed question removed from history |
| BLIP model unavailable | Image captions fall back to dimension placeholders; indexing continues |
| ChromaDB corrupted | Delete `chroma_db/` directory and restart to rebuild |
| File upload (unsupported type) | 400 error with Chinese message listing supported formats |

## Testing

**70 tests across 7 modules** (`python -m pytest tests/ -v`):

| Module | Tests | Coverage |
|--------|-------|----------|
| `test_answer_cache.py` | 12 | Cache CRUD, persistence, case/punctuation/stop-word tolerance |
| `test_conversation_manager.py` | 11 | Messages, history, context building, persistence |
| `test_session_manager.py` | 10 | Session CRUD, legacy handling, labels |
| `test_status_tracker.py` | 6 | Task lifecycle, updates, concurrent safety |
| `test_local_file_tool.py` | 3 | Empty folder, path validation, filtering |
| `test_rag.py` | 20 | Semantic chunking, table→Markdown, document dispatch, image captioning, vector store CRUD |
| `test_web_api.py` | 11 | Flask endpoints, validation, page routes |

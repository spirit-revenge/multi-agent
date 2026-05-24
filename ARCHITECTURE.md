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
- **Goal:** Synthesize Chinese lecture excerpts with English web research into a polished Markdown answer
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
    └──→ RAG Retrieval (ChromaDB)
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

### Key Design Decisions

**Why RAG runs before the crew (not inside an agent task):**

RAG retrieval is a deterministic database query, not an LLM reasoning step. Running it before crew kickoff and injecting results directly into the Analyst's task context avoids wasting an agent turn on a non-reasoning operation. This is clearly documented in the Analyst's prompt — it knows the lecture excerpts come from pre-retrieved RAG results.

**Why hierarchical process:**

The Manager dynamically decides task execution order and delegation. This provides resilience: if the search agent returns an error string, the Analyst is instructed to ignore it and rely solely on lecture excerpts.

## RAG Pipeline

```
knowledge/*.pdf, *.pptx
    │
    ├── File hash check (skip unchanged)
    │
    ├── Text extraction (PyPDF2 / python-pptx)
    │
    ├── Chunking (500 chars, 100 char overlap)
    │
    ├── Embedding (paraphrase-multilingual-MiniLM-L12-v2)
    │
    └── ChromaDB persistent storage (cosine similarity)
```

The embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) is chosen for Chinese-English cross-lingual retrieval — lectures are in Chinese, questions are in English.

## Web UI Architecture

### REST API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/status` | System status (session, cache, message count) |
| `GET` | `/api/sessions` | List all conversation sessions |
| `POST` | `/api/sessions` | Create new session |
| `POST` | `/api/sessions/<path>` | Switch to a session |
| `GET` | `/api/chat/task` | Get a task ID for SSE subscription |
| `POST` | `/api/chat` | Send a message, trigger crew execution |
| `GET` | `/api/chat/stream?task_id=` | SSE endpoint for progress updates |
| `GET` | `/api/history` | Get conversation history |
| `DELETE` | `/api/history` | Clear conversation history |
| `GET` | `/api/cache` | Cache statistics |
| `DELETE` | `/api/cache` | Clear cache |

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

The status tracker uses an in-memory `queue.Queue` per task. The SSE handler reads from the queue while the crew thread writes to it.

## Caching Strategy

- **Key:** MD5 hash of normalized question (lowercase, stripped)
- **TTL:** 30 days (configurable)
- **Storage:** JSON file (`cache/answer_cache.json`)
- **Expiration:** Checked on read; expired entries removed lazily

Limitation: exact string matching only. Semantically equivalent rephrasings ("What is BERT?" vs "Explain BERT") are treated as different questions.

## Error Handling

| Failure Mode | Behavior |
|-------------|----------|
| RAG retrieval fails | Warning logged; Analyst works with empty lecture context |
| Web search fails | Google Search Tool returns error string; Analyst prompted to ignore errors and use lectures only |
| DeepSeek API fails | Exception propagated to Web UI; user sees error toast; failed question removed from history |
| ChromaDB corrupted | Delete `chroma_db/` directory and restart to rebuild |

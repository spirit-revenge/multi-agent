# LectureCrewLLM 架构图

[English](README.md) | [中文](README_CN.md) | [BUG_REPORT](BUG_REPORT.md) ｜ [架构图](picts/diagrams.md)

## 1. 请求处理流程 (Request Processing Pipeline)

```mermaid
flowchart TD
    Q["User Question"]
    
    Q --> Cache{"Cache Check<br/>exact hash + token similarity"}
    Cache -->|"Hit"| Return["Return (0 LLM)"]
    Cache -->|"Miss"| Rule["Rule Router<br/>Weather / News / Stock keywords"]
    
    Rule -->|"keyword matched"| WebPath
    Rule -->|"no match"| LLMRouter["LLM Router<br/>classify: lecture / web / hybrid / unknown"]
    
    LLMRouter -->|"lecture"| RAG["RAG Retrieval<br/>ChromaDB + BM25"]
    LLMRouter -->|"web"| Tavily["Tavily Search<br/>with 1h cache"]
    LLMRouter -->|"hybrid"| Both["RAG + Search<br/>both pipelines"]
    
    RAG --> Gate{"Similarity Gate"}
    Gate -->|"≥ 0.82"| SkipGuard["Use directly<br/>(skip Guard)"]
    Gate -->|"0.45 ~ 0.82"| Guard["Guard LLM<br/>semantic verification"]
    Gate -->|"≤ 0.45"| SkipAll["Skip<br/>(no result)"]
    
    SkipGuard --> Analyst
    Guard -->|"RELEVANT"| Analyst
    Guard -->|"IRRELEVANT"| SkipAll
    Tavily --> Analyst
    Both --> Analyst
    
    Analyst["Analyst<br/>synthesize → Chinese Markdown"]
    Analyst --> Answer["Answer"]
    
    Answer -.-> SSE["SSE Progress<br/>4 steps → frontend"]

    style Q fill:#667eea,color:#fff
    style Cache fill:#10b981,color:#fff
    style Return fill:#d1fae5,color:#059669,stroke:#10b981
    style Rule fill:#f59e0b,color:#fff
    style LLMRouter fill:#475569,color:#fff
    style RAG fill:#e0e7ff,color:#4f46e5,stroke:#6366f1
    style Tavily fill:#fef3c7,color:#d97706,stroke:#f59e0b
    style Both fill:#d1fae5,color:#059669,stroke:#10b981
    style Gate fill:#8b5cf6,color:#fff
    style Guard fill:#f3e8ff,color:#7c3aed,stroke:#8b5cf6
    style Analyst fill:#3b82f6,color:#fff
    style Answer fill:#1e293b,color:#fff
    style SSE fill:#f1f5f9,color:#475569,stroke:#cbd5e1
    style SkipAll fill:#fee2e2,color:#dc2626
```

---

## 2. 多模态 RAG 管道 (Multi-Modal RAG Pipeline)

```mermaid
flowchart TD
    Input["knowledge/*.pdf / *.pptx / *.docx"]
    
    Input --> DP["DocumentProcessor"]
    
    DP --> Text["extract_text()<br/>semantic chunking<br/>paragraph/heading boundaries"]
    DP --> Image["extract_images()<br/>PIL Image → BLIP caption<br/>+ easyocr text extraction"]
    DP --> Table["extract_tables()<br/>convert to Markdown<br/>| A | B | → table string"]
    
    Text --> DB
    Image --> DB
    Table --> DB
    
    DB["ChromaDB — Local Persistence<br/>type: text | image | table | web<br/>384-dim (paraphrase-multilingual-MiniLM-L12-v2)"]
    
    DB --> Retrieve["Cosine ANN Search"]
    Retrieve --> BM25["BM25 Hybrid Re-rank (70/30)"]
    BM25 --> TopK["Top-K Results"]
    TopK --> Gate{"Similarity Gate<br/>≥0.82 skip Guard<br/>0.45~0.82 Guard LLM<br/>≤0.45 skip"}
    
    Gate --> Context["Context → Analyst LLM → Answer"]
    
    UserQuery["User Query"] -.-> Retrieve
    UserQuery -.->|"query rewrite<br/>expand abbreviations"| UserQuery

    style Input fill:#667eea,color:#fff
    style DP fill:#475569,color:#fff
    style Text fill:#3b82f6,color:#fff
    style Image fill:#8b5cf6,color:#fff
    style Table fill:#10b981,color:#fff
    style DB fill:#1e293b,color:#fff
    style Retrieve fill:#f1f5f9,color:#475569,stroke:#cbd5e1
    style BM25 fill:#f1f5f9,color:#475569,stroke:#cbd5e1
    style TopK fill:#f1f5f9,color:#475569,stroke:#cbd5e1
    style Gate fill:#8b5cf6,color:#fff
    style Context fill:#667eea,color:#fff
    style UserQuery fill:#f59e0b,color:#fff
```

---

## 3. Agent 交互序列 (Agent Interaction Sequence)

```mermaid
sequenceDiagram
    participant User as User
    participant Web as Web UI
    participant Route as Router
    participant RAG as RAG
    participant Guard as Guard
    participant Search as Tavily
    participant Analyst as Analyst

    User->>Web: "什么是 Transformer？"
    Web->>Route: classify intent
    
    alt intent = lecture
        Route->>RAG: retrieve(k=3)
        RAG-->>Route: [text chunks + image refs]
        
        alt max_sim ≥ 0.82
            Route->>Analyst: context (skip Guard)
        else 0.45 < max_sim < 0.82
            Route->>Guard: verify relevance
            Guard-->>Route: RELEVANT / IRRELEVANT
            Route->>Analyst: context
        else max_sim ≤ 0.45
            Route->>Web: no relevant content
        end
        
    else intent = web
        Route->>Search: search(query)
        Search-->>Route: facts + urls
        Route->>Analyst: search results
        
    else intent = hybrid
        Route->>RAG: retrieve(k=3)
        Route->>Search: search(query)
        Route->>Analyst: RAG + search results
        
    else intent = visual
        Route->>RAG: retrieve(k=3, type="image")
        Route->>Analyst: image descriptions + refs
    end
    
    Analyst-->>Web: Chinese Markdown answer
    Web->>Web: _strip_invalid_images()
    Web->>Web: _extract_valid_images() → append to answer
    Web-->>User: answer + real image refs
```

---

## 4. 数据存储结构 (Data Model)

```mermaid
classDiagram
    class ChromaDBEntry {
        +String id
        +String document
        +String type
        +String source
        +int chunk_index
        +String indexed_at
        +String image_path
        +String image_filename
        +String web_query
        +String urls
        +float[] vector
    }
    note for ChromaDBEntry "id: W6_LLM_GPT_449c3ce8_text_0\n"
    note for ChromaDBEntry "type: text | image | table | web\n"
    note for ChromaDBEntry "vector: 384-dim (paraphrase-multilingual-MiniLM-L12-v2)"
```

---

## 5. 缓存层级 (Cache Hierarchy)

```mermaid
flowchart LR
    Q["Query"] --> L1
    
    subgraph "4-Tier Cache"
        L1["① Answer Cache<br/>30-day TTL<br/>exact hash + fuzzy match"]
        L2["② Retrieval Cache<br/>query|type → entries<br/>in-memory + file"]
        L3["③ Search Cache<br/>1h TTL<br/>MD5 normalized query"]
        L4["④ Web→RAG<br/>search results → ChromaDB<br/>type=web persistence"]
    end
    
    L1 -->|"miss"| L2
    L2 -->|"miss"| L3
    L3 -->|"miss"| L4
    L4 -->|"miss"| LLM["LLM Generation"]
    
    L1 -->|"hit"| Return["Return"]
    L2 -->|"hit"| Return
    L3 -->|"hit"| Return
    L4 -->|"hit"| Return

    style L1 fill:#10b981,color:#fff
    style L2 fill:#3b82f6,color:#fff
    style L3 fill:#f59e0b,color:#fff
    style L4 fill:#8b5cf6,color:#fff
    style LLM fill:#ef4444,color:#fff
    style Return fill:#d1fae5,color:#059669
```

---
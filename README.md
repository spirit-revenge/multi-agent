# LectureCrewLLM

[English](README.md) | [中文](README_CN.md)

**多智能体讲座分析系统** — 多模态 RAG（文本+图片+表格）+ 联网搜索 + 交互式 Web UI

基于 CrewAI、ChromaDB 和 Flask 构建。使用 DeepSeek 作为 LLM，sentence-transformers 实现跨语言嵌入，BLIP 实现图片描述生成。

---

## 功能特性

- **多智能体协作** — 意图路由 → RAG 检索 → 相关性验证 → 分析师生成答案，智能编排流程
- **多模态 RAG** — 从 PDF/PPTX/DOCX 中提取文本（语义分块）、图片（BLIP 描述）、表格（Markdown），统一向量化检索
- **联网搜索** — Tavily API 实时搜索，支持手动开关，自动缓存（1h TTL）
- **智能缓存** — 答案缓存（30 天 TTL，标点/停用词容忍）、检索缓存、搜索缓存，三级缓存避免冗余调用
- **SSE 实时进度** — 4 步进度条 + 计时器 + 轮播提示，Web UI 实时展示执行状态
- **文件管理** — 上传、删除、重建索引，增量索引仅处理变更文件
- **多会话管理** — 持久化对话历史，支持会话切换、新建、删除
- **优雅降级** — 搜索失败时自动回退到仅讲座内容，缓存自动清理

---

## 系统架构

### 请求流程

```
用户提问
    │
    ▼
┌─ 缓存检查 ──────────────────────────────────┐
│  命中 → 直接返回缓存答案（零 LLM 调用）      │
│  未命中 → 继续                              │
└───────────────────────────────────────────-──┘
    │
    ▼
┌─ 规则路由器（快速路径）────────────────────┐
│  关键词匹配 → 直接识别为 web 意图（无 LLM） │
│  不匹配 → 交给 LLM Router                  │
└───────────────────────────────────────────-──┘
    │
    ▼
┌─ LLM Router（意图路由）────────────────────┐
│  分类: lecture / web / hybrid / unknown     │
│  → 决定走哪条 pipeline                      │
└───────────────────────────────────────────-──┘
    │
    ├── "lecture" ──→ RAG 检索 → 相似度阈值
    │                       │
    │          ├─ ≥0.82 ──→ 直接使用（跳过 Guard）
    │          ├─ 0.55~0.82 → Grounding Check
    │          └─ ≤0.55 ──→ 跳过（无结果）
    │                       │
    │                       ▼
    │                  Analyst LLM 生成答案
    │
    ├── "web" ────────→ Tavily 搜索 → Analyst
    │
    └── "hybrid" ─────→ RAG + 搜索 → Analyst
```

### Agent 角色

| Agent | 职责 | LLM | Token 消耗 |
|-------|------|-----|-----------|
| **🎯 意图路由器 (Router)** | 判断问题类别：lecture / web / hybrid / unknown | DeepSeek, temp=0.1 | ~50 tokens |
| **✅ 相关性验证员 (Guard)** | 边界案例判断 RAG 结果是否语义相关（区分关键词重叠） | DeepSeek, temp=0.1 | ~200 tokens |
| **📝 讲座分析师 (Analyst)** | 综合 RAG + 搜索信息，生成结构化的中文 Markdown 回答 | DeepSeek, temp=0.7 | ~1000-2000 tokens |

### 多模态 RAG 管道

```
knowledge/*.pdf / *.pptx / *.docx
    │
    ├── DocumentProcessor
    │   ├── extract_text()    → 语义分块（段落/标题边界，100-1200 字符）
    │   ├── extract_images()  → PIL Image → BLIP 描述 → 存储
    │   └── extract_tables()  → 转为 Markdown 表格字符串
    │
    └── ChromaDB（本地持久化）
        ├── document: 文本 / 图片描述 / 表格 Markdown
        ├── metadata:
        │   ├── type:       "text" | "image" | "table"
        │   ├── source:     来源文件名
        │   └── indexed_at: 索引时间戳
        └── vector: 384 维嵌入（paraphrase-multilingual-MiniLM-L12-v2）
                │
                ▼
        余弦相似度 ANN 搜索 → BM25 混合重排序 → Top-K
                │
                ▼
        相似度阈值门控（≥0.82 免 Guard，≤0.55 跳过）
```

### 判定门控原理

相似度阈值分为三档，避免不必要的 LLM 调用：

- **≥0.82** → 高置信度匹配，跳过 Guard LLM，直接送入 Analyst（节省 ~2s）
- **0.55 ~ 0.82** → 边界案例，调用 Guard Agent 做 LLM 语义验证（关键词重叠 vs 真正相关）
- **≤0.55** → 低置信度，跳过 Guard 和 Analyst（无结果需回答）

### 数据存储结构

每个 ChromaDB 条目：

```
{
  id:        "lecture1_text_3"           # {文件名}_{类型}_{索引}
  document:  "Transformer 的核心是自注意力机制..."
  metadata: {
    type:        "text"                  # text | image | table
    source:      "knowledge/lecture1.pptx"
    chunk_index: 3
    indexed_at:  "2026-05-26T10:30:00"
    image_path:  "images/...png"         # 仅 image 类型
  }
  vector:    [0.123, 0.456, ...]         # 384 维
}
```

---

## 快速开始

### 环境要求

- Python 3.11+
- DeepSeek API Key — [platform.deepseek.com](https://platform.deepseek.com/api_keys)
- Tavily API Key — [app.tavily.com](https://app.tavily.com)（联网搜索需要）

### 安装

```bash
# 1. 克隆项目
cd lecture_crewLLM

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入：
#   DEEPSEEK_API_KEY, TAVILY_API_KEY, FLASK_SECRET_KEY

# 3. 安装依赖
pip install -r requirements.txt

# 4. 将讲座文件放入 knowledge/ 目录
mkdir -p knowledge
```

### 启动

```bash
# Web UI（推荐）
python web_ui.py
# 访问 http://localhost:7860

# CLI 模式
python main.py
```

### 运行测试

```bash
python -m pytest tests/ -v
# 83 个测试，覆盖 8 个模块
```

---

## 项目结构

```
lecture_crewLLM/
├── main.py                      # CLI 入口 + Agent 编排 + 路由逻辑
├── web_ui.py                    # Flask Web UI + REST API + SSE 进度流
├── requirements.txt             # 依赖锁定版本
├── .env.example                 # 环境变量模板
│
├── tools/
│   ├── rag_store.py             # ChromaDB 向量存储 + BM25 混合检索
│   ├── document_processor.py    # 文档解析（PDF/PPTX/DOCX）+ 语义分块
│   ├── image_captioner.py       # BLIP 图片描述生成
│   ├── conversation_manager.py  # 对话历史持久化（≤300 tokens 摘要）
│   ├── session_manager.py       # 多会话创建与管理
│   ├── answer_cache.py          # 问答缓存（TTL 30 天，精确+语义匹配）
│   ├── google_search_tool.py    # Google Programmable Search 集成
│   ├── local_file_tool.py       # 本地文件读取（CrewAI Tool 兼容）
│   └── status_tracker.py        # SSE 进度追踪器
│
├── tests/
│   ├── test_rag.py              # RAG 测试（31 个）
│   ├── test_answer_cache.py     # 缓存测试（12 个）
│   ├── test_conversation_manager.py
│   ├── test_session_manager.py
│   ├── test_status_tracker.py
│   ├── test_local_file_tool.py
│   └── test_web_api.py          # Flask API 测试（11 个）
│
├── templates/index.html         # Web UI 模板（Markdown 渲染 + SSE）
├── static/
│   ├── style.css                # 样式表
│   └── script.js                # 前端逻辑
│
├── knowledge/                   # 讲座文件目录（PDF/PPTX/DOCX）
├── images/                      # 提取的图片文件（自动生成）
├── chroma_db/                   # ChromaDB 持久化数据（自动生成）
├── conversations/sessions/      # 对话会话文件（自动生成）
├── cache/                       # 答案/检索/搜索缓存（自动生成）
└── output/                      # 时间戳命名的答案导出（自动生成）
```

---

## 配置

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 |
| `TAVILY_API_KEY` | 否 | Tavily 联网搜索密钥（不需要联网可不填） |
| `FLASK_SECRET_KEY` | 是* | Flask 会话签名密钥。生成：`python -c "import secrets; print(secrets.token_hex(32))"` |
| `WEB_UI_PORT` | 否 | Web UI 端口（默认: `7860`） |
| `FLASK_DEBUG` | 否 | 调试模式（默认: `0`） |

\* Web UI 必需。无此密钥 Flask 拒绝启动。

---

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/status` | 系统状态 |
| `GET` | `/api/sessions` | 会话列表 |
| `POST` | `/api/sessions` | 创建新会话 |
| `POST` | `/api/sessions/<path>` | 切换会话 |
| `DELETE` | `/api/sessions/<path>` | 删除会话 |
| `GET` | `/api/chat/task` | 获取 SSE task ID |
| `POST` | `/api/chat` | 发送消息 |
| `GET` | `/api/chat/stream` | SSE 进度流 |
| `GET` | `/api/history` | 对话历史 |
| `DELETE` | `/api/history` | 清除历史 |
| `GET` | `/api/knowledge` | 文件列表 |
| `POST` | `/api/knowledge/upload` | 上传文件 |
| `DELETE` | `/api/knowledge/<filename>` | 删除文件 |
| `POST` | `/api/knowledge/reindex` | 重建索引 |
| `GET` | `/api/cache` | 缓存统计 |
| `DELETE` | `/api/cache` | 清除缓存 |
| `GET` | `/images/<filename>` | 提取的图片文件 |

---

## 关键设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **多 Agent vs 单 Agent** | Sequential pipeline（路由→验证→分析） | Hierarchical 多 3 次 Manager 调用（~24s），Sequential 仅 2-3 次（~8s） |
| **图片检索** | BLIP 描述文本 → 向量化 | 避免多模态嵌入模型，384 维即可检索图片 |
| **语义分块** | 段落/标题边界，100-1200 字符 | 尊重文档结构，而非固定长度切割 |
| **重排序** | 嵌入相似度 + BM25 融合（70/30） | 移除 CrossEncoder（+1-2s/次），BM25 足够 |
| **阈值门控** | 三档阈值（≥0.82 / 0.55-0.82 / ≤0.55） | 减少不必要的 Guard LLM 调用，仅边界案例需要 |
| **路由策略** | 规则匹配（关键词）→ LLM 兜底 | 天气/新闻等明确问题零 LLM 路由成本 |
| **缓存归一化** | MD5(去标点+排序+去重 tokens) | "什么是 BERT" ≡ "BERT 是什么" ← 同一个缓存命中 |

---

## 测试覆盖

| 模块 | 数量 | 覆盖内容 |
|------|------|---------|
| `test_rag.py` | 31 | 语义分块、表格转换、文档分发、图片描述、向量存储 CRUD、混合检索 |
| `test_answer_cache.py` | 12 | 缓存命中/过期/覆盖/标点容忍/停用词过滤/jieba 语义匹配 |
| `test_conversation_manager.py` | 11 | 消息 CRUD、持久化、上下文格式化 |
| `test_session_manager.py` | 10 | 会话创建/列表/标签/删除 |
| `test_status_tracker.py` | 6 | SSE 进度追踪、并发安全 |
| `test_local_file_tool.py` | 3 | PDF/PPTX 读取、文件不存在处理 |
| `test_web_api.py` | 11 | Flask API 状态/历史/会话/缓存/知识管理端点 |
| **总计** | **83** | 全部通过 |

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 向量库错误 | `rm -rf chroma_db/` 后重启重建索引 |
| API Key 错误 | 检查 `.env` 中的密钥是否正确 |
| Web UI 端口占用 | 修改 `WEB_UI_PORT` 环境变量 |
| BLIP 模型问题 | 图片描述回退为 `[图片：WxH 像素]` 占位符 |
| 对话文件损坏 | 删除 `conversations/` 目录 |

---

## 开发历程

| 阶段 | 内容 |
|------|------|
| **基础架构** | CrewAI + ChromaDB + DeepSeek + Flask Web UI + CLI |
| **RAG 增强** | 语义分块、图片 BLIP 描述、表格 MD 转换、DOCX 支持 |
| **性能优化** | Sequential 取代 Hierarchical（5→2 次 LLM），CrossEncoder 移除（省 1-2s/次），RAG 上下文减半（4000→2000 字），多级缓存 |
| **体验优化** | 中文界面、SSE 4 步进度条、实时计时器、轮播提示、Markdown 导出 |
| **智能路由** | Rule-based + LLM 双路由、Grounding Check 语义验证、三档阈值门控 |
| **稳定性** | 图片 URL 安全编码、路径穿越防护、文件名特殊字符清理、缓存自动清理 |

---

*最后更新：2026年5月*

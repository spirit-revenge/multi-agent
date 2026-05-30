# LectureCrewLLM 项目总结

> 多智能体讲座分析系统 — RAG 检索 + 联网搜索 + 图文表多模态支持

---

## 一、项目概述

LectureCrewLLM 是一个基于 **CrewAI** 的多智能体系统，用于对讲座文件（PDF/PPTX/DOCX）进行智能分析。用户提问后，系统通过 **RAG 检索** + **联网搜索** + **多智能体协作** 的方式生成答案。

### 核心技术栈

| 组件 | 技术 |
|------|------|
| LLM | DeepSeek Chat API |
| 多智能体框架 | CrewAI (sequential process) |
| 向量数据库 | ChromaDB (本地持久化) |
| 向量模型 | paraphrase-multilingual-MiniLM-L12-v2 (384维) |
| 图片描述 | BLIP (blip-image-captioning-base) |
| Web UI | Flask + SSE 实时进度 |
| 文档解析 | PyMuPDF / python-pptx / python-docx |

---

## 二、系统架构

```
用户提问
    │
    ▼
┌─ Cache Check ───────────────────────┐
│  命中 → 直接返回缓存答案            │
│  未命中 → 继续                      │
└─────────────────────────────────────┘
    │
    ▼
┌─ Router Agent (意图路由) ───────────┐
│  分类: lecture / web / hybrid        │
│  → 决定走哪条 pipeline               │
└─────────────────────────────────────┘
    │
    ├── "lecture" ──→ RAG → Grounding Check → Analyst
    │
    ├── "web" ─────→ Web Search → Analyst
    │
    └── "hybrid" ──→ RAG + Web Search → Grounding → Analyst
                           │
                           ▼
                      SSE 实时进度推送
                           │
                           ▼
                    前端显示答案
```

### Agent 角色

| Agent | 职责 |
|-------|------|
| **意图路由器 (Router)** | 判断问题类别：讲座/网络/混合/未知（1次短LLM调用） |
| **网络研究员 (Searcher)** | 调用 Google Programmable Search 搜索网络 |
| **讲座分析师 (Analyst)** | 综合 RAG 结果 + 网络搜索结果，生成 Markdown 回答 |
| **相关性验证员 (Grounding)** | 判断 RAG 检索结果是否能回答用户问题 |

---

## 三、RAG 管道

### 3.1 文档处理

```
knowledge/*.pdf / *.pptx / *.docx
    │
    ├── DocumentProcessor
    │   ├── extract_text()    → 语义分块（段落/标题/句子边界）
    │   ├── extract_images()  → PIL Image 列表（过滤 <50px 图标）
    │   └── extract_tables()  → Markdown 表格字符串
    │
    ├── ImageCaptioner (BLIP)
    │   └── describe(img)     → "[图片描述] a diagram of ..."
    │
    └── ChromaDB
        ├── document: 文本内容 / 图片描述 / 表格 Markdown
        ├── metadata:
        │   ├── type:       "text" | "image" | "table"
        │   ├── source:     来源文件名
        │   ├── indexed_at: 索引时间戳
        │   └── image_path: 图片文件路径（仅 image 类型）
        └── vector: 384维嵌入向量
```

### 3.2 分块策略

- **语义分块**：按段落/标题边界拆分
- 最小块 100 字符，最大块 1200 字符
- 超长块在句号/感叹号处切割
- 小段落自动合并

### 3.3 增量索引

- SHA256 文件哈希 → 仅索引变更的文件
- 文件变更时自动删除旧 chunks 并写入新 chunks
- 支持强制重建索引

### 3.4 检索结果验证 (Grounding Check)

- 使用 LLM 判断检索结果是否与问题相关
- 输出 `RELEVANT` / `IRRELEVANT`
- 不相关的结果不会传递给 Analyst

---

## 四、项目结构

```
lecture_crewLLM/
├── main.py                      # CLI 入口 + Agent 编排
├── web_ui.py                    # Flask Web UI + REST API + SSE
├── pyproject.toml               # 项目元数据与依赖
├── requirements.txt             # 锁定依赖版本
├── .env.example                 # 环境变量模板
│
├── tools/
│   ├── document_processor.py    # 文档解析（PDF/PPTX/DOCX）
│   ├── image_captioner.py       # BLIP 图片描述生成
│   ├── rag_store.py             # ChromaDB 向量存储 + 检索
│   ├── conversation_manager.py  # 对话历史持久化
│   ├── session_manager.py       # 多会话管理
│   ├── answer_cache.py          # 问答缓存（TTL 30天）
│   ├── google_search_tool.py    # Google 搜索集成
│   ├── local_file_tool.py       # 本地文件读取（CrewAI Tool）
│   └── status_tracker.py        # SSE 进度追踪
│
├── templates/index.html         # Web UI 模板
├── static/
│   ├── style.css                # 样式表
│   └── script.js                # 前端逻辑（Markdown 渲染、SSE）
│
├── knowledge/                   # 讲座文件目录
├── images/                      # 提取的图片文件
├── chroma_db/                   # ChromaDB 持久化数据
├── conversations/sessions/      # 对话会话 JSON
├── cache/                       # 答案缓存
└── tests/
    ├── test_rag.py              # RAG 测试（31个）
    ├── test_answer_cache.py     # 缓存测试（12个）
    ├── test_conversation_manager.py
    ├── test_session_manager.py
    ├── test_status_tracker.py
    └── test_web_api.py
```

---

## 五、Web UI 功能

### 5.1 页面布局

```
┌──────────────┬──────────────────────────────────┐
│  侧边栏       │  主聊天区                        │
│              │                                  │
│  📚 对话      │  [消息气泡]                      │
│  ├ 当前会话   │  [消息气泡]                      │
│  └ 切换/创建  │  [消息气泡]                      │
│              │                                  │
│  📁 讲座文件   │                                  │
│  ├ 文件列表   │                                  │
│  ├ 上传       │                                  │
│  └ 重建索引   │                                  │
│              │  ┌────────────────────────┐       │
│  ⚡ 缓存      │  │ 输入框         [发送][联网] │   │
│  🎛️ 控制      │  └────────────────────────┘       │
│  └ 导出对话   └──────────────────────────────────┘
└──────────────
```

### 5.2 功能清单

| 功能 | 说明 |
|------|------|
| 聊天问答 | 支持多轮对话 |
| 🎯 意图路由 | 自动判断问题是否需要联网搜索 |
| 🌐 联网搜索开关 | 可开启/关闭（按钮在发送框旁） |
| 🔄 SSE 实时进度 | 4步进度条 + 计时器 + 轮播提示 |
| 📁 文件管理 | 上传/删除/重建索引 |
| 📊 图文表支持 | 回答中可引用图片和表格 |
| 📝 导出对话 | 一键导出全部历史为 Markdown |
| 💬 多会话 | 创建/切换/删除对话会话 |
| ⚡ 智能缓存 | 相同问题快速返回（含标点/停用词容忍） |

### 5.3 REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 系统状态 |
| GET/POST | `/api/sessions` | 会话列表/创建 |
| POST/DELETE | `/api/sessions/<path>` | 切换/删除会话 |
| POST | `/api/chat` | 发送消息 |
| GET | `/api/chat/stream` | SSE 进度流 |
| GET | `/api/chat/task` | 获取 SSE task ID |
| GET/DELETE | `/api/history` | 对话历史 |
| GET | `/api/knowledge` | 文件列表 |
| POST | `/api/knowledge/upload` | 上传文件 |
| DELETE | `/api/knowledge/<filename>` | 删除文件 |
| POST | `/api/knowledge/reindex` | 重建索引 |
| GET/DELETE | `/api/cache` | 缓存统计/清除 |
| GET | `/images/<filename>` | 图片文件 |

---

## 六、关键设计决策

### 6.1 为什么用 sequential 替代 hierarchical

原架构使用 CrewAI `Process.hierarchical` + manager agent，每次查询产生 **5 次 LLM 调用**（~24s）。改为 `Process.sequential` 后降为 **2 次 LLM 调用**（~12s），去掉 manager 的委派和审核步骤。

### 6.2 图片检索策略

图片本身不直接做 embedding。改为：
1. 从文档中提取图片
2. BLIP 模型生成文字描述
3. 描述文本被向量化存储
4. 搜索时通过描述文本命中图片
5. 回答中可引用图片（`![描述](/images/文件名)`）

### 6.3 缓存匹配

使用 MD5 哈希，但增加了预处理：
- 去标点符号
- 去常见停用词（a/an/the/what/is 等）
- 排序去重 token
- 使得 "What is BERT?" ≡ "BERT" ≡ "Explain BERT"

### 6.4 安全防护

- 图片文件名 `_safe_filename()` 替换 `&` `*` 等 URL/Markdown 特殊字符
- 前端 Markdown 渲染器保护 HTML 标签属性不被斜体/加粗正则破坏
- 路径穿越防护（文件上传/删除）

---

## 七、测试覆盖

| 测试模块 | 数量 | 覆盖内容 |
|---------|------|---------|
| `test_rag.py` | 31 | 语义分块、表格转换、文档分发、图片描述、向量存储CRUD |
| `test_answer_cache.py` | 12 | 缓存命中/过期/覆盖/标点容忍/停用词过滤 |
| `test_conversation_manager.py` | 13 | 消息CRUD、持久化、上下文格式化 |
| `test_session_manager.py` | 10 | 会话创建/列表/标签/删除 |
| `test_status_tracker.py` | 6 | SSE进度追踪、并发 |
| 总计 | **72** | |

---

## 八、环境要求

### 依赖

```bash
pip install -r requirements.txt
# 或
pip install -e .
```

### 环境变量 (`.env`)

```
DEEPSEEK_API_KEY=sk-your-key
GOOGLE_API_KEY=your-google-api-key
GOOGLE_CSE_ID=your-cse-id
FLASK_SECRET_KEY=your-secret-key
WEB_UI_PORT=7860
FLASK_DEBUG=0
```

### 启动

```bash
# Web UI
python web_ui.py
# 访问 http://localhost:7860

# CLI 模式
python main.py
```

---

## 九、开发历程

| 阶段 | 内容 |
|------|------|
| 基础架构 | CrewAI + ChromaDB + DeepSeek + Flask Web UI |
| RAG 增强 | 语义分块、图片/BLIP描述、表格MD、DOCX支持 |
| 性能优化 | sequential取代hierarchical（5→2次LLM）、缓存策略改进 |
| 体验优化 | 中文化、实时计时器、轮播提示、SSE 4步进度、导出对话 |
| 智能路由 | Router Agent + Grounding Check、联网搜索开关 |
| 稳定性 | 图片URL编码、Markdown渲染器安全加固、文件名去特殊字符 |

---

*最后更新：2026年5月*

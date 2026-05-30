# LectureCrewLLM

> [English](README.md) | [中文](README_CN.md)

多智能体讲座分析系统 — **多模态 RAG**（文本+图片+表格）+ 联网搜索 + 交互式 Web UI

基于 [CrewAI](https://github.com/crewAIInc/crewAI)、ChromaDB 和 Flask 构建。使用 DeepSeek 作为 LLM，sentence-transformers 实现双语嵌入，BLIP 实现图片描述生成。

---

## 功能特性

- **多智能体架构** — 意图路由 → RAG 检索 → 相关性验证 → 分析师，4 个 Agent 协作
- **多模态 RAG** — 从 PDF/PPTX/DOCX 中提取文本（语义分块）、图片（BLIP 描述）、表格（Markdown）
- **联网搜索** — Google Programmable Search 获取补充信息，支持开关
- **实时进度** — SSE 4 步进度条 + 计时器 + 轮播提示
- **文件管理** — 通过 Web UI 上传、删除、重建索引
- **多会话** — 持久化对话历史，支持切换、新建、删除
- **智能缓存** — 30 天 TTL，支持标点容忍和停用词过滤
- **优雅降级** — 联网搜索失败时自动回退到仅讲座内容

## 系统架构

```
用户提问
    │
    ▼
┌─ 缓存检查 ──────────────────────────┐
│  命中 → 直接返回缓存答案            │
│  未命中 → 继续                      │
└─────────────────────────────────────┘
    │
    ▼
┌─ Router Agent (意图路由) ───────────┐
│  分类: lecture / web / hybrid       │
│  → 决定走哪条 pipeline              │
└─────────────────────────────────────┘
    │
    ├── "lecture" ──→ RAG → Grounding Check → Analyst
    │
    ├── "web" ──────→ 网络搜索 → Analyst
    │
    └── "hybrid" ───→ RAG + 搜索 → Grounding → Analyst
```

### Agent 角色

| Agent | 职责 | LLM 调用 |
|-------|------|---------|
| 🎯 **意图路由器 (Router)** | 判断问题类别：讲座/网络/混合 | 1 次短调用（~50 tokens） |
| 🔍 **网络研究员 (Searcher)** | Google 搜索补充信息 | 1 次调用 |
| ✅ **相关性验证员 (Grounding)** | 判断 RAG 结果是否与问题相关 | 1 次短调用 |
| 📝 **讲座分析师 (Analyst)** | 综合信息生成 Markdown 答案 | 1 次调用 |

### 多模态 RAG 管道

```
knowledge/*.pdf / *.pptx / *.docx
    │
    ├── DocumentProcessor
    │   ├── extract_text()    → 语义分块（段落/标题/句子边界）
    │   ├── extract_images()  → PIL Image → BLIP 描述 → 存文件
    │   └── extract_tables()  → 转为 Markdown 表格
    │
    └── ChromaDB
        ├── document: 文本/图片描述/表格 Markdown
        ├── metadata:
        │   ├── type:       "text" | "image" | "table"
        │   ├── source:     来源文件名
        │   ├── indexed_at: 索引时间戳
        │   └── image_path: 图片路径
        └── vector: 384 维嵌入
```

## 快速开始

### 环境要求

- Python 3.11+
- DeepSeek API Key — [platform.deepseek.com](https://platform.deepseek.com/api_keys)
- Google Programmable Search — [programmablesearchengine.google.com](https://programmablesearchengine.google.com)

### 安装

```bash
# 1. 克隆项目
cd lecture_crewLLM

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入:
#   DEEPSEEK_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID, FLASK_SECRET_KEY

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装测试依赖（可选）
pip install -e ".[test]"

# 5. 将讲座文件放入 knowledge/ 目录
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
# 70 个测试，覆盖 7 个模块
```

## Web UI 布局

```
┌──────────────┬──────────────────────────────────┐
│  侧边栏       │  主聊天区                        │
│              │  ┌──────────────────────────┐    │
│  📚 对话      │  │ 历史消息自动显示在主界面  │    │
│  ├ 当前会话   │  │ 支持图片和表格渲染        │    │
│  └ 切换/创建  │  └──────────────────────────┘    │
│              │                                  │
│  📁 讲座文件   │  ┌────────────────────────┐     │
│  ├ 文件列表   │  │ 输入框     [发送] [🌐联网] │   │
│  ├ 上传/删除  │  └────────────────────────┘     │
│  └ 重建索引   │                                  │
│              │  加载时显示: 4步进度 + 计时器      │
│  ⚡ 缓存      │                                  │
│  🎛️ 控制      │                                  │
│  └ 导出对话   │                                  │
└──────────────┴──────────────────────────────────┘
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 系统状态 |
| GET/POST | `/api/sessions` | 会话列表/创建 |
| POST/DELETE | `/api/sessions/<path>` | 切换/删除会话 |
| POST | `/api/chat` | 发送消息 |
| GET | `/api/chat/stream` | SSE 进度流 |
| GET/DELETE | `/api/history` | 对话历史 |
| GET | `/api/knowledge` | 文件列表 |
| POST/DELETE | `/api/knowledge/*` | 上传/删除/重建索引 |
| GET/DELETE | `/api/cache` | 缓存统计/清除 |
| GET | `/images/<filename>` | 图片文件 |

## 配置

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 |
| `GOOGLE_API_KEY` | 是 | Google Cloud API 密钥 |
| `GOOGLE_CSE_ID` | 是 | Google Custom Search Engine ID |
| `FLASK_SECRET_KEY` | 是* | Flask 会话密钥 |
| `WEB_UI_PORT` | 否 | Web UI 端口（默认: 7860） |
| `FLASK_DEBUG` | 否 | 调试模式（默认: 0） |

\* Web UI 必需

## 项目结构

```
lecture_crewLLM/
├── main.py                      # CLI 入口 + Agent 编排
├── web_ui.py                    # Flask Web UI + API + SSE
├── pyproject.toml               # 项目元数据
├── requirements.txt             # 依赖锁定
├── .env.example                 # 环境变量模板
│
├── tools/
│   ├── document_processor.py    # 文档解析（PDF/PPTX/DOCX）
│   ├── image_captioner.py       # BLIP 图片描述
│   ├── rag_store.py             # ChromaDB 向量存储
│   ├── conversation_manager.py  # 对话历史
│   ├── session_manager.py       # 多会话管理
│   ├── answer_cache.py          # 答案缓存
│   ├── google_search_tool.py    # Google 搜索
│   ├── local_file_tool.py       # 文件读取（CrewAI Tool）
│   └── status_tracker.py        # SSE 进度追踪
│
├── tests/                       # 70+ 测试
├── templates/index.html         # Web UI 模板
├── static/
│   ├── style.css
│   └── script.js
│
├── knowledge/                   # 讲座文件
├── images/                      # 提取的图片
├── chroma_db/                   # 向量数据库
├── conversations/               # 对话数据
└── cache/                       # 答案缓存
```

## 常见问题

| 问题 | 解决 |
|------|------|
| 向量库错误 | `rm -rf chroma_db/` 后重启重建索引 |
| API Key 错误 | 检查 `.env` 中的四个密钥 |
| 端口占用 | 修改 `WEB_UI_PORT` |
| 对话文件损坏 | 删除 `conversations/` 目录 |
| 模块导入错误 | 运行 `pip install -r requirements.txt` |

## 关键设计决策

| 决策 | 理由 |
|------|------|
| **Sequential 替代 Hierarchical** | Hierarchical 多 Manager 3 次调用（~24s），Sequential 仅 2 次（~12s） |
| **图片存为文字描述** | 用 BLIP 生成描述文本，避免多模态嵌入模型 |
| **语义分块** | 按段落/标题边界而非固定 500 字符 |
| **Grounding Check** | LLM 验证 RAG 结果相关性，防止无关上下文污染回答 |
| **Router Agent** | 预处理意图，天气类问题完全跳过 RAG |
| **缓存归一化** | 去标点+停用词+排序 token，"What is BERT?" ≡ "BERT" |

---

*最后更新：2026年5月*

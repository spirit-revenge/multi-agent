# LectureCrewLLM 项目报告

**项目类型**：本地化多模态讲座问答与分析系统

**报告用途**：课程展示、项目答辩、阶段性总结

---

## 1. 项目概述

LectureCrewLLM 是一个面向讲座和课程资料的本地化多模态多代理问答系统。它的核心目标是利用大模型与向量检索技术，把分散在 PDF、PPT、DOCX 中的教学内容——包括文本、图片和表格——转化为一个可以持续对话、追问和复用历史答案的知识服务平台。

功能上具备四类核心能力：

1. **多模态文档理解**：自动读取 PDF/PPTX/DOCX，提取文本（语义分块）、图片（BLIP 标注）、表格（Markdown 转换）。
2. **语义检索**：通过向量化机制支持中英文跨语言检索，可筛选文本/图片/表格类型。
3. **多代理协作**：CrewAI 层次化流程，3 Agent 分工（搜索 → 分析 → 编排）。
4. **多轮对话**：SSE 实时进度、会话历史、回答缓存、知识库 Web 管理。

工程上采用 Python、Flask、ChromaDB、CrewAI，使用 DeepSeek 作为 LLM、sentence-transformers 作为嵌入模型、BLIP 作为图像标注模型。系统强调本地运行、数据可控、容错降级和模块化扩展。

---

## 2. 项目背景

### 2.1 需求来源

教学场景中的核心矛盾是"资料多、找不到重点"，且讲座资料不仅仅是文字——包含大量图表、示意图、表格等视觉信息：

- 用户希望系统理解概念性问题，而非简单关键词匹配。
- 用户希望系统能"看懂"讲义中的图片和表格，而非只读文字。
- 用户希望系统记住上下文，而非每次重新解释。
- 用户希望本地处理敏感资料，而非上传到外部平台。
- 用户希望重复问题即时返回，而非每次等待推理。

### 2.2 为什么选择本地化方案

- **隐私保护**：讲义、试卷等不需要外发到第三方平台。
- **可控性**：用户自己管理索引、缓存和输出，支持手动清理和重建。
- **可复现性**：知识来源都在本地，便于调试复查。
- **可扩展性**：嵌入模型、LLM、检索策略均可替换。

### 2.3 项目定位

- **研究原型**：验证"多模态 RAG + 多代理 + 会话缓存 + 容错"组合的可行性。
- **实用工具**：可启动、可检索、可交互的 Web UI，支持文件上传和管理。
- **课程展示**：体现大模型时代的知识组织、多模态处理与系统集成方法。

---

## 3. 问题定义

### 3.1 核心问题

> 如何在本地环境中，对讲座材料（文本 + 图片 + 表格）进行多模态语义索引和多轮问答，并保证系统具有较好的响应性、容错性和可维护性？

### 3.2 子问题与解决方案

| 子问题 | 解决方案 |
|--------|---------|
| 多格式文档解析 | `document_processor.py`：PDF (PyMuPDF+pdfplumber)、PPTX (python-pptx)、DOCX (python-docx) |
| 图片内容理解 | `image_captioner.py`：BLIP 模型生成图片文字描述，描述存入向量库 |
| 表格提取 | 三种格式均提取表格 → Markdown 格式存入向量库 |
| 语义分块 | 按标题 + 段落 + 句边界智能分割（100-1200 字符） |
| 语义检索 | sentence-transformers 嵌入 + ChromaDB 向量库 + 增量索引（SHA256） |
| 多轮对话 | `conversation_manager.py` 持久化历史 + 上下文注入 |
| 重复计算 | `answer_cache.py` 基于 MD5 匹配 + 30 天 TTL |
| 多代理协调 | CrewAI 层次化流程，3 Agent 分工协作 |
| 进度可见 | SSE 实时推送 Agent 执行状态到 Web 前端 |
| 容错降级 | RAG 失败 / 搜索失败 / API 故障的三级降级 |
| 文件管理 | Web UI 上传 / 列出 / 删除 / 重建索引 |

### 3.3 评价标准

- **准确性**：回答贴合资料内容，引用来源，覆盖文本、图片和表格信息。
- **连续性**：后续问题继承前文语境。
- **完整性**：检索不遗漏图片和表格中的信息。
- **稳定性**：部分服务故障时仍能生成回答。
- **效率**：重复问题命中缓存 < 1ms 返回。

---

## 4. 方法设计

### 4.1 总体架构（五层）

1. **输入层**：Web UI（Flask + SSE）或 CLI，支持文档上传。
2. **缓存层**：MD5 匹配，命中则即时返回。
3. **检索层**：多模态 RAG（ChromaDB），区分 text / image / table 三种内容类型。
4. **生成层**：CrewAI 3 Agent 层次化流程编排与回答生成。
5. **输出层**：返回前端 + 保存到会话 JSON、缓存 JSON、Markdown 文件。

### 4.2 模块划分

| 模块 | 文件 | 职责 |
|------|------|------|
| Web 服务 | `web_ui.py` | Flask REST API (15 端点) + SSE + 知识库管理 |
| 主编排 | `main.py` | CLI 入口 + `run_crew` 多代理流程 |
| 基础文件读取 | `tools/local_file_tool.py` | 简易 PDF/PPTX 文本提取 |
| **文档处理** | `tools/document_processor.py` | PDF/PPTX/DOCX 统一处理：语义分块 + 图片提取 + 表格提取 |
| **图像标注** | `tools/image_captioner.py` | BLIP 模型图片描述（失败时回退为像素占位符） |
| 向量检索 | `tools/rag_store.py` | 多模态 ChromaDB 存储 + 增量索引 + 按类型检索 |
| 对话管理 | `tools/conversation_manager.py` | 历史持久化 + 上下文构建 |
| 会话管理 | `tools/session_manager.py` | 多会话创建/删除/切换 |
| 回答缓存 | `tools/answer_cache.py` | MD5 匹配 + TTL 过期 |
| 网络搜索 | `tools/google_search_tool.py` | Google 可编程搜索引擎 |
| 进度追踪 | `tools/status_tracker.py` | 内存队列 SSE 进度推送 |

> 新增模块以加粗标记（对比最初版本）。

### 4.3 多模态文档处理流程

```
文件 → 格式判断 (PDF/PPTX/DOCX)
  │
  ├── 文本提取 → 语义分块 (标题/段落/句边界)
  ├── 图片提取 → BLIP 标注 → 描述文本 + 图片保存到 images/
  └── 表格提取 → Markdown 表格字符串

  ↓
ChromaDB 存储 (type: text / image / table)
```

**分块策略：**
- 先在标题（`##`、`###`）处分界
- 再在段落（双换行）处分界
- 超长段落（> 1200 字符）在句子边界（。！？.!?）处强制切分
- 相邻过短段落（< 100 字符）合并

**图像标注：**
- 模型：`Salesforce/blip-image-captioning-base`（Hugging Face transformers）
- 成功输出：`"[图片描述] a diagram of transformer architecture"`
- 失败回退：`"[图片：1920x1080 像素]"`

### 4.4 多代理架构

```
Manager Agent (Educational Manager)
│
├── 分配 → Internet Researcher
│   └── 工具: Google Programmable Search
│   └── 输出: 带 URL 的网络搜索结果
│
└── 分配 → Lecture Analyst
    └── 输入: RAG 多模态片段 + 网络搜索结果 + 对话历史
    └── 输出: 英文 Markdown 结构化回答（含引用来源）
```

- RAG 检索在 Crew 启动前完成，结果直接注入 Analyst 的 task context。
- 检索结果包含 📝 文本、🖼️ 图片描述、📊 表格三种类型标记。
- Internet Researcher 失败时返回错误字符串，Analyst 自动忽略并用讲义内容回答。

### 4.5 Web UI 与 API 设计

共 **15 个 API 端点**，分五组：

| 组 | 端点 | 方法 |
|----|------|------|
| 状态 | `/api/status` | GET |
| 会话 | `/api/sessions`, `/api/sessions/<path>` | GET, POST, DELETE |
| 聊天 | `/api/chat`, `/api/chat/task`, `/api/chat/stream` | POST, GET, GET(SSE) |
| 历史 | `/api/history` | GET, DELETE |
| 缓存 | `/api/cache` | GET, DELETE |
| 知识库 | `/api/knowledge`, `/api/knowledge/upload`, `/api/knowledge/<filename>`, `/api/knowledge/reindex` | GET, POST, DELETE, POST |

**SSE 实时进度：** 前端先通过 `/api/chat/task` 获取 task_id → 订阅 `/api/chat/stream` → 发送问题到 `/api/chat` → 收到三步进度推送（starting → generating → complete）。

### 4.6 关键设计决策

- **RAG 不放入 Agent**：RAG 是确定性数据库查询，放在 Crew 前执行更高效。
- **图片不入向量**：图片经 BLIP 转为文字描述后存入向量库，原文保存到 `images/`，兼顾检索效率和可读性。
- **嵌入模型选择**：`paraphrase-multilingual-MiniLM-L12-v2`，支持中文讲义 → 英文问题的跨语言检索。
- **增量索引**：基于 SHA256 文件哈希，只处理变更文件。
- **本地优先**：所有数据（知识库、会话、缓存、提取图片、输出）均在本地目录。

---

## 5. 实验与验证

### 5.1 实验环境

- **OS:** macOS / Linux / Windows
- **Python:** 3.13
- **LLM:** DeepSeek (deepseek-chat)
- **嵌入模型:** paraphrase-multilingual-MiniLM-L12-v2 (384 维)
- **图像标注:** Salesforce/blip-image-captioning-base

### 5.2 端到端验证流程

1. `GET /api/status` → 确认服务正常，会话和缓存可读。
2. `GET /api/sessions` → 验证会话列表，`POST /api/sessions` → 创建新会话。
3. `POST /api/knowledge/upload` → 上传 PDF/PPTX/DOCX 文件，验证自动索引。
4. `GET /api/knowledge` → 查看文件列表及索引状态。
5. `POST /api/chat` → 发送问题，验证多代理推理 + SSE 进度推送（约 90s）。
6. `GET /api/history` + `GET /api/cache` → 验证历史和缓存记录。
7. `DELETE /api/knowledge/<filename>` → 删除文件并验证索引同步清理。

### 5.3 测试覆盖

共 **70 个自动化测试**，覆盖 7 个模块：

| 模块 | 测试数 | 覆盖范围 |
|------|--------|---------|
| `test_answer_cache.py` | 12 | 缓存 CRUD、持久化、大小写/标点/停用词/词序容错 |
| `test_conversation_manager.py` | 11 | 消息、历史、上下文构建、持久化 |
| `test_session_manager.py` | 10 | 会话 CRUD、legacy 处理、标签 |
| `test_status_tracker.py` | 6 | 任务生命周期、并发安全 |
| `test_local_file_tool.py` | 3 | 空目录、路径校验、文件过滤 |
| `test_rag.py` | 20 | 语义分块（6 项）、表格→Markdown（5 项）、文档分发（4 项）、图像标注（3 项）、向量库 CRUD（6 项） |
| `test_web_api.py` | 11 | API 端点、参数校验、页面路由 |

运行方式：`python -m pytest tests/ -v`

### 5.4 开发中的问题与修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | **假 Agent**：File Reader Agent 形同虚设 | 重构为真正 3 Agent 架构 |
| 2 | **纯文本局限**：初版只处理文字，图片和表格信息丢失 | 新增 document_processor.py + image_captioner.py，实现多模态 RAG |
| 3 | **API 密钥泄露**：`.env` 提交到 git | 轮换密钥 + `.env.example` + `.gitignore` 修复 |
| 4 | **无进度反馈**：Web UI 只有无限旋转圈 | 新增 SSE 三步进度推送 |
| 5 | **错误处理缺失**：API 失败直接崩溃 | 三级容错降级 + Python logging |
| 6 | **无文件管理**：用户必须手动把文件放进 knowledge/ | 新增知识库 API：上传/列表/删除/重建索引 |
| 7 | **简单分块**：500 字符固定切分，截断句子 | 语义分块算法：标题→段落→句边界 |
| 8 | **文档冗余**：10 个 md 文件 3363 行 | 精简为 README + ARCHITECTURE + PROJECT_REPORT |

---

## 6. 结果分析

### 6.1 已实现的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| Web UI | 可用 | Flask + 15 个 API 端点 |
| 3 Agent 协作 | 可用 | CrewAI 层次化流程 |
| 多模态 RAG | 可用 | 文本 + 图片描述 + 表格，语义分块 |
| 图像标注 | 可用 | BLIP 模型，失败时回退 |
| 文件上传/管理 | 可用 | Web UI 直接上传、删除、重建索引 |
| 网络搜索 | 可用 | Google CSE，结果带 URL 引用 |
| SSE 进度 | 可用 | 三步实时进度推送 |
| 多会话 | 可用 | 创建、切换、删除 |
| 回答缓存 | 可用 | MD5 + TTL，12 项测试覆盖 |
| 容错降级 | 可用 | 搜索/API 失败不影响回答 |
| 日志系统 | 可用 | INFO/WARNING/ERROR 分级 |
| 自动化测试 | 可用 | 70 个测试，7 个模块 |
| pyproject.toml | 可用 | 9 个直接依赖 + test 可选依赖 |

### 6.2 性能特征

- **缓存命中**：< 1ms（对比完整推理 ~90s）
- **文档索引**：取决于文件大小和图片数量（BLIP 标注每张图片约 1-2s）
- **模型推理**：主要瓶颈，受 API 延迟和上下文大小影响
- **适用场景**：小规模、低并发的教学环境

### 6.3 优点

- 多模态处理：不丢失讲义中的图片和表格信息
- 数据不出本地，隐私友好
- 模块化设计，各层可独立替换
- 容错降级保证基本可用性（BLIP 失败回退、搜索失败回退）
- SSE 实时进度反馈，用户体验好
- Web UI 文件管理，操作便捷
- 70 个自动化测试，工程规范完善

### 6.4 局限

- 缓存匹配依赖精确文本，不支持语义等价重述
- 首次推理响应时间长（~90s）
- 依赖外部 API（DeepSeek + Google），离线不可用
- BLIP 模型增加首次启动时间和内存占用
- 无用户认证和并发控制

---

## 7. 总结与展望

### 7.1 总结

LectureCrewLLM 的核心价值在于将"讲义文件"转化为"可持续对话的多模态知识系统"。相比初版纯文本系统，本版本新增了多模态文档处理（文本 + 图片 + 表格）、BLIP 图像标注、语义分块、Web 文件管理和 70 个自动化测试，构建了从"文件"到"回答"的完整闭环。

### 7.2 改进方向

**短期：**
- Agent 思考过程可视化面板（展示调用链和中间输出）
- 缓存语义匹配（近义问题识别，目前仅精确匹配）
- Web UI 流式回答（markdown 逐字渲染）
- 支持更多文档格式（Markdown、TXT、HTML）

**中长期：**
- 可插拔 LLM 后端（Claude、GPT-4、本地量化模型）
- 多用户协作和权限控制
- 多模态检索增强（图片直接向量化，而非仅依赖文字描述）
- 基于用户反馈的检索质量优化（RLHF）

### 7.3 可交付价值

用于课程汇报时，本项目能够展示：
- 对真实需求的分析和定义能力
- 多模态文档处理系统的设计能力
- 多模块系统的分层设计能力
- 工程问题的排查、修复和迭代能力（8 项问题修复记录）
- 大模型应用从原型到工程化的完整链路
- 70 个自动化测试的工程质量意识

---

## 8. 项目结构

```
lecture_crewLLM/
├── main.py                      # CLI 入口 + Crew 编排
├── web_ui.py                    # Flask Web UI + 15 API 端点 + SSE
├── pyproject.toml               # 项目元数据 & 9 个直接依赖
├── requirements.txt             # 锁定版本依赖
├── .env.example                 # 环境变量模板
│
├── tools/
│   ├── __init__.py
│   ├── local_file_tool.py       # 基础 PDF/PPTX 文本提取
│   ├── document_processor.py    # ★ 多格式文档处理器 (PDF/PPTX/DOCX)
│   │   └── 语义分块 + 图片提取 + 表格→Markdown
│   ├── image_captioner.py       # ★ BLIP 图像标注
│   ├── rag_store.py             # ★ 多模态 ChromaDB 向量存储
│   ├── conversation_manager.py  # 对话历史管理
│   ├── session_manager.py       # 多会话管理
│   ├── answer_cache.py          # 回答缓存 (TTL)
│   ├── google_search_tool.py    # Google 搜索集成
│   └── status_tracker.py        # SSE 进度追踪
│
├── tests/                       # ★ 70 个自动化测试 (7 模块)
│   ├── test_answer_cache.py     # 12 tests
│   ├── test_conversation_manager.py  # 11 tests
│   ├── test_session_manager.py  # 10 tests
│   ├── test_status_tracker.py   # 6 tests
│   ├── test_local_file_tool.py  # 3 tests
│   ├── test_rag.py              # 20 tests
│   └── test_web_api.py          # 11 tests
│
├── templates/index.html         # Web UI 模板
├── static/
│   ├── style.css                # 样式表
│   └── script.js                # 前端 JS + EventSource SSE
│
├── knowledge/                   # ← 讲义文件 (PDF/PPTX/DOCX)
├── images/                      # 提取的图片 (自动创建)
├── conversations/sessions/      # 会话 JSON (自动创建)
├── cache/                       # 缓存数据 (自动创建)
├── chroma_db/                   # 向量数据库 (自动创建)
└── output/                      # 输出 Markdown (自动创建)
```

> ★ = 本轮新增

---

## 9. 附录：快速复现

```bash
# 1. 环境准备
git clone <repo>
cd lecture_crewLLM

# 2. 配置密钥
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID, FLASK_SECRET_KEY

# 3. 安装依赖
pip install -r requirements.txt
pip install -e ".[test]"     # 可选：安装测试依赖

# 4. 放入讲义文件
mkdir -p knowledge
# 将 PDF/PPTX/DOCX 文件放入 knowledge/（或通过 Web UI 上传）

# 5. 启动
python web_ui.py
# 打开 http://localhost:7860
```

API 验证：
```bash
curl http://127.0.0.1:7860/api/status
curl http://127.0.0.1:7860/api/knowledge
curl -X POST http://127.0.0.1:7860/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize the lecture materials briefly."}'
```

运行测试：
```bash
python -m pytest tests/ -v    # 70 tests
```

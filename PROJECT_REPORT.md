# LectureCrewLLM 项目报告

**项目类型**：本地化讲座问答与分析系统

**报告用途**：课程展示、项目答辩、阶段性总结

---

## 1. 项目概述

LectureCrewLLM 是一个面向讲座和课程资料的本地化多代理问答系统。它的核心目标是把分散在 PDF、PPT 中的教学内容，转化为一个可以持续对话、追问和复用历史答案的知识服务平台。

功能上具备三类能力：

1. **文档理解**：自动读取 PDF/PPTX 并建立语义索引。
2. **语义检索**：通过向量化机制找到与问题最相关的内容（支持中英文跨语言检索）。
3. **多轮对话**：结合会话历史、回答缓存和实时进度反馈，持续回答后续问题。

工程上采用 Python、Flask、ChromaDB、CrewAI，使用 DeepSeek 作为 LLM、sentence-transformers 作为嵌入模型。系统强调本地运行、数据可控、容错降级和模块化扩展。

---

## 2. 项目背景

### 2.1 需求来源

教学场景中的核心矛盾是"资料多、找不到重点"：
- 用户希望系统理解概念性问题，而非简单关键词匹配。
- 用户希望系统记住上下文，而非每次重新解释。
- 用户希望本地处理敏感资料，而非上传到外部平台。
- 用户希望重复问题即时返回，而非每次等待推理。

### 2.2 为什么选择本地化方案

- **隐私保护**：讲义、试卷等不需要外发。
- **可控性**：用户自己管理索引、缓存和输出。
- **可复现性**：知识来源都在本地，便于调试复查。
- **可扩展性**：嵌入模型、LLM、检索策略均可替换。

### 2.3 项目定位

- **研究原型**：验证"多代理 + RAG + 会话缓存 + 容错"组合的可行性。
- **实用工具**：可启动、可检索、可交互的 Web UI。
- **课程展示**：体现大模型时代的知识组织与系统集成方法。

---

## 3. 问题定义

### 3.1 核心问题

> 如何在本地环境中，对讲座材料进行语义索引和多轮问答，并保证系统具有较好的响应性、容错性和可维护性？

### 3.2 子问题

| 子问题 | 解决方案 |
|--------|---------|
| 文档解析 | `local_file_tool.py` 统一抽取 PDF/PPTX 文本 |
| 语义检索 | sentence-transformers 嵌入 + ChromaDB 向量库 + 增量索引 |
| 多轮对话 | `conversation_manager.py` 持久化历史 + 上下文注入 |
| 重复计算 | `answer_cache.py` 基于 MD5 匹配 + 30 天 TTL |
| 多代理协调 | CrewAI 层次化流程，3 Agent 分工协作 |
| 进度可见 | SSE 实时推送 Agent 执行状态到 Web 前端 |
| 容错降级 | RAG 失败 / 搜索失败 / API 故障的三级降级策略 |

### 3.3 评价标准

- **准确性**：回答贴合资料内容，引用来源。
- **连续性**：后续问题继承前文语境。
- **稳定性**：部分服务故障时仍能生成回答。
- **效率**：重复问题命中缓存，< 1ms 返回。

---

## 4. 方法设计

### 4.1 总体架构（五层）

1. **输入层**：Web UI（Flask + SSE）或 CLI 接收用户问题。
2. **缓存层**：检查问题是否命中缓存，命中则即时返回。
3. **检索层**：RAG 语义检索（ChromaDB），返回相关讲义片段。
4. **生成层**：CrewAI 3 Agent 层次化流程编排与回答生成。
5. **输出层**：返回前端 + 保存到会话 JSON、缓存 JSON、Markdown 文件。

### 4.2 模块划分

| 模块 | 文件 | 职责 |
|------|------|------|
| Web 服务 | `web_ui.py` | Flask REST API + SSE 端点 |
| 主编排 | `main.py` | CLI 入口 + `run_crew` 多代理流程 |
| 文件读取 | `tools/local_file_tool.py` | PDF/PPTX 文本提取 |
| 向量检索 | `tools/rag_store.py` | ChromaDB 存储 + 增量索引 + 语义检索 |
| 对话管理 | `tools/conversation_manager.py` | 历史持久化 + 上下文构建 |
| 会话管理 | `tools/session_manager.py` | 多会话创建/删除/切换 |
| 回答缓存 | `tools/answer_cache.py` | MD5 匹配 + TTL 过期 |
| 网络搜索 | `tools/google_search_tool.py` | Google 可编程搜索引擎 |
| 进度追踪 | `tools/status_tracker.py` | 内存队列 SSE 进度推送 |

### 4.3 多代理架构

```
Manager Agent (Educational Manager)
│
├── 分配 → Internet Researcher
│   └── 工具: Google Programmable Search
│   └── 输出: 带 URL 的网络搜索结果
│
└── 分配 → Lecture Analyst
    └── 输入: RAG 讲义片段 + 网络搜索结果 + 对话历史
    └── 输出: 英文 Markdown 结构化回答（含引用来源）
```

- RAG 检索在 Crew 启动前完成，结果直接注入 Analyst 的 task context，避免浪费 Agent 回合。
- Internet Researcher 失败时返回错误字符串，Analyst 自动忽略并用讲义内容生成回答。

### 4.4 SSE 实时进度

```
Browser ──GET /api/chat/task──→ 获取 task_id
Browser ──EventSource /api/chat/stream?task_id=──→ 订阅进度
Browser ──POST /api/chat {message, task_id}──→ 启动推理
         ←── SSE: {"step":"starting"}    "Searching web..."
         ←── SSE: {"step":"generating"}  "Synthesizing answer..."
         ←── SSE: {"step":"complete"}    "Answer ready!"
```

### 4.5 关键设计决策

- **RAG 不放入 Agent**：RAG 是确定性数据库查询，非 LLM 推理步骤。放在 Crew 启动前执行，结果注入 prompt，更高效。
- **层次化流程**：Manager 动态决定任务执行顺序，搜索失败时 Analyst 自动降级。
- **嵌入模型选择**：`paraphrase-multilingual-MiniLM-L12-v2`，支持中文讲义 → 英文问题的跨语言检索。
- **本地优先**：所有数据（知识库、会话、缓存、输出）均在本地目录。

---

## 5. 实验与验证

### 5.1 环境与启动

```bash
cp .env.example .env          # 配置 4 个密钥
pip install -r requirements.txt  # 或 pip install -e .
python web_ui.py              # 启动，默认 http://localhost:7860
```

### 5.2 端到端验证流程

1. `GET /api/status` → 确认服务正常，会话和缓存可读。
2. `GET /api/sessions` → 验证会话列表。
3. `POST /api/sessions` → 创建新会话，确认文件写入。
4. `POST /api/chat` → 发送问题，验证多代理推理 + SSE 进度推送。
5. `GET /api/history` + `GET /api/cache` → 验证历史和缓存记录。

实际测试中 `/api/chat` 完整响应约 90 秒（取决于 DeepSeek API 和 Google Search 延迟）。

### 5.3 开发中遇到的问题与修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | **假 Agent**：File Reader Agent 形同虚设，不实际执行工具调用 | 重构为真正的 3 Agent 架构（Internet Researcher + Lecture Analyst + Manager） |
| 2 | **API 密钥泄露**：`.env` 中的真实密钥被提交到 git 历史 | 轮换所有密钥、创建 `.env.example`、修复 `.gitignore`、清理 git 跟踪 |
| 3 | **无进度反馈**：Web UI 只有无限旋转的加载圈，答辩展示体验差 | 新增 SSE 进度推送：`status_tracker.py` + `/api/chat/stream` 端点 + 前端 EventSource |
| 4 | **错误处理缺失**：API 失败直接崩溃，无降级策略 | 三级容错降级（RAG / 搜索 / API）+ Python logging 模块替换全部 print() |
| 5 | **文档冗余**：10 个 markdown 文件共 3363 行，内容严重重叠 | 精简为 README.md + ARCHITECTURE.md，删除 6 个冗余文件（-2695 行） |
| 6 | **依赖声明**：`requirements.txt` 是 190 行的 `pip freeze` 全量导出 | 新增 `pyproject.toml`，声明 9 个直接依赖 |

---

## 6. 结果分析

### 6.1 已实现的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| Web UI | 可用 | Flask + 完整 REST API |
| 3 Agent 协作 | 可用 | CrewAI 层次化流程 |
| RAG 检索 | 可用 | ChromaDB，30 个文档块已索引 |
| 网络搜索 | 可用 | Google CSE，结果带 URL 引用 |
| SSE 进度 | 可用 | 实时推送 2 步进度到前端 |
| 多会话 | 可用 | 创建、切换、持久化 |
| 回答缓存 | 可用 | 4 条缓存已验证命中 |
| 容错降级 | 可用 | 搜索失败不影响回答生成 |
| 日志系统 | 可用 | INFO/WARNING/ERROR 分级 |
| pyproject.toml | 可用 | 9 个直接依赖 |

### 6.2 性能特征

- **缓存命中**：< 1ms（对比完整推理 90s）
- **首次索引**：取决于文件数量和大小
- **模型推理**：主要瓶颈，受 API 延迟和上下文大小影响
- **适用场景**：小规模、低并发的教学环境

### 6.3 优点

- 数据不出本地，隐私友好
- 模块化设计，各层可独立替换
- 容错降级保证基本可用性
- 实时进度反馈，用户体验好
- 工程规范完善（pyproject.toml、logging、.env.example）

### 6.4 局限

- 缓存匹配依赖精确文本，不支持语义等价重述
- 首次推理响应时间长（~90s）
- 依赖外部 API（DeepSeek + Google），离线不可用
- 无用户认证和并发控制

---

## 7. 总结与展望

### 7.1 总结

LectureCrewLLM 的核心价值在于将"讲义文件"转化为"可持续对话的知识系统"。项目完成了从知识源管理、向量索引、多代理编排、会话存储、缓存机制到 Web 交互的完整链路，并在此基础上实现了 SSE 实时进度、三级容错降级和工程化规范。

### 7.2 改进方向

**短期：**
- Agent 思考过程可视化面板（展示完整调用链）
- 基础自动化测试（RAG、缓存、API）
- Web UI 文件上传功能
- 缓存语义匹配（近义问题识别）

**中长期：**
- 可插拔 LLM 后端（支持 Claude、GPT-4、本地模型）
- 多用户协作和权限控制
- 流式回答生成（Streaming Response）
- 基于用户反馈的检索质量优化

### 7.3 可交付价值

用于课程汇报时，本项目能够展示：
- 对真实需求的分析和定义能力
- 多模块系统的分层设计能力
- 工程问题的排查、修复和迭代能力
- 大模型应用从原型到工程化的完整链路

---

## 8. 项目结构

```
lecture_crewLLM/
├── main.py                      # CLI 入口 + Crew 编排
├── web_ui.py                    # Flask Web UI + REST API + SSE
├── pyproject.toml               # 项目元数据 & 依赖声明
├── requirements.txt             # 锁定版本依赖
├── .env.example                 # 环境变量模板
│
├── tools/
│   ├── __init__.py
│   ├── local_file_tool.py       # PDF/PPTX 文本提取
│   ├── rag_store.py             # ChromaDB 向量存储 + RAG
│   ├── conversation_manager.py  # 对话历史管理
│   ├── session_manager.py       # 多会话管理
│   ├── answer_cache.py          # 回答缓存 (TTL)
│   ├── google_search_tool.py    # Google 搜索集成
│   └── status_tracker.py        # SSE 进度追踪
│
├── templates/index.html         # Web UI 模板
├── static/
│   ├── style.css                # 样式表
│   └── script.js                # 前端 JS + EventSource
│
├── knowledge/                   # ← 讲义文件 (PDF/PPTX)
├── conversations/sessions/      # 会话 JSON (自动创建)
├── cache/                       # 缓存数据 (自动创建)
├── chroma_db/                   # 向量数据库 (自动创建)
└── output/                      # 输出 Markdown (自动创建)
```

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

# 4. 放入讲义文件
mkdir -p knowledge
# 将 PDF/PPTX 文件放入 knowledge/

# 5. 启动
python web_ui.py
# 打开 http://localhost:7860
```

API 验证：
```bash
curl http://127.0.0.1:7860/api/status
curl -X POST http://127.0.0.1:7860/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize the lecture materials briefly."}'
```

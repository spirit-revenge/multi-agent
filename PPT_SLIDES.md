# LectureCrewLLM — PPT Slides

---

## Slide 1 — 项目标题与简介
- Title: LectureCrewLLM — 本地化讲座 RAG + 多代理问答平台
- One-liner: 基于本地文件的检索增强生成 (RAG)，支持多轮会话与实时进度反馈
- Audience: 教师、研究者、课程助理

---

## Slide 2 — 项目背景
- 问题域: 课堂讲义、PPT、笔记等资料量大，难以快速检索与组织
- 动机: 在不外发数据的前提下提供高质量问答与讲义摘要
- 技术栈: Python、Flask、ChromaDB、CrewAI 多代理、DeepSeek LLM

---

## Slide 3 — 问题定义
- 主问题: 如何对讲座材料做语义索引并生成上下文相关的多轮回答
- 子问题:
  - 文档解析与增量索引
  - 语义向量检索（中英文跨语言）
  - 会话持久化与多会话管理
  - 回答缓存与 TTL 过期
  - 多代理协调与容错降级
- Success Criteria: 响应准确、会话连续、容错降级、实时进度可见

---

## Slide 4 — 系统架构
- 前端: Flask Web UI + SSE 实时进度推送
- 检索层: sentence-transformers 嵌入 + ChromaDB 向量库
- 代理层: CrewAI 3 代理 + 层次化流程 (Hierarchical Process)
  - Internet Researcher — 网络搜索
  - Lecture Analyst — 内容综合
  - Educational Manager — 任务编排
- 支持系统: 会话管理、回答缓存、日志系统

---

## Slide 5 — 多代理架构详解
```
Manager Agent
├── 分配 → Internet Researcher (Google Search Tool)
│         搜索网络补充信息，返回带 URL 的结果
│
└── 分配 → Lecture Analyst
          结合 RAG 讲义片段 + 网络搜索结果 + 对话历史
          生成英文 Markdown 结构化回答
```
- RAG 检索在 Crew 启动前完成，结果注入 Analyst 的 task context
- 搜索失败时 Analyst 自动降级，仅用讲义内容生成回答

---

## Slide 6 — 关键模块详解
- `tools/rag_store.py` — ChromaDB 向量存储、增量索引、语义检索
- `tools/conversation_manager.py` — 对话历史持久化、上下文构建
- `tools/session_manager.py` — 多会话创建/删除/标签化
- `tools/answer_cache.py` — 问题缓存（MD5 匹配、30 天 TTL）
- `tools/status_tracker.py` — 内存队列 SSE 进度追踪
- `tools/google_search_tool.py` — Google 可编程搜索引擎集成
- `main.py` — CLI 入口 + `run_crew` 多代理编排
- `web_ui.py` — Flask REST API + SSE 端点

---

## Slide 7 — Web UI 特性
- REST API: `/api/chat`, `/api/status`, `/api/sessions`, `/api/cache` 等
- SSE 实时进度: `/api/chat/stream?task_id=` 推送 Agent 执行状态
  - "Searching web resources..." → "Synthesizing answer..." → "Complete!"
- 多会话管理: 会话创建、切换、历史查看
- 缓存管理: 统计面板、一键清除

---

## Slide 8 — 错误处理与容错
| 故障场景 | 降级策略 |
|---------|---------|
| RAG 检索失败 | 警告日志，使用空讲义上下文继续 |
| 网络搜索失败 | 返回错误字符串，Analyst 忽略并用讲义回答 |
| DeepSeek API 失败 | 异常传播到 Web UI，移除失败消息，提示用户 |
| ChromaDB 损坏 | 删除数据库目录，重启自动重建 |

- 日志系统: Python logging 模块，按 INFO/WARNING/ERROR 分级

---

## Slide 9 — 数据流
```
User Question
  → Cache Check (命中 → 即时返回)
  → RAG Retrieval (ChromaDB 语义检索)
  → Multi-Agent Crew
      ├── Internet Researcher (Google Search)
      └── Lecture Analyst (综合 + 生成)
  → Save: Session JSON + Cache JSON + Output Markdown
```

---

## Slide 10 — 实验 / 调研过程
- 环境: Python 3.13 + `pyproject.toml` 依赖管理
- 目录: `knowledge/`, `conversations/sessions/`, `cache/`, `output/`
- 启动: `python web_ui.py`（端口 7860）
- 端到端验证:
  1. `/api/status` — 服务状态
  2. `/api/sessions` — 会话管理
  3. `/api/chat` — 多代理问答（约 90s 完整响应）

---

## Slide 11 — 遇到的问题与修复
- **假 Agent 问题**: 原 File Reader Agent 形同虚设 → 重构为真正 3 Agent 架构
- **API 密钥泄露**: `.env` 提交到 git → 密钥轮换 + `.gitignore` 修复 + `.env.example`
- **无进度反馈**: Web UI 只有无限 loading → 新增 SSE 实时进度推送
- **错误处理缺失**: API 失败直接崩溃 → 多级容错降级 + 日志系统
- **print() 调试**: 全项目用 print → 统一替换为 logging 模块

---

## Slide 12 — 结果分析
- **功能**: 3 Agent 协作、RAG 检索、网络搜索、SSE 进度、多会话、缓存全部可用
- **稳定性**: 容错降级（搜索失败不影响回答生成）
- **安全性**: 密钥不再硬编码/提交，Flask debug 可选，密钥必须从环境变量加载
- **工程规范**: pyproject.toml、logging、`.env.example`、`ARCHITECTURE.md`

---

## Slide 13 — 短期改进
- Agent 思考过程可视化面板（展示调用链）
- 基础自动化测试（RAG、缓存、API）
- Web UI 文件上传功能
- 缓存语义匹配（近义问题识别）

---

## Slide 14 — 快速复现
```bash
git clone <repo>
cp .env.example .env
# 编辑 .env 填入 API 密钥
pip install -e .
python web_ui.py
# 打开 http://localhost:7860
```

---

## Slide 15 — 演示流程
1. 启动服务，展示 `/api/status` 响应
2. 创建会话，展示 SSE 实时进度
3. 发送问答请求，观察 3 Agent 协作
4. 展示缓存命中效果
5. 展示 `output/` 和 `conversations/` 持久化文件

---

## Slide 16 — 总结
- 本地 RAG + 多代理 = 可控的知识问答系统
- 3 Agent 层次化协作 + 容错降级
- SSE 实时反馈 + 多会话管理
- 工程化: pyproject.toml, logging, 安全配置

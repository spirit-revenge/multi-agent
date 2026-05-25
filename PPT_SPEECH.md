# LectureCrewLLM — 演讲稿（逐页）

---

## Slide 1 — 项目标题与简介（30s）
大家好，我将介绍 LectureCrewLLM，这是一个面向讲座材料的本地化问答平台。我们的目标是在不外发数据的前提下，用多代理系统帮助用户从讲义中获得高质量回答。

---

## Slide 2 — 项目背景（40s）
现代教学产生大量讲义、PPT，手动检索耗时且效率低。我们希望通过语义检索 + 多代理生成技术，让用户像对话一样问问题。技术上采用 Python、Flask、ChromaDB、CrewAI，使用 DeepSeek 作为 LLM。

---

## Slide 3 — 问题定义（40s）
核心问题是把非结构化讲义变为可检索、可对话的知识库。子问题包括文件解析、语义索引、多轮对话、缓存、多代理协调。成功标准包括回答准确性、会话连续性、容错降级和实时进度可见。

---

## Slide 4 — 系统架构（50s）
系统分四层：前端 Flask Web UI + SSE 实时推送；检索层用 sentence-transformers 和 ChromaDB；代理层用 CrewAI 的层次化流程调度 3 个 Agent；支撑层包括会话管理、缓存和日志系统。

---

## Slide 5 — 多代理架构详解（50s）
这是我们重点改进的部分。最初有 4 个 Agent，但 File Reader 是"假 Agent"——它不实际执行工具调用。重构后改为真正的 3 Agent：
- Internet Researcher 负责网络搜索
- Lecture Analyst 负责综合讲义片段和搜索结果，生成英文 Markdown
- Educational Manager 负责编排整个流程

RAG 检索在 Crew 启动前完成，失败时自动降级。

---

## Slide 6 — 关键模块详解（50s）
7 个核心模块：向量存储和检索、对话历史管理、多会话支持、答案缓存、SSE 进度追踪、Google 搜索工具、以及主编排器。每个模块职责单一、可替换。

---

## Slide 7 — Web UI 特性（40s）
Flask 提供完整的 REST API 和 SSE 端点。前端在发送问题前先通过 `/api/chat/task` 获取任务 ID，然后订阅 SSE 流。执行过程中用户能看到"Searching web..."→"Synthesizing answer..."→"Complete!"的实时步骤切换。

---

## Slide 8 — 错误处理与容错（40s）
系统有三级容错：RAG 检索失败不影响回答生成；网络搜索失败时 Analyst 自动忽略错误并只用讲义内容；DeepSeek API 失败时前端显示友好提示。同时全项目使用 Python logging 模块做结构化日志。

---

## Slide 9 — 数据流（30s）
用户问题进来先查缓存，命中直接返回。否则走 RAG 检索 → 多代理推理 → 回答生成。最终保存到三个地方：对话历史 JSON、答案缓存 JSON、Markdown 输出文件。

---

## Slide 10 — 实验 / 调研过程（30s）
Python 3.13 环境，用 pyproject.toml 管理 9 个直接依赖。启动后通过 curl 验证各 API 端点。`/api/chat` 的完整响应约 90 秒，取决于模型响应时间。

---

## Slide 11 — 遇到的问题与修复（50s）
开发中发现了五个主要问题并全部修复：
1. 假 Agent — 重构为真正的 3 Agent 架构
2. API 密钥泄露到 git — 轮换密钥，创建 .env.example
3. 无进度反馈 — 新增 SSE 实时推送
4. 错误处理缺失 — 多级降级 + 日志系统
5. print() 调试 — 统一替换为 logging 模块

这些问题说明：系统设计好不等于落地好，需要关注工程细节。

---

## Slide 12 — 结果分析（40s）
功能上所有模块可用。稳定性上容错降级保证了即使部分服务故障也能生成回答。安全性上密钥不再硬编码。工程上具备 pyproject.toml、logging、架构文档。

---

## Slide 13 — 短期改进（30s）
- Agent 思考过程可视化面板
- 基础自动化测试
- Web UI 文件上传
- 缓存语义匹配

---

## Slide 14 — 快速复现（30s）
四步启动：克隆仓库、配置 .env、安装依赖、运行 web_ui.py。所有必需目录自动创建。

---

## Slide 15 — 演示流程（40s）
建议演示顺序：先展示 `/api/status` 确认服务正常；再创建新会话并展示 SSE 进度条；发送一个问题观察 3 Agent 协作过程；重复同一问题展示缓存命中；最后打开本地文件展示持久化输出。

---

## Slide 16 — 结束与 Q&A（30s）
总结三个核心价值：本地 RAG + 多代理协作、实时进度反馈 + 容错降级、工程化规范。邀请提问。

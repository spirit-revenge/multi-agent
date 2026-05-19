# LectureCrewLLM — PPT Slides

---

## Slide 1 — 项目标题与简介
- Title: LectureCrewLLM — 本地化讲座 RAG 与多代理问答平台
- One-liner: 基于本地文件的检索增强生成 (RAG)，支持多轮会话与会话持久化
- Audience: 教师、研究者、课程助理

---

## Slide 2 — 项目背景
- 问题域: 课堂讲义、PPT、笔记等资料量大，难以快速检索与组织
- 动机: 在不外发数据的前提下提供高质量问答与讲义摘要
- 技术栈: Python、Flask、Chroma 向量库、本地/可配置 LLM

---

## Slide 3 — 问题定义
- 主问题: 如何对讲座材料做语义索引并生成上下文相关的多轮回答
- 子问题:
  - 文档解析与增量索引
  - 向量数据库持久化
  - 会话保存与切换
  - 回答缓存与重复查询处理
  - 多代理协调
- Success Criteria: 响应准确、会话连续、延迟可控、重复查询成本低

---

## Slide 4 — 方法设计（总体架构）
- 前端: `Flask` 提供 Web UI 与 REST API
- 检索层: 文本分段 → 嵌入 → Chroma 向量索引
- 协调器/代理: `run_crew` 协调文件读取器、分析器、互联网研究者、管理器
- 支持系统: 会话管理、回答缓存、输出保存

---

## Slide 5 — 关键模块详解（1/2）
- File Reader: `tools/local_file_tool.py` — 提取 PDF/PPTX/TXT 文本
- Vector Store: `tools/rag_store.py` — 生成嵌入、持久化、增量索引
- Conversation Manager: `tools/conversation_manager.py` — 管理会话历史

---

## Slide 6 — 关键模块详解（2/2）
- Session Manager: `tools/session_manager.py` — 会话创建/删除/标签化
- Answer Cache: `tools/answer_cache.py` — 问题去重、TTL（30 天）
- LLM / Orchestrator: `main.py` — `run_crew`, `deepseek_llm` 的检索-生成流程

---

## Slide 7 — 实验 / 调研流程（准备）
- 环境: Conda (`camel`)、`requirements.txt`
- 目录: `knowledge/`, `conversations/`, `cache/`, `output/`
- 启动脚本: `start_web_ui.sh` 或手动 `WEB_UI_PORT=7860 conda run -n camel python web_ui.py`
- 工具: `lsof`、`curl` 做本地验证

---

## Slide 8 — 实验 / 调研流程（执行）
- API 测试序列: `/api/status` → `/api/sessions` → POST `/api/sessions` → POST `/api/chat`
- 用法: 使用 `curl -c/-b cookies.txt` 保持会话
- 问题示例: 端口冲突（macOS AirTunes 占用 5000） → 改为 7860

---

## Slide 9 — 结果（功能验证）
- 状态接口: 返回缓存/会话统计（示例 JSON）
- 会话管理: 成功列出/创建会话，保存文件到 `conversations/sessions/`
- 聊天接口: 触发 `run_crew`，模型/索引未就绪时响应耗时较长

---

## Slide 10 — 结果（问题与修复）
- 问题: `AttributeError: 'str' object has no attribute 'stem'`（路径类型不匹配）
- 修复: `web_ui.py` 将字符串转为 `Path`；加入 `@app.before_request` 会话初始化
- 端口: 将默认端口改为 7860 并更新文档与启动脚本

---

## Slide 11 — 结果分析（性能与可用性）
- 优势: 本地运行、隐私保护、模块化、缓存降低重复成本
- 限制: 依赖本地算力或远程模型、首次索引耗时、并发受限
- 风险: 模型不可用或索引膨胀

---

## Slide 12 — 实践建议（短期）
- 增加端到端 CI 测试
- 在 `/api/chat` 增加超时/异步与进度查询
- UI 中显示索引/缓存状态

---

## Slide 13 — 路线图（中长期）
- 支持可插拔模型后端（本地量化/远程 API）
- 引入增量学习与人类反馈
- 扩展多人协作、注释与导出功能

---

## Slide 14 — 复现命令汇总
```bash
conda create -n camel python=3.13 -y
conda activate camel
pip install -r requirements.txt
WEB_UI_PORT=7860 ./start_web_ui.sh
lsof -nP -iTCP:7860 -sTCP:LISTEN
curl -i -c cookies.txt http://127.0.0.1:7860/api/status
curl -i -b cookies.txt -c cookies.txt http://127.0.0.1:7860/api/sessions
curl -i -b cookies.txt -c cookies.txt -H "Content-Type: application/json" -d '{"name":"e2e-test"}' http://127.0.0.1:7860/api/sessions
curl -i -b cookies.txt -c cookies.txt -H "Content-Type: application/json" -d '{"message":"Summarize the lecture materials briefly."}' --max-time 600 http://127.0.0.1:7860/api/chat
```

---

## Slide 15 — 演示流程
1. 启动服务并展示 `/api/status` 响应
2. 创建并切换会话，展示 `conversations/sessions/` 文件
3. 发送问答请求并展示缓存与输出文件
4. 展示 `output/lecture_output_*.md` 示例

---

## Slide 16 — 附件与参考
- 主要文件: `PROJECT_SUMMARY.md`, `web_ui.py`, `main.py`, `tools/*`, `start_web_ui.sh`
- 目录: `knowledge/`, `conversations/`, `cache/`, `output/`, `templates/`, `static/`
- 下一步: 英文版、PPTX 导出或现场演示准备

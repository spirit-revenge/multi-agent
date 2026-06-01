# LectureCrewLLM — 项目总结

> 多智能体讲座分析系统 | 2026年5月 | 131 项测试全部通过

---

## Slide 1: 项目概述

**LectureCrewLLM** 是一个基于多智能体协作的讲座智能分析系统。

- **定位**：面向教育资源（PDF/PPTX/DOCX 讲座课件）的 RAG 问答系统
- **核心能力**：多模态文档解析 → 向量化存储 → 意图路由 → 智能体协作 → 结构化回答
- **交互方式**：Flask Web UI（推荐）+ CLI 命令行
- **开发周期**：7 个阶段迭代，从基础架构到交互增强

---

## Slide 2: 系统架构概览

```
用户提问 → 缓存检查 → 规则路由器 → LLM 路由器 → 三路分发
                                              ├─ lecture: RAG → 相似度门控 → Guard → Analyst
                                              ├─ web:     Tavily 搜索 → Analyst
                                              └─ hybrid:  RAG + 搜索 → Analyst
                                              ↓
                                         SSE 实时进度推送 → 前端 Markdown 渲染
```

- **4 级缓存**：答案缓存 + 检索缓存 + 搜索缓存 + web→RAG 持久化
- **3 档门控**：≥0.82 跳过 Guard / 0.45-0.82 Guard 验证 / ≤0.45 跳过
- **双路由**：规则关键词（零 LLM）→ LLM Router（仅兜底）

---

## Slide 3: 多智能体角色

| Agent | 职责 | 模型配置 | Token 消耗 |
|-------|------|---------|-----------|
| 🎯 **意图路由器** | 分类用户问题为 lecture / web / hybrid / unknown | temp=0.1 | ~50 |
| ✅ **相关性验证员** | 判断 RAG 检索是否语义相关（区分关键词重叠 vs 真正相关） | temp=0.1 | ~200 |
| 📝 **讲座分析师** | 综合 RAG + 搜索结果，生成结构化中文 Markdown 回答 | temp=0.7 | ~1000-2000 |

**编排模式**：CrewAI Sequential Process

- 从 Hierarchical 迁移到 Sequential，LLM 调用从 5 次降至 2-3 次
- 响应时间从 ~24s 降至 ~8s

---

## Slide 4: 多模态 RAG 管道

```
knowledge/*.pdf / *.pptx / *.docx
    │
    ├── DocumentProcessor ───┐
    │   ├── extract_text()    → 语义分块（段落/标题边界，100-1200 字符）
    │   ├── extract_images()  → PIL Image → BLIP 批量描述 → 存 images/
    │   └── extract_tables()  → Markdown 表格字符串
    │
    └── ChromaDB ─────────────┘
        ├── type: "text"  | "image"  | "table" | "web"
        ├── source: 来源文件路径 或 web_search:{hash}
        └── vector: 384 维（paraphrase-multilingual-MiniLM-L12-v2）
              │
              ▼
      余弦 ANN 搜索 → BM25 混合重排序 (70/30) → Top-K → 相似度门控
```

**关键技术**：
- 图片不直接嵌入，而是通过 BLIP 生成文字描述后再向量化
- BM25 统计重排序补充嵌入相似度（移除 CrossEncoder，省 1-2s/次）
- 搜索结果持久化到 RAG（type="web"），相似查询免重新调用 API

---

## Slide 5: 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| **LLM** | DeepSeek Chat API（可通过 `LLM_MODEL` 切换） | — |
| **Agent 框架** | CrewAI（Sequential Process） | 1.14.3 |
| **向量数据库** | ChromaDB（本地持久化） | 1.1.1 |
| **嵌入模型** | paraphrase-multilingual-MiniLM-L12-v2（384 维） | 5.4.1 |
| **深度学习** | PyTorch + Transformers + BLIP | 2.11.0 / 5.7.0 |
| **重排序** | BM25 Okapi（scikit-learn） | 1.8.0 |
| **文档解析** | PyMuPDF / python-pptx / python-docx | 1.26 / 1.0 / 1.2 |
| **联网搜索** | Tavily API | 0.7.24 |
| **Web 框架** | Flask + SSE + Font Awesome | 3.0.0 |
| **中文 NLP** | jieba（分词用于缓存匹配） | — |
| **测试** | pytest（131 项，8 模块） | 9.0.3 |

---

## Slide 6: 功能特性一览

| 功能 | 说明 |
|------|------|
| 🧠 **多智能体协作** | 意图路由 → RAG 检索 → 相关性验证 → 分析师，4 Agent 协同 |
| 📚 **多模态 RAG** | 文本（语义分块）+ 图片（BLIP）+ 表格（Markdown），统一向量化 |
| 🌐 **联网搜索** | Tavily API，手动开关，1h 缓存，结果持久化到 RAG |
| ⚡ **四级缓存** | 答案(30天TTL) + 检索 + 搜索(1hTTL) + web→RAG，最大化复用 |
| 📡 **SSE 实时进度** | 4 步进度条 + 计时器 + 轮播提示，前端实时感知后台状态 |
| 📁 **文件管理** | 上传/删除/重建索引，SHA256 增量索引，单文件索引 O(1) |
| 🔍 **历史搜索** | CLI `find` + Web UI 侧边栏，跨会话全文检索，点击一键跳转 |
| 💬 **多会话** | 持久化对话历史，会话切换/新建/删除 |
| 📍 **自动定位** | 浏览器 Geolocation API，天气等查询自动附带城市 |
| 🛡️ **优雅降级** | 搜索失败→仅讲座内容，BLIP 失败→图片占位符 |

---

## Slide 7: 关键设计决策

| 决策 | 方案 | 效果 |
|------|------|------|
| **Sequential 替代 Hierarchical** | 去掉 Manager Agent，直接 pipeline | 5→2 次 LLM 调用，~24s→~8s |
| **CrossEncoder 移除** | BM25 + 嵌入相似度融合 (70/30) | 省 1-2s/次查询 |
| **RAG 上下文减半** | 4000→2000 字符限制 | 省 ~500 token/次查询 |
| **阈值三档门控** | ≥0.82 直接使用 / 0.45-0.82 Guard / ≤0.45 跳过 | 扩大 Guard 覆盖范围，避免短查询漏召回 |
| **双路由策略** | 规则关键词匹配（零 LLM）→ LLM 兜底 | 天气/新闻类问题零路由成本 |
| **图片→文字描述** | BLIP 描述文本化，不直接嵌入图片 | 无需多模态嵌入模型，384 维足矣 |
| **缓存归一化** | MD5(去标点+去停用词+排序 token) | "什么是BERT" ≡ "BERT是什么" |
| **相似度阈值 0.65** | Jaccard + coverage 融合 | 防止"水原天气"↔"明天天气"假命中 |
| **单文件索引** | `index_file()` 跳过目录扫描 | 上传 API：O(N)→O(1) |
| **批量 BLIP** | Pipeline 批量模式替代串行 | 多图文档 2-5× 加速 |
| **模型环境变量** | `LLM_MODEL` 统一管理 | 切换模型无需改代码 |

---

## Slide 8: 性能优化历程

| 阶段 | 优化项 | 效果 |
|------|--------|------|
| **架构** | Hierarchical → Sequential | -3 次 LLM 调用（~16s） |
| **重排序** | 移除 CrossEncoder | -1-2s/次查询 |
| **上下文** | RAG 上下文 4000→2000 字 | -500 token/次 |
| **采样** | ChromaDB 候选 12→8 | -33% 检索开销 |
| **路由** | Guard 重试路径移除 | -1 次 LLM（~3% 请求） |
| **上传** | `index_file()` 单文件索引 | O(N)→O(1)，大目录显著加速 |
| **BLIP** | 批量推理替代逐个处理 | 多图文档 2-5× 加速 |
| **前端** | 侧边栏自动刷新 | 缓存/文件列表实时更新 |

---

## Slide 9: 测试覆盖（131 项）

| 模块 | 数量 | 覆盖内容 |
|------|------|---------|
| `test_rag.py` | 37 | 语义分块、文档分发、图片描述、向量 CRUD、混合检索、web→RAG、单文件索引 |
| `test_answer_cache.py` | 12 | 缓存命中/过期、标点容忍、停用词过滤、jieba 语义匹配 |
| `test_conversation_manager.py` | 16 | 消息 CRUD、持久化、上下文格式化、搜索 |
| `test_session_manager.py` | 15 | 会话创建/列表/标签/删除、跨会话搜索 |
| `test_web_api.py` | 42 | Flask API + HTML 模板 + SSE + 聊天 + 会话/知识/图片端点 |
| `test_status_tracker.py` | 6 | SSE 进度追踪、并发安全 |
| `test_local_file_tool.py` | 3 | PDF/PPTX 读取、文件不存在处理 |
| **总计** | **131** | |

---

## Slide 10: REST API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/status` | 系统状态 |
| `GET/POST` | `/api/sessions` | 会话列表/创建 |
| `POST/DELETE` | `/api/sessions/<path>` | 切换/删除会话 |
| `GET` | `/api/chat/task` | SSE task ID |
| `POST` | `/api/chat` | 发送消息 |
| `GET` | `/api/chat/stream` | SSE 进度流 |
| `GET/DELETE` | `/api/history` | 对话历史 |
| `GET` | `/api/history/search` | 搜索历史（`?q=关键词&all=true`） |
| `GET/POST/DELETE` | `/api/knowledge/*` | 文件上传/列表/删除/重建索引 |
| `GET/DELETE` | `/api/cache` | 缓存统计/清除 |
| `GET` | `/images/<filename>` | 提取的图片文件 |

---

## Slide 11: 项目结构

```
lecture_crewLLM/
├── main.py                          # CLI 入口 + Agent 编排
├── web_ui.py                        # Flask Web UI + REST API + SSE
├── requirements.txt                 # 依赖锁定
├── .env.example                     # 环境变量模板
│
├── tools/
│   ├── rag_store.py                 # ChromaDB + BM25 混合检索
│   ├── document_processor.py        # 文档解析（PDF/PPTX/DOCX）+ 语义分块
│   ├── image_captioner.py           # BLIP 批量图片描述
│   ├── conversation_manager.py      # 对话历史（≤300 token 摘要）
│   ├── session_manager.py           # 多会话管理 + 跨会话搜索
│   ├── answer_cache.py              # 答案缓存（精确哈希 + 相似度回退）
│   ├── google_search_tool.py        # Google 搜索（历史遗留）
│   ├── local_file_tool.py           # CrewAI 文件读取 Tool
│   └── status_tracker.py            # SSE 进度追踪
│
├── tests/                           # 131 项测试（8 模块）
├── templates/index.html             # Web UI 模板
├── static/{style.css,script.js}     # 前端（零框架，纯 JS Markdown 渲染）
├── picts/                           # SVG 架构图
│   ├── request_flow.svg             # 请求流程图
│   └── rag_pipeline.svg             # RAG 管道图
│
├── knowledge/                       # 讲座文件（PDF/PPTX/DOCX）
├── images/                          # 提取的图片
├── chroma_db/                       # 向量数据库
├── conversations/sessions/          # 会话 JSON
├── cache/                           # 答案/检索/搜索缓存
└── output/                          # 答案导出
```

---

## Slide 12: 开发历程

| 阶段 | 内容 |
|------|------|
| **基础架构** | CrewAI + ChromaDB + DeepSeek + Flask Web UI + CLI |
| **RAG 增强** | 语义分块、BLIP 图片描述、表格 MD 转换、DOCX 支持 |
| **性能优化** | Sequential 取代 Hierarchical、移除 CrossEncoder、RAG 上下文减半、多级缓存 |
| **体验优化** | 中文界面、SSE 4 步进度、实时计时器、轮播提示、Markdown 导出 |
| **智能路由** | 规则匹配 + LLM 双路由、Grounding Check 语义验证、三档阈值门控 |
| **稳定性** | 图片 URL 编码、路径穿越防护、文件名特殊字符清理、缓存自动清理 |
| **交互增强** | 历史搜索（CLI + Web UI）、搜索结果一键跳转、浏览器自动定位 |
| **上传链路优化** | 单文件索引 O(1)、批量 BLIP 2-5× 加速、侧边栏自动刷新 |

---

## Slide 13: 配置与环境变量

| 变量 | 必填 | 说明 | 默认 |
|------|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 | — |
| `LLM_MODEL` | ❌ | LLM 模型名（provider/model） | `deepseek/deepseek-chat` |
| `TAVILY_API_KEY` | ❌ | Tavily 联网搜索密钥 | — |
| `FLASK_SECRET_KEY` | ✅* | Flask 会话签名密钥 | — |
| `WEB_UI_PORT` | ❌ | Web UI 端口 | `7860` |
| `FLASK_DEBUG` | ❌ | 调试模式（1/0） | `0` |

---

## Slide 14: 启动与运行

```bash
# 安装
cp .env.example .env    # 编辑填入密钥
pip install -r requirements.txt

# Web UI（推荐）
python web_ui.py         # http://localhost:7860

# CLI 模式
python main.py           # 支持 find/history/sessions/cache 等命令

# 测试
python -m pytest tests/ -v   # 131 项，全部通过
```

---

## Slide 15: 总结

**LectureCrewLLM** 是一个完整的多智能体 RAG 问答系统，特点：

1. **全链路优化**：从用户提问到答案生成，每一层都有针对性优化
2. **多模态支持**：文本 + 图片 + 表格 + 网页搜索结果统一向量化检索
3. **智能缓存体系**：4 级缓存 + 相似度回退匹配，最大化复用
4. **工程完备**：131 项测试、SVG 架构图、中英文文档、环境变量统一管理
5. **实战可部署**：增量索引、单文件快速上传、SSE 实时反馈、优雅降级

---

*Generated: May 2026 | Tests: 131/131 passing | Python 3.11+*

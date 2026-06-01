# Bug Report — LectureCrewLLM

> 最后更新：2026年6月 | 测试：131/131 全部通过

---

## 总览

| # | Bug | 严重程度 | 状态 | 类型 |
|---|-----|---------|------|------|
| 1 | 缓存假阳性 — 不同查询命中同一缓存 | 🔴 高 | ✅ 已修复 | 算法 |
| 2 | RAG 漏召回 — 短查询被门控误杀 | 🔴 高 | ✅ 已修复 | 算法 |
| 3 | 侧边栏不自动刷新 | 🟡 中 | ✅ 已修复 | 前端 |
| 4 | 关闭搜索仍显示搜索步骤 | 🟡 中 | ✅ 已修复 | 前端 |
| 5 | SVG 架构图无法渲染 | 🟢 低 | ✅ 已修复 | 代码 |
| 6 | `.env` 无用变量 (Google → Tavily) | 🟢 低 | ✅ 已修复 | 配置 |
| 7 | 搜索结果点击无跳转 | 🟡 中 | ✅ 已修复 | 前端 |
| 8 | 图片文件名冲突 — 同 stem 覆盖 | 🔴 高 | ✅ 已修复 | 数据 |
| 9 | 图片 URL 中 `_` → `%5F` | 🟡 中 | ✅ 已修复 | 代码 |
| 10 | LLM 编造图片路径 → 404 | 🔴 高 | ✅ 已修复 | 安全网 |
| — | `google_search_tool.py` 死代码 | 🟢 低 | ✅ 已删除 | 清理 |
| — | `PROJECT_SUMMARY.md` 冗余 | 🟢 低 | ✅ 已删除 | 清理 |
| — | `tests/a.py` 草稿文件 | 🟢 低 | ✅ 已删除 | 清理 |

## 删除的死代码文件

| 文件 | 原因 | 操作 |
|------|------|------|
| `tools/google_search_tool.py` | Google Search 已被 Tavily 替代，类定义从未被任何代码导入 | `git rm` |
| `PROJECT_SUMMARY.md` | 内容完全被 README 覆盖 | `git rm` |
| `tests/a.py` | 草稿/手动测试文件 | 删除 |

---



## Bug #1: 缓存假阳性匹配 — 不同查询命中同一缓存

**严重程度**: 🔴 高  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

用户分别问"水原天气如何"和"明天天气如何"，两次查询命中同一个缓存答案。

### 根因

答案缓存的相似度回退算法中，两个完全不同的问题仅共用一词：

```
"水原天气如何" → jieba 分词 → {"水原", "天气"}
"明天天气如何" → jieba 分词 → {"明天", "天气"}

交集 = {"天气"}
Jaccard = 1/3 ≈ 0.333
Coverage = 1/2 = 0.5
合成得分 = 0.417 ≥ 0.4（阈值） → 假命中
```

### 修复

[`tools/answer_cache.py:118`](tools/answer_cache.py#L118) — `_SIMILARITY_THRESHOLD` 从 `0.4` 提高到 `0.65`

### 验证

```
新阈值 0.65:
- "水原天气如何" ↔ "明天天气如何" → 0.417 < 0.65 ✓ 正确过滤
- "北京天气" ↔ "上海天气" → 0.417 < 0.65 ✓ 正确过滤
- "水原天气如何" ↔ "水原天气" → 精确哈希命中 ✓ 正确匹配
```

---

## Bug #2: RAG 检索漏召回 — 短查询/缩写词被相似度门控误杀

**严重程度**: 🔴 高  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

数据库中有 RAG 相关讲座内容（W12_LLM_RAG&Agent.pptx），但用户问"rag是什么"（关闭联网搜索）时系统显示"找不到相关信息"。

### 根因

两个因素叠加：

1. **嵌入模型对短查询天然低相似度**：`paraphrase-multilingual-MiniLM-L12-v2` 对"rag是什么"这类短查询+缩写词的嵌入向量，与文档向量的余弦相似度仅在 0.33~0.44 之间。

2. **门控跳过阈值过严**：旧阈值 `≤0.55` 直接把所有检索结果丢弃，不给 Guard LLM 验证的机会。

### 修复

| 修复 | 文件 | 改动 |
|------|------|------|
| 降低跳过阈值 | [`main.py:423`](main.py#L423) | `0.55` → `0.45`，扩大 Guard 覆盖范围 |
| 关键词词面匹配 Boost | [`tools/rag_store.py`](tools/rag_store.py) | 查询展开词在文档中命中 → 相似度自动抬到 0.55 |

### 验证

```
"rag是什么" 检索流程（修复后）：
  ↓ 展开 → "rag是什么 (Retrieval Augmented Generation 检索增强生成)"
  ↓ 嵌入 → 相似度 0.44
  ↓ 关键词 Boost: "retrieval" "检索增强生成" 在文档中命中 ✓
  ↓ 相似度 → 0.55 ≥ 0.45
  ↓ Guard LLM → RELEVANT ✓
  ↓ 生成答案
```

---

## Bug #3: 前端侧边栏不自动刷新

**严重程度**: 🟡 中  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

- 发送消息后，新的缓存条目不反映在侧边栏缓存计数上
- 切换/创建/删除会话后，知识文件列表和缓存计数不更新
- 清除缓存后，计数仍显示旧值

### 根因

多个操作成功后只刷新了对话区，缺少 `loadCacheStats()` 和 `loadKnowledge()` 调用。

### 修复

[`static/script.js`](static/script.js) — 5 处补齐侧边栏刷新：

| 操作 | 修复前 | 修复后 |
|------|--------|--------|
| `sendMessage()` 成功 | `updateStatus()` | + `loadCacheStats()` |
| `clearCache()` 成功 | 手动 `textContent = '0'` | `loadCacheStats()` |
| `switchSession()` 成功 | `loadChatHistory()` | + `loadKnowledge()` + `loadCacheStats()` |
| `createNewSession()` 成功 | `loadSessions()` + `loadChatHistory()` | + `loadKnowledge()` + `loadCacheStats()` |
| `deleteSession()` 成功 | `loadSessions()` + `updateStatus()` + `loadChatHistory()` | + `loadKnowledge()` + `loadCacheStats()` |

---

## Bug #4: 关闭联网搜索时 UI 仍显示"搜索网络"步骤

**严重程度**: 🟡 中  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

用户在 Web UI 关闭联网搜索开关后提问，加载动画仍显示 4 步（含"🌐 搜索网络资源"），但该步骤永远不会亮起。

### 根因

加载步骤的 HTML 是静态模板，未根据 `useWebSearch` 状态条件渲染。

### 修复

| 文件 | 改动 |
|------|------|
| [`static/script.js`](static/script.js) `addLoadingMessage()` | inline 加载气泡中搜索步骤改为条件渲染 |
| [`static/script.js`](static/script.js) `toggleWebSearch()` | 切换开关时同步 overlay 搜索步骤显隐 |
| [`static/script.js`](static/script.js) `initializeUI()` | 页面加载时同步初始状态 |
| [`templates/index.html`](templates/index.html) | overlay 搜索步骤添加 class |

### 验证

```
联网开启：4 步（路由 → RAG → 搜索 → 生成）
联网关闭：3 步（路由 → RAG → 生成），搜索步骤隐藏
```

---

## Bug #5: SVG 架构图无法渲染

**严重程度**: 🟢 低  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

`picts/request_flow.svg` 在浏览器/Markdown 预览中无法显示。

### 根因

第 135 行 XML 属性值末尾有一个多余的引号：
```xml
<text ... fill="#047857"">Both pipelines</text>
                         ↑ 多余引号导致 XML 解析失败
```

### 修复

移除多余的 `"`，改为 `fill="#047857"`。两文件通过 `xml.etree.ElementTree` 解析验证。

---

## Bug #6: `.env` 文件存在无用变量

**严重程度**: 🟢 低  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

`.env` 中包含 `GOOGLE_API_KEY` 和 `GOOGLE_CSE_ID`，但项目已改用 Tavily API，Google Search Tool 仅作为历史遗留文件存在。

### 修复

| 文件 | 改动 |
|------|------|
| [`.env`](.env) | 移除 `GOOGLE_API_KEY`、`GOOGLE_CSE_ID` |
| [`.env.example`](.env.example) | 移除 Google 条目，补全 `TAVILY_API_KEY`、`LLM_MODEL`、`FLASK_DEBUG` |
| [`tests/test_web_api.py`](tests/test_web_api.py) | 移除 `os.environ.setdefault("GOOGLE_API_KEY", ...)` |

---

## Bug #7: 搜索结果点击无跳转

**严重程度**: 🟡 中  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

Web UI 侧边栏搜索历史记录后，点击搜索结果不会跳转到对应消息。

### 根因

1. 缺少 `e.stopPropagation()`，事件可能被父容器拦截
2. `jumpToMessage()` 异步异常静默吞掉，无错误提示
3. 切换会话后 DOM 未完全渲染就执行滚动，存在竞态条件
4. `btnToggleWeb` 缺少 click 事件绑定

### 修复

[`static/script.js`](static/script.js):
- 点击处理器添加 `e.stopPropagation()` + `.catch()` 错误提示
- `jumpToMessage()` 内部添加 `setTimeout(100ms)` 延迟滚动
- 成功跳转后显示 toast 提示
- 补充 `btnToggleWeb` 事件绑定

---

## Bug #8: 图片文件名冲突 — 同名 stem 导致图片互相覆盖

**严重程度**: 🔴 高  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

当 `knowledge/` 下存在两个不同文件但 `_safe_filename(stem)` 相同时，后索引的文件图片会覆盖前面的。

### 根因

三处图片文件名生成仅使用 `_safe_filename(file_path.stem)` 作为前缀：

```python
# PDF:   knowledge/W11_LLM_提示词工程.pptx → safe_stem = "W11_LLM"
# PPTX:  knowledge/archive/W11_LLM_测试.pptx → safe_stem = "W11_LLM"  ← 冲突！
# 结果:  W11_LLM_s1_img0.png → 被后者覆盖
```

同样的问题也存在于 ChromaDB ID：`{stem}_text_0` / `{stem}_img_0` / `{stem}_table_0`。

### 修复

| 文件 | 改动 |
|------|------|
| [`tools/document_processor.py`](tools/document_processor.py) | 新增 `_file_path_hash()` 和 `_image_stem()`，图片文件名前缀改为 `{safe_stem}_{8位路径hash}` |
| [`tools/rag_store.py`](tools/rag_store.py) | `_index_single_file()` 中 ID 前缀改为 `{stem}_{8位路径hash}`，图片/文本/表格 ID 统一 |
| [`tools/rag_store.py`](tools/rag_store.py) | `image_path` 存储为 `.resolve()` 绝对路径，确保删除时不受 CWD 变化影响 |

### 修复后

```
W11_LLM_提示词工程.pptx  → stem=W11_LLM, hash=a3f2c1b0 → W11_LLM_a3f2c1b0
W11_LLM_测试.pptx        → stem=W11_LLM, hash=9d8e7f6a → W11_LLM_9d8e7f6a
```

图片文件名：`W11_LLM_a3f2c1b0_s1_img0.png` vs `W11_LLM_9d8e7f6a_s1_img0.png` — **不再冲突**。

ChromaDB ID：`W11_LLM_a3f2c1b0_text_0` vs `W11_LLM_9d8e7f6a_text_0` — **不再冲突**。

---

## Bug #9: 答案中图片无法显示 — 下划线被错误编码为 %5F

**严重程度**: 🔴 高  
**发现日期**: 2026-05  
**状态**: ✅ 已修复

### 现象

生成的答案中图片引用无法正常显示（404 或加载失败）。

### 根因

`format_chunks_as_context()` 中多余的 `.replace('_', '%5F')`：

```python
# 修复前（bug）
safe_name = quote(img_filename).replace('_', '%5F')
# "W11_LLM_s1_img0.png" → "W11%5FLLM%5Fa3f2c1b0%5Fs1%5Fimg0.png"
```

`_` 是 URL 合法字符，不需要也不应该被编码。该行代码将所有下划线强制替换为 `%5F`，导致：

1. 图片路径冗长且丑陋
2. 部分 Markdown 解析器可能将 `%5F` 与标准 %-encoding 混淆
3. 与 `_safe_filename` 产生的大量下划线形成组合效应

### 修复

[`tools/rag_store.py:795`](tools/rag_store.py#L795)：移除 `.replace('_', '%5F')`，仅保留 `quote()` 处理真正的特殊字符。

```python
# 修复后
safe_name = quote(img_filename)
# "W11_LLM_a3f2c1b0_s1_img0.png" → "W11_LLM_a3f2c1b0_s1_img0.png"
```

### 对比

| 版本 | 生成的 URL |
|------|-----------|
| 旧（bug） | `/images/W11%5FLLM%5Fa3f2c1b0%5Fs1%5Fimg0.png` |
| 新（fix） | `/images/W11_LLM_a3f2c1b0_s1_img0.png` |

---

## Bug #10: 答案中图片路径错误 — 404 for /images/{source.pptx}/幻灯片1.png

**严重程度**: 🔴 高  
**发现日期**: 2026-06-01  
**状态**: ✅ 已修复

### 现象

答案中的图片引用返回 404，路径形如：

```
GET /images/W5_LLM_Transformer_applications zh-Hans.pptx/幻灯片1.png → 404
GET /images/W11_LLM_提示词工程.pptx/幻灯片1.png → 404
```

### 根因

双重问题：

**问题 A — 数据库与磁盘不一致**：文件重命名后（加入路径 hash），旧 ChromaDB 条目中的 `image_path` 指向已被删除的旧文件名。`format_chunks_as_context()` 检查 `img_path.exists()` → False → 跳过图片引用。LLM 拿到无图片链接的纯文本上下文，从 `source` 字段（`{filename}.pptx`）自行猜测路径 → 生成 `/images/{filename}.pptx/幻灯片1.png`。

触发路径：
1. 代码将图片命名从 `W5_..._s1_img0.png` 改为 `W5_..._a3f2c1b0_s1_img0.png`（加入路径 hash）
2. 用户重建索引触发 500 错误 → `_delete_file_entries()` 删除了旧图片文件，但 ChromaDB 旧条目未被清理
3. ChromaDB 残留旧条目 → `image_path` 指向不存在的文件 → `format_chunks_as_context()` 跳过

**问题 B — LLM 自行猜测路径**：即使没有图片引用，LLM 看到 source 文件名后会创造性地生成 `{source.pptx}/幻灯片1.png` 路径。

### 修复

| 文件 | 改动 | 解决 |
|------|------|------|
| [`tools/rag_store.py`](tools/rag_store.py) `format_chunks_as_context()` | `image_path` 找不到文件时，尝试用 `image_filename` metadata 作为 fallback 重查 `images/` 目录 | 问题 A — 兼容旧条目文件名 |
| [`tools/rag_store.py`](tools/rag_store.py) `format_chunks_as_context()` | 强化 LLM 指令：**"绝对不要在回答中使用 `幻灯片1.png`、`Slide1.png` 等你猜测的文件名"** | 问题 B — 让 LLM 不再猜测 |
| [`main.py`](main.py) `content_analyst_agent()` | 系统提示新增规则 #6：图片路径必须原样保留，不得猜测 | 问题 B — 全局生效 |
| [`main.py`](main.py) visual 路径 Task | 补充 `![](/images/...)` 原样保留的指令 | 问题 B — visual 路径覆盖 |

**问题 B 持续 — LLM 仍在编造新路径**

第一轮修复（2026-06-01）后 LLM 不再用 `幻灯片1.png`，但转而生成随机哈希文件名：

```
GET /images/ffccdd88087a.png → 404
```

LLM 从"猜常见名字"变成了"凭空创造名字"，指令无法完全阻止。

**第二轮修复 — 答案后处理安全网**

新增 [`_strip_invalid_images()`](main.py#L372-389) 函数，正则扫描每条 LLM 答案：

```python
# 对所有 ![](/images/xxx) 引用: 文件存在? → 保留 : → 移除
```

4 个 return 点全部包裹：

| 路径 | 保护公式 |
|------|---------|
| web | `_strip_invalid_images(str(result)) + metrics_section` |
| visual | 同上 |
| lecture | `_strip_invalid_images(str(result)) + _format_rag_metrics(...)` |
| hybrid | 同上 |

### 验证

重建索引后，ChromaDB 条目与磁盘文件完全一致：

```
旧条目: image_path="images/W5_..._s1_img0.png"  → 文件可能不存在
新条目: image_path="images/W5_..._a3f2c1b0_s1_img0.png" → 文件存在 ✓
```

Fallback 逻辑：旧条目 `image_path` 未命中时，用 `image_filename` 重新匹配 `images/` 目录。

---

## 测试回归

所有 Bug 修复后，测试套件保持 **131/131 全部通过**。

新增的回归测试：
- `test_index_file_single_upload` — 单文件索引
- `test_index_file_rejects_wrong_extension` — 非法扩展名拒绝
- `test_index_web_search_stores_facts` — web→RAG 存储
- `test_index_web_search_skips_empty_facts` — 空 facts 跳过
- `test_index_web_search_dedup_same_query` — 去重
- `test_index_web_search_without_urls` — 默认 URL
- `test_search_messages_finds_match` — 搜索消息
- `test_search_messages_case_insensitive` — 大小写
- `test_search_messages_no_match` — 无匹配
- `test_search_messages_empty_history` — 空历史
- `test_search_messages_has_timestamp` — 时间戳
- `test_search_all_sessions_finds_match` — 跨会话搜索
- `test_search_all_sessions_case_insensitive` — 大小写
- `test_search_all_sessions_no_match` — 无匹配
- `test_search_all_sessions_empty` — 空
- `test_search_all_sessions_has_required_fields` — 字段完整性
- `test_search_requires_query` / `test_search_empty_query` / `test_search_returns_results` / `test_search_with_all_flag` — API 搜索

---

## 第二阶段 Bug 修复

### B001 — logger.debug 缺失 f-string 前缀

**严重度**: 🔴 低 | **状态**: ✅ 已修复

`tools/rag_store.py` 中 14 处 `logger.debug()` 使用了 `{variable}` 语法但缺少 `f` 前缀，运行时输出字面量 `{variable}` 而非变量值。

---

### B002 — `btnReindex` DOM 缺失导致 JS 崩溃

**严重度**: 🔴 致命 | **状态**: ✅ 已修复

`btnReindex` 按钮不在 HTML 中但 JS 引用它 → `null.addEventListener()` TypeError → `setupEventListeners()` 中断 → `loadInitialData()` 不执行 → 页面空白。

**修复**: HTML 添加按钮 + JS `if` 守卫。

---

### B003 — `/api/cache` 500 错误

**严重度**: 🟡 中 | **状态**: ✅ 已修复

`_is_expired()` 被重命名为 `_is_cache_valid()`，但 `/api/cache` 端点仍调用旧名。

---

### B004 — 图片 URL 中 `&` 被解析为查询参数

**严重度**: 🟡 中 | **状态**: ✅ 已修复

`W12_LLM_RAG&Agent.pptx` 中的 `&` 在 URL 中被当作查询参数分隔符 → 404。

**修复**: `_safe_filename()` 替换特殊字符 + `urllib.parse.quote()` + 前端 HTML 属性保护。

---

### B005 — `%%HTML0%%` 占位符未替换

**严重度**: 🔴 致命 | **状态**: ✅ 已修复

斜体正则 `_([^_]+)_` 匹配了 `%%BLOCK_0%%` 中的 `_0_` → `<em>0</em>` → 替换失败。

**修复**: 占位符格式改为无下划线（`%%B0%%` / `%%H0%%`）+ 恢复顺序修正。

---

### B006 — 线程冗余

**严重度**: 🟢 低 | **状态**: ✅ 已修复

`thread.start(); thread.join()` 无并行效果。

---

### B007 — 联网搜索按钮无响应

**严重度**: 🟡 中 | **状态**: ✅ 已修复

`btnToggleWeb` DOM 引用代码通过 `multi_edit` 排队未落地。

---

### B008 — Google Custom Search 403

**严重度**: 🟡 中 | **状态**: 环境配置

Google Cloud 项目未启用 API / API Key 受限 / 未关联结算。

---

### B009 — Agent 编造图片文件名

**严重度**: 🟡 中 | **状态**: ✅ 已修复

Agent 看到 `![](/images/xxx.png)` 格式后自行发明 `transformer_architecture.png`。

**修复**: prompt 增加「不要编造图片文件名」约束。

---

### B010 — `_load_search_cache()` 返回 `None`

**严重度**: 🔴 致命 | **状态**: ✅ 已修复

`cache/search_cache.json` 不存在时返回 `None` → `cache.get(key)` AttributeError → 500。

**修复**: 添加 `return {}`。

---

### B011 — `name "re" is not defined`

**严重度**: 🔴 致命 | **状态**: ✅ 已修复

使用 `re.sub()` 但未 `import re`。

---

### B012 — 加载计时器始终为 0

**严重度**: 🟢 低 | **状态**: ✅ 已修复

`addLoadingMessage()` 和 `startElapsedTimer()` 各自创建 `setInterval`，后者覆盖前者。

**修复**: 统一由 `startElapsedTimer()` 管理。

---

### B013 — `exportConversation()` 重复定义

**严重度**: 🟢 低 | **状态**: ✅ 已修复

函数被定义两次（复制粘贴残留）。

---

### B014 — `DOMContentLoaded` 无错误隔离

**严重度**: 🟡 中 | **状态**: ✅ 已修复

`setupEventListeners()` 抛异常 → `loadInitialData()` 不执行。

**修复**: `try/catch` 包裹 + 确保继续执行。

---

### B015 — `const userLoc` 插入 fetch options 内部

**严重度**: 🔴 致命 | **状态**: ✅ 已修复

`const userLoc = ...` 被错误放在 `fetch({...})` 内部 → SyntaxError。

---

## 性能优化

| # | 优化 | 之前 | 之后 | 节省 |
|---|------|------|------|------|
| P001 | Hierarchical → Sequential | 5 次 LLM 调用/次 | 2 次 LLM 调用/次 | ~12s |
| P002 | Guard 触发范围 | 0.55-0.82 触发 | 0.55-0.70 触发 | 减少 40% Guard 调用 |
| P003 | Prompt 模板精简 | 长篇 backstory | 一句话 | ~50% 输入 token |
| P004 | RAG 上限 + 搜索上限 + max_tokens | 4000+4000+无上限 | 2000+800+2048 | 减半 |

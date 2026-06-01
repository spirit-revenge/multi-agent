# Bug Report — LectureCrewLLM

> 最后更新：2026年5月 | 测试：131/131 全部通过

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

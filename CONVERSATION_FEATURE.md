# 🎯 Conversation History & Follow-up Questions - Usage Guide

## 什么是新功能？

你的系统现在支持**多轮对话**和**追问**功能：
- ✅ 系统记住所有之前的问题和回答
- ✅ 用户可以问追问问题，系统知道上下文
- ✅ 对话历史自动保存到 `conversations/session.json`
- ✅ 随时可以查看对话历史或开始新对话

---

## 使用方式

### 1. 启动系统

```bash
cd /Users/tengyue/Documents/LLM/lecture_crewLLM
conda run -n camel python main.py
```

你会看到：
```
Place your lecture files inside '...'
Checking vector store for updates...
✓ Loaded 5 previous messages from history
Type 'clear' to start a new conversation, or ask a follow-up question.

You: 
```

### 2. 第一个问题

```
You: What is the transformer architecture?
🔄 Processing your question...
[...crew 处理...]
ANSWER FROM CREW
================
[详细的英文答案，引用讲座和网络资源]

✓ Output saved to: output/lecture_output_20260517_140530.md
```

系统自动保存了：
- 你的问题到 `conversations/session.json`
- 助手的回答到 `conversations/session.json`
- 最终答案到 `output/lecture_output_TIMESTAMP.md`

### 3. 追问（Follow-up Question）

```
You: Can you explain the self-attention mechanism in more detail?
🔄 Processing your question...

ANSWER FROM CREW
================
[新答案会引用之前关于 transformer 的讨论，更深入地解释 self-attention]
```

系统会自动：
- 加载之前的对话历史
- 告诉 Agents 用户之前问过什么
- Agents 知道背景，回答更有针对性

### 4. 特殊命令

在 `You: ` 提示符后，你可以输入：

| 命令 | 作用 |
|------|------|
| `exit` 或 `quit` | 退出程序 |
| `clear` | 清除对话历史，开始新对话 |
| `history` | 显示当前对话历史摘要 |
| `cache` | 显示缓存统计和最近的缓存问题 |
| `cache clear` | 清除所有缓存答案 |
| `sessions` | 打开会话选择菜单，切换/新建对话 |
| `session` | 显示当前会话信息 |
| 空行（直接按 Enter） | 使用默认问题（讲座总结） |

例如：
```
You: history
📝 Conversation History:
You: What is the transformer architecture?
Assistant: The transformer is a neural network architecture...

You: Can you explain self-attention?
Assistant: Self-attention is a mechanism that allows...
```

---

## 🚀 缓存功能（Persistent Answer Cache）

### 什么是缓存？

缓存系统自动存储问题和答案，避免重复处理相同问题：

```
第一次问：What is transformer?
  → Crew 处理（需要 API 调用，耗时）
  ✓ 答案保存到 cache/answer_cache.json
  
第二次问：What is transformer?
  → 直接从缓存返回（瞬间）
  🎉 省时省钱，避免重复 API 调用
```

### 缓存工作原理

1. **自动检测重复问题** - 使用问题哈希识别重复
2. **智能匹配** - 对问题进行规范化（小写、去除多余空格）
3. **时间过期** - 默认 30 天后缓存过期（可配置）
4. **自动保存** - 答案得到后自动保存到缓存

### 数据流（带缓存）

```
用户问题
  ↓
检查缓存
  ├─ 命中 → 返回缓存答案（⚡快速）
  └─ 未命中 → 运行 Crew（标准流程）
       ↓
    生成答案
       ↓
    保存到缓存 + 对话历史
       ↓
    返回给用户
```

### 缓存文件格式

文件位置: `cache/answer_cache.json`

```json
{
  "answers": [
    {
      "question": "What is transformer?",
      "answer": "The transformer is a neural network architecture...",
      "timestamp": "2026-05-17T14:05:30.123456",
      "question_hash": "a1b2c3d4e5f6g7h8..."
    },
    {
      "question": "Explain self-attention mechanism",
      "answer": "Self-attention allows...",
      "timestamp": "2026-05-17T14:15:45.654321",
      "question_hash": "b2c3d4e5f6g7h8i9..."
    }
  ]
}
```

### 缓存命令详解

#### 查看缓存统计
```
You: cache
📊 Cache Statistics:
  Total entries: 5
  Valid entries: 5
  Expired entries: 0

📝 Recent cached questions:
  [✓ Valid, 2 days ago] What is the transformer architecture?
  [✓ Valid, 1 day ago] Explain self-attention mechanism
  [✓ Valid, 0 days ago] What is a neural network?
```

#### 清除缓存
```
You: cache clear
✓ Answer cache cleared.
```

### `AnswerCache` 类 API

```python
from tools.answer_cache import AnswerCache

# 创建缓存实例（自动加载现有缓存）
cache = AnswerCache(
    cache_file="cache/answer_cache.json",
    ttl_days=30  # 时间过期设置
)

# 查询缓存
answer = cache.get_answer("What is X?")
if answer:
    print(f"Found in cache: {answer}")

# 保存答案
cache.save_answer(
    question="What is X?",
    answer="X is..."
)

# 统计信息
stats = cache.get_stats()
print(f"Total: {stats['total_entries']}, Valid: {stats['valid_entries']}")

# 清理过期缓存
cache.cleanup_expired()

# 清除所有缓存
cache.clear_cache()

# 显示缓存信息
cache.display_cache()

# 获取有效缓存数量
count = len(cache)
```

### 缓存性能优化

| 场景 | 无缓存 | 有缓存 | 节省 |
|------|-------|-------|------|
| 重复问题 1 次 | 30-60 秒 | < 1 秒 | 99% ⚡ |
| 重复问题 10 次 | 300-600 秒 | 一次 30s + 9 次 < 1s | ~95% |
| 新问题 | 30-60 秒 | 30-60 秒 | 0% |

---

## 架构说明

### `ConversationManager` 类（tools/conversation_manager.py）

```python
# 创建或加载对话
conv_mgr = ConversationManager()

# 添加消息
conv_mgr.add_message("user", "What is X?")
conv_mgr.add_message("assistant", "X is...")

# 获取历史（格式化供 Agent 使用）
context = conv_mgr.get_full_context_for_agent()

# 获取最近 N 条消息
recent = conv_mgr.get_last_n_messages(n=4)

# 保存和加载
conv_mgr.save_session()
conv_mgr.load_or_create_session()

# 清除历史
conv_mgr.clear_session()
```

### 数据流

```
用户输入
  ↓
保存到 conversation_manager
  ↓
加载对话历史上下文
  ↓
创建 tasks，加入上下文 → create_tasks(..., conversation_manager)
  ↓
Agents 接收上下文，知道前面的问题
  ↓
生成答案
  ↓
保存答案到 conversation_manager
  ↓
显示给用户 + 保存到 output/
```

---

## 文件位置

```
lecture_crewLLM/
├── main.py                    # ✅ 已更新，支持多轮对话 + 缓存
├── tools/
│   ├── conversation_manager.py  # ✅ 管理对话历史
│   ├── answer_cache.py          # ✅ 管理答案缓存
│   ├── rag_store.py            # 向量存储 RAG
│   └── local_file_tool.py      # 本地文件读取
├── conversations/
│   └── session.json            # 对话历史保存
├── cache/
│   └── answer_cache.json       # 答案缓存保存
└── output/
    └── lecture_output_*.md     # 每个回答的输出
```

---

## 对话历史格式（conversations/session.json）

```json
{
  "messages": [
    {
      "role": "user",
      "content": "What is the transformer architecture?",
      "timestamp": "2026-05-17T14:05:30.123456"
    },
    {
      "role": "assistant",
      "content": "The transformer is a neural network architecture...",
      "timestamp": "2026-05-17T14:06:45.654321"
    },
    ...
  ]
}
```

---

## 高级用法

### 1. 手动编辑对话历史

你可以直接编辑 `conversations/session.json` 来修改历史。系统会在下次启动时加载。

### 2. 多个独立会话

创建不同的会话文件：

```python
# 为特定主题创建会话
conv_mgr = ConversationManager("conversations/transformer_session.json")
```

### 2.1 启动时选择不同会话

系统现在会在启动时显示一个会话菜单，你可以：
- 选择已有会话继续对话
- 新建一个会话开始新的主题
- 在运行时输入 `sessions` 再次切换会话

会话文件会保存在：
- `conversations/session.json` - 旧的默认会话
- `conversations/sessions/*.json` - 新建的独立会话

### 3. 导出对话

```python
import json

with open("conversations/session.json", "r") as f:
    data = json.load(f)
    
# 导出为 Markdown
with open("conversation_export.md", "w") as f:
    for msg in data["messages"]:
        role = "**You**" if msg["role"] == "user" else "**Assistant**"
        f.write(f"\n{role}: {msg['content']}\n")
```

---

## 示例对话流程

### 场景 1: 缓存 + 追问

```
[第一天]
You: What is deep learning?
🔄 Processing your question (not in cache)...
[Crew 处理 - 耗时 45 秒]
ANSWER FROM CREW
================
Deep learning is...
✓ Cached answer for: What is deep learning?
✓ Output saved to: output/lecture_output_20260517_140530.md

You: What is neural network?
🔄 Processing your question (not in cache)...
[Crew 处理 - 耗时 42 秒]
ANSWER FROM CREW
================
A neural network is...
✓ Cached answer for: What is neural network?

You: Can you explain backpropagation?
🔄 Processing your question (not in cache)...
[Crew 处理 - 耗时 48 秒]
ANSWER FROM CREW
================
Backpropagation is a technique that...

[第二天，重启程序]
✓ Loaded 6 previous messages from history
✓ Loaded 3 cached answers

You: What is deep learning?
⚡ 直接从缓存返回（< 1 秒）
ANSWER FROM CACHE (cached cache)
================
Deep learning is...
✓ Output saved to: output/lecture_output_20260518_090000.md

You: Given the context of deep learning, what are transformers?
🔄 Processing your question (not in cache)...
[系统知道之前问过 "What is deep learning?"]
[Crew 生成答案时会引用上下文]
ANSWER FROM CREW
================
Based on the deep learning foundation, transformers are...
✓ Cached answer for: Given the context of deep learning, what are transformers?
```

### 场景 2: 缓存统计

```
You: cache
📊 Cache Statistics:
  Total entries: 12
  Valid entries: 12
  Expired entries: 0

📝 Recent cached questions:
  [✓ Valid, 0 days ago] What is deep learning?
  [✓ Valid, 0 days ago] What is neural network?
  [✓ Valid, 0 days ago] Can you explain backpropagation?
  [✓ Valid, 1 day ago] What is a reinforcement learning?
  [✓ Valid, 5 days ago] Explain convolutional neural networks
```

### 场景 3: 清空缓存重新开始

```
You: clear
✓ Starting a new conversation.

You: cache
📊 Cache Statistics:
  Total entries: 12
  Valid entries: 12
  Expired entries: 0

You: What is deep learning?
⚡ 从缓存快速返回（保留全局缓存，只清除对话历史）
ANSWER FROM CACHE (cached cache)
```

---

## 示例对话流程（旧版本 - 仅供参考）

---

## 下一步可能的改进

1. ~~**Persistent Cache**~~ ✅ **已实现** - 缓存 LLM 回答，相同问题不重复调用
2. **多会话管理** - UI 界面选择不同的对话
3. **导出功能** - 一键导出为 PDF/Word
4. **对话搜索** - 快速搜索之前问过什么
5. **对话摘要** - 系统自动摘要长对话
6. **并发处理** - 支持多用户同时使用
7. **自适应缓存** - 根据问题相似度智能匹配（不仅是精确匹配）

---

## 故障排除

### Q: 对话历史没有被加载？
A: 检查 `conversations/session.json` 是否存在。如果文件损坏，删除它，系统会创建新的。

### Q: 如何重置所有历史？
A: 
```bash
rm conversations/session.json
```
或在程序中输入 `clear` 命令。

### Q: Agents 如何知道对话历史？
A: 在 `create_tasks` 中，每个 task 的 description 都包含了 `conversation_context`，通过 `conversation_manager.get_full_context_for_agent()` 获取。Agents 在处理任务时会读到这个上下文。

### Q: 缓存的答案来自哪里？
A: 系统自动记住所有之前的 LLM 答案（从缓存显示时会显示 "ANSWER FROM CACHE"）。相同问题会直接返回缓存，避免重复 API 调用。

### Q: 缓存会占用很多空间吗？
A: 不会。每个缓存项只包含问题、答案和时间戳。对于大多数使用场景，缓存文件 < 10MB。

### Q: 如何清除所有缓存？
A:
```bash
rm cache/answer_cache.json
```
或在程序中输入 `cache clear` 命令。

### Q: 缓存如何判断"相同问题"？
A: 系统对问题进行规范化（小写、去除多余空格），然后计算 MD5 哈希值进行比对。所以"What is X?"和"what is x?"被认为是同一个问题。

### Q: 缓存会过期吗？
A: 默认 30 天后过期。过期的缓存会在查询时自动删除。可以在初始化时修改 TTL：
```python
cache = AnswerCache(ttl_days=60)  # 60 天过期
cache = AnswerCache(ttl_days=0)   # 永不过期
```

| 功能 | 状态 | 说明 |
|------|------|------|
| 多轮对话 | ✅ | 支持无限轮对话 |
| 对话历史保存 | ✅ | 自动保存到 JSON |
| 追问功能 | ✅ | Agents 知道上下文 |
| 对话恢复 | ✅ | 重启后自动加载 |
| 多会话管理 | ✅ | 启动时选择/运行时切换 |
| 持久化缓存 | ✅ | **新增** - 避免重复处理 |
| 缓存统计 | ✅ | **新增** - 查看缓存状态 |
| 特殊命令 | ✅ | clear/history/cache/sessions/exit |
| 导出功能 | ⏳ | 可后续添加 |
| Web UI | ✅ | **新增** - 现代化网页界面 |

---

## Web UI（网页界面）

现在支持**完整的网页用户界面**！提供更加友好和专业的使用体验。

### 启动 Web UI

```bash
cd /Users/tengyue/Documents/LLM/lecture_crewLLM
conda run -n camel python web_ui.py
```

浏览器自动打开: **http://localhost:5000**

### 主要特性

✨ **漂亮的聊天界面**
- 响应式设计，支持桌面和移动设备
- 实时消息更新
- 自动滚动到最新消息

💬 **会话管理**
- 创建多个独立的对话
- 快速切换不同的主题讨论
- 每个会话独立保存

📝 **对话历史**
- 查看完整的对话记录
- 一键清空对话（保留缓存）
- 精美的时间线展示

⚡ **智能缓存**
- 缓存答案瞬间返回（< 1ms）
- 查看缓存统计信息
- 轻松管理缓存

### 界面布局

```
┌─────────────────────────────────────────┐
│ 侧边栏                  │  主聊天区域    │
│                         │                │
│ 📚 会话管理             │  💬 聊天消息   │
│ 📝 当前会话信息        │  📝 对话历史   │
│                         │                │
│ ⚡ 缓存统计             │  ✍️ 输入框   │
│ 缓存: 5                 │  [Send Button] │
│ 有效: 5                 │                │
│                         │                │
│ 🎛️ 控制按钮            │                │
│ [Show History]          │                │
│ [Clear Cache]           │                │
│ [Clear Conversation]    │                │
└─────────────────────────────────────────┘
```

### Web UI 与 CLI 的对比

| 功能 | Web UI | CLI |
|------|--------|-----|
| 用户体验 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 会话管理 | UI 菜单 | 菜单选择 |
| 查看历史 | 时间线 | 文本列表 |
| 缓存管理 | 图表+统计 | 文本统计 |
| 响应式设计 | ✅ 适配手机 | ❌ 仅CLI |
| 键盘快捷键 | Shift+Enter | 回车 |
| 实时反馈 | 加载动画 | 文本消息 |

### 快速开始

#### 1. 安装 Flask

```bash
conda run -n camel pip install Flask==3.0.0
```

#### 2. 运行 Web UI

```bash
python web_ui.py
```

#### 3. 打开浏览器

访问: http://localhost:5000

#### 4. 开始提问

在输入框输入问题，按 `Shift + Enter` 发送。

### 常用快捷键

| 快捷键 | 功能 |
|--------|------|
| `Shift + Enter` | 发送消息 |
| `Enter` | 输入框换行 |
| `Ctrl+K` 或 `Cmd+K` | 聚焦输入框 |

### API 接口

Web UI 基于 Flask RESTful API，主要端点：

```
POST   /api/chat              # 发送消息
GET    /api/sessions          # 获取会话列表
POST   /api/sessions          # 创建新会话
POST   /api/sessions/<path>   # 切换会话
GET    /api/history           # 获取对话历史
DELETE /api/history           # 清空对话
GET    /api/cache             # 获取缓存统计
DELETE /api/cache             # 清空缓存
GET    /api/status            # 获取系统状态
```

### 文件结构

新增的 Web UI 相关文件：

```
lecture_crewLLM/
├── web_ui.py                 # Flask 主应用
├── templates/
│   └── index.html            # 网页模板
├── static/
│   ├── style.css             # 样式表
│   └── script.js             # 客户端逻辑
└── WEB_UI_GUIDE.md          # Web UI 详细指南
```

### 浏览器兼容性

- ✅ Chrome/Chromium (最新版)
- ✅ Firefox (最新版)
- ✅ Safari (最新版)
- ✅ Edge (最新版)
- ✅ 移动浏览器

### 故障排除

**Flask not found**
```bash
conda run -n camel pip install Flask==3.0.0
```

**端口被占用**
```bash
# 查看占用 5000 端口的进程
lsof -i :5000
# 杀死进程
kill -9 <PID>
```

**无法连接**
- 检查 Flask 服务器是否仍在运行
- 检查浏览器是否访问 http://localhost:5000
- 尝试刷新页面 (Ctrl+R)

### 详细指南

更多信息请查看：**[WEB_UI_GUIDE.md](WEB_UI_GUIDE.md)**

---

祝你使用愉快！🚀

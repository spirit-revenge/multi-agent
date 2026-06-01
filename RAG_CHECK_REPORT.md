# RAG 设计检查报告

> 检查日期：2026-06-01 | 131 测试全部通过

---

## 1. Router 是否把 "架构图" 路由到 Image Agent

**状态**: ❌ 缺失

当前 Router 只输出 4 种意图：`lecture` / `web` / `hybrid` / `unknown`。

```python
# main.py:196
backstory="...只输出一个词：lecture（仅讲座）、web（仅网络）、hybrid（两者都需要）、unknown（不确定）。"
```

没有 `image` 意图。用户问"架构图是什么样的"时，Router 只会分类为 `lecture`，然后用文本 RAG 检索——不会特别检索 `type="image"` 的条目。

**建议**: 规则路由器增加关键词触发（"架构图"、"图片"、"图表"、"示意图"），Router 新增 `visual` 意图，走 `retrieve(content_type="image")` 专用路径。

---

## 2. Planner 是否跳过 RAG Tool

**状态**: ✅ 部分实现

- `intent == "web"` 时完全跳过 RAG（只调 Tavily） ✓
- `intent == "lecture"` 且 RAG 返回空结果、"cannot answer" 场景有处理 ✓
- 但 `intent == "unknown"` 仍然走 RAG → 无结果时仍可能浪费一次检索

```python
# main.py:395
if intent in ("lecture", "hybrid", "unknown"):
    raw_entries = vector_store.retrieve(user_question, k=RAG_K)
```

**建议**: `unknown` 意图先走快速关键词匹配确认是否有相关内容，无相关内容时跳过 RAG。

---

## 3. Query Rewrite 前后内容

**状态**: ✅ 已实现

```python
# tools/rag_store.py:55-70
def rewrite_query(query: str) -> str:
    """Expand abbreviations and add Chinese equivalents."""
    for abbrev, expansion in QUERY_REWRITE_MAP.items():
        if abbrev in lower:
            full_terms = [t for t in expansion.lower().split()[:4] if t != abbrev]
            if not any(term in lower for term in full_terms):
                query = query + f" ({expansion})"
                break
    return query
```

示例变换:
| 输入 | 输出 |
|------|------|
| `rag是什么` | `rag是什么 (Retrieval Augmented Generation 检索增强生成)` |
| `介绍一下bert` | `介绍一下bert (BERT Bidirectional Encoder 双向编码器)` |
| `Transformer注意力` | 不展开（"注意力"已在 expansion 中命中） |
| `今天天气` | 不展开（不匹配任何缩写） |

**问题**: 仅展开第一个匹配的缩写（`break`），不支持组合查询如"rag和transformer的关系"。且展开词用空格拼接到原 query 末尾，格式依赖模型理解。

---

## 4. Query Expansion / MultiQueryRetriever

**状态**: ❌ 缺失

当前无 MultiQuery 或子查询生成。只有一个 query 走一次 `collection.query()`。

```python
# tools/rag_store.py:691
results = self.collection.query(
    query_texts=[final_query],   # 单查询
    n_results=hybrid_k,
    where=where,
)
```

**建议**: 增加 MultiQuery 策略：
1. LLM 生成 2-3 个查询变体
2. 每个变体独立检索
3. 融合去重后返回 Top-K

---

## 5. Metadata Filter

**状态**: ✅ 已实现但未充分利用

```python
# tools/rag_store.py:654-687
def retrieve(self, query, k=5, content_type=None):
    where = None
    if content_type:
        where = {"type": content_type}   # "text" | "image" | "table" | "web"
    results = self.collection.query(query_texts=[final_query], n_results=hybrid_k, where=where)
```

`retrieve()` 支持 `content_type` 参数，但 **在 `run_crew()` 中从未使用**——总是 `content_type=None`（返回所有类型）。

```python
# main.py:400 — 从未传 content_type
raw_entries = vector_store.retrieve(user_question, k=RAG_K)
```

**建议**: 用户查询含"图片"、"图表"、"表格"等词时，传入 `content_type="image"` 或 `content_type="table"` 做定向检索。

---

## 6. Similarity Threshold

**状态**: ✅ 已实现（三档门控）

```python
# main.py:418-432
if max_sim >= 0.82:      # 高置信度 → 跳过 Guard，直接使用
elif max_sim <= 0.45:    # 低置信度 → 跳过，无结果
else:                     # 0.45~0.82 → 触发 Guard LLM 语义验证
```

| 阈值 | 决策 | LLM 调用 |
|------|------|---------|
| ≥ 0.82 | 高置信度，直接使用 | 0 |
| 0.45 ~ 0.82 | 边界案例，Guard 验证 | 1（Guard） |
| ≤ 0.45 | 低置信度，跳过 | 0 |

关键词词面匹配 Boost：查询展开词在文档中命中时，相似度自动抬到 0.55（确保不会被 ≤0.45 误杀）。

---

## 7. Top-K 实际相似度分数

**状态**: ✅ 已记录并展示（新增功能）

修复后每条回答末尾追加检索质量指标：

```markdown
## 📊 RAG 检索质量指标

| 指标 | 值 |
|------|-----|
| 检索块数 (k) | 3 |
| 最高相似度 | 0.7234 |
| 平均相似度 | 0.5612 |
| 各块相似度 | 0.7234 → 0.5601 → 0.3998 |
| 门控决策 | 0.45~0.82 边界案例（触发 Guard 验证） |
| Guard 验证结果 | **RELEVANT** |
| 有效块数 | 3 / 3 |
| 伪精确率 (Precision@3) | 100.00% |
| 伪召回率 (Recall@3) | 100.00% |
```

相似度计算：`similarity = 0.7 × embedding_cosine + 0.3 × BM25_normalized`

---

## 8. HyDE 是否开启

**状态**: ❌ 缺失

HyDE (Hypothetical Document Embeddings) 未实现。当前检索直接使用用户问题的 embedding，没有先生成假设答案再检索的步骤。

**说明**: HyDE 适合"用户问题很短、但期望答案很长"的场景（如"什么是 Transformer？"）。但对于本项目的问答场景（问题本就不短 + 查询展开已做），HyDE 收益有限，且会增加一次 LLM 调用（~2s）。

**建议**: 暂不实施。如后续发现短查询漏召回率高，可作为一种补充策略。

---

## 9. OCR 图片内容是否入库

**状态**: ❌ 缺失

项目不使用 OCR（Tesseract / EasyOCR / PaddleOCR）。图片处理方式是 **BLIP 描述**：

```python
# tools/image_captioner.py:37-58
def describe_image(image, max_length=50):
    captioner = _get_captioner()       # BLIP
    result = captioner(image, text='', max_new_tokens=max_length)
    caption = result[0]['generated_text'].strip()
    return f"[图片描述] {caption}"     # "a diagram of a neural network"
```

**BLIP vs OCR 区别**:

| 方式 | 输出 | 适合 |
|------|------|------|
| BLIP | 语义描述（"a flowchart showing..."） | 照片、示意图、自然场景 |
| OCR | 文字提取（图片中嵌入的文字内容） | 截图、扫描文档、含文字的图表 |

**问题**: 讲座 PPTX/PDF 中的架构图、流程图通常包含大量文字（如"Transformer Encoder"、"Self-Attention"），BLIP 只描述图的视觉内容，不提取图中文字。

**建议**: 对图片额外增加 OCR 层，将提取的文字追加到 BLIP 描述中：
```python
ocr_text = pytesseract.image_to_string(image, lang='chi_sim+eng')
full_description = f"[BLIP] {blip_caption} [OCR] {ocr_text}"
```

---

## 10. Query Intent Normalization

**状态**: ❌ 缺失

当前意图路由只做分类（lecture/web/hybrid/unknown），没有做意图归一化。同一语义的不同表述会产生不同的检索行为：

| 用户输入 | Router 分类 | 检索行为 |
|----------|------------|---------|
| `Transformer架构图` | lecture | RAG 全部类型 |
| `给我看Transformer的架构` | lecture | RAG 全部类型 |
| `有没有Transformer的示意图` | lecture | RAG 全部类型 |
| `Transformer长什么样` | lecture | RAG 全部类型 |

前三者都应触发 `visual` 意图（检索 image 类型），但当前都被分到 `lecture`。

**建议**: 在规则路由器中增加意图归一化层：

```python
VISUAL_KEYWORDS = ["架构图", "示意图", "图表", "图片", "流程图", "长什么样", "图示"]
DOC_KEYWORDS   = ["文档", "课件", "讲义", "PPT", "第几章", "哪一页"]

def normalize_intent(query: str) -> str:
    for kw in VISUAL_KEYWORDS:
        if kw in query:
            return "visual"    # → retrieve(content_type="image")
    for kw in DOC_KEYWORDS:
        if kw in query:
            return "lecture"   # → retrieve(content_type="text")
    return rule_router(query)  # → 原有 web / None
```

---

## 总结

| # | 检查项 | 状态 | 优先级 |
|---|--------|------|--------|
| 1 | Router 路由 "架构图" → Image | ❌ 缺失 | 🔴 高 |
| 2 | Planner 跳过 RAG | ✅ 部分 | 🟡 中 |
| 3 | Query Rewrite 展开缩写 | ✅ 已实现 | — |
| 4 | MultiQuery Retriever | ❌ 缺失 | 🟢 低 |
| 5 | Metadata Filter 按类型检索 | ✅ API存在但未调用 | 🔴 高 |
| 6 | Similarity Threshold 三档门控 | ✅ 已实现 | — |
| 7 | Top-K 相似度分数展示 | ✅ 已实现 | — |
| 8 | HyDE 假设文档嵌入 | ❌ 缺失 | 🟢 低 |
| 9 | OCR 图片文字入库 | ❌ 缺失 | 🔴 高 |
| 10 | Query Intent Normalization | ❌ 缺失 | 🔴 高 |

**建议优先实施**: #1（visual 意图路由）+ #5（metadata filter 调用）+ #9（OCR）+ #10（意图归一化），四项联动可显著提升图片/图表类查询的召回质量。

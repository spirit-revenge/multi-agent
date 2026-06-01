import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai import LLM
from tools.rag_store import LectureVectorStore
from tools.conversation_manager import ConversationManager
from tools.answer_cache import AnswerCache
from tools.session_manager import ConversationSessionManager, SessionInfo
from tools.status_tracker import status_tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 1. Configure the DeepSeek Model ---
load_dotenv()
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

def _build_llm():
    return LLM(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        api_key=deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.7,
        max_tokens=4000
    )

deepseek_llm = _build_llm()

# Lightweight LLM for routing (cheap, fast)
def _build_router_llm():
    return LLM(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        api_key=deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.1,
        max_tokens=100
    )

router_llm = _build_router_llm()

# Initialize persistent vector store
vector_store = LectureVectorStore(persist_directory="chroma_db", collection_name="lectures_chinese")


# --- 1.5 Rule-Based Router (fast path, no LLM) ---

VISUAL_KEYWORDS = [
    "架构图", "示意图", "图表", "图片", "流程图",
    "长什么样", "图示", "图解", "框图", "结构图",
    "有什么图", "看图", "图中", "图片描述", "展示图",
]

WEB_KEYWORDS = [
    "天气", "新闻", "股价", "股票", "汇率", "地震",
    "今天", "最新", "刚刚", "当前", "实时",
    "热搜", "头条", "预报", "预警",
]

def rule_router(question: str) -> str | None:
    """Fast keyword-based intent normalization. Returns None if unsure.

    Priority: visual > web.  Visual queries need image-type retrieval;
    web queries skip RAG entirely and go to Tavily.
    """
    q = question.lower().strip()

    # Visual intent — user is asking for images / diagrams / charts
    for kw in VISUAL_KEYWORDS:
        if kw in q:
            return "visual"

    # Web intent — time-sensitive or real-world information
    for kw in WEB_KEYWORDS:
        if kw in q:
            return "web"

    return None


# --- 1.6 Direct Search (no LLM Agent needed) ---

# --- 1.7 Search Cache (1h TTL, avoids redundant Tavily API calls) ---

import hashlib as _hashlib
import json as _json
import re
import time as _time

_SEARCH_CACHE_FILE = Path("cache/search_cache.json")
_SEARCH_CACHE_TTL = 3600  # 1 hour


def _load_search_cache() -> dict:
    try:
        if _SEARCH_CACHE_FILE.exists():
            return _json.loads(_SEARCH_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}
    return {}


def _save_search_cache(cache: dict):
    try:
        _SEARCH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Trim to 200 entries max
        if len(cache) > 200:
            keys = sorted(cache, key=lambda k: cache[k]["ts"])[-200:]
            cache = {k: cache[k] for k in keys}
        _SEARCH_CACHE_FILE.write_text(
            _json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _search_cache_key(query: str) -> str:
    q = query.lower().strip()
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    tokens = sorted(q.split())
    return _hashlib.md5((" ".join(tokens)).encode()).hexdigest()


def _get_cached_search(query: str) -> str | None:
    cache = _load_search_cache()
    key = _search_cache_key(query)
    entry = cache.get(key)
    if entry and (_time.time() - entry["ts"]) < _SEARCH_CACHE_TTL:
        logger.debug("Search cache hit: %s", query[:40])
        return entry["result"]
    return None


def _set_cached_search(query: str, result: str):
    cache = _load_search_cache()
    key = _search_cache_key(query)
    cache[key] = {"result": result, "ts": _time.time()}
    _save_search_cache(cache)


def tavily_direct_search(query: str) -> str:
    """Call Tavily API directly — saves 1 LLM call vs using Search Agent.

    Checks 1h cache first. Returns compact JSON string for prompt injection.
    """
    # Check cache
    cached = _get_cached_search(query)
    if cached:
        return cached

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return '{"facts":[],"urls":[]}'

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=True,
        )
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return '{"facts":[],"urls":[]}'

    results = response.get("results", [])
    answer = response.get("answer")
    facts = []
    if answer:
        facts.append(f"[摘要] {answer[:200]}")
    for r in results:
        content = r.get("content", "")[:150]
        if content:
            facts.append(content)
    urls = [r.get("url", "") for r in results if r.get("url")]

    result = _json.dumps({"facts": facts, "urls": urls}, ensure_ascii=False)
    _set_cached_search(query, result)
    return result


# --- 2. Define Agents ---

def content_analyst_agent():
    """Agent that synthesizes lecture content with web research into a polished Chinese answer."""
    return Agent(
        role="讲座分析师",
        goal="分析讲座内容与网络搜索结果，生成结构清晰、易懂的中文 Markdown 回答。",
        backstory="""你是一位经验丰富的讲师，善于用简单的方式解释复杂概念。

规则（始终遵守）：
1. 讲座内容是主要信息来源，必须仔细阅读。
2. 如果搜索结果包含 "Error:" 等错误信息，忽略它们，仅使用讲座内容。
3. 以 **中文 Markdown** 格式输出，使用标题和列表组织内容。
4. 标注来源——讲座内容标注文件名，网络信息标注 URL。
5. 如果讲座内容不足以回答问题，请如实说明。
6. ⚠️ 图片规则：如果检索内容中已经附带了 `![](/images/...)` 图片链接，必须**原样保留**在回答中。
   **绝对不要自己猜测图片路径**，比如 `幻灯片1.png`、`Slide1.png`、`图片1.png` 等都是错误的。
   只能复制使用已有的 `![](/images/具体文件名.png)` 格式。""",
        llm=deepseek_llm,
        verbose=False,
        allow_delegation=False,
    )


def router_agent():
    """Agent that classifies user intent into: visual / lecture / web / hybrid / unknown."""
    return Agent(
        role="意图路由器",
        goal="判断用户问题是关于讲座内容、实时信息、图片图表、还是组合需求。",
        backstory="你擅长快速识别用户意图，只输出一个词：visual（图片/图表相关）、lecture（仅讲座）、web（仅网络）、hybrid（两者都需要）、unknown（不确定）。",
        llm=router_llm,
        verbose=False,
        allow_delegation=False,
    )




# --- 3.5 Guard Agent (LLM-based relevance gate) ---

def guard_agent():
    """Guard Agent: checks if the user's question is genuinely related to lecture content.

    Unlike a simple keyword-matcher, the Guard Agent distinguishes between:
    - Genuine relevance: question and content share the same conceptual domain
    - Keyword overlap: similar words but different meaning
      (e.g. "天气温度" ≠ "模型温度缩放", "吃饭" ≠ "Tokenizer 分词")

    Returns RELEVANT only when the lecture content can substantively help answer.
    """
    return Agent(
        role="知识边界守卫",
        goal=(
            "严格判断检索到的讲座内容是否与用户问题属于同一知识领域。"
            "区分真正的语义相关和表面的关键词重叠。"
        ),
        backstory=(
            "你是一名严谨的学术守门人。你的职责是防止系统用不相关的讲座内容来"
            "回答与课程无关的问题。你擅长识别：同一个词在不同语境下的含义差异"
            "（如物理温度 vs 模型温度）、通用问题 vs 学术问题、以及讲座知识"
            "的边界。当内容不相关时，你毫不犹豫地输出 IRRELEVANT。"
        ),
        llm=router_llm,
        verbose=False,
        allow_delegation=False,
    )


def grounding_check(user_question: str, rag_context: str) -> str:
    """Use Guard Agent to verify RAG context relevance.

    The guard checks for genuine semantic relevance, not just keyword overlap.
    For example, asking about weather ("今天天气") should NOT match lecture
    content about "temperature scaling" even though both mention "温度".

    Returns:
        - Filtered context string (if RELEVANT)
        - "IRRELEVANT" (if nothing is relevant)
        - "" (if no context)
    """
    if not rag_context:
        return ""

    import re
    chunks = re.split(r'\n\[\d+\]', rag_context)
    content_chunks = [c.strip() for c in chunks if c.strip() and "以下是与问题" not in c]

    if not content_chunks:
        return ""

    sample = "\n\n".join(content_chunks[:3])
    if len(sample) > 2000:
        sample = sample[:2000] + "..."

    guard = guard_agent()
    task = Task(
        description=f"""你是一名知识边界守卫。请判断以下讲座内容是否与用户问题属于同一知识领域、能否实质性地帮助回答该问题。

⚠️ 关键原则：区分"语义相关"和"关键词重叠"——
- "今天天气怎么样" vs 讲座中"模型温度缩放（temperature scaling）" → IRRELEVANT（虽然都有"温度"，但一个是气候，一个是 ML 技术）
- "什么是 Transformer" vs 讲座中"Transformer 架构详解" → RELEVANT
- "推荐一家餐厅" vs 讲座中"推荐系统的协同过滤" → IRRELEVANT（虽然都有"推荐"，但语境完全不同）

用户问题：{user_question}

检索到的讲座内容：
{sample}

请判断：这些讲座内容能实质性地帮助回答用户问题吗？
只输出一个词：RELEVANT 或 IRRELEVANT""",
        expected_output="RELEVANT 或 IRRELEVANT",
        agent=guard,
    )
    crew = Crew(agents=[guard], tasks=[task], process=Process.sequential, verbose=False)
    result = str(crew.kickoff()).strip().upper()

    logger.info("Guard check: %s → %s", user_question[:40], result)

    if "IRRELEVANT" in result:
        return "IRRELEVANT"

    return rag_context


# --- 3.8 RAG Metrics ---

def _format_rag_metrics(metrics: dict) -> str:
    """Build a Markdown summary of RAG retrieval quality metrics."""
    if not metrics or metrics.get("retrieved_count", 0) == 0:
        return ""

    lines = [
        "",
        "---",
        "",
        "## 📊 RAG 检索质量指标",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 检索块数 (k) | {metrics['retrieved_count']} |",
        f"| 最高相似度 | {metrics['max_similarity']:.4f} |",
        f"| 平均相似度 | {metrics['mean_similarity']:.4f} |",
    ]

    # Show all similarity scores
    scores_str = " → ".join(f"{s:.4f}" for s in metrics.get("similarity_scores", []))
    lines.append(f"| 各块相似度 | {scores_str} |")

    # Gate decision
    gate = metrics.get("gate_decision", "unknown")
    gate_label = {
        "high": "≥0.82 高置信度（跳过 Guard，直接使用）",
        "low": "≤0.45 低置信度（跳过，无结果）",
        "guard": "0.45~0.82 边界案例（触发 Guard 验证）",
    }.get(gate, gate)
    lines.append(f"| 门控决策 | {gate_label} |")

    if gate == "guard":
        guard_verdict = metrics.get("guard_verdict", "N/A")
        lines.append(f"| Guard 验证结果 | **{guard_verdict}** |")

    # Precision / Recall (pseudo, based on gate)
    effective = metrics.get("effective_count", 0)
    retrieved = metrics["retrieved_count"]
    pseudo_precision = effective / retrieved if retrieved > 0 else 0
    pseudo_recall = effective / 3  # k=3 fixed

    lines.extend([
        f"| 有效块数 | {effective} / {retrieved} |",
        f"| 伪精确率 (Precision@{retrieved}) | {pseudo_precision:.2%}（通过门控的块 / 检索到的块） |",
        f"| 伪召回率 (Recall@3) | {pseudo_recall:.2%}（通过门控的块 / 3） |",
        "",
        "*注：精确率和召回率为近似值。门控决策基于相似度阈值和 Guard LLM 判定。*",
        "",
    ])

    return "\n".join(lines)


# --- 3.9 Answer Post-Processing — strip hallucinated image references ---

import re as _image_re

_VALID_IMAGE_DIR = Path("images").resolve()
from urllib.parse import unquote as _url_unquote


def _strip_invalid_images(answer: str) -> str:
    """Remove any `![](/images/...)` references where the file doesn't exist.

    The LLM sometimes hallucinates image paths (e.g. ``幻灯片1.png``,
    ``ffccdd88087a.png``).  This function checks every image reference and
    drops those that point to nonexistent files.
    """
    kept = 0
    stripped = 0

    def _check(m):
        nonlocal kept, stripped
        full_path = m.group(0)
        fname = _url_unquote(m.group(2))
        if (_VALID_IMAGE_DIR / fname).exists():
            kept += 1
            return full_path
        stripped += 1
        logger.info("STRIP invalid image: %s", full_path[:120])
        return ""

    result = _image_re.sub(r'!\[([^\]]*)\]\(/images/([^)]+)\)', _check, answer)
    if kept + stripped > 0:
        logger.info("_strip_invalid_images: kept=%d stripped=%d", kept, stripped)
    return result


def _extract_valid_images(text: str) -> str:
    """Extract all valid ![](/images/...) references from a text block."""
    refs = []
    seen = set()
    for m in _image_re.finditer(r'!\[([^\]]*)\]\(/images/([^)]+)\)', text):
        fname = _url_unquote(m.group(2))
        if (_VALID_IMAGE_DIR / fname).exists() and fname not in seen:
            seen.add(fname)
            refs.append(m.group(0))
    return "\n\n".join(refs)


def _finalize_answer(raw_answer: str, rag_context: str) -> str:
    """Clean hallucinated image refs, then re-append any valid ones from RAG."""
    cleaned = _strip_invalid_images(raw_answer)
    valid_images = _extract_valid_images(rag_context or "")
    if valid_images:
        cleaned = cleaned.rstrip() + "\n\n---\n\n**相关图片：**\n\n" + valid_images
    return cleaned


# --- 4. Run Crew ---

def run_crew(folder_path="knowledge", user_question=None, conversation_manager=None,
             task_id=None, use_web_search=True):
    """
    Run agents with intent routing + grounding check pipeline.
    Steps:
      1. Router: classify intent (lecture / web / hybrid / unknown)
      2. RAG retrieval + Grounding Check (filter low-quality results)
      3. Execute appropriate pipeline based on intent + web search setting
    """
    analyst = content_analyst_agent()

    # ---- Step 1: Router ----
    if task_id:
        status_tracker.update(task_id, "routing", "正在分析问题意图...")

    # Rule-based pre-check: fast path for obvious web queries
    intent = rule_router(user_question)
    if intent:
        logger.info("Rule router: %s → %s", user_question[:40], intent)
    else:
        # Fall back to LLM router for ambiguous queries
        router = router_agent()
        route_task = Task(
            description=f"""判断以下用户问题属于哪个类别，只输出一个词：

类别说明：
- visual：关于图片、架构图、示意图、图表、流程图等视觉内容的问题
- lecture：关于讲座内容、AI/技术概念、课程知识的问题
- web：关于实时信息、新闻、天气、最新事件的问题
- hybrid：需要同时参考讲座知识和最新信息的问题
- unknown：无法确定的问题

用户问题：{user_question}

输出（只输出一个类别词）：""",
            expected_output="visual 或 lecture 或 web 或 hybrid 或 unknown",
            agent=router,
        )
        route_crew = Crew(agents=[router], tasks=[route_task], process=Process.sequential, verbose=False)
        intent = str(route_crew.kickoff()).strip().lower()
        logger.info("LLM router: %s → %s", user_question[:40], intent)

    # ---- Step 2: RAG Retrieval (lecture / hybrid routes) ----
    RAG_K = 3               # reduce from 5 to 3 → fewer tokens
    MAX_RAG_CHARS = 2000    # hard character limit (was 4000 — 3 chunks × ~660 chars is plenty)

    rag_context = ""
    rag_metrics = None  # capture retrieval quality metrics
    if intent in ("lecture", "hybrid", "unknown", "visual"):
        if task_id:
            status_tracker.update(task_id, "rag", "正在检索讲座知识库...")

        # Visual intent → retrieve image-type entries only (BLIP descriptions + OCR)
        if intent == "visual":
            content_type = "image"
        else:
            content_type = None
        try:
            raw_entries = vector_store.retrieve(user_question, k=RAG_K, content_type=content_type)
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            raw_entries = []

        # When web search is OFF, filter out type="web" entries so the LLM
        # doesn't hallucinate "（图片来源：网络搜索结果）" from stale web data.
        if not use_web_search and raw_entries:
            raw_entries = [e for e in raw_entries if e.get("type") != "web"]
            logger.info("Filtered web entries (web search OFF): %d remaining", len(raw_entries))

        # Build base metrics from retrieval results
        if raw_entries:
            sims = [e["similarity"] for e in raw_entries]
            rag_metrics = {
                "retrieved_count": len(raw_entries),
                "similarity_scores": sims,
                "max_similarity": max(sims),
                "mean_similarity": sum(sims) / len(sims),
            }

            max_sim = max(sims)

            # Visual intent: image entries have naturally low similarity
            # (BLIP descriptions are generic English).  Skip the gate.
            if intent == "visual":
                rag_context = vector_store.format_chunks_as_context(raw_entries)
                rag_metrics["gate_decision"] = "visual_skip"
                rag_metrics["effective_count"] = len(raw_entries)
            elif max_sim >= 0.82:
                rag_context = vector_store.format_chunks_as_context(raw_entries)
                rag_metrics["gate_decision"] = "high"
                rag_metrics["effective_count"] = len(raw_entries)
            elif max_sim <= 0.45:
                rag_context = ""
                rag_metrics["gate_decision"] = "low"
                rag_metrics["effective_count"] = 0
            else:
                rag_metrics["gate_decision"] = "guard"
                raw_rag = vector_store.format_chunks_as_context(raw_entries)
                rag_result = grounding_check(user_question, raw_rag)

                rag_metrics["guard_verdict"] = "RELEVANT" if rag_result != "IRRELEVANT" else "IRRELEVANT"
                if rag_result == "IRRELEVANT":
                    rag_context = ""
                    rag_metrics["effective_count"] = 0
                else:
                    rag_context = rag_result
                    rag_metrics["effective_count"] = len(raw_entries)
        else:
            rag_context = ""
            rag_metrics = {"retrieved_count": 0, "similarity_scores": [], "max_similarity": 0, "mean_similarity": 0, "gate_decision": "none", "effective_count": 0}

        # Hard token cap
        if rag_context and len(rag_context) > MAX_RAG_CHARS:
            rag_context = rag_context[:MAX_RAG_CHARS] + "\n\n[内容已截断]"

        # ---- Step 2b: Always fetch image entries alongside text results ----
        if intent in ("lecture", "hybrid", "unknown"):
            try:
                img_entries = vector_store.retrieve(user_question, k=2, content_type="image")
                if img_entries:
                    img_context = vector_store.format_chunks_as_context(img_entries)
                    if img_context:
                        img_refs = img_context.count('![](/images/')
                        logger.info(
                            "Step2b image fallback: %d entries, %d image refs in context",
                            len(img_entries), img_refs,
                        )
                        if rag_context:
                            rag_context += "\n\n--- 以下为相关图片内容 ---\n\n" + img_context
                        else:
                            rag_context = "以下为相关图片内容：\n\n" + img_context
            except Exception as e:
                logger.warning("Step2b image fallback failed: %s", e)
                pass

    # ---- Step 3: Route execution ----

    # Case A: intent is "web" (no RAG needed) — direct search, no Search Agent
    if intent == "web" and use_web_search:
        if task_id:
            status_tracker.update(task_id, "searching", "正在搜索网络资源...")

        search_context = tavily_direct_search(user_question)

        # Index web search results into RAG for future queries
        try:
            import json as _json
            parsed = _json.loads(search_context)
            facts = parsed.get("facts", [])
            urls = parsed.get("urls", [])
            if facts:
                vector_store.index_web_search(user_question, facts, urls)
        except Exception:
            pass

        if task_id:
            status_tracker.update(task_id, "generating", "正在生成答案...")

        task_answer = Task(
            description=f"""用户问题：{user_question}

--- 网络搜索结果 ---
{search_context}""",
            expected_output="中文 Markdown 回答。",
            agent=analyst,
        )
        crew = Crew(agents=[analyst], tasks=[task_answer],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        if task_id:
            status_tracker.update(task_id, "complete", "答案已生成！")
        # Web-only query: minimal RAG metrics
        metrics_section = _format_rag_metrics(rag_metrics) if rag_metrics else ""
        return _finalize_answer(str(result), rag_context) + metrics_section

    # Case Visual: image/diagram/chart queries — use image-type RAG results only
    if intent == "visual":
        if task_id:
            status_tracker.update(task_id, "generating", "正在根据图片内容生成答案...")

        if not rag_context:
            # No matching images found — fall back to general text RAG
            try:
                raw_entries = vector_store.retrieve(user_question, k=RAG_K)
                rag_context = vector_store.format_chunks_as_context(raw_entries) if raw_entries else ""
            except Exception:
                rag_context = ""

            if not rag_context:
                if task_id:
                    status_tracker.update(task_id, "complete", "无法回答")
                return None

        conv_ctx = conversation_manager.get_summary_context() if conversation_manager and len(conversation_manager) > 0 else ""

        task_answer = Task(
            description=f"""用户问题：{user_question}

{conv_ctx}

用户想了解讲座中的图片、架构图或图表内容。以下是检索到的相关内容：

--- 图片内容（RAG 检索）---
{rag_context}

请根据以上图片描述和内容回答用户问题。如果含有 `![](/images/...)` 图片引用，**必须原样保留在回答中**，不要自己猜测或修改图片路径。""",
            expected_output="中文 Markdown 回答。",
            agent=analyst,
        )
        crew = Crew(agents=[analyst], tasks=[task_answer],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        if task_id:
            status_tracker.update(task_id, "complete", "答案已生成！")
        metrics_section = _format_rag_metrics(rag_metrics) if rag_metrics else ""
        return _finalize_answer(str(result), rag_context) + metrics_section

    # Case B: intent is "lecture" or web search is OFF
    if intent == "lecture" or not use_web_search:
        # If web search is OFF and RAG is empty → cannot answer
        if not use_web_search and not rag_context:
            if task_id:
                status_tracker.update(task_id, "complete", "无法回答")
            return None  # signal: cannot answer

        # If web search is ON but RAG is empty → fall through to web-only search (Case C)
        if not rag_context and use_web_search:
            pass  # will fall through to Case C below

        # If RAG context exists → lecture-only answer
        if rag_context:
            if task_id:
                status_tracker.update(task_id, "generating", "正在根据讲座内容生成答案...")

            conv_ctx = conversation_manager.get_summary_context() if conversation_manager and len(conversation_manager) > 0 else ""

            task_answer = Task(
                description=f"""用户问题：{user_question}

{conv_ctx}

--- 讲座内容（RAG 检索）---
{rag_context}""",
                expected_output="中文 Markdown 回答。",
                agent=analyst,
            )

            crew = Crew(agents=[analyst], tasks=[task_answer],
                        process=Process.sequential, verbose=False)
            result = crew.kickoff()
            if task_id:
                status_tracker.update(task_id, "complete", "答案已生成！")
            return _finalize_answer(str(result), rag_context) + _format_rag_metrics(rag_metrics)

    # Case C: hybrid or unknown + web search ON → RAG + direct search, no Search Agent
    conv_ctx = conversation_manager.get_summary_context() if conversation_manager and len(conversation_manager) > 0 else ""

    if task_id:
        status_tracker.update(task_id, "searching", "正在搜索网络资源...")

    search_context = tavily_direct_search(user_question)

    # Index web search results into RAG for future queries
    try:
        import json as _json
        parsed = _json.loads(search_context)
        facts = parsed.get("facts", [])
        urls_list = parsed.get("urls", [])
        if facts:
            vector_store.index_web_search(user_question, facts, urls_list)
    except Exception:
        pass

    rag_display = rag_context if rag_context else "向量库中未找到相关的讲座内容。"

    if task_id:
        status_tracker.update(task_id, "generating", "正在综合生成答案...")

    task_answer = Task(
        description=f"""用户问题：{user_question}

{conv_ctx}

--- 讲座内容（RAG 检索）---
{rag_display}

--- 网络搜索结果 ---
{search_context}""",
        expected_output="中文 Markdown 回答。",
        agent=analyst,
    )

    crew = Crew(
        agents=[analyst],
        tasks=[task_answer],
        process=Process.sequential,
        verbose=False,
    )

    if task_id:
        status_tracker.update(task_id, "generating", "正在综合生成答案...")

    result = crew.kickoff()

    if task_id:
        status_tracker.update(task_id, "complete", "答案已生成！")

    return _finalize_answer(str(result), rag_context) + _format_rag_metrics(rag_metrics)


# --- 5. CLI helpers (shared with web_ui) ---

def print_session_summary(conversation_manager, session_label: str):
    logger.info("Current session: %s (%d messages)", session_label, len(conversation_manager))


def format_session_info(session: SessionInfo, index: int) -> str:
    legacy_tag = " (legacy)" if session.is_legacy else ""
    return f"{index}. {session.name}{legacy_tag} - {session.message_count} messages - updated {session.updated_at}"


def select_conversation_session(session_manager: ConversationSessionManager) -> tuple[ConversationManager, str]:
    while True:
        sessions = session_manager.list_sessions()
        print("\n" + "=" * 60)
        print("Conversation Sessions")
        print("=" * 60)

        if not sessions:
            print("No saved sessions found. A new default session will be created.")
        else:
            for index, session in enumerate(sessions, start=1):
                print(format_session_info(session, index))

        print("\nOptions:")
        print("  [number] - Open that session")
        print("  n - Create a new session")
        print("  r - Refresh the list")
        print("  q - Quit")

        choice = input("Select a session: ").strip().lower()

        if choice == "q":
            raise SystemExit(0)
        if choice == "r":
            continue
        if choice == "n":
            session_name = input("New session name (optional): ").strip()
            session_path = session_manager.create_session(session_name or None)
            conversation_manager = ConversationManager(session_file=str(session_path))
            return conversation_manager, session_manager.session_label(session_path)

        if choice.isdigit():
            selected_index = int(choice) - 1
            if 0 <= selected_index < len(sessions):
                selected_session = sessions[selected_index]
                conversation_manager = ConversationManager(session_file=str(selected_session.file_path))
                return conversation_manager, session_manager.session_label(selected_session.file_path)

        print("Invalid selection. Please try again.")


def switch_session_interactively(session_manager: ConversationSessionManager) -> tuple[ConversationManager, str]:
    print("\nSwitching conversation session...")
    return select_conversation_session(session_manager)


# --- 6. CLI Entry Point ---

if __name__ == "__main__":
    knowledge_dir = Path("knowledge")
    knowledge_dir.mkdir(exist_ok=True)
    logger.info("Place your lecture files inside '%s'", knowledge_dir.absolute())

    try:
        logger.info("Checking vector store for updates...")
        vector_store.index_files(str(knowledge_dir), force_reindex=False)
    except Exception as e:
        logger.warning("Failed to index files at startup: %s", e)

    session_manager = ConversationSessionManager(legacy_session_file="conversations/session.json")
    conversation_manager, current_session_label = select_conversation_session(session_manager)
    answer_cache = AnswerCache(cache_file="cache/answer_cache.json", ttl_days=30)

    print("\n" + "=" * 60)
    print("Welcome to LectureCrewLLM - Multi-Agent Lecture Analysis")
    print("=" * 60)
    print_session_summary(conversation_manager, current_session_label)
    if len(conversation_manager) > 0:
        print(f"Loaded {len(conversation_manager)} previous messages from history")
    if len(answer_cache) > 0:
        print(f"Loaded {len(answer_cache)} cached answers")
    print("Type 'sessions' to switch conversations, 'clear' to start fresh, 'find <关键词>' to search, 'cache' for cache info, or ask a question.\n")

    while True:
        print("\n" + "-" * 60)
        user_input = input("You: ").strip()

        if user_input.lower() in ('exit', 'quit'):
            print("Goodbye!")
            break
        elif user_input.lower() == 'sessions':
            conversation_manager, current_session_label = switch_session_interactively(session_manager)
            print_session_summary(conversation_manager, current_session_label)
            continue
        elif user_input.lower() == 'clear':
            conversation_manager.clear_session()
            print("Starting a new conversation.")
            continue
        elif user_input.lower() == 'history':
            print("\nConversation History:")
            for msg in conversation_manager.history:
                role = "You" if msg.role == "user" else "Assistant"
                content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                print(f"{role}: {content}")
            continue
        elif user_input.lower() == 'cache':
            answer_cache.display_cache()
            continue
        elif user_input.lower() == 'cache clear':
            answer_cache.clear_cache()
            print("Answer cache cleared.")
            continue
        elif user_input.lower() == 'session':
            print_session_summary(conversation_manager, current_session_label)
            continue
        elif user_input.lower().startswith('find '):
            rest = user_input[5:].strip()
            search_all = False
            if rest.lower().startswith('all '):
                search_all = True
                keyword = rest[4:].strip()
            else:
                keyword = rest

            if not keyword:
                print("用法: find <关键词>  或  find all <关键词>")
                continue

            print("\n" + "=" * 60)
            print(f"搜索: \"{keyword}\" {'（所有会话）' if search_all else '（当前会话）'}")
            print("=" * 60)

            if search_all:
                results = session_manager.search_all_sessions(keyword)
                if not results:
                    print("未找到匹配的消息。")
                else:
                    # Group by session
                    from collections import defaultdict
                    grouped = defaultdict(list)
                    for r in results:
                        grouped[r["session"]].append(r)
                    print(f"共 {len(results)} 条匹配\n")
                    for session_name, items in grouped.items():
                        print(f"  📂 {session_name} ({len(items)} 条)")
                        for item in items:
                            role_tag = "👤 你" if item["role"] == "user" else "🤖 助手"
                            ts = item.get("timestamp", "")[:16]
                            preview = item["content"][:200] + "..." if len(item["content"]) > 200 else item["content"]
                            preview = preview.replace("\n", " ")
                            print(f"    #{item['index']} [{ts}] {role_tag}: {preview}")
                        print()
            else:
                results = conversation_manager.search_messages(keyword)
                if not results:
                    print("当前会话中未找到匹配的消息。尝试 find all <关键词> 搜索所有会话。")
                else:
                    print(f"共 {len(results)} 条匹配\n")
                    for item in results:
                        role_tag = "👤 你" if item["role"] == "user" else "🤖 助手"
                        ts = item.get("timestamp", "")[:16]
                        preview = item["content"][:200] + "..." if len(item["content"]) > 200 else item["content"]
                        preview = preview.replace("\n", " ")
                        print(f"  #{item['index']} [{ts}] {role_tag}: {preview}")
            continue
        elif not user_input:
            user_input = "Provide a concise summary of all lectures and list 3-5 key takeaways."

        cached_answer = answer_cache.get_answer(user_input)
        if cached_answer:
            print("\n" + "=" * 60)
            print("ANSWER FROM CACHE")
            print("=" * 60)
            final_answer = cached_answer
            print(final_answer)
            conversation_manager.add_message("user", user_input)
            conversation_manager.add_message("assistant", final_answer)
        else:
            print("\nProcessing your question...\n")
            conversation_manager.add_message("user", user_input)

            try:
                final_answer = run_crew(
                    folder_path="knowledge",
                    user_question=user_input,
                    conversation_manager=conversation_manager,
                )
                print("\n" + "=" * 60)
                print("ANSWER FROM CREW")
                print("=" * 60)
                print(final_answer)
                conversation_manager.add_message("assistant", final_answer)
                answer_cache.save_answer(user_input, final_answer)
            except Exception as e:
                logger.exception("Crew execution failed")
                print(f"\nError: {e}")
                if conversation_manager.history and conversation_manager.history[-1].role == "user":
                    conversation_manager.history.pop()
                    conversation_manager.save_session()
                continue

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(f"output/lecture_output_{timestamp}.md")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(str(final_answer), encoding="utf-8")
        print(f"\nOutput saved to: {output_file.absolute()}")
        print("\nTips: Type 'clear' to start fresh, 'history' for chat, 'find <关键词>' to search, 'cache' for cache info, 'exit' to quit.")

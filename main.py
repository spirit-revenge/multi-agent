import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai import LLM
from tools.local_file_tool import ReadLocalLectureFilesTool
from tools.rag_store import LectureVectorStore
from tools.conversation_manager import ConversationManager
from tools.answer_cache import AnswerCache
from tools.session_manager import ConversationSessionManager, SessionInfo
from tools.google_search_tool import GoogleProgrammableSearchTool
from tools.status_tracker import status_tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 1. Configure the DeepSeek Model ---
load_dotenv()
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

def _build_llm():
    return LLM(
        model="deepseek/deepseek-chat",
        api_key=deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.7,
        max_tokens=4000
    )

deepseek_llm = _build_llm()

# Lightweight LLM for routing (cheap, fast)
def _build_router_llm():
    return LLM(
        model="deepseek/deepseek-chat",
        api_key=deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.1,
        max_tokens=100
    )

router_llm = _build_router_llm()

# Initialize persistent vector store
vector_store = LectureVectorStore(persist_directory="chroma_db", collection_name="lectures_chinese")


# --- 2. Define Agents ---

def content_analyst_agent():
    """Agent that synthesizes lecture content with web research into a polished Chinese answer."""
    return Agent(
        role="讲座分析师",
        goal="分析讲座内容与网络搜索结果，生成结构清晰、易懂的中文 Markdown 回答。",
        backstory="你是一位经验丰富的讲师，善于用简单的方式解释复杂概念。你擅长将中文讲座资料和网络信息整合为全面的中文解释。",
        llm=deepseek_llm,
        verbose=False,
        allow_delegation=False,
    )


def router_agent():
    """Agent that classifies user intent into: lecture / web / hybrid / unknown."""
    return Agent(
        role="意图路由器",
        goal="判断用户问题是关于讲座内容、实时信息、还是两者都需要。",
        backstory="你擅长快速识别用户意图，只输出一个词：lecture（仅讲座）、web（仅网络）、hybrid（两者都需要）、unknown（不确定）。",
        llm=router_llm,
        verbose=False,
        allow_delegation=False,
    )


def search_agent():
    """Agent that searches the web for supplementary information."""
    return Agent(
        role="网络研究员",
        goal="搜索与讲座主题相关的定义、示例和最新进展。",
        backstory="你是一位快速准确的网络研究员，擅长找到最相关的在线资源来丰富理解。",
        tools=[GoogleProgrammableSearchTool()],
        llm=deepseek_llm,
        verbose=False,
        allow_delegation=False,
    )





# --- 3. Define Tasks ---

def create_tasks(folder_path="knowledge", user_question=None, conversation_manager=None, task_id=None):
    """
    Build the task list for the crew.
    RAG retrieval runs here (before crew kickoff) and its results are injected
    directly into the Analyst's task as context.
    In sequential mode:
      1. Internet Researcher → web search
      2. Lecture Analyst   → final answer synthesis
    """
    if task_id:
        status_tracker.update(task_id, "rag", "正在检索讲座知识库...")

    try:
        rag_context = vector_store.get_context_for_query(user_question, k=5)
    except Exception as e:
        logger.warning("RAG retrieval failed: %s. Falling back to file reader.", e)
        rag_context = ""
    if not rag_context:
        rag_context = "向量库中未找到相关的讲座内容。"

    if task_id:
        status_tracker.update(task_id, "rag", f"已检索到相关知识（{len(rag_context)} 字符）")

    conversation_context = ""
    if conversation_manager and len(conversation_manager) > 0:
        conversation_context = conversation_manager.get_full_context_for_agent()

    # Task 1: Internet search
    task_search = Task(
        description=f"""搜索与以下问题相关的网页信息、定义和示例：{user_question}

{conversation_context}

以中文返回结果并附上来源 URL。如果是追问，优先查找更新或更具体的信息。""",
        expected_output="带来源 URL 的搜索要点列表。",
        agent=search_agent(),
    )

    # Task 2: Final answer synthesis
    task_answer = Task(
        description=f"""用户问题：{user_question}

{conversation_context}

--- 讲座内容（RAG 检索）---
{rag_context}

--- 网络搜索结果 ---
{{{{task_search.output}}}}

说明：
1. 仔细阅读中文讲座内容——这是你的主要信息来源。
2. 如果搜索结果包含错误（如 "Error:" 开头），忽略它们，仅使用讲座内容。
3. 将讲座知识与有效的搜索结果结合。
4. 以 **中文 Markdown** 格式输出最终答案。
5. 使用标题、列表组织内容，并标注来源（讲座来源文件名、网络 URL）。
6. 如果讲座内容中包含图片，可以用 Markdown 图片语法引用：\n    ![描述](/images/文件名)
7. 如果是追问，明确说明与之前对话的关联。""",
        expected_output="带有引用的结构清晰的中文 Markdown 文档。",
        agent=content_analyst_agent(),
        context=[task_search],
    )

    return [task_search, task_answer]


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

    router = router_agent()
    route_task = Task(
        description=f"""判断以下用户问题属于哪个类别，只输出一个词：

类别说明：
- lecture：关于讲座内容、AI/技术概念、课程知识的问题
- web：关于实时信息、新闻、天气、最新事件的问题
- hybrid：需要同时参考讲座知识和最新信息的问题
- unknown：无法确定的问题

用户问题：{user_question}

输出（只输出一个类别词）：""",
        expected_output="lecture 或 web 或 hybrid 或 unknown",
        agent=router,
    )
    route_crew = Crew(agents=[router], tasks=[route_task], process=Process.sequential, verbose=False)
    intent = str(route_crew.kickoff()).strip().lower()
    logger.info("Router intent: %s → %s", user_question[:40], intent)

    # ---- Step 2: RAG Retrieval (lecture / hybrid routes) ----
    rag_context = ""
    if intent in ("lecture", "hybrid", "unknown"):
        if task_id:
            status_tracker.update(task_id, "rag", "正在检索讲座知识库...")
        try:
            raw_rag = vector_store.get_context_for_query(user_question, k=5)
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            raw_rag = ""

        # Grounding Check: verify relevance via LLM
        if raw_rag:
            rag_result = grounding_check(user_question, raw_rag)
            if rag_result == "IRRELEVANT":
                rag_context = ""  # clear context, will trigger "cannot answer" downstream
            else:
                rag_context = rag_result
        if not rag_context:
            rag_context = ""

    # ---- Step 3: Route execution ----

    # Case A: intent is "web" (no RAG needed)
    if intent == "web" and use_web_search:
        if task_id:
            status_tracker.update(task_id, "searching", "正在搜索网络资源...")

        searcher = search_agent()
        task_search = Task(
            description=f"""搜索与以下问题相关的网页信息：{user_question}

以中文返回结果并附上来源 URL。""",
            expected_output="带来源 URL 的搜索要点列表。",
            agent=searcher,
        )
        task_answer = Task(
            description=f"""用户问题：{user_question}

--- 网络搜索结果 ---
{{{{task_search.output}}}}

说明：
1. 根据网络搜索结果回答用户问题。
2. 以 **中文 Markdown** 格式输出。
3. 标注信息来源 URL。""",
            expected_output="中文 Markdown 回答。",
            agent=analyst,
            context=[task_search],
        )

        if task_id:
            status_tracker.update(task_id, "generating", "正在生成答案...")

        crew = Crew(agents=[searcher, analyst], tasks=[task_search, task_answer],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        if task_id:
            status_tracker.update(task_id, "complete", "答案已生成！")
        return str(result)

    # Case B: intent is "lecture" or web search is OFF
    if intent == "lecture" or not use_web_search:
        if not rag_context:
            if task_id:
                status_tracker.update(task_id, "complete", "无法回答")
            return None  # signal: cannot answer

        if task_id:
            status_tracker.update(task_id, "generating", "正在根据讲座内容生成答案...")

        conv_ctx = conversation_manager.get_full_context_for_agent() if conversation_manager and len(conversation_manager) > 0 else ""

        task_answer = Task(
            description=f"""用户问题：{user_question}

{conv_ctx}

--- 讲座内容（RAG 检索）---
{rag_context}

说明：
1. 仔细阅读中文讲座内容回答用户问题。
2. 以 **中文 Markdown** 格式输出。
3. 如果讲座内容不足以回答问题，请如实说明。
4. 标注信息来源（文件名）。""",
            expected_output="中文 Markdown 回答。",
            agent=analyst,
        )

        crew = Crew(agents=[analyst], tasks=[task_answer],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        if task_id:
            status_tracker.update(task_id, "complete", "答案已生成！")
        return str(result)

    # Case C: hybrid or unknown + web search ON → RAG + Web Search
    searcher = search_agent()
    conv_ctx = conversation_manager.get_full_context_for_agent() if conversation_manager and len(conversation_manager) > 0 else ""

    if task_id:
        status_tracker.update(task_id, "searching", "正在搜索网络资源...")

    task_search = Task(
        description=f"""搜索与以下问题相关的网页信息：{user_question}

{conv_ctx}

以中文返回结果并附上来源 URL。""",
        expected_output="带来源 URL 的搜索要点列表。",
        agent=searcher,
    )

    rag_display = rag_context if rag_context else "向量库中未找到相关的讲座内容。"
    task_answer = Task(
        description=f"""用户问题：{user_question}

{conv_ctx}

--- 讲座内容（RAG 检索）---
{rag_display}

--- 网络搜索结果 ---
{{{{task_search.output}}}}

说明：
1. 仔细阅读中文讲座内容。
2. 如果搜索结果包含错误，忽略它们。
3. 以 **中文 Markdown** 格式输出最终答案。
4. 标注来源（讲座文件名、网络 URL）。""",
        expected_output="带有引用的中文 Markdown 文档。",
        agent=analyst,
        context=[task_search],
    )

    if task_id:
        status_tracker.update(task_id, "searching", "正在搜索网络资源...")

    crew = Crew(
        agents=[searcher, analyst],
        tasks=[task_search, task_answer],
        process=Process.sequential,
        verbose=False,
    )

    if task_id:
        status_tracker.update(task_id, "generating", "正在综合生成答案...")

    result = crew.kickoff()

    if task_id:
        status_tracker.update(task_id, "complete", "答案已生成！")

    return str(result)


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
    print("Type 'sessions' to switch conversations, 'clear' to start fresh, 'cache' for cache info, or ask a question.\n")

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
        print("\nTips: Type 'clear' to start fresh, 'history' for chat, 'cache' for cache info, 'exit' to quit.")

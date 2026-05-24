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

# Initialize persistent vector store
vector_store = LectureVectorStore(persist_directory="chroma_db", collection_name="lectures_chinese")


# --- 2. Define Agents ---

def content_analyst_agent():
    """Agent that synthesizes lecture content with web research into a polished English answer."""
    return Agent(
        role="Lecture Analyst",
        goal="Analyze lecture excerpts and web research to produce clear, well-structured answers in English Markdown.",
        backstory="You are an expert tutor who explains complex ideas simply. You combine Chinese lecture material with English web research to create comprehensive explanations.",
        llm=deepseek_llm,
        verbose=False,
        allow_delegation=False,
    )


def search_agent():
    """Agent that searches the web for supplementary information."""
    return Agent(
        role="Internet Researcher",
        goal="Search the web for definitions, examples, and recent developments related to lecture topics.",
        backstory="You are a fast and accurate web researcher who finds the most relevant online resources to enrich understanding.",
        tools=[GoogleProgrammableSearchTool()],
        llm=deepseek_llm,
        verbose=False,
        allow_delegation=False,
    )


def manager_agent():
    """Orchestrator that delegates tasks to the appropriate agents."""
    return Agent(
        role="Educational Manager",
        goal="Coordinate web search and lecture analysis to produce the best answer for the user.",
        backstory="You supervise the entire process, delegating tasks and combining results into a coherent response.",
        llm=deepseek_llm,
        allow_delegation=True,
        verbose=False,
    )


# --- 3. Define Tasks ---

def create_tasks(folder_path="knowledge", user_question=None, conversation_manager=None):
    """
    Build the task list for the crew.
    RAG retrieval runs here (before crew kickoff) and its results are injected
    directly into the Analyst's task as context. The Manager delegates:
      1. Internet Researcher → web search
      2. Lecture Analyst   → final answer synthesis
    """
    try:
        rag_context = vector_store.get_context_for_query(user_question, k=5)
    except Exception as e:
        logger.warning("RAG retrieval failed: %s. Falling back to file reader.", e)
        rag_context = ""
    if not rag_context:
        rag_context = "No relevant lecture excerpts found in the vector store."

    conversation_context = ""
    if conversation_manager and len(conversation_manager) > 0:
        conversation_context = conversation_manager.get_full_context_for_agent()

    # Task 1: Internet search
    task_search = Task(
        description=f"""Search the web for recent information, definitions, and examples related to: {user_question}

{conversation_context}

Return findings in English with source URLs. If the user is asking a follow-up question, prioritize updated or more specific information relevant to the conversation context.""",
        expected_output="Bullet list of online findings with URLs.",
        agent=search_agent(),
    )

    # Task 2: Final answer synthesis
    task_answer = Task(
        description=f"""User question: {user_question}

{conversation_context}

--- Lecture excerpts (RAG-retrieved, in Chinese) ---
{rag_context}

--- Internet research ---
{{{{task_search.output}}}}

Instructions:
1. Read the Chinese lecture excerpts carefully - they are your primary source.
2. If web research results contain errors (e.g. "Error:" prefix), ignore them and rely solely on the lecture excerpts.
3. Combine lecture knowledge with any valid web research results.
4. Produce a final answer in **English Markdown**.
5. Organize with headings, bullet points, and cite sources (file names for lectures, URLs for web).
6. If the lectures contain specific terms or formulas, explain them in English.
7. If this is a follow-up question, explicitly address how it relates to the previous conversation.""",
        expected_output="A well-structured English Markdown document with citations.",
        agent=content_analyst_agent(),
        context=[task_search],
    )

    return [task_search, task_answer]


# --- 4. Run Crew ---

def run_crew(folder_path="knowledge", user_question=None, conversation_manager=None,
             task_id=None):
    """
    Assemble and run the crew. Accepts an optional task_id for SSE progress reporting.
    """
    searcher = search_agent()
    analyst = content_analyst_agent()
    manager = manager_agent()

    tasks = create_tasks(
        folder_path=folder_path,
        user_question=user_question,
        conversation_manager=conversation_manager,
    )

    if task_id:
        status_tracker.update(task_id, "starting", "Searching the web for relevant resources...")

    crew = Crew(
        agents=[searcher, analyst],
        tasks=tasks,
        process=Process.hierarchical,
        manager_agent=manager,
        verbose=False,
    )

    if task_id:
        status_tracker.update(task_id, "generating", "Synthesizing answer from lectures and web research...")

    result = crew.kickoff()

    if task_id:
        status_tracker.update(task_id, "complete", "Answer ready!")

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

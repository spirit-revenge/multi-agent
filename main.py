import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai import LLM  # Import the LLM class
from tools.local_file_tool import ReadLocalLectureFilesTool
from tools.rag_store import LectureVectorStore
from tools.conversation_manager import ConversationManager
from tools.answer_cache import AnswerCache
from tools.session_manager import ConversationSessionManager, SessionInfo
from tools.google_search_tool import GoogleProgrammableSearchTool

# --- 1. Configure the DeepSeek V4 Pro Model ---
# Retrieve your API key from environment variables for security
load_dotenv()  # Load environment variables from .env file
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

# Instantiate the LLM with the correct model name and API details
deepseek_llm = LLM(
    model="deepseek/deepseek-chat", 
    api_key=deepseek_api_key, 
    base_url="https://api.deepseek.com", 
    temperature=0.7,
    max_tokens=4000
)

# Initialize persistent vector store
vector_store = LectureVectorStore(persist_directory="chroma_db", collection_name="lectures_chinese")


# --- 2. Define Agents, Using the Configured LLM ---
def file_reader_agent():
    return Agent(
        role="Local Document Reader",
        goal="Read all PDF and PPT lecture files from a given folder and extract raw text accurately.",
        backstory=("You are a meticulous assistant. You open every lecture file and extract every word."),
        tools=[ReadLocalLectureFilesTool()],
        llm=deepseek_llm,  
        verbose=False,
        allow_delegation=False,
    )

def content_analyst_agent():
    return Agent(
        role="Lecture Analyst",
        goal="Analyze the extracted lecture text to answer user questions, summarize, or highlight key concepts.",
        backstory=("You are an expert tutor. You explain complex ideas simply."),
        llm=deepseek_llm,  # <-- Assign the LLM here
        verbose=False,
        allow_delegation=False,
    )

def search_agent():
    return Agent(
        role="Internet Researcher",
        goal="Search the web for additional information, definitions, examples, and recent developments related to lecture topics.",
        backstory=("You are a fast and accurate web researcher. You find the most relevant and trustworthy online resources to enrich the student's understanding."),
        tools=[GoogleProgrammableSearchTool()],
        llm=deepseek_llm,
        verbose=False,
        allow_delegation=False,
    )

# --- 3. Define Manager Agent (Orchestrator) ---
def manager_agent():
    return Agent(
        role="Educational Manager",
        goal="Coordinate file reading and analysis to produce the best answer for the user.",
        backstory=("You supervise the entire process, delegating tasks and combining results."),
        llm=deepseek_llm,  # <-- Assign the LLM here
        allow_delegation=True,
        verbose=False,
    )

# ------------------------------------------------------------
# 2. Define Tasks
# ------------------------------------------------------------

def create_tasks(folder_path="knowledge", user_question=None, conversation_manager=None):
    # 1. Ensure indexing (runs once, but we can call it inside the task? Better to do before crew kicks off)
    # We'll index outside tasks because CrewAI tasks shouldn't run long setup code.
    # Instead, we index before creating crew.
    
    # Retrieve RAG context (executed before crew starts)
    rag_context = vector_store.get_context_for_query(user_question, k=5)
    if not rag_context:
        rag_context = "No relevant lecture excerpts found. You may need to read all files manually."
    
    # Get conversation history context if available
    conversation_context = ""
    if conversation_manager and len(conversation_manager) > 0:
        conversation_context = conversation_manager.get_full_context_for_agent()
    
    # Task 1: (Optional) Read all files – we can skip because RAG already gives us chunks.
    # But to keep the hierarchical flow, we create a dummy task that just passes the RAG context.
    # Actually, in hierarchical mode, the manager can decide to skip reading if RAG is sufficient.
    # We'll create a Task that simply provides the RAG context.
    task_rag = Task(
        description=f"""RAG retrieval result:\n{rag_context}\n\nUse this as the primary source of lecture content.
        
{conversation_context}

Current user question: {user_question}""",
        expected_output="RAG context as plain text, with consideration of previous conversation.",
        agent=file_reader_agent(),  # reuse the reader agent but it won't read files
    )
    
    # Task 2: Internet search based on the question
    task_search = Task(
        description=f"""Search the web for recent information, definitions, and examples related to: {user_question}. 
        
{conversation_context}

Return findings in English with sources. If the user is asking a follow-up question based on previous context, prioritize relevant updated or more specific information.""",
        expected_output="Bullet list of online findings with URLs.",
        agent=search_agent(),
        context=[task_rag],
    )
    
    # Task 3: Final answer synthesis
    task_answer = Task(
        description=f"""User question: {user_question}

{conversation_context}

--- Lecture content (from RAG, in Chinese) ---
{{task_rag.output}}

--- Internet research (English) ---
{{task_search.output}}

Instructions:
1. Read the Chinese lecture excerpts carefully.
2. Combine the knowledge from lectures with the online research.
3. Produce a final answer in **English Markdown**.
4. Organize with headings, bullet points, and cite sources (file names for lectures, URLs for web).
5. If the lectures contain specific terms or formulas, explain them in English.
6. If this is a follow-up question, explicitly address how it relates to or builds on the previous conversation.""",
        expected_output="A well-structured English Markdown document.",
        agent=content_analyst_agent(),
        context=[task_rag, task_search],
    )
    
    return [task_rag, task_search, task_answer]

## ------------------------------------------------------------
## Utility Function to Save Output as Markdown
## ------------------------------------------------------------

def save_as_markdown(content, base_filename="output/lecture_analysis", user_question=None, add_metadata=True):
    """Save content as a nicely formatted Markdown file."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_filename}_{timestamp}.md"
    output_path = Path(filename)
    
    with open(output_path, "w", encoding="utf-8") as f:
        if add_metadata:
            f.write(f"# Lecture Analysis Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            if user_question:
                f.write(f"**User Question:** {user_question}\n\n")
            f.write("---\n\n")
        
        f.write(content)
    
    print(f"\n Markdown file saved: {output_path.absolute()}")
    return output_path


def print_session_summary(conversation_manager, session_label: str):
    print(f"Current conversation: {session_label}")
    print(f"Messages in session: {len(conversation_manager)}")


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

# ------------------------------------------------------------
# 3. Build and Run Crew (Hierarchical Process)
# ------------------------------------------------------------

def run_crew(folder_path="knowledge", user_question=None, conversation_manager=None):
    # Instantiate agents
    reader = file_reader_agent()
    analyst = content_analyst_agent()
    searcher = search_agent()
    manager = manager_agent()

    # Create tasks with conversation context
    Tasks = create_tasks(folder_path=folder_path, user_question=user_question, conversation_manager=conversation_manager)

    # For hierarchical process, the manager decides the flow.
    # But we can also set dependencies manually (task_analyze depends on task_extract).
    # In hierarchical mode, the manager will delegate each task sequentially.
    crew = Crew(
        agents=[reader, analyst, searcher],
        tasks= Tasks,
        process=Process.hierarchical,   # Manager decides which agent does what
        manager_agent=manager,
        verbose=False,
    )

    # Kick off the process
    result = crew.kickoff()

    # After getting result
    #save_as_markdown(str(result), user_question=user_question, add_metadata=True)

    # Return both the result string and the metrics
    return str(result)

if __name__ == "__main__":
    # 1. Place your PDF/PPT files in the "knowledge" folder (create it if missing)
    knowledge_dir = Path("knowledge")
    knowledge_dir.mkdir(exist_ok=True)
    print(f"Place your lecture files inside '{knowledge_dir.absolute()}'")
    
    # Ensure the vector store indexes files (only new/changed files will be processed)
    try:
        print("Checking vector store for updates...")
        vector_store.index_files(str(knowledge_dir), force_reindex=False)
    except Exception as e:
        print("Warning: failed to index files at startup:", e)
    
    # Initialize conversation manager and answer cache
    session_manager = ConversationSessionManager(legacy_session_file="conversations/session.json")
    conversation_manager, current_session_label = select_conversation_session(session_manager)
    answer_cache = AnswerCache(cache_file="cache/answer_cache.json", ttl_days=30)
    
    print("\n" + "="*60)
    print("Welcome to LectureCrewLLM - Multi-Agent Lecture Analysis")
    print("="*60)
    print_session_summary(conversation_manager, current_session_label)
    if len(conversation_manager) > 0:
        print(f"Loaded {len(conversation_manager)} previous messages from history")
    if len(answer_cache) > 0:
        print(f"Loaded {len(answer_cache)} cached answers")
    print("Type 'sessions' to switch conversations, 'clear' to start fresh, 'cache' for cache info, or ask a question.\n")
    
    # Multi-turn conversation loop
    while True:
        print("\n" + "-"*60)
        user_input = input("You: ").strip()
        
        # Handle special commands
        if user_input.lower() == 'exit' or user_input.lower() == 'quit':
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
            print(" Answer cache cleared.")
            continue
        elif user_input.lower() == 'session':
            print_session_summary(conversation_manager, current_session_label)
            continue
        elif not user_input:
            # Default question if nothing provided
            user_input = "Provide a concise summary of all lectures and list 3-5 key takeaways."
        
        # Check if answer is already cached
        cached_answer = answer_cache.get_answer(user_input)
        if cached_answer:
            print("\n" + "="*60)
            print("ANSWER FROM CACHE (cached " + answer_cache.cache_file.parent.name + ")")
            print("="*60)
            final_answer = cached_answer
            print(final_answer)
            # Still save to conversation history
            conversation_manager.add_message("user", user_input)
            conversation_manager.add_message("assistant", final_answer)
        else:
            # Not in cache, run crew
            print("\nProcessing your question (not in cache)...\n")
            
            # Save user question to conversation history
            conversation_manager.add_message("user", user_input)
            
            try:
                # Run crew with conversation context
                final_answer = run_crew(
                    folder_path="knowledge", 
                    user_question=user_input,
                    conversation_manager=conversation_manager
                )
                
                print("\n" + "="*60)
                print("ANSWER FROM CREW")
                print("="*60)
                print(final_answer)
                
                # Save assistant response to conversation history and cache
                conversation_manager.add_message("assistant", final_answer)
                answer_cache.save_answer(user_input, final_answer)
                
            except Exception as e:
                print(f"\n Error: {e}")
                import traceback
                traceback.print_exc()
                # Remove the failed question from history
                if conversation_manager.history and conversation_manager.history[-1].role == "user":
                    conversation_manager.history.pop()
                    conversation_manager.save_session()
                continue
        
        # Save the output to a timestamped markdown file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(f"output/lecture_output_{timestamp}.md")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(str(final_answer), encoding="utf-8")
        print(f"\nOutput saved to: {output_file.absolute()}")
        
        print("\nTips: Type 'clear' to start fresh, 'history' for chat, 'cache' for cache info, 'exit' to quit.")
"""
Web UI for LectureCrewLLM using Flask
Provides a user-friendly interface for multi-agent lecture analysis
"""

import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Import core components
from tools.local_file_tool import ReadLocalLectureFilesTool
from tools.rag_store import LectureVectorStore
from tools.conversation_manager import ConversationManager
from tools.answer_cache import AnswerCache
from tools.session_manager import ConversationSessionManager, SessionInfo
from main import (
    run_crew,
    deepseek_llm,
    vector_store,
)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, 
    template_folder='templates',
    static_folder='static'
)

# Set secret key - use persistent key to avoid session invalidation
secret_key = os.getenv('FLASK_SECRET_KEY') or 'lecture-crewllm-default-key-change-in-production'
app.secret_key = secret_key

# Configure session settings
app.config['SESSION_COOKIE_SECURE'] = False  # Allow localhost without HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# Initialize session manager and cache (global)
session_manager = ConversationSessionManager(legacy_session_file="conversations/session.json")
answer_cache = AnswerCache(cache_file="cache/answer_cache.json", ttl_days=30)

# Ensure directories exist
Path("knowledge").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)
Path("conversations").mkdir(exist_ok=True)
Path("conversations/sessions").mkdir(exist_ok=True)
Path("cache").mkdir(exist_ok=True)


# ============================================================================
# Helper Functions
# ============================================================================

def get_conversation_manager_from_session():
    """Get or create conversation manager from Flask session."""
    if 'session_file' not in session:
        # Default to first session or create new
        sessions = session_manager.list_sessions()
        if sessions:
            session['session_file'] = str(sessions[0].file_path)
        else:
            session_path = session_manager.create_session("default")
            session['session_file'] = str(session_path)
    
    return ConversationManager(session_file=session['session_file'])


def get_session_label_from_path(file_path: str) -> str:
    """Get a friendly label for a session file path."""
    return session_manager.session_label(Path(file_path))


def format_timestamp(dt):
    """Format datetime object to readable string."""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.before_request
def ensure_session_initialized():
    """Ensure the Flask session exists before handling requests."""
    session.permanent = True
    if 'session_file' not in session:
        sessions = session_manager.list_sessions()
        if sessions:
            session['session_file'] = str(sessions[0].file_path)
        else:
            session_path = session_manager.create_session("default")
            session['session_file'] = str(session_path)


# ============================================================================
# Routes
# ============================================================================

@app.route('/')
def index():
    """Home page - redirect to chat."""
    return redirect(url_for('chat'))


@app.route('/chat')
def chat():
    """Main chat interface."""
    # Get current session info
    conv_mgr = get_conversation_manager_from_session()
    session_label = get_session_label_from_path(session.get('session_file', ''))
    
    return render_template('index.html', 
        session_label=session_label,
        message_count=len(conv_mgr)
    )


@app.route('/api/sessions', methods=['GET'])
def api_get_sessions():
    """Get all available sessions."""
    try:
        sessions = session_manager.list_sessions()
        sessions_data = []
        
        for sess in sessions:
            sessions_data.append({
                'name': sess.name,
                'file_path': str(sess.file_path),
                'message_count': sess.message_count,
                'updated_at': format_timestamp(sess.updated_at),
                'is_legacy': sess.is_legacy
            })
        
        return jsonify({
            'success': True,
            'sessions': sessions_data,
            'current_session': session.get('session_file', '')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/sessions', methods=['POST'])
def api_create_session():
    """Create a new session."""
    try:
        data = request.json
        session_name = data.get('name', '').strip()
        
        session_path = session_manager.create_session(session_name or None)
        session['session_file'] = str(session_path)
        
        return jsonify({
            'success': True,
            'message': 'Session created successfully',
            'session_file': str(session_path),
            'session_label': get_session_label_from_path(str(session_path))
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/sessions/<path:file_path>', methods=['POST'])
def api_switch_session(file_path):
    """Switch to a different session."""
    try:
        session['session_file'] = file_path
        conv_mgr = get_conversation_manager_from_session()
        
        return jsonify({
            'success': True,
            'message': 'Session switched successfully',
            'session_label': get_session_label_from_path(file_path),
            'message_count': len(conv_mgr)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Send a message and get a response."""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'success': False, 'error': 'Empty message'}), 400
        
        # Get conversation manager
        conv_mgr = get_conversation_manager_from_session()
        
        # Check cache first
        cached_answer = answer_cache.get_answer(user_message)
        
        if cached_answer:
            # Use cached answer
            conv_mgr.add_message("user", user_message)
            conv_mgr.add_message("assistant", cached_answer)
            conv_mgr.save_session()
            
            return jsonify({
                'success': True,
                'response': cached_answer,
                'from_cache': True,
                'timestamp': datetime.now().isoformat()
            })
        
        else:
            # Run crew to generate answer
            conv_mgr.add_message("user", user_message)
            
            try:
                final_answer = run_crew(
                    folder_path="knowledge",
                    user_question=user_message,
                    conversation_manager=conv_mgr
                )
                
                # Save to history and cache
                conv_mgr.add_message("assistant", final_answer)
                conv_mgr.save_session()
                answer_cache.save_answer(user_message, final_answer)
                
                # Save to markdown file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = Path(f"output/lecture_output_{timestamp}.md")
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(str(final_answer), encoding="utf-8")
                
                return jsonify({
                    'success': True,
                    'response': final_answer,
                    'from_cache': False,
                    'timestamp': datetime.now().isoformat()
                })
            
            except Exception as e:
                # Remove failed message from history
                if conv_mgr.history and conv_mgr.history[-1].role == "user":
                    conv_mgr.history.pop()
                    conv_mgr.save_session()
                
                raise e
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def api_get_history():
    """Get conversation history."""
    try:
        conv_mgr = get_conversation_manager_from_session()
        
        history = []
        for msg in conv_mgr.history:
            history.append({
                'role': msg.role,
                'content': msg.content,
                'timestamp': format_timestamp(msg.timestamp) if hasattr(msg, 'timestamp') else ''
            })
        
        return jsonify({
            'success': True,
            'history': history,
            'message_count': len(conv_mgr)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/history', methods=['DELETE'])
def api_clear_history():
    """Clear conversation history."""
    try:
        conv_mgr = get_conversation_manager_from_session()
        conv_mgr.clear_session()
        
        return jsonify({
            'success': True,
            'message': 'Conversation cleared'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/cache', methods=['GET'])
def api_get_cache():
    """Get cache statistics."""
    try:
        stats = answer_cache.get_stats()
        
        # Get recent cached questions
        recent = []
        if answer_cache.data and answer_cache.data.get('answers'):
            for item in answer_cache.data['answers'][-10:]:  # Last 10 items
                cached_at = item.get('timestamp', '')
                is_valid = not answer_cache._is_expired(cached_at) if cached_at else True
                recent.append({
                    'question': item.get('question', '')[:100],  # Truncate
                    'timestamp': cached_at,
                    'is_valid': is_valid
                })
        
        return jsonify({
            'success': True,
            'stats': stats,
            'recent': list(reversed(recent))  # Most recent first
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/cache', methods=['DELETE'])
def api_clear_cache():
    """Clear answer cache."""
    try:
        answer_cache.clear_cache()
        
        return jsonify({
            'success': True,
            'message': 'Cache cleared successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/status', methods=['GET'])
def api_get_status():
    """Get system status."""
    try:
        conv_mgr = get_conversation_manager_from_session()
        cache_stats = answer_cache.get_stats()
        sessions = session_manager.list_sessions()
        
        return jsonify({
            'success': True,
            'status': {
                'current_session': get_session_label_from_path(session.get('session_file', '')),
                'message_count': len(conv_mgr),
                'total_sessions': len(sessions),
                'cache_entries': cache_stats['total_entries'],
                'valid_cache_entries': cache_stats['valid_entries'],
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    # Initialize vector store
    print("Initializing vector store...")
    try:
        knowledge_dir = Path("knowledge")
        knowledge_dir.mkdir(exist_ok=True)
        vector_store.index_files(str(knowledge_dir), force_reindex=False)
        print(f"✓ Vector store ready. Lecture files location: {knowledge_dir.absolute()}")
    except Exception as e:
        print(f"⚠ Vector store initialization warning: {e}")
    
    print("\n" + "="*70)
    print(" LectureCrewLLM Web UI Started")
    print("="*70)
    port = int(os.getenv('WEB_UI_PORT', '7860'))
    print(f" Open your browser and go to: http://localhost:{port}")
    print(f"  Place your lecture files in: {Path('knowledge').absolute()}")
    print(f" Conversations saved to: {Path('conversations').absolute()}")
    print(f"  Outputs saved to: {Path('output').absolute()}")
    print(f"Cache location: {Path('cache/answer_cache.json').absolute()}")
    print("="*70 + "\n")
    
    # Run Flask app
    app.run(
        host='127.0.0.1',
        port=port,
        debug=True,
        use_reloader=True
    )

"""
Web UI for LectureCrewLLM using Flask
Provides a user-friendly interface for multi-agent lecture analysis
with real-time SSE progress updates.
"""

import os
import json
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, send_from_directory, abort
from datetime import datetime, timedelta
from dotenv import load_dotenv

from tools.conversation_manager import ConversationManager
from tools.answer_cache import AnswerCache
from tools.session_manager import ConversationSessionManager
from tools.status_tracker import status_tracker
from main import run_crew, vector_store

logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__,
    template_folder='templates',
    static_folder='static'
)

secret_key = os.getenv('FLASK_SECRET_KEY')
if not secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be set in .env")
app.secret_key = secret_key

app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

session_manager = ConversationSessionManager(legacy_session_file="conversations/session.json")
answer_cache = AnswerCache(cache_file="cache/answer_cache.json", ttl_days=30)

Path("knowledge").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)
Path("conversations").mkdir(exist_ok=True)
Path("conversations/sessions").mkdir(exist_ok=True)
Path("cache").mkdir(exist_ok=True)


# ============================================================================
# Helper Functions
# ============================================================================

def get_conversation_manager_from_session():
    if 'session_file' not in session:
        sessions = session_manager.list_sessions()
        if sessions:
            session['session_file'] = str(sessions[0].file_path)
        else:
            session_path = session_manager.create_session("default")
            session['session_file'] = str(session_path)

    return ConversationManager(session_file=session['session_file'])


def get_session_label_from_path(file_path: str) -> str:
    return session_manager.session_label(Path(file_path))


def format_timestamp(dt):
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.before_request
def ensure_session_initialized():
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
    return redirect(url_for('chat'))


@app.route('/chat')
def chat():
    conv_mgr = get_conversation_manager_from_session()
    session_label = get_session_label_from_path(session.get('session_file', ''))
    return render_template('index.html',
        session_label=session_label,
        message_count=len(conv_mgr)
    )


@app.route('/api/sessions', methods=['GET'])
def api_get_sessions():
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
    try:
        data = request.json
        session_name = data.get('name', '').strip()
        session_path = session_manager.create_session(session_name or None)
        session['session_file'] = str(session_path)
        return jsonify({
            'success': True,
            'message': '会话创建成功',
            'session_file': str(session_path),
            'session_label': get_session_label_from_path(str(session_path))
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/sessions/<path:file_path>', methods=['POST'])
def api_switch_session(file_path):
    try:
        session['session_file'] = file_path
        conv_mgr = get_conversation_manager_from_session()
        return jsonify({
            'success': True,
            'message': '会话切换成功',
            'session_label': get_session_label_from_path(file_path),
            'message_count': len(conv_mgr)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/sessions/<path:file_path>', methods=['DELETE'])
def api_delete_session(file_path):
    try:
        session_path = Path(file_path)
        if not session_manager.delete_session(session_path):
            return jsonify({'success': False, 'error': '无法删除此会话'}), 400

        # If the deleted session was the current one, switch to first available
        if session.get('session_file') == file_path:
            sessions = session_manager.list_sessions()
            if sessions:
                session['session_file'] = str(sessions[0].file_path)
            else:
                new_path = session_manager.create_session("default")
                session['session_file'] = str(new_path)

        return jsonify({'success': True, 'message': '会话已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        task_id = data.get('task_id', '')
        use_web_search = data.get('use_web_search', True)

        if not user_message:
            return jsonify({'success': False, 'error': '消息不能为空'}), 400

        conv_mgr = get_conversation_manager_from_session()

        cached_answer = answer_cache.get_answer(user_message)

        if cached_answer:
            conv_mgr.add_message("user", user_message)
            conv_mgr.add_message("assistant", cached_answer)
            conv_mgr.save_session()

            # Signal completion on SSE if task_id was provided
            if task_id:
                status_tracker.update(task_id, "complete", "")

            return jsonify({
                'success': True,
                'response': cached_answer,
                'from_cache': True,
                'timestamp': datetime.now().isoformat()
            })

        # --- Fresh answer: use background thread + SSE progress ---
        conv_mgr.add_message("user", user_message)
        if not task_id:
            task_id = status_tracker.create_task()

        try:
            final_answer = run_crew(
                folder_path="knowledge",
                user_question=user_message,
                conversation_manager=conv_mgr,
                task_id=task_id,
                use_web_search=use_web_search,
            )
        except Exception as e:
            if conv_mgr.history and conv_mgr.history[-1].role == "user":
                conv_mgr.history.pop()
                conv_mgr.save_session()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            status_tracker.cleanup(task_id)

        # Handle "cannot answer" case (web search off, RAG found nothing)
        if final_answer is None:
            cannot_msg = (
                "我无法从知识库中找到与您问题相关的信息。"
                "如果您需要实时信息，请打开「联网搜索」开关后重试。"
            )
            conv_mgr.add_message("user", user_message)
            conv_mgr.add_message("assistant", cannot_msg)
            conv_mgr.save_session()
            return jsonify({
                'success': True,
                'response': cannot_msg,
                'from_cache': False,
                'cannot_answer': True,
                'timestamp': datetime.now().isoformat(),
            })
        conv_mgr.add_message("assistant", final_answer)
        conv_mgr.save_session()
        answer_cache.save_answer(user_message, final_answer)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return jsonify({
            'success': True,
            'response': final_answer,
            'from_cache': False,
            'timestamp': datetime.now().isoformat(),
            'export_name': f"lecture_output_{timestamp}",
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chat/stream')
def api_chat_stream():
    """SSE endpoint that streams crew execution progress."""
    task_id = request.args.get('task_id', '')
    if not task_id:
        return jsonify({'error': 'Missing task_id'}), 400

    def generate():
        for msg in status_tracker.get_updates(task_id):
            yield f"data: {json.dumps(msg)}\n\n"
            if msg.get("step") == "complete":
                break

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/chat/task', methods=['GET'])
def api_get_task_id():
    """Create a task ID so the frontend can subscribe to SSE before sending the question."""
    task_id = status_tracker.create_task()
    return jsonify({'success': True, 'task_id': task_id})


@app.route('/api/history', methods=['GET'])
def api_get_history():
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
    try:
        conv_mgr = get_conversation_manager_from_session()
        conv_mgr.clear_session()
        return jsonify({'success': True, 'message': '对话已清除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/cache', methods=['GET'])
def api_get_cache():
    try:
        stats = answer_cache.get_stats()
        recent = []
        if answer_cache.cache:
            for item in answer_cache.cache[-10:]:
                recent.append({
                    'question': item.question[:100],
                    'timestamp': item.timestamp,
                    'is_valid': answer_cache._is_cache_valid(item)
                })
        return jsonify({
            'success': True,
            'stats': stats,
            'recent': list(reversed(recent))
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/cache', methods=['DELETE'])
def api_clear_cache():
    try:
        answer_cache.clear_cache()
        return jsonify({'success': True, 'message': '缓存已清除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/status', methods=['GET'])
def api_get_status():
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
# Knowledge (File) Management API
# ============================================================================

@app.route('/api/knowledge', methods=['GET'])
def api_list_knowledge():
    try:
        knowledge_dir = Path("knowledge")
        files = []
        for f in sorted(knowledge_dir.iterdir()):
            if f.suffix.lower() not in ('.pdf', '.pptx', '.docx'):
                continue
            # Check if indexed by looking up a single chunk in ChromaDB
            indexed = False
            try:
                existing = vector_store.collection.get(
                    where={"source": str(f)},
                    limit=1
                )
                indexed = len(existing.get('ids', [])) > 0
            except Exception:
                pass
            files.append({
                'name': f.name,
                'size': f.stat().st_size,
                'indexed': indexed,
                'mtime': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        logger.warning("Failed to list knowledge files: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/knowledge/upload', methods=['POST'])
def api_upload_knowledge():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未提供文件'}), 400

        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'success': False, 'error': '文件名为空'}), 400

        ext = Path(uploaded_file.filename).suffix.lower()
        if ext not in ('.pdf', '.pptx', '.docx'):
            return jsonify({
                'success': False,
                'error': f'不支持的文件类型：{ext}。仅支持 .pdf、.pptx 和 .docx'
            }), 400

        dest = Path("knowledge") / uploaded_file.filename
        uploaded_file.save(str(dest))

        # Incremental index
        try:
            vector_store.index_files("knowledge", force_reindex=False)
        except Exception as e:
            logger.warning("File saved but indexing failed: %s", e)

        return jsonify({
            'success': True,
            'message': f'文件 "{uploaded_file.filename}" 已上传并索引'
        })
    except Exception as e:
        logger.warning("Upload failed: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/knowledge/<filename>', methods=['DELETE'])
def api_delete_knowledge(filename):
    try:
        # Prevent path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'success': False, 'error': '文件名不合法'}), 400

        file_path = Path("knowledge") / filename
        if not file_path.exists():
            return jsonify({'success': False, 'error': '文件不存在'}), 404

        # Remove from ChromaDB (text + image descriptions + tables)
        # Also deletes associated image files from images/
        try:
            removed = vector_store.delete_file(str(file_path))
            logger.info("Removed %d entries for %s", removed, filename)
        except Exception as e:
            logger.warning("Failed to remove from vector store: %s", e)

        # Delete the actual file
        file_path.unlink()
        return jsonify({'success': True, 'message': f'文件 "{filename}" 已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/knowledge/reindex', methods=['POST'])
def api_reindex_knowledge():
    try:
        vector_store.index_files("knowledge", force_reindex=True)
        return jsonify({'success': True, 'message': '重建索引完成'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/images/<path:filename>')
def serve_images(filename):
    """Serve extracted images from the images/ directory."""
    from urllib.parse import unquote
    filename = unquote(filename)
    images_dir = Path('images')
    file_path = images_dir / filename
    # Security: prevent path traversal
    try:
        file_path = file_path.resolve()
        images_dir_resolved = images_dir.resolve()
        if not str(file_path).startswith(str(images_dir_resolved)):
            abort(404)
    except (ValueError, OSError):
        abort(404)
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_from_directory(str(images_dir), filename)


@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': '接口不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    print("正在初始化向量数据库...")
    try:
        knowledge_dir = Path("knowledge")
        knowledge_dir.mkdir(exist_ok=True)
        vector_store.index_files(str(knowledge_dir), force_reindex=False)
        print(f"  向量数据库就绪。讲座文件位置：{knowledge_dir.absolute()}")
    except Exception as e:
        print(f"  向量数据库初始化警告：{e}")

    print("\n" + "=" * 70)
    print("  LectureCrewLLM Web UI 已启动")
    print("=" * 70)
    port = int(os.getenv('WEB_UI_PORT', '7860'))
    print(f"  打开浏览器访问：http://localhost:{port}")
    print(f"  讲座文件：{Path('knowledge').absolute()}")
    print(f"  对话目录：{Path('conversations').absolute()}")
    print(f"  输出目录：{Path('output').absolute()}")
    print("=" * 70 + "\n")

    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(
        host='127.0.0.1',
        port=port,
        debug=debug_mode,
        use_reloader=debug_mode,
        threaded=True,
    )

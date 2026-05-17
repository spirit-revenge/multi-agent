# 🌐 Web UI Quick Start Guide

## Overview

The **LectureCrewLLM Web UI** provides a modern, user-friendly interface for interacting with your lecture analysis system. It includes:

- ✨ **Beautiful Chat Interface** - Clean, intuitive design for asking questions
- 💬 **Multi-Session Management** - Create and switch between multiple conversations
- ⚡ **Smart Caching** - Cached answers are served instantly
- 📚 **Conversation History** - View and manage your chat history
- 📊 **Cache Statistics** - Monitor your cached answers
- 🎨 **Responsive Design** - Works on desktop, tablet, and mobile

## Installation

### 1. Install Flask Dependency

```bash
conda run -n camel pip install Flask==3.0.0
```

Or if you've updated requirements.txt:

```bash
conda run -n camel pip install -r requirements.txt
```

### 2. Verify Installation

```bash
conda run -n camel python -c "import flask; print(f'Flask {flask.__version__} installed')"
```

## Starting the Web UI

```bash
cd /Users/tengyue/Documents/LLM/lecture_crewLLM
conda run -n camel python web_ui.py
```

You'll see:

```
======================================================================
🚀 LectureCrewLLM Web UI Started
======================================================================
📍 Open your browser and go to: http://localhost:7860
⌨️  Place your lecture files in: /path/to/knowledge
💾 Conversations saved to: /path/to/conversations
🗂️  Outputs saved to: /path/to/output
⚡ Cache location: /path/to/cache/answer_cache.json
======================================================================
```

### 3. Open in Browser

Navigate to: **http://localhost:7860**

## Features

### 💬 Chat Interface

**Ask Questions:**
1. Type your question in the input box
2. Press `Shift + Enter` to send (or click the send button)
3. Wait for the AI to generate an answer
4. Results are automatically saved to `output/` folder

**Tips:**
- Use `Enter` for new lines
- Use `Ctrl+K` (or `Cmd+K` on Mac) to focus the input
- Click on messages to view full content

### 📚 Conversation Sessions

**View All Sessions:**
1. Click "Switch/Create" button in the sidebar
2. See all your previous conversations
3. Click any session to switch to it

**Create New Session:**
1. Click "Switch/Create" button
2. Enter a name (optional)
3. Click "Create"
4. The new session becomes active

**Session File Structure:**
```
conversations/
├── session.json          # Default/legacy session
└── sessions/
    ├── session_1.json
    ├── session_2.json
    └── my_topic.json     # Custom named sessions
```

### 📝 View Conversation History

**Access History:**
1. Click "Show History" button in sidebar
2. See all your previous questions and answers
3. Scroll through the timeline

**Clear Conversation:**
1. Click "Clear Conversation" button
2. Confirm the action
3. Conversation history is cleared (cache still intact)

### ⚡ Smart Caching

**How It Works:**
- When you ask a question, the system checks the cache first
- If found, the cached answer is returned instantly (< 1ms)
- If not found, the system generates a new answer and caches it

**View Cache Status:**
- Check sidebar "Cache" section for statistics
- "Cached:" = Total cached answers
- "Valid:" = Non-expired cached answers

**Clear Cache:**
1. Click "Clear Cache" button in sidebar
2. Confirm the action
3. All cached answers are deleted

### 📊 System Status

The sidebar displays:
- **Current Session** - Which conversation you're in
- **Message Count** - Number of messages in current session
- **Cache Statistics** - How many answers are cached

## API Endpoints

The Web UI communicates with these backend APIs:

### Chat
- `POST /api/chat` - Send a message and get response
  ```json
  {
    "message": "What is transformer?"
  }
  ```

### Sessions
- `GET /api/sessions` - List all sessions
- `POST /api/sessions` - Create new session
- `POST /api/sessions/<path>` - Switch to session

### History
- `GET /api/history` - Get conversation history
- `DELETE /api/history` - Clear conversation

### Cache
- `GET /api/cache` - Get cache statistics
- `DELETE /api/cache` - Clear cache

### Status
- `GET /api/status` - Get system status

## File Structure

```
lecture_crewLLM/
├── web_ui.py                 # Flask web server
├── templates/
│   └── index.html            # HTML interface
├── static/
│   ├── style.css             # Styling
│   └── script.js             # Client-side logic
├── conversations/
│   ├── session.json          # Default session
│   └── sessions/             # Additional sessions
├── cache/
│   └── answer_cache.json     # Cached answers
└── output/
    └── lecture_output_*.md   # Generated answers
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Shift + Enter` | Send message |
| `Enter` | New line in input |
| `Ctrl+K` / `Cmd+K` | Focus input field |

## Configuration

### Change Port

To run on a different port, edit `web_ui.py`:

```python
if __name__ == '__main__':
    app.run(
        host='127.0.0.1',
        port=8000,  # Change this
        debug=True,
        use_reloader=True
    )
```

Then run: `python web_ui.py`

### Change Host

To allow external connections:

```python
app.run(
    host='0.0.0.0',  # Change from 127.0.0.1
    port=5000,
    debug=False,  # Don't use debug mode for external access
    use_reloader=False
)
```

## Troubleshooting

### "Flask not found" error

**Solution:**
```bash
conda run -n camel pip install Flask==3.0.0
```

### Port already in use

**Solution:**
```bash
# Kill the process using port 5000
lsof -i :5000
kill -9 <PID>

# Or use a different port (see Configuration section)
```

### Chat not working

1. Check if backend is running (`web_ui.py` still active)
2. Check browser console for errors (F12)
3. Verify `.env` file has correct API keys
4. Check `knowledge/` folder has lecture files

### Sessions not loading

1. Check if `conversations/` folder exists
2. Verify permissions on `conversations/` folder
3. Check `conversations/session.json` is valid JSON

### Cache not working

1. Check if `cache/` folder exists
2. Verify `cache/answer_cache.json` is readable
3. Try clearing cache and starting fresh

## Performance Tips

1. **Use the Web UI** instead of CLI for better user experience
2. **Sessions** are lightweight - create them for different topics
3. **Cache** automatically optimizes repeated questions
4. **Reload page** if UI becomes unresponsive

## Browser Support

- ✅ Chrome/Chromium (Latest)
- ✅ Firefox (Latest)
- ✅ Safari (Latest)
- ✅ Edge (Latest)
- ✅ Mobile browsers

## Security Notes

⚠️ **For Development Only:**
- Default configuration uses `debug=True`
- Not suitable for production deployment
- Don't expose to untrusted networks

**For Production:**
- Set `debug=False`
- Use environment variables for secrets
- Deploy behind a reverse proxy (nginx)
- Enable HTTPS
- Set `host='127.0.0.1'` or configure properly

## Next Steps

1. ✅ Install Flask
2. ✅ Run `python web_ui.py`
3. ✅ Open http://localhost:7860
4. ✅ Ask your first question!

## Getting Help

If you encounter issues:

1. Check the browser console (F12 → Console tab)
2. Check terminal output for server errors
3. Verify `.env` configuration
4. Check `knowledge/` folder has lecture files
5. Try clearing cache and session

---

**Enjoy your interactive lecture analysis experience! 🚀**

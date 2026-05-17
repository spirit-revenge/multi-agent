/**
 * LectureCrewLLM Web UI - Client-side JavaScript
 */

// ============================================================================
// DOM Elements
// ============================================================================

const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const btnSend = document.getElementById('btnSend');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');
const toastContainer = document.getElementById('toastContainer');

// Sidebar elements
const currentSessionEl = document.getElementById('currentSession');
const messageCountEl = document.getElementById('messageCount');
const cacheCountEl = document.getElementById('cacheCount');
const cacheValidEl = document.getElementById('cacheValid');

// Modal elements
const sessionsModal = document.getElementById('sessionsModal');
const historyModal = document.getElementById('historyModal');
const sessionsList = document.getElementById('sessionsList');
const historyList = document.getElementById('historyList');

// Buttons
const btnSessions = document.getElementById('btnSessions');
const btnShowHistory = document.getElementById('btnShowHistory');
const btnClearHistory = document.getElementById('btnClearHistory');
const btnClearCache = document.getElementById('btnClearCache');
const btnCreateSession = document.getElementById('btnCreateSession');
const newSessionName = document.getElementById('newSessionName');

// ============================================================================
// Global State
// ============================================================================

let isProcessing = false;
let currentSessionLabel = 'Loading...';

// ============================================================================
// Event Listeners
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initializeUI();
    setupEventListeners();
    loadInitialData();
});

function setupEventListeners() {
    // Send message
    btnSend.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', handleMessageInputKeypress);
    messageInput.addEventListener('keydown', handleMessageInputKeydown);

    // Session management
    btnSessions.addEventListener('click', openSessionsModal);
    btnCreateSession.addEventListener('click', createNewSession);

    // History
    btnShowHistory.addEventListener('click', openHistoryModal);
    btnClearHistory.addEventListener('click', clearConversation);

    // Cache
    btnClearCache.addEventListener('click', clearCache);

    // Modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').classList.add('hidden');
        });
    });

    // Click outside modal to close
    [sessionsModal, historyModal].forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
            }
        });
    });
}

// ============================================================================
// Message Sending
// ============================================================================

function handleMessageInputKeypress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function handleMessageInputKeydown(e) {
    if (e.key === 'Enter' && e.shiftKey) {
        // Allow shift+enter for new line
        return;
    }
}

async function sendMessage() {
    const message = messageInput.value.trim();
    
    if (!message || isProcessing) {
        return;
    }

    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';

    // Add user message to chat
    addMessageToChat('user', message);

    // Show loading overlay
    isProcessing = true;
    showLoadingOverlay(true);

    try {
        // Send message to backend
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        });

        const data = await response.json();

        if (data.success) {
            // Add assistant response
            const badge = data.from_cache ? 'cached' : 'fresh';
            const badgeText = data.from_cache ? '⚡ From Cache' : '🔄 Fresh Response';
            
            addMessageToChat('assistant', data.response, badge, badgeText);
            
            // Show toast
            const toastMsg = data.from_cache 
                ? '⚡ Answer found in cache!' 
                : '✅ Answer generated successfully';
            showToast(toastMsg, 'success');

            // Update message count
            updateStatus();
        } else {
            showToast('Error: ' + data.error, 'error');
            // Remove user message if there was an error
            const lastMessage = chatContainer.lastElementChild;
            if (lastMessage && lastMessage.classList.contains('user')) {
                lastMessage.remove();
            }
        }
    } catch (error) {
        console.error('Error sending message:', error);
        showToast('Error: Could not send message', 'error');
    } finally {
        isProcessing = false;
        showLoadingOverlay(false);
        messageInput.focus();
    }
}

function addMessageToChat(role, content, badge = null, badgeText = null) {
    // Remove welcome message if present
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // Create message element
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    // Avatar
    const avatarEl = document.createElement('div');
    avatarEl.className = 'message-avatar';
    avatarEl.innerHTML = role === 'user' ? '👤' : '🤖';

    // Message bubble
    const bubbleEl = document.createElement('div');
    bubbleEl.className = 'message-bubble';

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    contentEl.innerHTML = markdownToHtml(content);

    bubbleEl.appendChild(contentEl);

    // Add badge if provided
    if (badge && badgeText) {
        const badgeEl = document.createElement('div');
        badgeEl.className = `message-badge ${badge}`;
        badgeEl.textContent = badgeText;
        bubbleEl.appendChild(badgeEl);
    }

    // Append elements
    if (role === 'user') {
        messageEl.appendChild(bubbleEl);
        messageEl.appendChild(avatarEl);
    } else {
        messageEl.appendChild(avatarEl);
        messageEl.appendChild(bubbleEl);
    }

    chatContainer.appendChild(messageEl);

    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function markdownToHtml(markdown) {
    // Simple markdown to HTML conversion
    let html = markdown
        // Code blocks
        .replace(/```[\s\S]*?```/g, (match) => {
            const code = match.replace(/```/g, '').trim();
            return `<pre><code>${escapeHtml(code)}</code></pre>`;
        })
        // Inline code
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Links
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
        // Bold
        .replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*([^\*]+)\*/g, '<em>$1</em>')
        .replace(/_([^_]+)_/g, '<em>$1</em>')
        // Headings
        .replace(/^### (.*?)$/gm, '<h3>$1</h3>')
        .replace(/^## (.*?)$/gm, '<h2>$1</h2>')
        .replace(/^# (.*?)$/gm, '<h1>$1</h1>')
        // Lists
        .replace(/^\- (.*?)$/gm, '<li>$1</li>')
        // Paragraphs
        .split('\n').map(line => {
            if (line.trim() === '') return '';
            if (line.trim().startsWith('<')) return line;
            return `<p>${line}</p>`;
        }).join('')
        // Remove extra <p> tags
        .replace(/<p><h[1-3]/g, '<h')
        .replace(/<\/h[1-3]><\/p>/g, '</h>')
        .replace(/<p><li>/g, '<li>')
        .replace(/<\/li><\/p>/g, '</li>')
        .replace(/<p><pre>/g, '<pre>')
        .replace(/<\/pre><\/p>/g, '</pre>');

    return html;
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// ============================================================================
// Session Management
// ============================================================================

async function openSessionsModal() {
    sessionsModal.classList.remove('hidden');
    await loadSessions();
}

async function loadSessions() {
    try {
        const response = await fetch('/api/sessions');
        const data = await response.json();

        if (data.success) {
            sessionsList.innerHTML = '';

            if (data.sessions.length === 0) {
                sessionsList.innerHTML = '<p class="loading">No sessions found. Create a new one!</p>';
                return;
            }

            data.sessions.forEach(session => {
                const sessionEl = document.createElement('div');
                sessionEl.className = 'session-item';
                if (session.file_path === data.current_session) {
                    sessionEl.classList.add('active');
                }

                sessionEl.innerHTML = `
                    <div class="session-name">${escapeHtml(session.name)}</div>
                    <div class="session-meta">
                        ${session.message_count} messages • Updated ${session.updated_at}
                        ${session.is_legacy ? '<span style="margin-left: 8px;">(legacy)</span>' : ''}
                    </div>
                `;

                sessionEl.addEventListener('click', () => switchSession(session.file_path));
                sessionsList.appendChild(sessionEl);
            });
        }
    } catch (error) {
        console.error('Error loading sessions:', error);
        sessionsList.innerHTML = '<p class="loading text-secondary">Error loading sessions</p>';
    }
}

async function switchSession(filePath) {
    try {
        const response = await fetch(`/api/sessions/${encodeURIComponent(filePath)}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            currentSessionLabel = data.session_label;
            currentSessionEl.textContent = currentSessionLabel;
            messageCountEl.textContent = data.message_count;
            
            // Clear chat and reload
            chatContainer.innerHTML = '<div class="welcome-message"><div class="welcome-box"><h3>👋 Welcome</h3><p>Session switched. Ask a question to begin.</p></div></div>';
            
            sessionsModal.classList.add('hidden');
            showToast('✅ Session switched', 'success');
            
            // Reload page to refresh conversation
            setTimeout(() => location.reload(), 500);
        }
    } catch (error) {
        console.error('Error switching session:', error);
        showToast('Error switching session', 'error');
    }
}

async function createNewSession() {
    const name = newSessionName.value.trim();
    
    try {
        const response = await fetch('/api/sessions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name: name })
        });

        const data = await response.json();

        if (data.success) {
            currentSessionLabel = data.session_label;
            currentSessionEl.textContent = currentSessionLabel;
            newSessionName.value = '';
            
            showToast('✅ New session created', 'success');
            await loadSessions();
            
            // Clear chat
            chatContainer.innerHTML = '<div class="welcome-message"><div class="welcome-box"><h3>👋 New Session</h3><p>Ask your first question!</p></div></div>';
        }
    } catch (error) {
        console.error('Error creating session:', error);
        showToast('Error creating session', 'error');
    }
}

// ============================================================================
// Conversation Management
// ============================================================================

async function openHistoryModal() {
    historyModal.classList.remove('hidden');
    await loadHistory();
}

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();

        if (data.success) {
            historyList.innerHTML = '';

            if (data.history.length === 0) {
                historyList.innerHTML = '<p class="loading">No conversation history yet</p>';
                return;
            }

            data.history.forEach(msg => {
                const historyItemEl = document.createElement('div');
                historyItemEl.className = `history-item ${msg.role}`;
                
                const roleText = msg.role === 'user' ? '👤 You' : '🤖 Assistant';
                const truncated = msg.content.length > 150 ? msg.content.substring(0, 150) + '...' : msg.content;
                
                historyItemEl.innerHTML = `
                    <div class="history-role">${roleText}</div>
                    <div class="history-content">${escapeHtml(truncated)}</div>
                `;
                
                historyList.appendChild(historyItemEl);
            });
        }
    } catch (error) {
        console.error('Error loading history:', error);
        historyList.innerHTML = '<p class="loading text-secondary">Error loading history</p>';
    }
}

async function clearConversation() {
    if (!confirm('⚠️ Clear all conversation history? This cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch('/api/history', {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            chatContainer.innerHTML = '<div class="welcome-message"><div class="welcome-box"><h3>👋 Fresh Start</h3><p>Conversation cleared. Ask your first question!</p></div></div>';
            messageCountEl.textContent = '0';
            showToast('✅ Conversation cleared', 'success');
        }
    } catch (error) {
        console.error('Error clearing history:', error);
        showToast('Error clearing history', 'error');
    }
}

// ============================================================================
// Cache Management
// ============================================================================

async function loadCacheStats() {
    try {
        const response = await fetch('/api/cache');
        const data = await response.json();

        if (data.success) {
            cacheCountEl.textContent = data.stats.total_entries;
            cacheValidEl.textContent = data.stats.valid_entries;
        }
    } catch (error) {
        console.error('Error loading cache stats:', error);
    }
}

async function clearCache() {
    if (!confirm('⚠️ Clear all cached answers? This will cause repeated questions to be re-processed.')) {
        return;
    }

    try {
        const response = await fetch('/api/cache', {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            cacheCountEl.textContent = '0';
            cacheValidEl.textContent = '0';
            showToast('✅ Cache cleared', 'success');
        }
    } catch (error) {
        console.error('Error clearing cache:', error);
        showToast('Error clearing cache', 'error');
    }
}

// ============================================================================
// UI Updates
// ============================================================================

function initializeUI() {
    messageInput.focus();
}

async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        if (data.success) {
            currentSessionEl.textContent = data.status.current_session;
            messageCountEl.textContent = data.status.message_count;
            currentSessionLabel = data.status.current_session;
        }
    } catch (error) {
        console.error('Error updating status:', error);
    }
}

async function loadInitialData() {
    await updateStatus();
    await loadCacheStats();
}

function showLoadingOverlay(show) {
    if (show) {
        loadingOverlay.classList.remove('hidden');
    } else {
        loadingOverlay.classList.add('hidden');
    }
}

function showToast(message, type = 'info') {
    const toastEl = document.createElement('div');
    toastEl.className = `toast ${type}`;
    toastEl.textContent = message;

    toastContainer.appendChild(toastEl);

    // Auto remove after 4 seconds
    setTimeout(() => {
        toastEl.style.animation = 'slideOutRight 0.3s ease-out forwards';
        setTimeout(() => toastEl.remove(), 300);
    }, 4000);
}

// ============================================================================
// Auto-resize textarea
// ============================================================================

messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
});

// Add slideOutRight animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOutRight {
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ============================================================================
// Keyboard shortcuts
// ============================================================================

document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K to focus input
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        messageInput.focus();
    }
});

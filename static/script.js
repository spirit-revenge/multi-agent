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

// Sidebar knowledge elements
const knowledgeList = document.getElementById('knowledgeList');
const btnUploadFile = document.getElementById('btnUploadFile');
const btnReindex = document.getElementById('btnReindex');
const fileInput = document.getElementById('fileInput');

// Buttons
const btnSessions = document.getElementById('btnSessions');
const btnClearHistory = document.getElementById('btnClearHistory');
const btnClearCache = document.getElementById('btnClearCache');
const btnCreateSession = document.getElementById('btnCreateSession');
const newSessionName = document.getElementById('newSessionName');

// ============================================================================
// Global State
// ============================================================================

let isProcessing = false;
let currentSessionLabel = 'Loading...';
let activeEventSource = null;

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
    btnClearHistory.addEventListener('click', clearConversation);

    // Knowledge management
    btnUploadFile.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileUpload);
    btnReindex.addEventListener('click', reindexKnowledge);

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

function resetProgressSteps() {
    document.querySelectorAll('.progress-step').forEach(el => {
        el.classList.remove('active', 'done');
    });
}

function setProgressStep(stepId) {
    const step = document.getElementById(stepId);
    if (!step) return;
    // Mark previous steps as done
    const allSteps = document.querySelectorAll('.progress-step');
    let found = false;
    allSteps.forEach(el => {
        if (el === step) {
            el.classList.add('active');
            el.classList.remove('done');
            found = true;
        } else if (!found) {
            el.classList.add('done');
            el.classList.remove('active');
        } else {
            el.classList.remove('active', 'done');
        }
    });
}

function subscribeToProgress(taskId) {
    if (activeEventSource) {
        activeEventSource.close();
    }
    const es = new EventSource(`/api/chat/stream?task_id=${encodeURIComponent(taskId)}`);
    activeEventSource = es;

    es.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            switch (msg.step) {
                case 'starting':
                    setProgressStep('stepSearching');
                    break;
                case 'generating':
                    setProgressStep('stepGenerating');
                    break;
                case 'complete':
                    setProgressStep('stepGenerating');
                    document.querySelectorAll('.progress-step').forEach(el => {
                        el.classList.add('done');
                        el.classList.remove('active');
                    });
                    es.close();
                    activeEventSource = null;
                    break;
                case 'heartbeat':
                    break;
            }
        } catch (e) {
            // ignore parse errors
        }
    };

    es.onerror = () => {
        es.close();
        activeEventSource = null;
    };
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

    // Show loading overlay with progress steps
    isProcessing = true;
    resetProgressSteps();
    showLoadingOverlay(true);

    try {
        // Get a fresh task_id for progress tracking
        const taskResp = await fetch('/api/chat/task');
        const taskData = await taskResp.json();
        const taskId = taskData.task_id;

        // Subscribe to SSE before sending the message
        subscribeToProgress(taskId);

        // Send message to backend
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message, task_id: taskId })
        });

        const data = await response.json();

        // Clean up SSE
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }

        if (data.success) {
            const badge = data.from_cache ? 'cached' : 'fresh';
            const badgeText = data.from_cache ? 'From Cache' : 'Fresh Response';

            addMessageToChat('assistant', data.response, badge, badgeText);

            const toastMsg = data.from_cache
                ? 'Answer found in cache!'
                : 'Answer generated successfully';
            showToast(toastMsg, 'success');

            updateStatus();
        } else {
            showToast('Error: ' + data.error, 'error');
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
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }
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
    // —— Step 1: Extract & protect fenced code blocks ——
    const blocks = [];
    let html = markdown.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
        const placeholder = `%%BLOCK_${blocks.length}%%`;
        const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : '';
        blocks.push(`<pre><code${langClass}>${escapeHtml(code.trimEnd())}</code></pre>`);
        return placeholder;
    });

    // —— Step 2: Extract & protect inline code ——
    html = html.replace(/`([^`]+)`/g, (_, code) => {
        const placeholder = `%%BLOCK_${blocks.length}%%`;
        blocks.push(`<code>${escapeHtml(code)}</code>`);
        return placeholder;
    });

    // —— Step 3: Process tables (multi-line blocks with | alignment) ——
    const paragraphBlocks = html.split(/\n\s*\n/);
    for (let b = 0; b < paragraphBlocks.length; b++) {
        const tableLines = paragraphBlocks[b].split('\n');
        // Heuristic: at least 3 lines, all start with |, second line is separator
        if (tableLines.length >= 3 &&
            tableLines.every(l => l.trim().startsWith('|')) &&
            /^\|[:\- ]+\|/.test(tableLines[1].trim())) {
            const headerCells = tableLines[0].split('|').map(c => c.trim()).filter(Boolean);
            const bodyRows = tableLines.slice(2).map(row =>
                row.split('|').map(c => c.trim()).filter(Boolean)
            );
            let tbl = '<table>\n<thead>\n<tr>';
            headerCells.forEach(c => { tbl += `<th>${c}</th>`; });
            tbl += '</tr>\n</thead>\n<tbody>\n';
            bodyRows.forEach(row => {
                tbl += '<tr>';
                row.forEach((c, i) => { tbl += `<td>${c || ''}</td>`; });
                tbl += '</tr>\n';
            });
            tbl += '</tbody>\n</table>';
            paragraphBlocks[b] = tbl;
        }
    }
    html = paragraphBlocks.join('\n\n');

    // —— Step 4: Line-by-line block-level processing ——
    const lines = html.split('\n');
    const out = [];
    let listType = null;   // 'ul' | 'ol' | null
    let listBuffer = [];

    function flushList() {
        if (listType && listBuffer.length > 0) {
            out.push(`<${listType}>`);
            out.push(...listBuffer);
            out.push(`</${listType}>`);
        }
        listType = null;
        listBuffer = [];
    }

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const t = line.trim();

        // Empty line → flush any open list
        if (t === '') {
            flushList();
            out.push('');
            continue;
        }

        // Skip if it's a protected block placeholder
        if (/^%%BLOCK_\d+%%$/.test(t)) {
            flushList();
            out.push(line);
            continue;
        }

        // Skip if already a rendered HTML tag
        if (t.startsWith('<')) {
            flushList();
            out.push(line);
            continue;
        }

        // Horizontal rule
        if (/^(?:---|\*\*\*|___)\s*$/.test(t)) {
            flushList();
            out.push('<hr>');
            continue;
        }

        // Heading
        if (/^#{1,3}\s/.test(t)) {
            flushList();
            const level = t.match(/^#+/)[0].length;
            out.push(`<h${level}>${t.replace(/^#+\s*/, '')}</h${level}>`);
            continue;
        }

        // Blockquote
        if (/^>\s/.test(t)) {
            flushList();
            out.push(`<blockquote><p>${t.replace(/^>\s*/, '')}</p></blockquote>`);
            continue;
        }

        // Unordered list item
        if (/^[\*\-]\s/.test(t)) {
            if (listType !== 'ul') { flushList(); listType = 'ul'; }
            listBuffer.push(`  <li>${t.replace(/^[\*\-]\s*/, '')}</li>`);
            continue;
        }

        // Ordered list item
        if (/^\d+\.\s/.test(t)) {
            if (listType !== 'ol') { flushList(); listType = 'ol'; }
            listBuffer.push(`  <li>${t.replace(/^\d+\.\s*/, '')}</li>`);
            continue;
        }

        // Plain text → paragraph
        flushList();
        out.push(`<p>${line}</p>`);
    }
    flushList();
    html = out.join('\n');

    // —— Step 5: Inline formatting (applied last so block tags stay intact) ——
    html = html
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
        .replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/\*([^\*]+)\*/g, '<em>$1</em>')
        .replace(/_([^_]+)_/g, '<em>$1</em>');

    // —— Step 6: Restore protected blocks (code blocks, inline code) ——
    html = html.replace(/%%BLOCK_(\d+)%%/g, (_, i) => blocks[parseInt(i)] || '');

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

                const canDelete = !session.is_legacy;
                sessionEl.innerHTML = `
                    <div class="session-info-wrap">
                        <div class="session-name">${escapeHtml(session.name)}</div>
                        <div class="session-meta">
                            ${session.message_count} messages • Updated ${session.updated_at}
                            ${session.is_legacy ? '<span style="margin-left: 8px;">(legacy)</span>' : ''}
                        </div>
                    </div>
                    ${canDelete ? `<button class="session-delete" data-path="${escapeHtml(session.file_path)}" title="Delete session"><i class="fas fa-trash"></i></button>` : ''}
                `;

                sessionEl.addEventListener('click', (e) => {
                    if (e.target.closest('.session-delete')) return;
                    switchSession(session.file_path);
                });
                const delBtn = sessionEl.querySelector('.session-delete');
                if (delBtn) {
                    delBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        deleteSession(session.file_path);
                    });
                }
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
            
            sessionsModal.classList.add('hidden');
            showToast('✅ 会话已切换', 'success');
            await loadChatHistory();
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
            
            showToast('✅ 新会话已创建', 'success');
            await loadSessions();
            await loadChatHistory();
        }
    } catch (error) {
        console.error('Error creating session:', error);
        showToast('Error creating session', 'error');
    }
}

// ============================================================================
// Session Delete
// ============================================================================

async function deleteSession(filePath) {
    if (!confirm('⚠️ Delete this session? All messages will be lost. Cancel to keep it.')) {
        return;
    }

    try {
        const response = await fetch(`/api/sessions/${encodeURIComponent(filePath)}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.success) {
            showToast('✅ 会话已删除', 'success');
            await loadSessions();
            await updateStatus();
            await loadChatHistory();
        } else {
            showToast('Error: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error deleting session:', error);
        showToast('Error deleting session', 'error');
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
            messageCountEl.textContent = '0';
            showToast('✅ 对话已清除', 'success');
            await loadChatHistory();
        }
    } catch (error) {
        console.error('Error clearing history:', error);
        showToast('Error clearing history', 'error');
    }
}

// ============================================================================
// Knowledge (File) Management
// ============================================================================

async function loadKnowledge() {
    try {
        const response = await fetch('/api/knowledge');
        const data = await response.json();

        if (!data.success) {
            knowledgeList.innerHTML = '<p class="knowledge-empty">Error loading files</p>';
            return;
        }

        if (data.files.length === 0) {
            knowledgeList.innerHTML = '<p class="knowledge-empty">No lecture files</p>';
            return;
        }

        knowledgeList.innerHTML = '';
        data.files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'knowledge-item';
            const icon = file.indexed ? '🟢' : '⏳';
            const sizeKB = (file.size / 1024).toFixed(1);
            item.innerHTML = `
                <div class="knowledge-info">
                    <span class="knowledge-icon">${icon}</span>
                    <span class="knowledge-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
                    <span class="knowledge-size">${sizeKB} KB</span>
                </div>
                <button class="knowledge-delete" data-filename="${escapeHtml(file.name)}" title="Delete">
                    <i class="fas fa-times"></i>
                </button>
            `;
            item.querySelector('.knowledge-delete').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteKnowledgeFile(file.name);
            });
            knowledgeList.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading knowledge:', error);
        knowledgeList.innerHTML = '<p class="knowledge-empty">Error loading files</p>';
    }
}

async function handleFileUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    let hasValid = false;
    for (const f of files) {
        const ext = f.name.toLowerCase().slice(f.name.lastIndexOf('.'));
        if (ext === '.pdf' || ext === '.pptx') {
            formData.append('file', f);
            hasValid = true;
        } else {
            showToast(`Skipped ${f.name}: only .pdf and .pptx allowed`, 'warning');
        }
    }

    if (!hasValid) {
        showToast('No valid files selected', 'warning');
        fileInput.value = '';
        return;
    }

    try {
        const response = await fetch('/api/knowledge/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message, 'success');
            await loadKnowledge();
        } else {
            showToast('Upload error: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error uploading file:', error);
        showToast('Upload failed', 'error');
    }

    fileInput.value = '';
}

async function deleteKnowledgeFile(filename) {
    if (!confirm(`Delete "${filename}"? This will remove it from the vector store as well.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/knowledge/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message, 'success');
            await loadKnowledge();
        } else {
            showToast('Delete error: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error deleting file:', error);
        showToast('Delete failed', 'error');
    }
}

async function reindexKnowledge() {
    btnReindex.disabled = true;
    btnReindex.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Indexing...';

    try {
        const response = await fetch('/api/knowledge/reindex', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            showToast('Reindexing complete', 'success');
            await loadKnowledge();
        } else {
            showToast('Reindex error: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error reindexing:', error);
        showToast('Reindex failed', 'error');
    }

    btnReindex.disabled = false;
    btnReindex.innerHTML = '<i class="fas fa-sync"></i> Reindex';
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
    await loadKnowledge();
    await loadChatHistory();
}

async function loadChatHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();

        // Clear chat container
        chatContainer.innerHTML = '';

        if (!data.success || data.history.length === 0) {
            // Show welcome message when no history
            chatContainer.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-box">
                        <h3>👋 欢迎使用 LectureCrewLLM</h3>
                        <p>提出关于讲座的问题，AI 将结合网络搜索为你解答。</p>
                        <div class="features">
                            <div class="feature-item">
                                <i class="fas fa-database"></i>
                                <span>RAG 增强分析</span>
                            </div>
                            <div class="feature-item">
                                <i class="fas fa-globe"></i>
                                <span>网络搜索整合</span>
                            </div>
                            <div class="feature-item">
                                <i class="fas fa-bolt"></i>
                                <span>智能缓存</span>
                            </div>
                            <div class="feature-item">
                                <i class="fas fa-floppy-disk"></i>
                                <span>多会话支持</span>
                            </div>
                        </div>
                        <p class="hint-text">💡 试试提问："什么是 Transformer 架构？"</p>
                    </div>
                </div>
            `;
            return;
        }

        // Render each message in history
        data.history.forEach(msg => {
            addMessageToChat(msg.role, msg.content);
        });

        // Scroll to bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
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

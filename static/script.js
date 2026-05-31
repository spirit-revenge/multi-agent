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
const elapsedTime = document.getElementById('elapsedTime');
const loadingTips = document.getElementById('loadingTips');
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
const btnExportChat = document.getElementById('btnExportChat');
const btnClearHistory = document.getElementById('btnClearHistory');
const btnClearCache = document.getElementById('btnClearCache');
const btnCreateSession = document.getElementById('btnCreateSession');
const btnToggleWeb = document.getElementById('btnToggleWeb');
const webSearchLabel = document.getElementById('webSearchLabel');
const newSessionName = document.getElementById('newSessionName');

// Search
const searchInput = document.getElementById('searchInput');
const btnSearch = document.getElementById('btnSearch');
const searchAllSessions = document.getElementById('searchAllSessions');
const searchResults = document.getElementById('searchResults');

// Web search toggle state
let useWebSearch = true;

// ============================================================================
// Global State
// ============================================================================

const TIPS = [
    '💡 正在从讲座中检索相关知识...',
    '🌐 正在搜索网络上的补充信息...',
    '🧠 正在用 AI 综合分析多源信息...',
    '⏳ 正在生成答案，请稍候...',
    '🔍 查找更详细的相关资料...',
];

let isProcessing = false;
let currentSessionLabel = 'Loading...';
let currentSessionFile = '';
let activeEventSource = null;
let elapsedTimer = null;
let elapsedSeconds = 0;
let tipIndex = 0;
let currentLoadingMsg = null;  // track the inline loading bubble
let currentMessageIndex = 0;   // counter for data-index on messages

// ============================================================================
// Event Listeners
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    try {
        initializeUI();
        setupEventListeners();
    } catch (e) {
        console.error('Initialization error (non-fatal):', e);
    }
    loadInitialData();
});

function setupEventListeners() {
    // Send message
    if (btnSend) btnSend.addEventListener('click', sendMessage);
    if (messageInput) {
        messageInput.addEventListener('keypress', handleMessageInputKeypress);
        messageInput.addEventListener('keydown', handleMessageInputKeydown);
    }

    // Auto-detect location on page load
    detectLocation();

    // Search
    if (btnSearch && searchInput) {
        btnSearch.addEventListener('click', searchHistory);
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') searchHistory();
        });
    }

    // Session management
    if (btnSessions) btnSessions.addEventListener('click', openSessionsModal);
    if (btnCreateSession) btnCreateSession.addEventListener('click', createNewSession);

    // History
    if (btnExportChat) btnExportChat.addEventListener('click', exportConversation);
    btnClearHistory.addEventListener('click', clearConversation);

    // Knowledge management
    btnUploadFile.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileUpload);
    if (btnReindex) btnReindex.addEventListener('click', reindexKnowledge);

    // Cache
    btnClearCache.addEventListener('click', clearCache);

    // Web search toggle
    if (btnToggleWeb) btnToggleWeb.addEventListener('click', toggleWebSearch);

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
    if (loadingTips) {
        loadingTips.textContent = TIPS[0];
    }
    if (elapsedTime) {
        elapsedTime.textContent = '已用 0 秒';
    }
}

function startElapsedTimer() {
    elapsedSeconds = 0;
    if (elapsedTimer) clearInterval(elapsedTimer);
    elapsedTimer = setInterval(() => {
        elapsedSeconds++;
        // Update old overlay timer (if visible)
        if (elapsedTime) {
            elapsedTime.textContent = `已用 ${elapsedSeconds} 秒`;
        }
        // Update inline bubble timer
        if (currentLoadingMsg) {
            const counter = currentLoadingMsg.querySelector('.elapsed-count');
            if (counter) counter.textContent = elapsedSeconds;
        }
        // Rotate tip every 8 seconds
        if (elapsedSeconds > 0 && elapsedSeconds % 8 === 0) {
            tipIndex = (tipIndex + 1) % TIPS.length;
            if (loadingTips) {
                loadingTips.style.animation = 'none';
                loadingTips.offsetHeight; // trigger reflow
                loadingTips.textContent = TIPS[tipIndex];
                loadingTips.style.animation = 'fadeInTip 0.6s ease-in-out';
            }
        }
    }, 1000);
}

function stopElapsedTimer() {
    if (elapsedTimer) {
        clearInterval(elapsedTimer);
        elapsedTimer = null;
    }
}

function updateLoadingTip(step) {
    const stepTips = {
        'routing': '🎯 正在分析问题意图...',
        'rag': '💡 正在从讲座中检索相关知识...',
        'searching': '🌐 正在搜索网络上的补充信息...',
        'generating': '🧠 正在用 AI 分析综合信息生成答案...',
        'complete': '✅ 答案已生成！',
    };
    if (loadingTips && stepTips[step]) {
        loadingTips.style.animation = 'none';
        loadingTips.offsetHeight;
        loadingTips.textContent = stepTips[step];
        loadingTips.style.animation = 'fadeInTip 0.6s ease-in-out';
    }
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
    updateLoadingTip(stepId);
}

// ============================================================================
// Inline Loading Bubble (replaces full-screen overlay)
// ============================================================================

function addLoadingMessage() {
    // Remove welcome message if present
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();

    const messageEl = document.createElement('div');
    messageEl.className = 'message assistant loading-message';

    const avatarEl = document.createElement('div');
    avatarEl.className = 'message-avatar';
    avatarEl.textContent = '🤖';

    const bubbleEl = document.createElement('div');
    bubbleEl.className = 'message-bubble loading-bubble';
    bubbleEl.innerHTML = `
        <div class="loading-header">
            <span class="loading-spinner"></span>
            <span class="loading-status">正在思考...</span>
        </div>
        <div class="loading-steps">
            <div class="lstep" data-step="routing">🎯 分析问题意图</div>
            <div class="lstep" data-step="rag">💡 检索讲座知识库</div>
            <div class="lstep" data-step="searching">🌐 搜索网络资源</div>
            <div class="lstep" data-step="generating">🧠 生成答案</div>
        </div>
        <div class="loading-elapsed">⏱ 已用 <span class="elapsed-count">0</span> 秒</div>
    `;

    messageEl.appendChild(avatarEl);
    messageEl.appendChild(bubbleEl);
    chatContainer.appendChild(messageEl);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    return messageEl;
}

function updateLoadingStep(step) {
    if (!currentLoadingMsg) return;
    const steps = currentLoadingMsg.querySelectorAll('.lstep');
    let found = false;
    steps.forEach(el => {
        if (el.dataset.step === step) {
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

    // Update status text
    const statusEl = currentLoadingMsg.querySelector('.loading-status');
    const tips = {
        'routing': '正在分析问题意图...',
        'rag': '正在检索讲座知识库...',
        'searching': '正在搜索网络资源...',
        'generating': '正在生成答案...',
        'complete': '✅ 答案已生成！',
    };
    if (statusEl && tips[step]) statusEl.textContent = tips[step];
}

function removeLoadingMessage() {
    if (currentLoadingMsg) {
        currentLoadingMsg.remove();
        currentLoadingMsg = null;
    }
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
                case 'routing':
                case 'rag':
                case 'searching':
                case 'generating':
                    updateLoadingStep(msg.step);
                    break;
                case 'complete':
                    updateLoadingStep('complete');
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

    // Add inline loading bubble
    isProcessing = true;
    currentLoadingMsg = addLoadingMessage();
    startElapsedTimer();

    try {
        // Get a fresh task_id for progress tracking
        const taskResp = await fetch('/api/chat/task');
        const taskData = await taskResp.json();
        const taskId = taskData.task_id;

        // Subscribe to SSE
        subscribeToProgress(taskId);

        // Send message to backend
        const userLoc = localStorage.getItem('user_location') || '';
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message, task_id: taskId, use_web_search: useWebSearch, location: userLoc })
        });

        const data = await response.json();

        // Clean up SSE
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }

        if (data.success) {
            // Handle cannot_answer case
            if (data.cannot_answer) {
                removeLoadingMessage();
                addMessageToChat('assistant', data.response, 'no-web', '⚠️ 未联网');
                showToast('知识库中未找到相关信息', 'warning');
                updateStatus();
                return;
            }

            const badge = data.from_cache ? 'cached' : 'fresh';
            const badgeText = data.from_cache ? '来自缓存' : '实时生成';

            removeLoadingMessage();
            addMessageToChat('assistant', data.response, badge, badgeText, data.export_name);

            const toastMsg = data.from_cache
                ? '✅ 答案来自缓存'
                : '✅ 答案已生成';
            showToast(toastMsg, 'success');

            updateStatus();
        } else {
            showToast('错误：' + data.error, 'error');
            const lastMessage = chatContainer.lastElementChild;
            if (lastMessage && lastMessage.classList.contains('user')) {
                lastMessage.remove();
            }
        }
    } catch (error) {
        console.error('Error sending message:', error);
        showToast('发送失败：无法连接到服务器', 'error');
    } finally {
        isProcessing = false;
        stopElapsedTimer();
        currentLoadingMsg = null;
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }
        messageInput.focus();
    }
}

function addMessageToChat(role, content, badge = null, badgeText = null, exportName = null) {
    // Remove welcome message if present
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // Create message element
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;
    messageEl.dataset.index = currentMessageIndex++;

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

    // Add export button for assistant messages
    if (role === 'assistant' && content) {
        const exportBtn = document.createElement('button');
        exportBtn.className = 'message-export-btn';
        exportBtn.title = '导出为 Markdown 文件';
        exportBtn.innerHTML = '<i class="fas fa-download"></i>';
        const fileName = exportName || `lecture_output_${Date.now()}`;
        exportBtn.addEventListener('click', () => {
            const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${fileName}.md`;
            a.click();
            URL.revokeObjectURL(url);
            showToast('✅ 已导出 Markdown 文件', 'success');
        });
        bubbleEl.appendChild(exportBtn);
    }

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
    // Step 0: Strip LLM artifacts (%%HTML0%%, %%BLOCK1%%, etc.)
    // These tokens are sometimes output by the LLM; strip them before rendering.
    markdown = markdown
        .replace(/%%HTML\d+%%/g, '')
        .replace(/%%BLOCK\d+%%/g, '');

    // Step 1: Extract & protect fenced code blocks
    const blocks = [];
    let html = markdown.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
        const placeholder = `%%B${blocks.length}%%`;
        const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : '';
        blocks.push(`<pre><code${langClass}>${escapeHtml(code.trimEnd())}</code></pre>`);
        return placeholder;
    });

    // —— Step 2: Extract & protect inline code ——
    html = html.replace(/`([^`]+)`/g, (_, code) => {
        const placeholder = `%%B${blocks.length}%%`;
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
        if (/^%%B\d+%%$/.test(t)) {
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
    // Protect HTML tags from inline regex
    const protectedHtml = [];
    html = html.replace(/(<[^>]+>)/g, (match) => {
        const ph = `%%H${protectedHtml.length}%%`;
        protectedHtml.push(match);
        return ph;
    });

    html = html
        // Images (must come before links since ![ is a subset of [)
        .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" class="msg-image" loading="lazy">')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // Protect newly generated HTML tags
    html = html.replace(/(<[^>]+>)/g, (match) => {
        const ph = `%%H${protectedHtml.length}%%`;
        protectedHtml.push(match);
        return ph;
    });

    html = html
        .replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/\*([^\*]+)\*/g, '<em>$1</em>')
        .replace(/_([^_]+)_/g, '<em>$1</em>');

    // —— Step 6: Restore protected blocks ——
    html = html.replace(/%%H(\d+)%%/g, (_, i) => protectedHtml[parseInt(i)] || '');
    html = html.replace(/%%B(\d+)%%/g, (_, i) => blocks[parseInt(i)] || '');

    console.log("myhtml"+html);
    console.log(protectedHtml);

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
                            ${session.message_count} 条消息 • 更新于 ${session.updated_at}
                            ${session.is_legacy ? '<span style="margin-left: 8px;">(旧版)</span>' : ''}
                        </div>
                    </div>
                    ${canDelete ? `<button class="session-delete" data-path="${escapeHtml(session.file_path)}" title="删除会话"><i class="fas fa-trash"></i></button>` : ''}
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
        sessionsList.innerHTML = '<p class="loading text-secondary">加载会话失败</p>';
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
            currentSessionFile = filePath;
            currentSessionEl.textContent = currentSessionLabel;
            messageCountEl.textContent = data.message_count;

            sessionsModal.classList.add('hidden');
            showToast('✅ 会话已切换', 'success');
            await loadChatHistory();
        }
    } catch (error) {
        console.error('Error switching session:', error);
        showToast('切换会话失败', 'error');
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
        showToast('创建会话失败', 'error');
    }
}

// ============================================================================
// Session Delete
// ============================================================================

async function deleteSession(filePath) {
    if (!confirm('⚠️ 删除此会话？所有消息将永久丢失。取消以保留。')) {
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
            showToast('错误：' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error deleting session:', error);
        showToast('删除会话失败', 'error');
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
                historyList.innerHTML = '<p class="loading">暂无对话历史</p>';
                return;
            }

            data.history.forEach(msg => {
                const historyItemEl = document.createElement('div');
                historyItemEl.className = `history-item ${msg.role}`;
                
                const roleText = msg.role === 'user' ? '👤 你' : '🤖 助手';
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
        historyList.innerHTML = '<p class="loading text-secondary">加载历史失败</p>';
    }
}

async function clearConversation() {
    if (!confirm('⚠️ 清除所有对话历史？此操作不可撤销。')) {
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
        showToast('清除历史失败', 'error');
    }
}

// ============================================================================
// Conversation Export
// ============================================================================

async function exportConversation() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();

        if (!data.success || data.history.length === 0) {
            showToast('暂无对话可导出', 'warning');
            return;
        }

        // Build Markdown content
        let md = `# LectureCrewLLM 对话导出\n\n`;
        md += `导出时间：${new Date().toLocaleString('zh-CN')}\n\n`;
        md += `---\n\n`;

        data.history.forEach((msg, i) => {
            const roleLabel = msg.role === 'user' ? '## 👤 用户' : '## 🤖 助手';
            md += `${roleLabel}\n\n`;
            md += `${msg.content}\n\n`;
            if (i < data.history.length - 1) {
                md += `---\n\n`;
            }
        });

        // Download
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
        const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `对话导出_${timestamp}.md`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('✅ 对话已导出为 Markdown 文件', 'success');
    } catch (error) {
        console.error('Error exporting conversation:', error);
        showToast('导出失败', 'error');
    }
}

// ============================================================================
// Conversation Export
// ============================================================================
// Knowledge (File) Management
// ============================================================================

async function loadKnowledge() {
    try {
        const response = await fetch('/api/knowledge');
        const data = await response.json();

        if (!data.success) {
            knowledgeList.innerHTML = '<p class="knowledge-empty">加载文件失败</p>';
            return;
        }

        if (data.files.length === 0) {
            knowledgeList.innerHTML = '<p class="knowledge-empty">暂无讲座文件</p>';
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
        knowledgeList.innerHTML = '<p class="knowledge-empty">加载文件失败</p>';
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
            showToast(`已跳过 ${f.name}：仅支持 .pdf、.pptx 和 .docx`, 'warning');
        }
    }

    if (!hasValid) {
        showToast('未选择有效文件', 'warning');
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
            showToast('上传错误：' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error uploading file:', error);
        showToast('上传失败', 'error');
    }

    fileInput.value = '';
}

async function deleteKnowledgeFile(filename) {
    if (!confirm(`删除 "${filename}"？将从向量数据库中同时移除。`)) {
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
            showToast('删除错误：' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error deleting file:', error);
        showToast('删除失败', 'error');
    }
}

async function reindexKnowledge() {
    btnReindex.disabled = true;
    btnReindex.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 索引中...';

    try {
        const response = await fetch('/api/knowledge/reindex', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            showToast('重建索引完成', 'success');
            await loadKnowledge();
        } else {
            showToast('重建索引错误：' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error reindexing:', error);
        showToast('重建索引失败', 'error');
    }

    btnReindex.disabled = false;
    btnReindex.innerHTML = '<i class="fas fa-sync"></i> 重建索引';
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
    if (!confirm('⚠️ 清除所有缓存答案？重复的问题将被重新处理。')) {
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
            showToast('✅ 缓存已清除', 'success');
        }
    } catch (error) {
        console.error('Error clearing cache:', error);
        showToast('清除缓存失败', 'error');
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
    // Also fetch current session file path
    try {
        const resp = await fetch('/api/sessions');
        const d = await resp.json();
        if (d.success) {
            currentSessionFile = d.current_session || '';
        }
    } catch (e) {
        console.error('Error getting current session file:', e);
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
        currentMessageIndex = 0;
        data.history.forEach(msg => {
            addMessageToChat(msg.role, msg.content, null, null, null);
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
// Web Search Toggle
// ============================================================================

// ============================================================================
// Location Detection
// ============================================================================

function detectLocation() {
    if (!navigator.geolocation) return;
    if (localStorage.getItem('user_location')) return; // already detected

    navigator.geolocation.getCurrentPosition(
        async (pos) => {
            const { latitude, longitude } = pos.coords;
            try {
                const resp = await fetch(
                    `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json&accept-language=zh`,
                    { headers: { 'User-Agent': 'LectureCrewLLM/1.0' } }
                );
                const data = await resp.json();
                const city = data.address?.city || data.address?.town || data.address?.village || data.address?.county || '';
                const country = data.address?.country || '';
                const loc = city ? `${city}, ${country}` : `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`;
                localStorage.setItem('user_location', loc);
            } catch (e) {
                const loc = `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`;
                localStorage.setItem('user_location', loc);
            }
        },
        (err) => {
            console.warn('Geolocation error:', err.message);
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

async function searchHistory() {
    const keyword = searchInput.value.trim();
    if (!keyword) {
        searchResults.innerHTML = '<p class="search-empty">请输入搜索关键词</p>';
        return;
    }

    const all = searchAllSessions ? searchAllSessions.checked : false;
    try {
        const resp = await fetch(`/api/history/search?q=${encodeURIComponent(keyword)}&all=${all}`);
        const data = await resp.json();

        if (!data.success) {
            searchResults.innerHTML = `<p class="search-empty">搜索失败：${escapeHtml(data.error)}</p>`;
            return;
        }

        if (data.count === 0) {
            searchResults.innerHTML = '<p class="search-empty">未找到匹配的消息</p>';
            return;
        }

        searchResults.innerHTML = `<p class="search-count">共 ${data.count} 条匹配</p>`;
        data.results.forEach(item => {
            const el = document.createElement('div');
            el.className = 'search-result-item';
            el.dataset.sessionFile = item.session_file || '';
            el.dataset.msgIndex = item.index;
            el.title = '点击跳转到此消息';
            const roleTag = item.role === 'user' ? '👤 你' : '🤖 助手';
            const sessionTag = all && item.session ? ` [${escapeHtml(item.session)}]` : '';
            const preview = item.content.length > 100
                ? escapeHtml(item.content.substring(0, 100)) + '...'
                : escapeHtml(item.content);
            el.innerHTML = `
                <div class="search-result-role">${roleTag}${sessionTag} · #${item.index}</div>
                <div class="search-result-content">${preview}</div>
            `;
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const sf = el.dataset.sessionFile || '';
                const idx = parseInt(el.dataset.msgIndex, 10);
                console.log('Search result clicked: sessionFile=' + sf + ' index=' + idx);
                jumpToMessage(sf, idx).catch(err => {
                    console.error('jumpToMessage failed:', err);
                    showToast('跳转失败：' + err.message, 'error');
                });
            });
            searchResults.appendChild(el);
        });
    } catch (error) {
        console.error('Search error:', error);
        searchResults.innerHTML = '<p class="search-empty">搜索请求失败</p>';
    }
}

async function jumpToMessage(sessionFile, index) {
    console.log('jumpToMessage called: sessionFile=' + sessionFile + ' index=' + index + ' currentSessionFile=' + currentSessionFile);

    // If from a different session, switch first
    if (sessionFile && sessionFile !== currentSessionFile) {
        console.log('Switching session from ' + currentSessionFile + ' to ' + sessionFile);
        try {
            const response = await fetch(`/api/sessions/${encodeURIComponent(sessionFile)}`, {
                method: 'POST'
            });
            const data = await response.json();
            if (!data.success) {
                showToast('切换会话失败', 'error');
                return;
            }
            currentSessionLabel = data.session_label;
            currentSessionFile = sessionFile;
            currentSessionEl.textContent = currentSessionLabel;
            messageCountEl.textContent = data.message_count;
            await loadChatHistory();
        } catch (e) {
            console.error('Session switch error:', e);
            showToast('切换会话失败', 'error');
            return;
        }
    }

    // Find and scroll to the message
    const target = chatContainer.querySelector(`.message[data-index="${index}"]`);
    console.log('Looking for .message[data-index="' + index + '"], found:', !!target);
    if (!target) {
        showToast('未找到该消息（可能已被清除）', 'warning');
        return;
    }

    // Scroll to the message (small delay ensures DOM is ready)
    setTimeout(() => {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Highlight animation
        target.classList.add('highlight-flash');
        setTimeout(() => target.classList.remove('highlight-flash'), 1500);
    }, 100);

    showToast('📍 已跳转到消息 #' + index, 'success');
}

function toggleWebSearch() {
    useWebSearch = !useWebSearch;
    if (useWebSearch) {
        btnToggleWeb.classList.add('active');
        btnToggleWeb.classList.remove('inactive');
        btnToggleWeb.title = '点击关闭联网搜索';
        webSearchLabel.textContent = '联网';
    } else {
        btnToggleWeb.classList.remove('active');
        btnToggleWeb.classList.add('inactive');
        btnToggleWeb.title = '点击开启联网搜索';
        webSearchLabel.textContent = '离线';
    }
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

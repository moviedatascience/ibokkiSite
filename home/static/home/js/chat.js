const ROLE_COLORS = {
    admin:     'font-bold text-green-400',
    moderator: 'font-bold text-red-400',
    subscriber:'font-semibold text-blue-400',
    user:      'font-semibold text-white',
};

class ChatClient {
    constructor(options = {}) {
        this.options = {
            reconnectInterval: 1000,
            maxReconnectAttempts: 10,
            pingInterval: 30000,
            pongTimeout: 10000,
            ...options
        };

        this.socket = null;
        this.reconnectAttempts = 0;
        this.isReconnecting = false;
        this.isConnected = false;
        this.pingInterval = null;
        this.pongTimeout = null;
        this.currentStreamId = 'general';

        this.connect = this.connect.bind(this);
        this.reconnect = this.reconnect.bind(this);
        this.sendMessage = this.sendMessage.bind(this);
        this.sendCommand = this.sendCommand.bind(this);
        this.switchStream = this.switchStream.bind(this);
        this.handleMessage = this.handleMessage.bind(this);
        this.handleOpen = this.handleOpen.bind(this);
        this.handleClose = this.handleClose.bind(this);
        this.handleError = this.handleError.bind(this);

        // Event callbacks
        this.onMessage = null;
        this.onHistory = null;
        this.onError = null;
        this.onConnected = null;
        this.onDisconnected = null;
        this.onClear = null;
        this.onTimeout = null;
        this.onBan = null;
        this.onPollStart = null;
        this.onPollUpdate = null;
        this.onPollEnd = null;
        this.onInfo = null;
    }

    connect(streamId = 'general') {
        this.currentStreamId = streamId;

        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        let wsPath;

        if (streamId && streamId !== 'general') {
            wsPath = `${wsScheme}://${window.location.host}/ws/chat/${streamId}/`;
        } else {
            wsPath = `${wsScheme}://${window.location.host}/ws/chat/?stream=${streamId}`;
        }

        console.log('Connecting to WebSocket:', wsPath);

        try {
            this.socket = new WebSocket(wsPath);
            this.socket.onopen = this.handleOpen;
            this.socket.onmessage = this.handleMessage;
            this.socket.onclose = this.handleClose;
            this.socket.onerror = this.handleError;
        } catch (error) {
            console.error('Error creating WebSocket:', error);
            this.scheduleReconnect();
        }
    }

    handleOpen(event) {
        console.log('Chat WebSocket connection established');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.isReconnecting = false;

        this.startPingInterval();

        if (this.onConnected) {
            this.onConnected(event);
        }
    }

    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'history':
                    if (this.onHistory) {
                        this.onHistory(data.history, data.stream_id);
                    }
                    break;

                case 'message':
                    if (this.onMessage) {
                        this.onMessage(data);
                    }
                    break;

                case 'clear':
                    if (this.onClear) {
                        this.onClear(data.stream_id);
                    }
                    break;

                case 'timeout':
                    if (this.onTimeout) {
                        this.onTimeout(data.username, data.duration, data.stream_id);
                    }
                    break;

                case 'ban':
                    if (this.onBan) {
                        this.onBan(data.message, data.stream_id);
                    }
                    break;

                case 'poll_start':
                    if (this.onPollStart) {
                        this.onPollStart(data);
                    }
                    break;

                case 'poll_update':
                    if (this.onPollUpdate) {
                        this.onPollUpdate(data);
                    }
                    break;

                case 'poll_end':
                    if (this.onPollEnd) {
                        this.onPollEnd(data);
                    }
                    break;

                case 'error':
                    console.error('Chat error:', data.error);
                    if (this.onError) {
                        this.onError(data.error);
                    }
                    break;

                case 'info':
                    if (this.onInfo) {
                        this.onInfo(data.message);
                    }
                    break;

                case 'ping':
                    this.send({
                        type: 'pong',
                        timestamp: Date.now()
                    });
                    break;

                case 'pong':
                    if (this.pongTimeout) {
                        clearTimeout(this.pongTimeout);
                        this.pongTimeout = null;
                    }
                    break;
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    handleClose(event) {
        console.log('Chat WebSocket connection closed', event.code, event.reason);
        this.isConnected = false;
        this.stopPingInterval();

        if (this.onDisconnected) {
            this.onDisconnected(event);
        }

        if (event.code !== 1000 && !this.isReconnecting) {
            this.scheduleReconnect();
        }
    }

    handleError(event) {
        console.error('Chat WebSocket error:', event);
        if (this.onError) {
            this.onError('Connection error occurred');
        }
    }

    scheduleReconnect() {
        if (this.isReconnecting || this.reconnectAttempts >= this.options.maxReconnectAttempts) {
            console.log('Max reconnection attempts reached');
            return;
        }

        this.isReconnecting = true;
        this.reconnectAttempts++;

        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => {
            if (this.isReconnecting) {
                this.connect(this.currentStreamId);
            }
        }, delay);
    }

    reconnect() {
        this.reconnectAttempts = 0;
        this.isReconnecting = false;
        this.connect(this.currentStreamId);
    }

    send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
            return true;
        } else {
            console.warn('WebSocket is not connected');
            return false;
        }
    }

    sendMessage(message) {
        return this.send({
            type: 'message',
            message: message
        });
    }

    sendCommand(command) {
        return this.send({
            type: 'command',
            command: command
        });
    }

    sendVote(pollId, optionId) {
        return this.send({
            type: 'vote',
            poll_id: pollId,
            option_id: optionId
        });
    }

    switchStream(streamId) {
        this.currentStreamId = streamId;
        return this.send({
            type: 'join_stream',
            stream_id: streamId
        });
    }

    startPingInterval() {
        this.stopPingInterval();

        this.pingInterval = setInterval(() => {
            if (this.isConnected) {
                this.send({
                    type: 'ping',
                    timestamp: Date.now()
                });

                this.pongTimeout = setTimeout(() => {
                    console.warn('Pong timeout - connection may be dead');
                    if (this.socket) {
                        this.socket.close();
                    }
                }, this.options.pongTimeout);
            }
        }, this.options.pingInterval);
    }

    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }

        if (this.pongTimeout) {
            clearTimeout(this.pongTimeout);
            this.pongTimeout = null;
        }
    }

    disconnect() {
        this.isReconnecting = false;
        this.stopPingInterval();

        if (this.socket) {
            this.socket.close(1000, 'Manual disconnect');
            this.socket = null;
        }
    }
}

// Chat UI Manager
class ChatUI {
    constructor(chatClient, options = {}) {
        this.chatClient = chatClient;
        this.options = {
            maxMessages: 100,
            ...options
        };

        this.messageContainer = null;
        this.inputForm = null;
        this.inputField = null;
        this.statusIndicator = null;
        this.pollContainer = null;

        this.activePollId = null;
        this.hasVoted = false;
        this.pollTimer = null;

        this.setupEventHandlers();
    }

    init(containerSelector, formSelector, inputSelector, statusSelector = null) {
        this.messageContainer = document.querySelector(containerSelector);
        this.inputForm = document.querySelector(formSelector);
        this.inputField = document.querySelector(inputSelector);
        this.statusIndicator = statusSelector ? document.querySelector(statusSelector) : null;
        this.pollContainer = document.querySelector('#poll-container');

        if (!this.messageContainer || !this.inputForm || !this.inputField) {
            console.error('Required chat UI elements not found');
            return false;
        }

        this.setupFormHandler();
        return true;
    }

    setupEventHandlers() {
        this.chatClient.onHistory = (history, streamId) => {
            this.clearMessages();
            history.forEach(msg => this.appendMessage(msg));
        };

        this.chatClient.onMessage = (data) => {
            this.appendMessage(data);
        };

        this.chatClient.onClear = () => {
            this.clearMessages();
        };

        this.chatClient.onError = (error) => {
            this.showError(error);
        };

        this.chatClient.onInfo = (message) => {
            this.showInfo(message);
        };

        this.chatClient.onConnected = () => {
            this.updateStatus('connected');
        };

        this.chatClient.onDisconnected = () => {
            this.updateStatus('disconnected');
        };

        this.chatClient.onTimeout = (username, duration) => {
            this.showTimeout(username, duration);
        };

        this.chatClient.onBan = (message) => {
            this.showBan(message);
        };

        this.chatClient.onPollStart = (data) => {
            this.showPoll(data);
        };

        this.chatClient.onPollUpdate = (data) => {
            this.updatePollResults(data);
        };

        this.chatClient.onPollEnd = (data) => {
            this.showPollEnd(data);
        };
    }

    setupFormHandler() {
        if (this.inputForm) {
            this.inputForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const message = this.inputField.value.trim();

                if (message) {
                    if (message.startsWith('/')) {
                        this.chatClient.sendCommand(message);
                    } else {
                        this.chatClient.sendMessage(message);
                    }
                    this.inputField.value = '';
                }
            });
        }
    }

    getRoleClass(data) {
        const role = data.role || (data.is_staff ? 'admin' : 'user');
        return ROLE_COLORS[role] || ROLE_COLORS.user;
    }

    appendMessage(data) {
        if (!this.messageContainer) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message text-youtube-primary py-1 break-words';

        const timestamp = data.timestamp ? new Date(data.timestamp * 1000) : new Date();
        const timeStr = timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const userClass = this.getRoleClass(data);

        messageDiv.innerHTML = `
            <span class="text-[10px] text-gray-500 mr-1">${timeStr}</span>
            <span class="${userClass} mr-1 cursor-pointer hover:underline" onclick="window.chatUI.insertMention('${data.user}')">${data.user}:</span>
            <span class="message-content text-gray-200">${data.message}</span>
        `;

        this.messageContainer.appendChild(messageDiv);
        this.scrollToBottom();
        this.limitMessages();
    }

    insertMention(username) {
        if (this.inputField) {
            const mention = `@${username} `;
            if (!this.inputField.value.includes(mention)) {
                this.inputField.value = mention + this.inputField.value;
            }
            this.inputField.focus();
        }
    }

    clearMessages() {
        if (this.messageContainer) {
            this.messageContainer.innerHTML = '';
        }
    }

    showError(error) {
        if (!this.messageContainer) return;

        const errorDiv = document.createElement('div');
        errorDiv.className = 'chat-error text-red-400 py-1 italic';
        errorDiv.textContent = `Error: ${error}`;

        this.messageContainer.appendChild(errorDiv);
        this.scrollToBottom();
    }

    showInfo(message) {
        if (!this.messageContainer) return;

        const infoDiv = document.createElement('div');
        infoDiv.className = 'chat-info text-blue-400 py-1 italic';
        infoDiv.textContent = message;

        this.messageContainer.appendChild(infoDiv);
        this.scrollToBottom();
    }

    showTimeout(username, duration) {
        if (!this.messageContainer) return;

        const timeoutDiv = document.createElement('div');
        timeoutDiv.className = 'chat-timeout text-yellow-400 py-1 italic';
        timeoutDiv.textContent = `${username} has been timed out for ${duration} seconds`;

        this.messageContainer.appendChild(timeoutDiv);
        this.scrollToBottom();
    }

    showBan(message) {
        if (!this.messageContainer) return;

        const banDiv = document.createElement('div');
        banDiv.className = 'chat-ban text-red-400 py-1 italic';
        banDiv.textContent = message;

        this.messageContainer.appendChild(banDiv);
        this.scrollToBottom();
    }

    // --- Poll UI ---

    _pollBarColors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#e84393', '#00cec9', '#fd79a8'];

    showPoll(data) {
        if (!this.pollContainer) return;

        this.activePollId = data.poll_id;
        this.hasVoted = false;

        const expiresAt = data.expires_at * 1000;
        const createdBy = data.created_by || 'Unknown';
        const duration = data.duration || 60;
        const totalVotes = data.options.reduce((sum, o) => sum + (o.votes || 0), 0);

        let optionsHtml = '';
        data.options.forEach((opt, i) => {
            const color = this._pollBarColors[i % this._pollBarColors.length];
            const pct = totalVotes > 0 ? Math.round((opt.votes || 0) / totalVotes * 100) : 0;
            const votes = opt.votes || 0;
            optionsHtml += `
                <div class="poll-option cursor-pointer hover:brightness-125 transition-all" data-option-id="${opt.id}" data-poll-id="${data.poll_id}">
                    <div class="flex justify-between text-xs text-gray-300 mb-0.5 px-1">
                        <span><span class="font-bold text-white">${i + 1}</span> ${this._escapeHtml(opt.text)}</span>
                        <span class="poll-vote-info">${pct}% (${votes} vote${votes !== 1 ? 's' : ''})</span>
                    </div>
                    <div class="w-full bg-gray-700 rounded-sm h-5 overflow-hidden">
                        <div class="poll-bar h-full rounded-sm transition-all duration-300" style="width: ${pct}%; background-color: ${color};"></div>
                    </div>
                </div>
            `;
        });

        this.pollContainer.innerHTML = `
            <div class="poll-widget bg-[#1a1a2e] border border-gray-700 rounded p-3 mb-1">
                <div class="flex justify-between items-start mb-1">
                    <p class="text-white text-sm font-bold leading-tight">${this._escapeHtml(data.question)}</p>
                    <button class="poll-dismiss text-gray-500 hover:text-white ml-2 text-lg leading-none flex-shrink-0" title="Dismiss">&times;</button>
                </div>
                <p class="text-gray-400 text-xs mb-2">Poll started by ${this._escapeHtml(createdBy)} for ${duration} seconds. <span class="poll-total-votes">${totalVotes}</span> votes</p>
                <div class="poll-options space-y-1.5">
                    ${optionsHtml}
                </div>
                <div class="text-right mt-1">
                    <span class="poll-timer text-gray-500 text-xs" id="poll-timer"></span>
                </div>
            </div>
        `;

        this.pollContainer.querySelector('.poll-dismiss').addEventListener('click', () => {
            this.pollContainer.innerHTML = '';
            if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
        });

        this.pollContainer.querySelectorAll('.poll-option').forEach(el => {
            el.addEventListener('click', () => {
                if (this.hasVoted) return;
                const optionId = parseInt(el.dataset.optionId);
                const pollId = parseInt(el.dataset.pollId);
                this.chatClient.sendVote(pollId, optionId);
                this.hasVoted = true;
                this.pollContainer.querySelectorAll('.poll-option').forEach(o => {
                    o.classList.remove('hover:brightness-125');
                    o.style.cursor = 'default';
                });
                el.style.outline = '2px solid white';
                el.style.outlineOffset = '-2px';
                el.style.borderRadius = '2px';
            });
        });

        this._startPollTimer(expiresAt);
    }

    updatePollResults(data) {
        if (!this.pollContainer || data.poll_id !== this.activePollId) return;

        const totalVotes = data.total_votes || 0;
        const totalEl = this.pollContainer.querySelector('.poll-total-votes');
        if (totalEl) totalEl.textContent = totalVotes;

        data.results.forEach((opt, i) => {
            const el = this.pollContainer.querySelector(`[data-option-id="${opt.id}"]`);
            if (!el) return;
            const pct = totalVotes > 0 ? Math.round(opt.votes / totalVotes * 100) : 0;
            const infoEl = el.querySelector('.poll-vote-info');
            const barEl = el.querySelector('.poll-bar');
            if (infoEl) infoEl.textContent = `${pct}% (${opt.votes} vote${opt.votes !== 1 ? 's' : ''})`;
            if (barEl) barEl.style.width = pct + '%';
        });
    }

    showPollEnd(data) {
        if (!this.pollContainer) return;

        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }

        this.activePollId = null;

        const totalVotes = data.results.reduce((sum, o) => sum + o.votes, 0);

        let resultsHtml = '';
        data.results.forEach((opt, i) => {
            const color = this._pollBarColors[i % this._pollBarColors.length];
            const pct = totalVotes > 0 ? Math.round(opt.votes / totalVotes * 100) : 0;
            resultsHtml += `
                <div>
                    <div class="flex justify-between text-xs text-gray-300 mb-0.5 px-1">
                        <span><span class="font-bold text-white">${i + 1}</span> ${this._escapeHtml(opt.text)}</span>
                        <span>${pct}% (${opt.votes} vote${opt.votes !== 1 ? 's' : ''})</span>
                    </div>
                    <div class="w-full bg-gray-700 rounded-sm h-5 overflow-hidden">
                        <div class="h-full rounded-sm" style="width: ${pct}%; background-color: ${color};"></div>
                    </div>
                </div>
            `;
        });

        this.pollContainer.innerHTML = `
            <div class="poll-widget bg-[#1a1a2e] border border-gray-700 rounded p-3 mb-1">
                <div class="flex justify-between items-start mb-1">
                    <p class="text-white text-sm font-bold leading-tight">${this._escapeHtml(data.question)}</p>
                    <button class="poll-dismiss text-gray-500 hover:text-white ml-2 text-lg leading-none flex-shrink-0" title="Dismiss">&times;</button>
                </div>
                <p class="text-gray-400 text-xs mb-2">Poll ended. ${totalVotes} vote${totalVotes !== 1 ? 's' : ''}</p>
                <div class="space-y-1.5">
                    ${resultsHtml}
                </div>
            </div>
        `;

        this.pollContainer.querySelector('.poll-dismiss').addEventListener('click', () => {
            this.pollContainer.innerHTML = '';
        });

        setTimeout(() => {
            if (this.pollContainer && !this.activePollId) {
                this.pollContainer.innerHTML = '';
            }
        }, 30000);
    }

    _startPollTimer(expiresAt) {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
        }

        const timerEl = document.getElementById('poll-timer');
        if (!timerEl) return;

        const updateTimer = () => {
            const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
            const mins = Math.floor(remaining / 60);
            const secs = remaining % 60;
            timerEl.textContent = `${mins}:${secs.toString().padStart(2, '0')} remaining`;

            if (remaining <= 0) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
                timerEl.textContent = 'Ended';
            }
        };

        updateTimer();
        this.pollTimer = setInterval(updateTimer, 1000);
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // --- End Poll UI ---

    updateStatus(status) {
        if (this.statusIndicator) {
            this.statusIndicator.className = `status-indicator ${status}`;
            this.statusIndicator.textContent = status === 'connected' ? '●' : '○';
        }
    }

    scrollToBottom() {
        if (this.messageContainer) {
            const threshold = 100;
            const isNearBottom = this.messageContainer.scrollHeight - this.messageContainer.scrollTop - this.messageContainer.clientHeight < threshold;

            if (isNearBottom) {
                this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
            }
        }
    }

    limitMessages() {
        if (!this.messageContainer) return;

        const messages = this.messageContainer.children;
        while (messages.length > this.options.maxMessages) {
            this.messageContainer.removeChild(messages[0]);
        }
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ChatClient, ChatUI };
} else {
    window.ChatClient = ChatClient;
    window.ChatUI = ChatUI;
}

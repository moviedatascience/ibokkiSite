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
        this.onPollResultsAnnouncement = null;
        this.onInfo = null;
    }

    connect(viewingStreamId = 'general') {
        this.currentStreamId = viewingStreamId;
        this.viewingStream = viewingStreamId;

        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsPath = `${wsScheme}://${window.location.host}/ws/chat/?stream=${viewingStreamId}`;

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

                case 'poll_results_announcement':
                    if (this.onPollResultsAnnouncement) {
                        this.onPollResultsAnnouncement(data);
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
        this.viewingStream = streamId;
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
    static MOD_COMMANDS = [
        { command: '/clear', usage: '/clear', description: 'Clear all chat messages' },
        { command: '/timeout', usage: '/timeout <user> [seconds]', description: 'Timeout a user (default 300s)' },
        { command: '/untimeout', usage: '/untimeout <user>', description: 'Remove a user\'s timeout' },
        { command: '/ban', usage: '/ban <user> [hours]', description: 'Ban a user (permanent if no duration)' },
        { command: '/unban', usage: '/unban <user>', description: 'Unban a user' },
        { command: '/poll', usage: '/poll [sec] Question | Opt1 | Opt2', description: 'Create a poll (default 60s)' },
        { command: '/endpoll', usage: '/endpoll', description: 'End the current poll early' },
    ];

    constructor(chatClient, options = {}) {
        this.chatClient = chatClient;
        this.options = {
            maxMessages: 100,
            isMod: false,
            ...options
        };

        this.messageContainer = null;
        this.inputForm = null;
        this.inputField = null;
        this.statusIndicator = null;
        this.pollContainer = null;

        this.activePollId = null;
        this.votedOptionId = null;
        this.pollTimer = null;
        this.pollExpired = false;
        this.currentPollResults = null;

        this.eyeFilterActive = false;
        this.slashHighlightIndex = -1;

        // Emotes
        this.emotes = [];
        this.emoteMap = {};
        this.emoteCodes = [];
        this.emoteHighlightIndex = -1;
        this.favoriteCodes = new Set();

        // User highlight filter (left-click a username)
        this.highlightedUser = null;

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
        this._setupEyeToggle();
        if (this.options.isMod) {
            this._setupSlashCommands();
        }
        this._loadEmotes();
        this._setupEmoteAutocomplete();
        this._setupEmotePicker();
        this._setupChatInteractions();
        this._setupUserCardModal();
        this._setupEmoteModal();
        return true;
    }

    setupEventHandlers() {
        this.chatClient.onHistory = (history) => {
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

        this.chatClient.onPollResultsAnnouncement = (data) => {
            this._showPollResultsInChat(data.question, data.results);
        };
    }

    setupFormHandler() {
        if (this.inputForm) {
            this.inputForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this._submitMessage();
            });
        }
        if (this.inputField) {
            // Enter sends, Shift+Enter inserts a newline (destiny-style; no Send button).
            this.inputField.addEventListener('keydown', (e) => this._onInputKeydown(e));
            this.inputField.addEventListener('input', () => this._autoResizeInput());
        }
    }

    _onInputKeydown(e) {
        if (e.key !== 'Enter' || e.shiftKey) return;
        // When the slash-command or emote popup is open, let its own handler
        // claim Enter (to complete a command/emote) instead of sending.
        const slashOpen = this.slashPopup && !this.slashPopup.classList.contains('hidden');
        const emoteOpen = this.emotePopup && !this.emotePopup.classList.contains('hidden');
        if (slashOpen || emoteOpen) return;
        e.preventDefault();
        this._submitMessage();
    }

    _submitMessage() {
        const message = this.inputField.value.trim();
        if (!message) return;
        if (message.startsWith('/')) {
            this.chatClient.sendCommand(message);
        } else {
            this.chatClient.sendMessage(message);
        }
        this.inputField.value = '';
        this._autoResizeInput();
        this._hideSlashPopup();
        this._hideEmoteAutocomplete();
    }

    _autoResizeInput() {
        const el = this.inputField;
        if (!el || el.tagName !== 'TEXTAREA') return;
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 128) + 'px';
    }

    getRoleClass(data) {
        const role = data.role || (data.is_staff ? 'admin' : 'user');
        return ROLE_COLORS[role] || ROLE_COLORS.user;
    }

    appendMessage(data) {
        if (!this.messageContainer) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message text-youtube-primary py-1 break-words';

        if (data.viewing_stream) {
            messageDiv.dataset.viewingStream = data.viewing_stream;
        }
        messageDiv.dataset.username = data.user;
        messageDiv.dataset.role = data.role || (data.is_staff ? 'admin' : 'user');

        const userClass = this.getRoleClass(data);

        messageDiv.innerHTML = `
            <span class="chat-username ${userClass} mr-1 cursor-pointer hover:underline">${this._escapeHtml(data.user)}:</span>
            <span class="message-content text-gray-200">${data.message}</span>
        `;

        this._applyFiltersToElement(messageDiv);
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
        this.votedOptionId = data.voted_option_id || null;
        this.pollExpired = false;
        this.pollResultsPosted = false;
        this.currentPollResults = {
            question: data.question,
            results: data.options.map(o => ({ id: o.id, text: o.text, votes: o.votes || 0 })),
        };

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

        // Highlight the option the user already voted for (e.g. on reconnect)
        if (this.votedOptionId) {
            this._updateVoteHighlight(this.votedOptionId);
        }

        this.pollContainer.querySelector('.poll-dismiss').addEventListener('click', () => {
            this.pollContainer.innerHTML = '';
            this.activePollId = null;
            this.votedOptionId = null;
            if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
        });

        this.pollContainer.querySelectorAll('.poll-option').forEach(el => {
            el.addEventListener('click', () => {
                if (!this.activePollId || this.pollExpired) return;
                const optionId = parseInt(el.dataset.optionId);
                const pollId = parseInt(el.dataset.pollId);
                if (isNaN(optionId) || isNaN(pollId)) return;
                this.chatClient.sendVote(pollId, optionId);
                this._updateVoteHighlight(optionId);
            });
        });

        this._startPollTimer(expiresAt);
    }

    _updateVoteHighlight(optionId) {
        this.votedOptionId = optionId;
        if (!this.pollContainer) return;
        this.pollContainer.querySelectorAll('.poll-option').forEach(o => {
            o.style.outline = '';
            o.style.outlineOffset = '';
            o.style.borderRadius = '';
        });
        const selected = this.pollContainer.querySelector(`[data-option-id="${optionId}"]`);
        if (selected) {
            selected.style.outline = '2px solid white';
            selected.style.outlineOffset = '-2px';
            selected.style.borderRadius = '2px';
        }
    }

    updatePollResults(data) {
        if (!this.pollContainer || data.poll_id !== this.activePollId) return;

        // Keep currentPollResults in sync so timer-expiry has fresh data
        if (this.currentPollResults) {
            this.currentPollResults.results = data.results.map(r => ({ id: r.id, text: r.text, votes: r.votes }));
        }

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
        this.votedOptionId = null;
        this.pollExpired = false;
        this.currentPollResults = null;

        const totalVotes = data.results.reduce((sum, o) => sum + o.votes, 0);
        this.pollContainer.innerHTML = `
            <div class="poll-widget bg-[#1a1a2e] border border-gray-700 rounded p-3 mb-1">
                <div class="flex justify-between items-start">
                    <p class="text-gray-400 text-xs">Poll ended — ${totalVotes} vote${totalVotes !== 1 ? 's' : ''} cast. See results in chat.</p>
                    <button class="poll-dismiss text-gray-500 hover:text-white ml-2 text-lg leading-none flex-shrink-0" title="Dismiss">&times;</button>
                </div>
            </div>
        `;

        this.pollContainer.querySelector('.poll-dismiss').addEventListener('click', () => {
            this.pollContainer.innerHTML = '';
        });

        setTimeout(() => {
            if (this.pollContainer) {
                this.pollContainer.innerHTML = '';
            }
        }, 5000);
    }

    _showPollResultsInChat(question, results) {
        if (!this.messageContainer) return;

        const totalVotes = results.reduce((sum, o) => sum + o.votes, 0);
        const sorted = [...results].sort((a, b) => b.votes - a.votes);
        const winner = sorted[0];

        const winnerLine = winner && winner.votes > 0
            ? `<div class="font-bold text-white mb-1">Winner: ${this._escapeHtml(winner.text)} (${winner.votes} vote${winner.votes !== 1 ? 's' : ''})</div>`
            : `<div class="text-gray-400 mb-1">No votes were cast.</div>`;

        let breakdownHtml = results.map((opt, i) => {
            const pct = totalVotes > 0 ? Math.round(opt.votes / totalVotes * 100) : 0;
            const isWinner = opt.id === winner?.id && winner.votes > 0;
            return `<div class="${isWinner ? 'text-white font-semibold' : 'text-gray-300'} text-xs">${i + 1}. ${this._escapeHtml(opt.text)} — ${opt.votes} vote${opt.votes !== 1 ? 's' : ''} (${pct}%)</div>`;
        }).join('');

        const resultDiv = document.createElement('div');
        resultDiv.className = 'chat-info text-blue-400 py-1';
        resultDiv.innerHTML = `
            <div class="text-xs text-gray-400 mb-0.5">Poll ended: "${this._escapeHtml(question)}"</div>
            ${winnerLine}
            ${breakdownHtml}
        `;

        this.messageContainer.appendChild(resultDiv);
        this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
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
                this.pollExpired = true;
                timerEl.textContent = 'Waiting for results...';

                if (this.pollContainer) {
                    this.pollContainer.querySelectorAll('.poll-option').forEach(o => {
                        o.style.opacity = '0.6';
                        o.style.pointerEvents = 'none';
                        o.classList.remove('cursor-pointer', 'hover:brightness-125');
                    });
                }
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

    // --- Eye Toggle (stream viewer filter) ---

    _setupEyeToggle() {
        const btn = document.getElementById('eye-toggle-btn');
        if (!btn) return;
        btn.addEventListener('click', () => this.toggleEyeFilter());
    }

    toggleEyeFilter() {
        this.eyeFilterActive = !this.eyeFilterActive;
        const btn = document.getElementById('eye-toggle-btn');
        if (btn) {
            btn.classList.toggle('active', this.eyeFilterActive);
        }
        console.log('[EyeToggle] active:', this.eyeFilterActive, '| myStream:', this.chatClient.viewingStream);
        this._applyMessageFilters();
    }

    // Applies both dim filters (eye toggle + user highlight) to one message.
    _applyFiltersToElement(el) {
        const vs = el.dataset.viewingStream;
        const dimEye = this.eyeFilterActive && vs && vs !== this.chatClient.viewingStream;
        const isHighlightedUser = this.highlightedUser && el.dataset.username === this.highlightedUser;
        const dimUser = this.highlightedUser && !isHighlightedUser;
        el.classList.toggle('chat-message-dimmed', !!(dimEye || dimUser));
        el.classList.toggle('chat-message-highlighted', !!isHighlightedUser);
    }

    _applyMessageFilters() {
        if (!this.messageContainer) return;
        this.messageContainer.querySelectorAll('.chat-message').forEach(el => {
            this._applyFiltersToElement(el);
        });
    }

    toggleUserHighlight(username) {
        this.highlightedUser = (this.highlightedUser === username) ? null : username;
        this._applyMessageFilters();
    }

    // --- Slash Command Popup ---

    _setupSlashCommands() {
        if (!this.inputField) return;
        this.slashPopup = document.getElementById('slash-command-popup');
        this.slashList = document.getElementById('slash-command-list');
        if (!this.slashPopup || !this.slashList) return;

        this.inputField.addEventListener('input', () => this._onSlashInput());
        this.inputField.addEventListener('keydown', (e) => this._onSlashKeydown(e));
        document.addEventListener('click', (e) => {
            if (this.slashPopup && !this.slashPopup.contains(e.target) && e.target !== this.inputField) {
                this._hideSlashPopup();
            }
        });
    }

    _onSlashInput() {
        const val = this.inputField.value;
        if (!val.startsWith('/')) {
            this._hideSlashPopup();
            return;
        }
        const typed = val.split(' ')[0].toLowerCase();
        const matches = ChatUI.MOD_COMMANDS.filter(c => c.command.startsWith(typed));

        if (matches.length === 0 || val.includes(' ')) {
            this._hideSlashPopup();
            return;
        }

        this.slashHighlightIndex = 0;
        this._renderSlashPopup(matches);
    }

    _renderSlashPopup(matches) {
        this.slashList.innerHTML = '';
        matches.forEach((cmd, i) => {
            const row = document.createElement('div');
            row.className = 'slash-cmd-item' + (i === this.slashHighlightIndex ? ' highlighted' : '');
            row.innerHTML = `
                <span class="cmd-name">${cmd.command}</span><span class="cmd-usage">${this._escapeHtml(cmd.usage)}</span>
                <span class="cmd-desc">${this._escapeHtml(cmd.description)}</span>
            `;
            row.addEventListener('click', () => {
                this.inputField.value = cmd.command + ' ';
                this._hideSlashPopup();
                this.inputField.focus();
            });
            this.slashList.appendChild(row);
        });
        this.slashPopup.classList.remove('hidden');
        this._currentSlashMatches = matches;
    }

    _onSlashKeydown(e) {
        if (!this.slashPopup || this.slashPopup.classList.contains('hidden')) return;
        const matches = this._currentSlashMatches || [];
        if (matches.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.slashHighlightIndex = Math.min(this.slashHighlightIndex + 1, matches.length - 1);
            this._updateSlashHighlight();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.slashHighlightIndex = Math.max(this.slashHighlightIndex - 1, 0);
            this._updateSlashHighlight();
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            if (this.slashHighlightIndex >= 0 && this.slashHighlightIndex < matches.length) {
                const inputHasArgs = this.inputField.value.includes(' ');
                if (!inputHasArgs) {
                    e.preventDefault();
                    this.inputField.value = matches[this.slashHighlightIndex].command + ' ';
                    this._hideSlashPopup();
                }
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            this._hideSlashPopup();
        }
    }

    _updateSlashHighlight() {
        if (!this.slashList) return;
        const items = this.slashList.querySelectorAll('.slash-cmd-item');
        items.forEach((el, i) => {
            el.classList.toggle('highlighted', i === this.slashHighlightIndex);
        });
    }

    _hideSlashPopup() {
        if (this.slashPopup) {
            this.slashPopup.classList.add('hidden');
        }
        this.slashHighlightIndex = -1;
        this._currentSlashMatches = [];
    }

    // --- Emotes ---

    _loadEmotes() {
        fetch('/emotes/manifest/', { credentials: 'same-origin' })
            .then(r => (r.ok ? r.json() : { emotes: [] }))
            .then(data => {
                this.emotes = data.emotes || [];
                this.emoteMap = {};
                this.emoteCodes = [];
                this.emotes.forEach(e => {
                    this.emoteMap[e.code] = e;
                    this.emoteCodes.push(e.code);
                });
                // Longest-first so prefix matches favour the more specific code.
                this.emoteCodes.sort((a, b) => b.length - a.length);
                this.favoriteCodes = new Set(data.favorites || []);
            })
            .catch(() => { /* emotes are non-critical; chat still works */ });
    }

    _getWordAtCaret() {
        const input = this.inputField;
        const pos = input.selectionStart;
        const val = input.value;
        let start = pos;
        while (start > 0 && !/\s/.test(val[start - 1])) start--;
        let end = pos;
        while (end < val.length && !/\s/.test(val[end])) end++;
        return { word: val.slice(start, end), start, end };
    }

    _insertEmoteCode(code) {
        const input = this.inputField;
        const start = input.selectionStart ?? input.value.length;
        const end = input.selectionEnd ?? input.value.length;
        const val = input.value;
        const before = val.slice(0, start);
        const after = val.slice(end);
        const needLead = before.length > 0 && !/\s$/.test(before);
        const insert = (needLead ? ' ' : '') + code + ' ';
        input.value = before + insert + after;
        const caret = (before + insert).length;
        input.setSelectionRange(caret, caret);
        input.focus();
    }

    // Emote autocomplete popup (reuses the slash-popup look)

    _setupEmoteAutocomplete() {
        if (!this.inputField) return;
        this.emotePopup = document.getElementById('emote-autocomplete-popup');
        this.emoteList = document.getElementById('emote-autocomplete-list');
        if (!this.emotePopup || !this.emoteList) return;

        this.inputField.addEventListener('input', () => this._onEmoteInput());
        this.inputField.addEventListener('keydown', (e) => this._onEmoteKeydown(e));
        document.addEventListener('click', (e) => {
            if (this.emotePopup && !this.emotePopup.contains(e.target) && e.target !== this.inputField) {
                this._hideEmoteAutocomplete();
            }
        });
    }

    _onEmoteInput() {
        if (!this.emotePopup) return;
        // Defer to the slash-command popup when it is open.
        if (this.slashPopup && !this.slashPopup.classList.contains('hidden')) {
            this._hideEmoteAutocomplete();
            return;
        }
        const val = this.inputField.value;
        if (val.startsWith('/') || this.emoteCodes.length === 0) {
            this._hideEmoteAutocomplete();
            return;
        }
        const { word } = this._getWordAtCaret();
        if (word.length < 2) {
            this._hideEmoteAutocomplete();
            return;
        }
        const lower = word.toLowerCase();
        const matches = this.emoteCodes
            .filter(c => c.toLowerCase().startsWith(lower))
            .slice(0, 12);
        if (matches.length === 0) {
            this._hideEmoteAutocomplete();
            return;
        }
        this.emoteHighlightIndex = 0;
        this._renderEmoteAutocomplete(matches);
    }

    _renderEmoteAutocomplete(matches) {
        this.emoteList.innerHTML = '';
        matches.forEach((code, i) => {
            const row = document.createElement('div');
            row.className = 'slash-cmd-item emote-suggestion' + (i === this.emoteHighlightIndex ? ' highlighted' : '');
            const emote = this.emoteMap[code];
            row.innerHTML = `
                <img src="${emote.url}" alt="${this._escapeHtml(code)}" class="emote-suggestion-img">
                <span class="cmd-name">${this._escapeHtml(code)}</span>
            `;
            row.addEventListener('click', () => this._completeEmote(code));
            this.emoteList.appendChild(row);
        });
        this.emotePopup.classList.remove('hidden');
        this._currentEmoteMatches = matches;
    }

    _completeEmote(code) {
        const { start, end } = this._getWordAtCaret();
        const val = this.inputField.value;
        const insert = code + ' ';
        this.inputField.value = val.slice(0, start) + insert + val.slice(end);
        const caret = start + insert.length;
        this.inputField.setSelectionRange(caret, caret);
        this._hideEmoteAutocomplete();
        this.inputField.focus();
    }

    _onEmoteKeydown(e) {
        if (!this.emotePopup || this.emotePopup.classList.contains('hidden')) return;
        const matches = this._currentEmoteMatches || [];
        if (matches.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.emoteHighlightIndex = Math.min(this.emoteHighlightIndex + 1, matches.length - 1);
            this._updateEmoteHighlight();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.emoteHighlightIndex = Math.max(this.emoteHighlightIndex - 1, 0);
            this._updateEmoteHighlight();
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            e.preventDefault();
            const idx = this.emoteHighlightIndex >= 0 ? this.emoteHighlightIndex : 0;
            this._completeEmote(matches[idx]);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            this._hideEmoteAutocomplete();
        }
    }

    _updateEmoteHighlight() {
        if (!this.emoteList) return;
        this.emoteList.querySelectorAll('.emote-suggestion').forEach((el, i) => {
            el.classList.toggle('highlighted', i === this.emoteHighlightIndex);
        });
    }

    _hideEmoteAutocomplete() {
        if (this.emotePopup) this.emotePopup.classList.add('hidden');
        this.emoteHighlightIndex = -1;
        this._currentEmoteMatches = [];
    }

    // Emote picker (grid menu)

    _setupEmotePicker() {
        this.emotePickerBtn = document.getElementById('emote-picker-btn');
        this.emotePickerPopup = document.getElementById('emote-picker-popup');
        this.emotePickerGrid = document.getElementById('emote-picker-grid');
        this.emotePickerSearch = document.getElementById('emote-picker-search');
        if (!this.emotePickerBtn || !this.emotePickerPopup || !this.emotePickerGrid) return;

        this.emotePickerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._toggleEmotePicker();
        });
        if (this.emotePickerSearch) {
            this.emotePickerSearch.addEventListener('input', () => {
                this._renderEmotePicker(this.emotePickerSearch.value.trim().toLowerCase());
            });
        }
        document.addEventListener('click', (e) => {
            if (!this.emotePickerPopup.contains(e.target) && e.target !== this.emotePickerBtn) {
                this._hideEmotePicker();
            }
        });
        // Mobile: tap-and-hold a picker emote opens the emote modal.
        this._addLongPress(this.emotePickerGrid, (target) => {
            const item = target.closest('.emote-picker-item');
            if (item && item.dataset.code) this.openEmoteModal(item.dataset.code);
        });
    }

    _toggleEmotePicker() {
        if (this.emotePickerPopup.classList.contains('hidden')) {
            this._renderEmotePicker('');
            this.emotePickerPopup.classList.remove('hidden');
            if (this.emotePickerSearch) {
                this.emotePickerSearch.value = '';
                this.emotePickerSearch.focus();
            }
        } else {
            this._hideEmotePicker();
        }
    }

    _hideEmotePicker() {
        if (this.emotePickerPopup) this.emotePickerPopup.classList.add('hidden');
    }

    _renderEmotePicker(filter) {
        if (!this.emotePickerGrid) return;
        this.emotePickerGrid.innerHTML = '';
        const list = filter
            ? this.emotes.filter(e => e.code.toLowerCase().includes(filter))
            : this.emotes;
        if (list.length === 0) {
            this.emotePickerGrid.innerHTML = '<div class="emote-picker-empty">No emotes</div>';
            return;
        }
        const favs = list.filter(e => this.favoriteCodes.has(e.code));
        const rest = list.filter(e => !this.favoriteCodes.has(e.code));

        if (favs.length > 0) {
            this._appendPickerHeader('Favorites');
            favs.forEach(emote => this._appendPickerItem(emote, true));
            if (rest.length > 0) this._appendPickerHeader('All Emotes');
        }
        rest.forEach(emote => this._appendPickerItem(emote, false));
    }

    _appendPickerHeader(label) {
        const header = document.createElement('div');
        header.className = 'emote-picker-header';
        header.textContent = label;
        this.emotePickerGrid.appendChild(header);
    }

    _appendPickerItem(emote, pinned) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'emote-picker-item';
        btn.title = emote.code;
        btn.dataset.code = emote.code;
        const pinOverlay = pinned
            ? '<span class="emote-pin-icon"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 3a1 1 0 011 1v1.586l2.207 2.207a1 1 0 01-.083 1.49L15 12.5V17a1 1 0 01-.293.707L13 19.414V21a1 1 0 01-2 0v-1.586l-1.707-1.707A1 1 0 019 17v-4.5L4.876 9.283a1 1 0 01-.083-1.49L7 5.586V4a1 1 0 011-1h8z"/></svg></span>'
            : '';
        btn.innerHTML = `<img src="${emote.url}" alt="${this._escapeHtml(emote.code)}">${pinOverlay}`;
        btn.addEventListener('click', () => {
            this._insertEmoteCode(emote.code);
            this._hideEmotePicker();
        });
        btn.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.openEmoteModal(emote.code);
        });
        this.emotePickerGrid.appendChild(btn);
    }

    // --- Chat interactions (username click/right-click, emote right-click) ---

    _setupChatInteractions() {
        if (!this.messageContainer) return;

        this.messageContainer.addEventListener('click', (e) => {
            const nameEl = e.target.closest('.chat-username');
            if (nameEl) {
                const msgEl = nameEl.closest('.chat-message');
                if (msgEl && msgEl.dataset.username) {
                    this.toggleUserHighlight(msgEl.dataset.username);
                }
            }
        });

        this.messageContainer.addEventListener('contextmenu', (e) => {
            this._handleChatContextTarget(e.target) && e.preventDefault();
        });

        // Mobile: tap-and-hold mirrors right-click.
        this._addLongPress(this.messageContainer, (target) => {
            this._handleChatContextTarget(target);
        });
    }

    // Returns true if the target opened a modal (so contextmenu can preventDefault).
    _handleChatContextTarget(target) {
        const nameEl = target.closest && target.closest('.chat-username');
        if (nameEl) {
            const msgEl = nameEl.closest('.chat-message');
            if (msgEl) {
                this.openUserCard(msgEl);
                return true;
            }
        }
        const emoteEl = target.closest && target.closest('.inline-emote');
        if (emoteEl) {
            const code = emoteEl.getAttribute('alt');
            if (code && this.emoteMap[code]) {
                this.openEmoteModal(code);
                return true;
            }
        }
        return false;
    }

    _addLongPress(el, handler, delay = 500) {
        let timer = null;
        el.addEventListener('touchstart', (e) => {
            const target = e.target;
            timer = setTimeout(() => {
                timer = null;
                this._suppressNextClick = Date.now();
                handler(target);
            }, delay);
        }, { passive: true });
        ['touchmove', 'touchend', 'touchcancel'].forEach(ev => {
            el.addEventListener(ev, () => {
                if (timer) clearTimeout(timer);
                timer = null;
            }, { passive: true });
        });
    }

    // Positions a modal as a compact card anchored to the top of the chat
    // messages area, so it works in both the side-panel and popout layouts.
    // Height is capped; the messages list inside scrolls.
    _positionOverChat(modal) {
        const rect = this.messageContainer.getBoundingClientRect();
        modal.style.left = (rect.left + 8) + 'px';
        modal.style.top = (rect.top + 8) + 'px';
        modal.style.width = (rect.width - 16) + 'px';
        modal.style.maxHeight = Math.min(400, rect.height - 16) + 'px';
    }

    _roleLabel(role) {
        const labels = { admin: 'Admin', moderator: 'Moderator', subscriber: 'Subscriber', user: 'User' };
        return labels[role] || 'User';
    }

    // --- User card modal (right-click a username) ---

    _setupUserCardModal() {
        this.userCardModal = document.getElementById('user-card-modal');
        if (!this.userCardModal) return;
        const closeBtn = document.getElementById('user-card-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this._hideUserCard());
        const mentionBtn = document.getElementById('user-card-mention');
        if (mentionBtn) {
            mentionBtn.addEventListener('click', () => {
                if (this._userCardUsername) this.insertMention(this._userCardUsername);
                this._hideUserCard();
            });
        }
        this._setupModalDismiss(this.userCardModal, () => this._hideUserCard());
    }

    openUserCard(msgEl) {
        if (!this.userCardModal) return;
        const username = msgEl.dataset.username;
        const role = msgEl.dataset.role || 'user';
        const watching = msgEl.dataset.viewingStream || '';
        this._userCardUsername = username;

        const nameEl = document.getElementById('user-card-name');
        nameEl.textContent = username;
        nameEl.className = ROLE_COLORS[role] || ROLE_COLORS.user;

        document.getElementById('user-card-watching').textContent = watching || 'Unknown';
        document.getElementById('user-card-tier').textContent = this._roleLabel(role);

        const msgList = document.getElementById('user-card-messages');
        msgList.innerHTML = '';
        this.messageContainer.querySelectorAll('.chat-message').forEach(el => {
            if (el.dataset.username !== username) return;
            const content = el.querySelector('.message-content');
            if (!content) return;
            const row = document.createElement('div');
            row.className = 'user-card-msg';
            row.innerHTML = `<span class="${ROLE_COLORS[role] || ROLE_COLORS.user}">${this._escapeHtml(username)}:</span> <span class="text-gray-200">${content.innerHTML}</span>`;
            msgList.appendChild(row);
        });

        this._positionOverChat(this.userCardModal);
        this._modalOpenedAt = Date.now();
        this.userCardModal.classList.remove('hidden');
    }

    _hideUserCard() {
        if (this.userCardModal) this.userCardModal.classList.add('hidden');
    }

    // --- Emote modal (right-click an emote in chat or in the picker) ---

    _setupEmoteModal() {
        this.emoteModal = document.getElementById('emote-modal');
        if (!this.emoteModal) return;
        const closeBtn = document.getElementById('emote-modal-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this._hideEmoteModal());
        const starBtn = document.getElementById('emote-modal-star');
        if (starBtn) {
            starBtn.addEventListener('click', () => {
                if (this._emoteModalCode) this._toggleFavorite(this._emoteModalCode);
            });
        }
        this._setupModalDismiss(this.emoteModal, () => this._hideEmoteModal());
    }

    openEmoteModal(code) {
        if (!this.emoteModal) return;
        const emote = this.emoteMap[code];
        if (!emote) return;
        this._emoteModalCode = code;

        const img = document.getElementById('emote-modal-img');
        img.src = emote.url;
        img.alt = code;
        document.getElementById('emote-modal-code').textContent = code;
        this._updateEmoteModalStar();

        const rect = this.messageContainer.getBoundingClientRect();
        this.emoteModal.style.left = (rect.left + rect.width / 2) + 'px';
        this.emoteModal.style.top = (rect.top + rect.height / 2) + 'px';
        this._modalOpenedAt = Date.now();
        this.emoteModal.classList.remove('hidden');
    }

    _hideEmoteModal() {
        if (this.emoteModal) this.emoteModal.classList.add('hidden');
        this._emoteModalCode = null;
    }

    _updateEmoteModalStar() {
        const starBtn = document.getElementById('emote-modal-star');
        if (!starBtn || !this._emoteModalCode) return;
        const favorited = this.favoriteCodes.has(this._emoteModalCode);
        starBtn.classList.toggle('favorited', favorited);
        const label = starBtn.querySelector('.star-label');
        if (label) label.textContent = favorited ? 'Favorited' : 'Favorite';
    }

    _toggleFavorite(code) {
        const favorited = !this.favoriteCodes.has(code);
        // Optimistic update; reverted if the server rejects.
        if (favorited) this.favoriteCodes.add(code); else this.favoriteCodes.delete(code);
        this._updateEmoteModalStar();
        this._refreshPickerIfOpen();

        fetch('/emotes/favorite/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': this._getCookie('csrftoken'),
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({ code, favorited: String(favorited) }),
        }).then(r => {
            if (!r.ok) throw new Error('favorite toggle failed');
        }).catch(() => {
            if (favorited) this.favoriteCodes.delete(code); else this.favoriteCodes.add(code);
            this._updateEmoteModalStar();
            this._refreshPickerIfOpen();
        });
    }

    _refreshPickerIfOpen() {
        if (this.emotePickerPopup && !this.emotePickerPopup.classList.contains('hidden')) {
            const filter = this.emotePickerSearch ? this.emotePickerSearch.value.trim().toLowerCase() : '';
            this._renderEmotePicker(filter);
        }
    }

    // Shared dismiss behavior: click outside or Escape closes the modal. The
    // opening gesture itself is ignored via a short grace period, since a
    // long-press can emit a synthetic click right after the modal opens.
    _setupModalDismiss(modal, hide) {
        document.addEventListener('click', (e) => {
            if (modal.classList.contains('hidden')) return;
            if (Date.now() - (this._modalOpenedAt || 0) < 300) return;
            if (!modal.contains(e.target)) hide();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !modal.classList.contains('hidden')) hide();
        });
    }

    _getCookie(name) {
        const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

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

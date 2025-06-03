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
        
        // Bind methods
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
        
        // Start ping/pong keepalive
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
                    
                case 'error':
                    console.error('Chat error:', data.error);
                    if (this.onError) {
                        this.onError(data.error);
                    }
                    break;
                    
                case 'ping':
                    // Respond to server ping
                    this.send({
                        type: 'pong',
                        timestamp: Date.now()
                    });
                    break;
                    
                case 'pong':
                    // Clear pong timeout
                    if (this.pongTimeout) {
                        clearTimeout(this.pongTimeout);
                        this.pongTimeout = null;
                    }
                    break;
                    
                default:
                    // Legacy message format support
                    if (data.history) {
                        if (this.onHistory) {
                            this.onHistory(data.history);
                        }
                    } else if (data.message) {
                        if (this.onMessage) {
                            this.onMessage(data);
                        }
                    } else if (data.command === 'clear') {
                        if (this.onClear) {
                            this.onClear();
                        }
                    } else if (data.error) {
                        console.error('Chat error:', data.error);
                        if (this.onError) {
                            this.onError(data.error);
                        }
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
        
        // Attempt to reconnect unless it was a clean close
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
                // Send ping and set timeout for pong response
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
        
        this.setupEventHandlers();
    }
    
    init(containerSelector, formSelector, inputSelector, statusSelector = null) {
        this.messageContainer = document.querySelector(containerSelector);
        this.inputForm = document.querySelector(formSelector);
        this.inputField = document.querySelector(inputSelector);
        this.statusIndicator = statusSelector ? document.querySelector(statusSelector) : null;
        
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
        
        this.chatClient.onConnected = () => {
            this.updateStatus('connected');
        };
        
        this.chatClient.onDisconnected = () => {
            this.updateStatus('disconnected');
        };
        
        this.chatClient.onTimeout = (username, duration) => {
            this.showTimeout(username, duration);
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
    
    appendMessage(data) {
        if (!this.messageContainer) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message text-youtube-primary py-1';
        
        const timeStr = new Date(data.timestamp * 1000).toLocaleTimeString();
        const userClass = data.is_staff ? 'font-bold text-red-400' : 'font-semibold';
        
        messageDiv.innerHTML = `
            <span class="text-xs text-gray-400">[${timeStr}]</span>
            <span class="${userClass}">${data.user}:</span>
            <span class="message-content">${data.message}</span>
        `;
        
        this.messageContainer.appendChild(messageDiv);
        this.scrollToBottom();
        this.limitMessages();
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
    
    showTimeout(username, duration) {
        if (!this.messageContainer) return;
        
        const timeoutDiv = document.createElement('div');
        timeoutDiv.className = 'chat-timeout text-yellow-400 py-1 italic';
        timeoutDiv.textContent = `${username} has been timed out for ${duration} seconds`;
        
        this.messageContainer.appendChild(timeoutDiv);
        this.scrollToBottom();
    }
    
    updateStatus(status) {
        if (this.statusIndicator) {
            this.statusIndicator.className = `status-indicator ${status}`;
            this.statusIndicator.textContent = status === 'connected' ? '●' : '○';
        }
    }
    
    scrollToBottom() {
        if (this.messageContainer) {
            this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
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
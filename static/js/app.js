// Discussio - Main Application JavaScript

class Discussio {
    constructor() {
        this.apiBase = '/api';
        this.token = localStorage.getItem('token');
        this.userId = localStorage.getItem('userId');
        this.socket = null;
        this.currentRoom = null;
        this.whiteboardCanvas = null;
        this.whiteboardContext = null;
        this.isDrawing = false;

        this.init();
    }

    async init() {
        // Check if user is logged in
        if (!this.token) {
            window.location.href = '/auth';
            return;
        }

        // Initialize Socket.IO
        this.initSocket();

        // Setup event listeners
        this.setupEventListeners();

        // Load user profile
        await this.loadUserProfile();

        // Load groups
        await this.loadGroups();
    }

    initSocket() {
        this.socket = io({
            auth: {
                token: this.token
            }
        });

        this.socket.on('connect', () => {
            console.log('Connected to server');
        });

        this.socket.on('new_message', (data) => {
            this.handleNewMessage(data);
        });

        this.socket.on('draw_update', (data) => {
            this.handleDrawUpdate(data);
        });

        this.socket.on('user_typing', (data) => {
            this.handleUserTyping(data);
        });

        this.socket.on('user_joined', (data) => {
            console.log(`User ${data.user_id} joined`);
        });
    }

    setupEventListeners() {
        // Create Group Button
        document.getElementById('createGroupBtn').addEventListener('click', () => {
            new bootstrap.Modal(document.getElementById('createGroupModal')).show();
        });

        document.getElementById('createGroupSubmit').addEventListener('click', () => {
            this.createGroup();
        });

        // Logout Button
        document.getElementById('logoutBtn').addEventListener('click', () => {
            this.logout();
        });

        // Message Form
        document.getElementById('messageForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Whiteboard Canvas
        this.whiteboardCanvas = document.getElementById('whiteboardCanvas');
        if (this.whiteboardCanvas) {
            this.whiteboardContext = this.whiteboardCanvas.getContext('2d');
            this.setupWhiteboard();
        }

        // Clear Canvas Button
        document.getElementById('clearCanvas').addEventListener('click', () => {
            this.clearCanvas();
        });

        // Save Canvas Button
        document.getElementById('saveCanvas').addEventListener('click', () => {
            this.saveCanvas();
        });
    }

    setupWhiteboard() {
        const canvas = this.whiteboardCanvas;
        const ctx = this.whiteboardContext;

        canvas.addEventListener('mousedown', (e) => this.startDrawing(e));
        canvas.addEventListener('mousemove', (e) => this.draw(e));
        canvas.addEventListener('mouseup', () => this.stopDrawing());
        canvas.addEventListener('mouseout', () => this.stopDrawing());

        // Touch support
        canvas.addEventListener('touchstart', (e) => this.startDrawing(e));
        canvas.addEventListener('touchmove', (e) => this.draw(e));
        canvas.addEventListener('touchend', () => this.stopDrawing());
    }

    startDrawing(e) {
        this.isDrawing = true;
        const rect = this.whiteboardCanvas.getBoundingClientRect();
        const x = (e.clientX || e.touches[0].clientX) - rect.left;
        const y = (e.clientY || e.touches[0].clientY) - rect.top;

        this.whiteboardContext.beginPath();
        this.whiteboardContext.moveTo(x, y);
    }

    draw(e) {
        if (!this.isDrawing) return;

        const rect = this.whiteboardCanvas.getBoundingClientRect();
        const x = (e.clientX || e.touches[0].clientX) - rect.left;
        const y = (e.clientY || e.touches[0].clientY) - rect.top;

        this.whiteboardContext.lineTo(x, y);
        this.whiteboardContext.stroke();

        // Emit drawing update to other users
        this.socket.emit('whiteboard_draw', {
            room: this.currentRoom,
            user_id: this.userId,
            drawing_data: {
                x, y,
                action: 'draw'
            }
        });
    }

    stopDrawing() {
        this.isDrawing = false;
        this.whiteboardContext.closePath();
    }

    clearCanvas() {
        this.whiteboardContext.clearRect(0, 0, this.whiteboardCanvas.width, this.whiteboardCanvas.height);
    }

    async saveCanvas() {
        const dataUrl = this.whiteboardCanvas.toDataURL('image/png');
        const link = document.createElement('a');
        link.href = dataUrl;
        link.download = `whiteboard-${Date.now()}.png`;
        link.click();
    }

    async loadUserProfile() {
        try {
            const response = await fetch(`${this.apiBase}/users/profile`, {
                headers: this.getAuthHeaders()
            });

            if (!response.ok) throw new Error('Failed to load profile');

            const data = await response.json();
            console.log('User Profile:', data);
        } catch (error) {
            console.error('Error loading profile:', error);
        }
    }

    async loadGroups() {
        try {
            // Fetch user profile to get groups
            const response = await fetch(`${this.apiBase}/users/profile`, {
                headers: this.getAuthHeaders()
            });

            if (!response.ok) throw new Error('Failed to load groups');

            const data = await response.json();
            const groups = data.data.groups || [];

            const groupsList = document.getElementById('groupsList');
            groupsList.innerHTML = '';

            for (const groupId of groups) {
                const groupResponse = await fetch(`${this.apiBase}/groups/${groupId}`, {
                    headers: this.getAuthHeaders()
                });

                if (groupResponse.ok) {
                    const groupData = await groupResponse.json();
                    const group = groupData.data;

                    const groupElement = document.createElement('a');
                    groupElement.href = '#';
                    groupElement.className = 'list-group-item list-group-item-action';
                    groupElement.innerHTML = `
                        <i class="fas fa-users"></i> ${group.name}
                        <br>
                        <small class="text-muted">${group.members.length} members</small>
                    `;
                    groupElement.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.selectGroup(group);
                    });

                    groupsList.appendChild(groupElement);
                }
            }
        } catch (error) {
            console.error('Error loading groups:', error);
        }
    }

    selectGroup(group) {
        this.currentRoom = group._id;
        this.socket.emit('join_room', {
            room: group._id,
            user_id: this.userId
        });

        this.loadGroupChannels(group._id);
    }

    async loadGroupChannels(groupId) {
        try {
            const response = await fetch(`${this.apiBase}/groups/${groupId}/channels`, {
                headers: this.getAuthHeaders()
            });

            if (!response.ok) throw new Error('Failed to load channels');

            const data = await response.json();
            const channels = data.data;

            const mainContent = document.getElementById('mainContent');
            mainContent.innerHTML = '';

            channels.forEach(channel => {
                const channelCard = document.createElement('div');
                channelCard.className = 'card mb-3 cursor-pointer';
                channelCard.innerHTML = `
                    <div class="card-body">
                        <h5 class="card-title">
                            <i class="fas fa-hashtag"></i> ${channel.name}
                        </h5>
                        <p class="card-text text-muted">${channel.description}</p>
                        <button class="btn btn-sm btn-primary" onclick="Discussio.openChannel('${channel._id}')">
                            <i class="fas fa-comments"></i> Open Chat
                        </button>
                    </div>
                `;

                mainContent.appendChild(channelCard);
            });
        } catch (error) {
            console.error('Error loading channels:', error);
        }
    }

    async openChannel(channelId) {
        const chatModal = new bootstrap.Modal(document.getElementById('chatModal'));
        chatModal.show();

        this.currentRoom = channelId;
        this.socket.emit('join_room', {
            room: channelId,
            user_id: this.userId
        });

        await this.loadChannelMessages(channelId);
    }

    async loadChannelMessages(channelId) {
        try {
            const response = await fetch(`${this.apiBase}/messages/channel/${channelId}?page=1&per_page=20`, {
                headers: this.getAuthHeaders()
            });

            if (!response.ok) throw new Error('Failed to load messages');

            const data = await response.json();
            const messages = data.data.messages;

            const chatMessages = document.getElementById('chatMessages');
            chatMessages.innerHTML = '';

            messages.forEach(message => {
                this.displayMessage(message);
            });

            // Scroll to bottom
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } catch (error) {
            console.error('Error loading messages:', error);
        }
    }

    displayMessage(message) {
        const chatMessages = document.getElementById('chatMessages');
        const messageElement = document.createElement('div');
        messageElement.className = `message ${message.user_id === this.userId ? 'message-own' : 'message-other'} fade-in`;
        messageElement.innerHTML = `
            ${message.content}
            <div class="message-time">${new Date(message.created_at).toLocaleTimeString()}</div>
        `;

        chatMessages.appendChild(messageElement);
    }

    handleNewMessage(data) {
        if (data.user_id !== this.userId) {
            this.displayMessage({
                user_id: data.user_id,
                content: data.message,
                created_at: data.timestamp
            });
        }
    }

    handleDrawUpdate(data) {
        // Update whiteboard from other users
        if (data.user_id !== this.userId) {
            const drawing = data.drawing_data;
            this.whiteboardContext.lineTo(drawing.x, drawing.y);
            this.whiteboardContext.stroke();
        }
    }

    handleUserTyping(data) {
        if (data.user_id !== this.userId && data.is_typing) {
            console.log(`${data.user_id} is typing...`);
        }
    }

    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const content = messageInput.value.trim();

        if (!content) return;

        try {
            const response = await fetch(`${this.apiBase}/messages`, {
                method: 'POST',
                headers: {
                    ...this.getAuthHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    content,
                    channel_id: this.currentRoom,
                    group_id: this.currentRoom
                })
            });

            if (!response.ok) throw new Error('Failed to send message');

            messageInput.value = '';
            const data = await response.json();
            this.displayMessage(data.data);

            // Emit message via Socket.IO
            this.socket.emit('message', {
                room: this.currentRoom,
                user_id: this.userId,
                message: content
            });
        } catch (error) {
            console.error('Error sending message:', error);
            await showCustomAlert('Failed to send message', 'Error');
        }
    }

    async createGroup() {
        const name = document.getElementById('groupName').value.trim();
        const description = document.getElementById('groupDescription').value.trim();
        const isPrivate = document.getElementById('isPrivate').checked;

        if (!name) {
            await showCustomAlert('Please enter a group name', 'Validation Error');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/groups`, {
                method: 'POST',
                headers: {
                    ...this.getAuthHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name,
                    description,
                    is_private: isPrivate
                })
            });

            if (!response.ok) throw new Error('Failed to create group');

            bootstrap.Modal.getInstance(document.getElementById('createGroupModal')).hide();

            // Reset form
            document.getElementById('createGroupForm').reset();

            // Reload groups
            await this.loadGroups();

            await showCustomAlert('Group created successfully', 'Success');
        } catch (error) {
            console.error('Error creating group:', error);
            await showCustomAlert('Failed to create group', 'Error');
        }
    }

    async logout() {
        localStorage.removeItem('token');
        localStorage.removeItem('userId');
        window.location.href = '/auth';
    }

    getAuthHeaders() {
        return {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
        };
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.Discussio = new Discussio();
});

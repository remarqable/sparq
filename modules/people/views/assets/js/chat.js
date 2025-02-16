// Define the chatApp component before Alpine.js loads
window.chatApp = () => ({
    socket: null,
    currentChannel: document.querySelector('meta[name="default-channel"]')?.content || 'general',
    currentChannelDescription: document.querySelector('meta[name="default-channel-description"]')?.content || '',
    currentUserId: parseInt(document.querySelector('meta[name="user-id"]').content),
    apiUrls: JSON.parse(document.querySelector('meta[name="api-urls"]').content),
    showPinnedOnly: false,
    searchQuery: '',
    pinnedMessagesCount: 0,
    messageToDelete: null,
    channelToDelete: null,
    filteredMessages: '',
    messageContent: '',
    channelStates: {},

    initializeApp() {
        // Initialize channel states from meta tag data
        try {
            const channelData = JSON.parse(document.querySelector('meta[name="channel-data"]').content);
            this.channelStates = Object.fromEntries(
                channelData.channels.map(channel => [
                    channel.id,
                    {
                        unreadCount: channel.unreadCount,
                        description: channel.description,
                        name: channel.name
                    }
                ])
            );
        } catch (error) {
            console.error('Error initializing channel states:', error);
            this.channelStates = {};
        }

        this.initializeSocket();
        this.loadChannelMessages(this.currentChannel);
        this.initializeModals();
        this.initializeBootstrapComponents();
        
        // Add event listeners
        window.addEventListener('delete-channel', () => this.deleteChannel());
        window.addEventListener('create-channel', (e) => this.createChannel(e.detail));
        window.addEventListener('update-channel', (e) => this.updateChannel(e.detail));
    },

    getApiUrl(urlName, params = {}) {
        let url = this.apiUrls[urlName];
        if (!url) return null;
        
        Object.entries(params).forEach(([key, value]) => {
            url = url.replace(`:${key}`, value);
        });
        
        return url;
    },

    initializeSocket() {
        this.socket = io();
        
        this.socket.on('connect', () => {
            // Join all channels to receive updates
            Object.keys(this.channelStates).forEach(channelId => {
                const channelName = this.channelStates[channelId].name;
                if (channelName) {
                    this.socket.emit('join', { channel: channelName });
                }
            });
        });
        
        this.socket.on('chat_changed', (data) => {
            if (data.channel === this.currentChannel) {
                this.loadChannelMessages(this.currentChannel);
                // Update pin count if needed
                if (data.pinned !== undefined) {
                    this.$nextTick(() => {
                        this.updatePinCount();
                    });
                }
            }
        });
        
        this.socket.on('message_created', (data) => {
            // Find channel ID using the channel name
            const channelId = Object.keys(this.channelStates).find(id => 
                this.channelStates[id].name === data.channel
            );
            
            if (channelId && data.author_id !== this.currentUserId) {
                if (data.channel === this.currentChannel) {
                    // User is in the channel where message was created
                    // Just reload messages - don't mark as read yet
                    this.loadChannelMessages(this.currentChannel);
                } else {
                    // User is not in the channel, increment unread count
                    this.updateChannelUnreadCount(channelId, true, 1);
                }
            }
        });
    },

    async loadChannelMessages(channelName, beforeId = null) {
        try {
            let url = this.getApiUrl('get_messages', { channel: channelName });
            const params = new URLSearchParams();
            
            if (beforeId) {
                params.append('before_id', beforeId);
            }
            if (this.showPinnedOnly) {
                params.append('pinned_only', 'true');
            }
            if (this.searchQuery) {
                params.append('search', encodeURIComponent(this.searchQuery.trim()));
            }
            
            if (params.toString()) {
                url += '?' + params.toString();
            }
            
            const response = await fetch(url);
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || 'Failed to load messages');
            }
            const html = await response.text();
            
            this.filteredMessages = html;
            
            // Use $nextTick to ensure DOM is updated before scrolling
            this.$nextTick(() => {
                if (!beforeId) {  // Only scroll to bottom for new messages
                    this.scrollToBottom();
                }
                this.updatePinCount();
            });
        } catch (error) {
            console.error('Error loading messages:', error);
            this.filteredMessages = `<div class="text-center p-4 text-danger">
                <i class="fas fa-exclamation-circle me-2"></i>
                Error loading messages. Please try again.
            </div>`;
        }
    },

    scrollToBottom() {
        const chatMessages = this.$refs.chatMessages;
        if (chatMessages) {
            // Use requestAnimationFrame to ensure smooth scrolling after layout
            requestAnimationFrame(() => {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        }
    },
    
    getUnreadCount(channelId) {
        return this.channelStates[channelId]?.unreadCount || 0;
    },

    updateChannelUnreadCount(channelId, increment = true, amount = 1) {
        if (!this.channelStates[channelId]) {
            this.channelStates[channelId] = { 
                unreadCount: 0,
                description: '',
                name: ''
            };
        }
        
        if (increment) {
            this.channelStates[channelId].unreadCount += amount;
        } else {
            this.channelStates[channelId].unreadCount = Math.max(0, this.channelStates[channelId].unreadCount - amount);
        }
        
        // Store the updated count in local storage for persistence
        try {
            const unreadCounts = JSON.parse(localStorage.getItem('unreadCounts') || '{}');
            unreadCounts[channelId] = this.channelStates[channelId].unreadCount;
            localStorage.setItem('unreadCounts', JSON.stringify(unreadCounts));
        } catch (error) {
            console.error('Error updating local storage:', error);
        }
        
        // Force Alpine to recognize the change
        this.channelStates = { ...this.channelStates };
    },

    async markChannelRead(channelId, channelName) {
        try {
            const response = await fetch(this.getApiUrl('mark_read', { channel: channelName }), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) throw new Error('Failed to mark channel as read');
            
            this.updateChannelUnreadCount(channelId, false);
        } catch (error) {
            console.error('Error marking channel as read:', error);
        }
    },

    async switchChannel(channelName, channelId) {
        this.currentChannel = channelName;
        this.currentChannelDescription = this.channelStates[channelId].description;
        await this.loadChannelMessages(channelName);
        await this.markChannelRead(channelId, channelName);
    },

    async sendMessage(e) {
        e.preventDefault();
        if (!this.messageContent.trim()) return;
        
        try {
            const formData = new FormData();
            formData.append('content', this.messageContent);
            formData.append('channel', this.currentChannel);
            
            const response = await fetch(this.getApiUrl('create_message'), {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) throw new Error('Failed to send message');
            
            this.messageContent = '';
            this.loadChannelMessages(this.currentChannel);
        } catch (error) {
            console.error('Error sending message:', error);
        }
    },

    async createChannel(data) {
        try {
            const formData = new FormData();
            formData.append('name', data.name.trim());
            formData.append('description', data.description.trim());
            formData.append('is_private', data.isPrivate);

            const response = await fetch(this.getApiUrl('create_channel'), {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const text = await response.text();
                throw new Error(text);
            }
            
            this.hideModal('newChannelModal');
            window.location.reload();
        } catch (error) {
            console.error('Error creating channel:', error);
            alert('Error creating channel: ' + error.message);
        }
    },

    async updateChannel(data) {
        if (!this.currentChannel) return;
        
        try {
            const formData = new FormData();
            formData.append('description', data.description.trim());
            formData.append('is_private', data.isPrivate);

            const response = await fetch(this.getApiUrl('update_channel', { channel: this.currentChannel }), {
                method: 'PUT',
                body: formData
            });
            
            if (!response.ok) throw new Error('Failed to update channel');
            
            this.hideModal('editChannelModal');
            window.location.reload();
        } catch (error) {
            console.error('Error updating channel:', error);
            alert('Error updating channel: ' + error.message);
        }
    },

    handleMessageAction(action, messageId) {
        switch (action) {
            case 'delete':
                this.messageToDelete = messageId;
                const deleteModal = new bootstrap.Modal(document.getElementById('deleteModal'));
                deleteModal.show();
                break;
            case 'pin':
                this.toggleMessagePin(messageId);
                break;
            // Add other actions here
        }
    },

    async deleteMessage() {
        if (!this.messageToDelete) return;

        try {
            const response = await fetch(this.getApiUrl('delete_message', { id: this.messageToDelete }), {
                method: 'DELETE',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });
            
            if (!response.ok) throw new Error('Failed to delete message');
            
            this.hideModal('delete');
            this.messageToDelete = null;
            this.loadChannelMessages(this.currentChannel);
        } catch (error) {
            console.error('Error deleting message:', error);
            alert('Error deleting message: ' + error.message);
            this.hideModal('delete');
        }
    },

    async toggleMessagePin(messageId) {
        try {
            const response = await fetch(this.getApiUrl('toggle_pin', { id: messageId }), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) throw new Error('Failed to toggle pin');
            
            this.loadChannelMessages(this.currentChannel);
        } catch (error) {
            console.error('Error toggling pin:', error);
            alert('Error toggling pin: ' + error.message);
        }
    },

    confirmDeleteChannel(channelName) {
        this.channelToDelete = channelName;
        const deleteChannelModal = new bootstrap.Modal(document.getElementById('deleteChannelModal'));
        deleteChannelModal.show();
    },

    async deleteChannel() {
        if (!this.channelToDelete) return;
        
        try {
            const response = await fetch(this.getApiUrl('delete_channel', { channel: this.channelToDelete }), {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) throw new Error('Failed to delete channel');
            
            this.hideModal('deleteChannel');
            this.channelToDelete = null;
            window.location.reload();
        } catch (error) {
            console.error('Error deleting channel:', error);
            alert('Error deleting channel: ' + error.message);
            this.hideModal('deleteChannel');
        }
    },

    handleSearch() {
        // Debounce the search to avoid too many requests
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => {
            // Sanitize search query to remove problematic characters
            this.searchQuery = this.searchQuery.replace(/[^\w\s@.-]/g, '');
            this.loadChannelMessages(this.currentChannel);
        }, 300);
    },

    togglePinFilter() {
        this.showPinnedOnly = !this.showPinnedOnly;
        this.loadChannelMessages(this.currentChannel);
    },

    initializeModals() {
        // Initialize all modals
        document.querySelectorAll('.modal').forEach(modalEl => {
            if (!modalEl._modal) {
                modalEl._modal = new bootstrap.Modal(modalEl);
            }
        });
    },

    initializeBootstrapComponents() {
        this.$nextTick(() => {
            // Initialize tooltips
            document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
                if (el._tooltip) {
                    el._tooltip.dispose();
                }
                el._tooltip = new bootstrap.Tooltip(el);
            });
        });
    },

    updatePinCount() {
        this.$nextTick(() => {
            this.pinnedMessagesCount = document.querySelectorAll('.message.pinned').length;
        });
    },

    hideModal(modalId) {
        const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
        if (modal) {
            modal.hide();
        }
    },

    async loadMoreMessages(beforeId) {
        try {
            let url = this.getApiUrl('get_messages', { channel: this.currentChannel });
            if (beforeId) {
                url += `?before_id=${beforeId}`;
            }
            
            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to load messages');
            const html = await response.text();
            
            // Create a temporary container
            const temp = document.createElement('div');
            temp.innerHTML = html;
            
            // Get the chat messages container
            const chatMessages = this.$refs.chatMessages;
            const loadMoreBtn = chatMessages.querySelector('.load-more-messages');
            
            // Remove the old "Load More" button if it exists
            if (loadMoreBtn) {
                loadMoreBtn.remove();
            }
            
            // Insert the new messages at the top
            Array.from(temp.children).forEach(child => {
                chatMessages.insertBefore(child, chatMessages.firstChild);
            });
        } catch (error) {
            console.error('Error loading more messages:', error);
        }
    }
});

document.addEventListener('alpine:init', () => {
    // Register the chatApp component
    Alpine.data('chatApp', window.chatApp);

    Alpine.data('newChannelModal', () => ({
        name: '',
        description: '',
        isPrivate: false,
        
        submit(e) {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent('create-channel', {
                detail: {
                    name: this.name,
                    description: this.description,
                    isPrivate: this.isPrivate
                }
            }));
        }
    }));

    Alpine.data('editChannelModal', () => ({
        description: '',
        isPrivate: false,
        
        updateChannel(e) {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent('update-channel', {
                detail: {
                    description: this.description,
                    isPrivate: this.isPrivate
                }
            }));
        }
    }));
}); 
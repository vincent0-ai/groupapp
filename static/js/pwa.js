// PWA (Progressive Web App) Support

class PWAManager {
    constructor() {
        this.deferredPrompt = null;
        this.registerServiceWorker();
        this.setupInstallPrompt();
        this.setupOnlineStatusListener();
        this.initDatabase();
        this.setupPushNotifications();
    }

    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                // Register service worker from root (served by Flask route)
                const registration = await navigator.serviceWorker.register('/service-worker.js', {
                    scope: '/'
                });
                console.log('Service Worker registered:', registration);
                this.swRegistration = registration;
                
                // Check for updates periodically
                setInterval(() => registration.update(), 60 * 60 * 1000); // Every hour
            } catch (error) {
                console.error('Service Worker registration failed:', error);
            }
        }
    }
    
    // Push Notifications Setup
    async setupPushNotifications() {
        // Wait for service worker to be ready
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.log('Push notifications not supported');
            return;
        }
        
        // Check if already subscribed
        await this.checkPushSubscription();
    }
    
    async checkPushSubscription() {
        try {
            const registration = await navigator.serviceWorker.ready;
            const subscription = await registration.pushManager.getSubscription();
            
            if (subscription) {
                console.log('Already subscribed to push notifications');
                return subscription;
            }
            
            return null;
        } catch (error) {
            console.error('Error checking push subscription:', error);
            return null;
        }
    }
    
    async subscribeToPush() {
        try {
            const permission = await this.requestNotificationPermission();
            if (!permission) {
                console.log('Notification permission denied');
                return false;
            }
            
            // For now, use browser's native Notification API
            // This allows local notifications without requiring VAPID/server push
            // Store subscription status in localStorage
            localStorage.setItem('notifications_enabled', 'true');
            
            // Notify server about preference
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    await fetch('/api/users/push-subscription', {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${token}`,
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            subscription: { type: 'browser', enabled: true }
                        })
                    });
                } catch (err) {
                    console.log('Server notification update skipped:', err);
                }
            }
            
            console.log('Notifications enabled successfully');
            return true;
        } catch (error) {
            console.error('Notification setup failed:', error);
            return false;
        }
    }
    
    async sendSubscriptionToServer(subscription) {
        const token = localStorage.getItem('token');
        if (!token) return;
        
        try {
            await fetch('/api/users/push-subscription', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    subscription: subscription
                })
            });
        } catch (error) {
            console.error('Failed to save push subscription:', error);
        }
    }
    
    async unsubscribeFromPush() {
        try {
            localStorage.removeItem('notifications_enabled');
            
            // Notify server
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    await fetch('/api/users/push-subscription', {
                        method: 'DELETE',
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                } catch (err) {
                    console.log('Server unsubscribe skipped:', err);
                }
            }
            
            return true;
        } catch (error) {
            console.error('Unsubscribe failed:', error);
            return false;
        }
    }
    
    isNotificationsEnabled() {
        return localStorage.getItem('notifications_enabled') === 'true' && 
               Notification.permission === 'granted';
    }

    setupInstallPrompt() {
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            this.showInstallBanner();
        });

        window.addEventListener('appinstalled', () => {
            console.log('PWA was installed');
            this.hideInstallBanner();
            this.deferredPrompt = null;
        });
    }

    showInstallBanner() {
        // Check if user dismissed before (within 7 days)
        const dismissed = localStorage.getItem('pwa-install-dismissed');
        if (dismissed && Date.now() - parseInt(dismissed) < 7 * 24 * 60 * 60 * 1000) {
            return;
        }

        // Remove existing banner if any
        const existing = document.querySelector('.pwa-install-banner');
        if (existing) existing.remove();

        const banner = document.createElement('div');
        banner.className = 'pwa-install-banner';
        banner.innerHTML = `
            <div class="pwa-install-content">
                <div class="pwa-install-icon">
                    <i class="fas fa-graduation-cap"></i>
                </div>
                <div class="pwa-install-text">
                    <h6>Install Discussio</h6>
                    <p>Add to home screen for quick access</p>
                </div>
                <div class="pwa-install-actions">
                    <button id="pwaInstallBtn" class="btn btn-primary btn-sm">
                        <i class="fas fa-download me-1"></i> Install
                    </button>
                    <button id="pwaDismissBtn" class="btn btn-link btn-sm text-muted">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;

        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            .pwa-install-banner {
                position: fixed;
                bottom: 80px;
                left: 50%;
                transform: translateX(-50%);
                background: white;
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
                padding: 12px 16px;
                z-index: 9999;
                animation: slideUp 0.3s ease;
                max-width: 360px;
                width: calc(100% - 32px);
            }
            @keyframes slideUp {
                from { transform: translateX(-50%) translateY(100px); opacity: 0; }
                to { transform: translateX(-50%) translateY(0); opacity: 1; }
            }
            .pwa-install-content {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .pwa-install-icon {
                width: 48px;
                height: 48px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 1.25rem;
            }
            .pwa-install-text {
                flex: 1;
            }
            .pwa-install-text h6 {
                margin: 0;
                font-weight: 600;
                font-size: 0.95rem;
            }
            .pwa-install-text p {
                margin: 0;
                font-size: 0.8rem;
                color: #6c757d;
            }
            .pwa-install-actions {
                display: flex;
                align-items: center;
                gap: 4px;
            }
            @media (max-width: 400px) {
                .pwa-install-content {
                    flex-wrap: wrap;
                }
                .pwa-install-actions {
                    width: 100%;
                    justify-content: flex-end;
                    margin-top: 8px;
                }
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(banner);

        document.getElementById('pwaInstallBtn').addEventListener('click', () => this.installApp());
        document.getElementById('pwaDismissBtn').addEventListener('click', () => this.dismissInstall());
    }

    async installApp() {
        if (!this.deferredPrompt) return;
        
        this.deferredPrompt.prompt();
        const { outcome } = await this.deferredPrompt.userChoice;
        
        if (outcome === 'accepted') {
            console.log('PWA installed');
        }
        this.deferredPrompt = null;
        this.hideInstallBanner();
    }

    dismissInstall() {
        localStorage.setItem('pwa-install-dismissed', Date.now().toString());
        this.hideInstallBanner();
    }

    hideInstallBanner() {
        const banner = document.querySelector('.pwa-install-banner');
        if (banner) {
            banner.style.animation = 'slideDown 0.3s ease forwards';
            setTimeout(() => banner.remove(), 300);
        }
    }

    // Request notification permission
    async requestNotificationPermission() {
        if (!('Notification' in window)) return false;
        
        if (Notification.permission === 'granted') return true;
        if (Notification.permission === 'denied') return false;
        
        const permission = await Notification.requestPermission();
        return permission === 'granted';
    }

    // Send local notification
    sendNotification(title, options = {}) {
        if ('Notification' in window && Notification.permission === 'granted') {
            const notification = new Notification(title, {
                icon: '/static/images/icon-192.png',
                badge: '/static/images/badge-72.png',
                ...options
            });
            
            notification.onclick = () => {
                window.focus();
                notification.close();
                if (options.url) {
                    window.location.href = options.url;
                }
            };
        }
    }

    // Initialize IndexedDB for offline storage
    async initDatabase() {
        this.db = await this.openDatabase();
    }

    openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open('Discussio', 2);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Pending messages store
                if (!db.objectStoreNames.contains('pendingMessages')) {
                    db.createObjectStore('pendingMessages', { keyPath: 'id', autoIncrement: true });
                }
                
                // Cached messages store for offline viewing
                if (!db.objectStoreNames.contains('cachedMessages')) {
                    const store = db.createObjectStore('cachedMessages', { keyPath: '_id' });
                    store.createIndex('group_id', 'group_id', { unique: false });
                }
                
                // Notifications store
                if (!db.objectStoreNames.contains('notifications')) {
                    const notifStore = db.createObjectStore('notifications', { keyPath: 'id', autoIncrement: true });
                    notifStore.createIndex('read', 'read', { unique: false });
                    notifStore.createIndex('created_at', 'created_at', { unique: false });
                }
            };
        });
    }

    // Cache messages for offline viewing
    async cacheMessages(groupId, messages) {
        if (!this.db) return;
        
        const tx = this.db.transaction('cachedMessages', 'readwrite');
        const store = tx.objectStore('cachedMessages');
        
        for (const msg of messages) {
            msg.group_id = groupId;
            await store.put(msg);
        }
    }

    // Get cached messages when offline
    async getCachedMessages(groupId) {
        if (!this.db) return [];
        
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('cachedMessages', 'readonly');
            const store = tx.objectStore('cachedMessages');
            const index = store.index('group_id');
            const request = index.getAll(groupId);
            
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    }

    // Save pending message for offline sending
    async savePendingMessage(message) {
        if (!this.db) return;
        
        const tx = this.db.transaction('pendingMessages', 'readwrite');
        const store = tx.objectStore('pendingMessages');
        await store.add({ ...message, timestamp: Date.now() });
        
        // Request background sync
        if ('serviceWorker' in navigator && 'sync' in navigator.serviceWorker) {
            const registration = await navigator.serviceWorker.ready;
            await registration.sync.register('sync-messages');
        }
    }

    // Online status listener
    setupOnlineStatusListener() {
        const updateOnlineStatus = () => {
            const isOnline = navigator.onLine;
            document.body.classList.toggle('offline', !isOnline);
            
            // Show offline indicator
            let indicator = document.getElementById('offlineIndicator');
            if (!isOnline) {
                if (!indicator) {
                    indicator = document.createElement('div');
                    indicator.id = 'offlineIndicator';
                    indicator.innerHTML = '<i class="fas fa-wifi-slash me-2"></i>You are offline';
                    indicator.style.cssText = `
                        position: fixed;
                        top: 60px;
                        left: 50%;
                        transform: translateX(-50%);
                        background: #f59e0b;
                        color: white;
                        padding: 8px 16px;
                        border-radius: 20px;
                        font-size: 0.85rem;
                        z-index: 9999;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    `;
                    document.body.appendChild(indicator);
                }
            } else if (indicator) {
                indicator.remove();
                this.syncOfflineData();
            }
        };

        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);
        updateOnlineStatus();
    }

    async syncOfflineData() {
        if ('serviceWorker' in navigator && 'sync' in navigator.serviceWorker) {
            const registration = await navigator.serviceWorker.ready;
            await registration.sync.register('sync-messages');
        }
    }
}

// Initialize PWA when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.pwaManager = new PWAManager();
});

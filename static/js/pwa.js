// PWA (Progressive Web App) Support

class PWAManager {
    constructor() {
        this.registerServiceWorker();
        this.setupInstallPrompt();
        this.requestNotificationPermission();
    }

    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.register('/static/js/service-worker.js', {
                    scope: '/'
                });
                console.log('Service Worker registered:', registration);
            } catch (error) {
                console.error('Service Worker registration failed:', error);
            }
        }
    }

    setupInstallPrompt() {
        let deferredPrompt;

        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;

            // Show install banner
            const installBanner = document.createElement('div');
            installBanner.className = 'pwa-install-banner';
            installBanner.innerHTML = `
                <h6 class="mb-2">Install GroupApp</h6>
                <p class="mb-3">Get quick access to GroupApp on your device.</p>
                <button id="installBtn" class="btn btn-primary btn-sm me-2">Install</button>
                <button id="dismissBtn" class="btn btn-secondary btn-sm">Dismiss</button>
            `;

            document.body.appendChild(installBanner);

            document.getElementById('installBtn').addEventListener('click', async () => {
                if (deferredPrompt) {
                    deferredPrompt.prompt();
                    const choiceResult = await deferredPrompt.userChoice;
                    if (choiceResult.outcome === 'accepted') {
                        console.log('PWA installed');
                    }
                    deferredPrompt = null;
                    installBanner.remove();
                }
            });

            document.getElementById('dismissBtn').addEventListener('click', () => {
                installBanner.remove();
            });
        });

        // Hide banner when app is installed
        window.addEventListener('appinstalled', () => {
            console.log('PWA was installed');
        });
    }

    requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    sendNotification(title, options = {}) {
        if ('Notification' in window && Notification.permission === 'granted') {
            if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({
                    type: 'SHOW_NOTIFICATION',
                    title,
                    options
                });
            }
        }
    }

    // Offline data storage
    async saveOfflineMessage(message) {
        if ('indexedDB' in window) {
            const db = await this.openDatabase();
            const transaction = db.transaction(['pendingMessages'], 'readwrite');
            const store = transaction.objectStore('pendingMessages');
            store.add({
                ...message,
                id: Date.now()
            });
        }
    }

    openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open('groupapp', 1);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('pendingMessages')) {
                    db.createObjectStore('pendingMessages', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('cachedMessages')) {
                    db.createObjectStore('cachedMessages', { keyPath: 'id' });
                }
            };
        });
    }

    // Check online status
    setupOnlineStatusListener() {
        window.addEventListener('online', () => {
            console.log('User is online');
            this.syncOfflineData();
        });

        window.addEventListener('offline', () => {
            console.log('User is offline');
        });
    }

    async syncOfflineData() {
        if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({
                type: 'SYNC_DATA'
            });
        }
    }
}

// Initialize PWA when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.pwaManager = new PWAManager();
});

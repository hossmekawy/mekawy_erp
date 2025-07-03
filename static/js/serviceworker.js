const CACHE_NAME = 'mekawy-erp-v1.0.0';
const urlsToCache = [
    '/',
    '/dashboard/',
    '/suppliers/',
    '/warehouses/',
    '/production/',
    '/finance/',
    '/hr/',
    '/static/css/dashboard.css',
    '/static/js/app.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://unpkg.com/htmx.org@1.9.6',
    'https://cdn.jsdelivr.net/npm/chart.js'
];

// Install Service Worker
self.addEventListener('install', function(event) {
    console.log('Service Worker: Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
        .then(function(cache) {
            console.log('Service Worker: Caching files');
            return cache.addAll(urlsToCache);
        })
        .then(function() {
            console.log('Service Worker: Installed');
            return self.skipWaiting();
        })
    );
});

// Activate Service Worker
self.addEventListener('activate', function(event) {
    console.log('Service Worker: Activating...');
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames.map(function(cacheName) {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Service Worker: Deleting old cache', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(function() {
            console.log('Service Worker: Activated');
            return self.clients.claim();
        })
    );
});

// Fetch Event - Cache First Strategy
self.addEventListener('fetch', function(event) {
    // Skip cross-origin requests
    if (!event.request.url.startsWith(self.location.origin)) {
        return;
    }

    event.respondWith(
        caches.match(event.request)
        .then(function(response) {
            // Return cached version or fetch from network
            if (response) {
                console.log('Service Worker: Serving from cache', event.request.url);
                return response;
            }

            return fetch(event.request).then(function(response) {
                // Don't cache if not a valid response
                if (!response || response.status !== 200 || response.type !== 'basic') {
                    return response;
                }

                // Clone the response
                var responseToCache = response.clone();

                caches.open(CACHE_NAME)
                    .then(function(cache) {
                        cache.put(event.request, responseToCache);
                    });

                return response;
            }).catch(function() {
                // Return offline page for navigation requests
                if (event.request.mode === 'navigate') {
                    return caches.match('/offline/');
                }
            });
        })
    );
});

// Background Sync for offline data
self.addEventListener('sync', function(event) {
    if (event.tag === 'background-sync') {
        console.log('Service Worker: Background sync');
        event.waitUntil(syncOfflineData());
    }
});

// Push Notifications
self.addEventListener('push', function(event) {
    const options = {
        body: event.data ? event.data.text() : 'New notification from Mekawy ERP',
        icon: '/static/images/icons/icon-192x192.png',
        badge: '/static/images/icons/icon-72x72.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: 1
        },
        actions: [{
                action: 'explore',
                title: 'Open App',
                icon: '/static/images/icons/icon-192x192.png'
            },
            {
                action: 'close',
                title: 'Close',
                icon: '/static/images/icons/icon-192x192.png'
            }
        ]
    };

    event.waitUntil(
        self.registration.showNotification('Mekawy ERP', options)
    );
});

// Notification Click
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    if (event.action === 'explore') {
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});

// Sync offline data function
function syncOfflineData() {
    return new Promise(function(resolve, reject) {
        // Get offline data from IndexedDB and sync with server
        console.log('Syncing offline data...');
        // Implementation for syncing offline data
        resolve();
    });
}
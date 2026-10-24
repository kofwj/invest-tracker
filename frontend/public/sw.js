// Invest Tracker Service Worker
const CACHE_NAME = 'invest-tracker-v1.7.0';
const STATIC_ASSETS = [
  '/manifest.webmanifest',
  '/favicon.ico',
  '/pwa-192x192.png',
  '/pwa-512x512.png',
  '/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // 预先缓存离线备用 index.html 以及静态图标与清单
      return cache.addAll([...STATIC_ASSETS, '/index.html']);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. API 接口与健康探测、以及所有非 GET 请求：一律直连网络，绝不缓存账本财务数据
  if (request.method !== 'GET' || url.pathname.startsWith('/api') || url.pathname === '/health') {
    return;
  }

  // 2. 页面导航请求（/, /index.html 以及所有 SPA 深链路由如 /holdings）：
  // 必须走「网络优先」（严格尊重服务端 / nginx 对 index.html 的 no-store 强刷策略，发版即生效），
  // 仅在离线断网时回落至预缓存的 /index.html
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', responseClone));
          }
          return networkResponse;
        })
        .catch(() => {
          return caches.match('/index.html').then((cached) => {
            return cached || new Response('离线备用页面不可用', {
              status: 503,
              headers: { 'Content-Type': 'text/plain; charset=utf-8' }
            });
          });
        })
    );
    return;
  }

  // 3. 静态哈希资源与图标（/assets/* 或 manifest/icons）：缓存优先，并异步回源保鲜
  if (url.pathname.startsWith('/assets/') || STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetchPromise = fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
          }
          return networkResponse;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }
});

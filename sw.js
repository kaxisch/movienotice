const CACHE_VERSION = 'movienotice-v9';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const POSTER_CACHE = `${CACHE_VERSION}-posters`;
const API_CACHE = `${CACHE_VERSION}-api`;

const STATIC_ASSETS = [
  './',
  './index.html',
  './styles.css',
  './movie-page.css',
  './app.js',
  './data/movie-data.json',
  './manifest.webmanifest',
  './logo.svg',
  './favicon.svg',
  './apple-touch-icon.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-512-maskable.png',
];

const API_TTL = 24 * 60 * 60 * 1000; // 24 小時

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !k.startsWith(CACHE_VERSION))
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;

  if (url.hostname === 'image.tmdb.org') {
    e.respondWith(cacheFirst(e.request, POSTER_CACHE));
    return;
  }
  if (url.origin === self.location.origin) {
    if (url.pathname.startsWith(new URL('./data/', self.registration.scope).pathname)) {
      e.respondWith(networkFirst(e.request, STATIC_CACHE));
      return;
    }
    const isHtml = e.request.headers.get('accept') && e.request.headers.get('accept').includes('text/html');
    e.respondWith(isHtml ? networkFirst(e.request, STATIC_CACHE) : staleWhileRevalidate(e.request, STATIC_CACHE));
    return;
  }
});

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return new Response('', { status: 503 });
  }
}

async function cacheFirstWithTTL(request, cacheName, ttl) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) {
    const cachedAt = parseInt(cached.headers.get('sw-cached-at') || '0');
    if (Date.now() - cachedAt < ttl) return cached;
  }
  try {
    const response = await fetch(request);
    if (response.ok) {
      const headers = new Headers(response.headers);
      headers.set('sw-cached-at', Date.now().toString());
      const blob = await response.blob();
      const cachedResponse = new Response(blob, {
        status: response.status,
        statusText: response.statusText,
        headers: headers,
      });
      cache.put(request, cachedResponse.clone());
      return cachedResponse;
    }
    return response;
  } catch (err) {
    if (cached) return cached;
    return new Response('', { status: 503 });
  }
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    return cached || new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => cached);
  return cached || fetchPromise;
}

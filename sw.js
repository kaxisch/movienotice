const CACHE_VERSION = 'movienotice-v17';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const POSTER_CACHE = `${CACHE_VERSION}-posters`;

const STATIC_ASSETS = [
  './',
  './index.html',
  './styles.css',
  './legal.css',
  './privacy.html',
  './terms.html',
  './movie-page.css',
  './app-data.js',
  './app-ui.js',
  './app.js',
  './manifest.webmanifest?v=10',
  './logo.svg?v=10',
  './favicon.svg?v=10',
  './apple-touch-icon.png?v=10',
  './icons/icon-192.png?v=10',
  './icons/icon-512.png?v=10',
  './icons/icon-512-maskable.png?v=10',
];

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

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request, { cache: 'no-store' });
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

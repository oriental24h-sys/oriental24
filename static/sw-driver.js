/* v1.7.2 · Worker « app livreur » : coquille en cache, réseau d’abord pour l’API (jamais de données en cache). */
const CACHE='o24-driver-1.10.0';
const ASSETS=['/static/driver-app.js','/static/driver-app.css','/static/wordmark.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)))});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{const ks=await caches.keys();await Promise.all(ks.filter(k=>k!==CACHE&&k.startsWith('o24-driver-')).map(k=>caches.delete(k)));await self.clients.claim()})())});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.pathname.startsWith('/api/'))return;e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request)))});
self.addEventListener('message',e=>{if(e.data==='skip')self.skipWaiting()});

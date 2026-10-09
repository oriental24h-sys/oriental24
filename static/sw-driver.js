/* v1.14.0 · Worker « app livreur » : actualisation globale et règles colis à jour. Réseau d’abord pour l’API (jamais de données en cache). */
const CACHE='o24-driver-1.15.6-full-localization';
const ASSETS=['/static/driver-app.js?v=languages-help-treatment-2026-10-09-v2','/static/driver-app.css?v=languages-help-treatment-2026-10-09','/static/i18n-catalog.js?v=full-localization-2026-10-09-v3','/static/i18n.js?v=full-localization-2026-10-09-v9','/static/i18n-ui.css?v=languages-help-2026-10-09','/static/wordmark.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)))});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{const ks=await caches.keys();await Promise.all(ks.filter(k=>k!==CACHE&&k.startsWith('o24-driver-')).map(k=>caches.delete(k)));await self.clients.claim()})())});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.pathname.startsWith('/api/'))return;e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request)))});
self.addEventListener('message',e=>{if(e.data==='skip')self.skipWaiting()});

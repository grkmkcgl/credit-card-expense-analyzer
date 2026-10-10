/* Service worker: uygulamanın kendi dosyalarını telefonda saklar, böylece ana ekrandan internetsiz açılır.
   Yalnızca bu sitedeki uygulama dosyaları saklanır (APP_FILES); ekstreler ve harcama verisi asla buraya girmez.
   İnternet varsa en yeni sürüm alınır (3 sn içinde gelmezse kayıtlı sürüm açılır), yoksa kayıtlı sürüm açılır. */
const SCOPE = self.registration.scope;               // ör. https://…/ veya https://…/onizleme/<branch>/
const CACHE = "harcama-app:" + SCOPE;                // önizlemeler aynı sitede kendi önbelleğini kullanır
const APP_FILES = ["./", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"]
  .map(p => new URL(p, SCOPE).href);
const PAGE = APP_FILES[0];
const TIMEOUT_MS = 3000;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(APP_FILES.map(u => new Request(u, { cache: "reload" })))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  // Bu kapsamın eski adlı önbelleklerini temizle; diğer önizlemelerinkine dokunma
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith("harcama-app") && k.endsWith(SCOPE) && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url); url.search = ""; url.hash = "";
  const href = url.href === SCOPE + "index.html" ? PAGE : url.href;
  if (href === PAGE) e.respondWith(networkFirst(req));
  else if (APP_FILES.includes(href)) e.respondWith(caches.match(href).then(r => r || fetch(req)));
  // Diğer her şey (ör. /onizleme/ listesi) dokunulmadan geçer
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  const net = fetch(req, { cache: "no-cache" }).then(r => {
    if (r.ok && r.type === "basic") cache.put(PAGE, r.clone());
    return r;
  });
  net.catch(() => {});
  const timeout = new Promise(res => setTimeout(res, TIMEOUT_MS));
  try {
    const r = await Promise.race([net, timeout]);
    if (r) return r;
  } catch (_) { /* çevrimdışı */ }
  return (await cache.match(PAGE)) || net;
}

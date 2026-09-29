// 最小 service worker：仅为满足 PWA 可安装性（"安装到主屏幕"提示），不做离线缓存，
// 所有请求直接透传网络，避免回测数据被陈旧缓存污染。
self.addEventListener('install', function(e){ self.skipWaiting(); });
self.addEventListener('activate', function(e){ e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function(e){ e.respondWith(fetch(e.request)); });

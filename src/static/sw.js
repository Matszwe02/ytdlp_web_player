const cacheName = 'offline_cache';


self.addEventListener("install", (event) =>
{
    console.log('[Service Worker] Install event: Service worker installed.');
});


function isCacheable(request)
{
    return !request.url.includes("?") && !request.url.includes("hls_stream");
}

async function cacheFirstWithRefresh(request)
{
    const fetchResponsePromise = fetch(request).then(async (networkResponse) =>
    {
        if (networkResponse.ok)
        {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
    }).catch(error =>
    {
        throw error;
    });

    return (await caches.match(request)) || (await fetchResponsePromise);
}

self.addEventListener("fetch", (event) =>
{
    if (isCacheable(event.request))
    {
        event.respondWith(cacheFirstWithRefresh(event.request));
    }
});

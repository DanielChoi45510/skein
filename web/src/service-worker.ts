/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

// App shell: precached per version, served cache-first.
// Feed JSON (…/feed/…): network-first with the last copy as offline fallback.
// Nothing else (in particular, no third-party article pages) is cached.

import { build, files, prerendered, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;

const SHELL_CACHE = `shell-${version}`;
const FEED_CACHE = 'feed';

const isFeed = (pathname: string) => pathname.includes('/feed/');
// A dev copy of the feed may sit in static/; never precache it.
const SHELL = [...build, ...files.filter((f) => !isFeed(f)), ...prerendered];
const SHELL_SET = new Set(SHELL);

sw.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(SHELL_CACHE)
			.then((cache) => cache.addAll(SHELL))
			.then(() => sw.skipWaiting())
	);
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(
					keys.filter((k) => k !== SHELL_CACHE && k !== FEED_CACHE).map((k) => caches.delete(k))
				)
			)
			.then(() => sw.clients.claim())
	);
});

async function networkFirst(request: Request, cacheName: string): Promise<Response> {
	const cache = await caches.open(cacheName);
	try {
		const response = await fetch(request);
		if (response.ok) await cache.put(request, response.clone());
		return response;
	} catch (err) {
		const cached = await cache.match(request, { ignoreSearch: request.mode === 'navigate' });
		if (cached) return cached;
		throw err;
	}
}

sw.addEventListener('fetch', (event) => {
	const { request } = event;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	if (url.origin !== sw.location.origin) return; // article links etc.: browser default

	if (isFeed(url.pathname)) {
		event.respondWith(networkFirst(request, FEED_CACHE));
		return;
	}
	if (request.mode === 'navigate') {
		// Fresh page when online; the precached shell (matched without ?id=) when offline.
		event.respondWith(
			fetch(request).catch(async () => {
				const cache = await caches.open(SHELL_CACHE);
				return (
					(await cache.match(url.pathname)) ??
					(await cache.match(request, { ignoreSearch: true })) ??
					Response.error()
				);
			})
		);
		return;
	}
	if (SHELL_SET.has(url.pathname)) {
		event.respondWith(
			caches
				.open(SHELL_CACHE)
				.then((cache) => cache.match(url.pathname))
				.then((hit) => hit ?? fetch(request))
		);
	}
});

// Static, client-rendered app: pages are prerendered shells that load the feed
// JSON at runtime, so the hourly pipeline only has to replace feed/*.json.
export const prerender = true;
export const ssr = false;
export const trailingSlash = 'always';

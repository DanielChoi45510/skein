import { resolve } from '$app/paths';
import { SCHEMA_VERSION, type FeedIndex, type TopicFeed } from './types';

// The feed JSON is written next to the built site at deploy time (it isn't in
// static/ at build time), so its URL is built from the site root.
function feedUrl(path: string): string {
	const root = resolve('/');
	return `${root.endsWith('/') ? root : `${root}/`}feed/${path}`;
}

export class FeedError extends Error {}

async function getJson<T extends { schema_version: number }>(path: string): Promise<T> {
	let res: Response;
	try {
		// no-cache: revalidate with the server; the service worker falls back to the
		// last copy when offline.
		res = await fetch(feedUrl(path), { cache: 'no-cache' });
	} catch {
		throw new FeedError('Offline, and no saved copy of the feed yet.');
	}
	if (res.status === 404) throw new FeedError('Not found.');
	if (!res.ok) throw new FeedError(`The feed couldn't be loaded (HTTP ${res.status}).`);
	const data = (await res.json()) as T;
	if (data.schema_version !== SCHEMA_VERSION) {
		throw new FeedError('The feed format changed. Reload the page to update the app.');
	}
	return data;
}

export const fetchIndex = () => getJson<FeedIndex>('index.json');
export const fetchTopic = (id: string) => getJson<TopicFeed>(`topics/${encodeURIComponent(id)}.json`);

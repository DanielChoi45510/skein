// Read state: "last seen" per topic and per thread, in this browser only
// (DESIGN §9.2). Owner sync through the Worker arrives in Phase 2b.

import { allItems } from './group';
import type { ExportItem, TopicFeed } from './types';

const KEY = 'skein.lastSeen.v1'; // topic id → instant
const THREAD_KEY = 'skein.threadSeen.v1'; // thread id → instant

export type Store = Pick<Storage, 'getItem' | 'setItem'>;

/** localStorage when usable (it can be missing or throw in private modes), else memory. */
export function safeStorage(): Store {
	try {
		const s = globalThis.localStorage;
		const probe = `${KEY}.probe`;
		s.setItem(probe, '1');
		s.removeItem(probe);
		return s;
	} catch {
		const mem = new Map<string, string>();
		return {
			getItem: (k) => mem.get(k) ?? null,
			setItem: (k, v) => void mem.set(k, v)
		};
	}
}

export type LastSeen = Record<string, string>; // id → ISO instant

function load(key: string, store: Store): LastSeen {
	try {
		const parsed: unknown = JSON.parse(store.getItem(key) ?? '{}');
		if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
			return Object.fromEntries(
				Object.entries(parsed).filter(([, v]) => typeof v === 'string' && !isNaN(Date.parse(v)))
			) as LastSeen;
		}
	} catch {
		// corrupt value: start fresh
	}
	return {};
}

function save(key: string, seen: LastSeen, store: Store): void {
	try {
		store.setItem(key, JSON.stringify(seen));
	} catch {
		// storage full or blocked: read state just won't persist
	}
}

function mark(key: string, id: string, instant: string, store: Store): void {
	const seen = load(key, store);
	const prev = seen[id];
	if (prev && Date.parse(prev) >= Date.parse(instant)) return; // never move backwards
	seen[id] = instant;
	save(key, seen, store);
}

export const loadLastSeen = (store: Store = safeStorage()) => load(KEY, store);
export const markSeen = (topicId: string, instant: string, store: Store = safeStorage()) =>
	mark(KEY, topicId, instant, store);

export const loadThreadSeen = (store: Store = safeStorage()) => load(THREAD_KEY, store);
export const markThreadSeen = (threadId: string, instant: string, store: Store = safeStorage()) =>
	mark(THREAD_KEY, threadId, instant, store);

/**
 * Threads never opened start from the topic's previous visit, so a thread card's
 * "N new" and the thread page's "N updates since your last visit" agree.
 * Opened threads keep their own time. Nothing happens on a first topic visit.
 */
export function seedThreadSeen(
	threadIds: string[],
	topicPreviousVisit: string | undefined,
	store: Store = safeStorage()
): void {
	if (topicPreviousVisit === undefined) return;
	const seen = load(THREAD_KEY, store);
	let changed = false;
	for (const id of threadIds) {
		if (seen[id] === undefined) {
			seen[id] = topicPreviousVisit;
			changed = true;
		}
	}
	if (changed) save(THREAD_KEY, seen, store);
}

/** New = first seen by the pipeline after the topic was last opened (or never opened). */
export function isNew(item: ExportItem, lastSeen: string | undefined): boolean {
	return lastSeen === undefined || Date.parse(item.first_seen_at) > Date.parse(lastSeen);
}

/** New items that are shown (collapsed ones sit behind "+N more" and don't count). */
export function newCount(items: ExportItem[], lastSeen: string | undefined): number {
	return items.filter((i) => !i.collapsed && isNew(i, lastSeen)).length;
}

export function latestFirstSeen(items: ExportItem[]): string | undefined {
	let best: string | undefined;
	for (const i of items) {
		if (best === undefined || Date.parse(i.first_seen_at) > Date.parse(best)) best = i.first_seen_at;
	}
	return best;
}

/** How many of these first-seen instants are after `lastSeen` (all of them if never seen). */
export function newSince(instants: string[], lastSeen: string | undefined): number {
	if (lastSeen === undefined) return instants.length;
	const since = Date.parse(lastSeen);
	return instants.filter((t) => Date.parse(t) > since).length;
}

/** New shown items in a topic: its single items plus every listed thread's. */
export function topicNewCount(feed: TopicFeed, lastSeen: string | undefined): number {
	return (
		newCount(allItems(feed.days), lastSeen) +
		feed.threads.reduce((n, t) => n + newSince(t.first_seen, lastSeen), 0)
	);
}

/** Newest first_seen_at in a topic, thread items included (what "seen" moves to). */
export function topicLatestFirstSeen(feed: TopicFeed): string | undefined {
	let best = latestFirstSeen(allItems(feed.days));
	for (const t of feed.threads) {
		if (best === undefined || Date.parse(t.latest_first_seen_at) > Date.parse(best)) {
			best = t.latest_first_seen_at;
		}
	}
	return best;
}

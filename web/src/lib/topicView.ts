// Topic view layout for threaded modes (DESIGN §9.1): threads sorted by last
// update, cooling threads lower, dormant ones at the bottom. Pending threads
// aren't in `threads`; their items arrive as single items in `days` and are
// shown inline among the active threads (DESIGN §5).

import type { ExportItem, ThreadSummary, TopicFeed } from './types';
import { allItems } from './group';

/** Modes whose topic files list threads (the rest show a ranked list by day). */
export const THREADED_MODES = new Set(['threaded', 'question', 'tracker', 'fixed']);

export type Entry =
	| { kind: 'thread'; id: string; at: string; thread: ThreadSummary }
	| { kind: 'item'; id: string; at: string; item: ExportItem };

export interface TopicLayout {
	live: Entry[]; // active threads and single items, newest update first
	moreItems: ExportItem[]; // single items over the topic's cap ("+N more"), by importance
	cooling: ThreadSummary[]; // newest update first
	dormant: ThreadSummary[]; // newest update first; collapsed by default
}

const newestFirst = (a: { at: string; id: string }, b: { at: string; id: string }) =>
	Date.parse(b.at) - Date.parse(a.at) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

const byUpdate = (a: ThreadSummary, b: ThreadSummary) =>
	newestFirst({ at: a.last_item_at, id: a.id }, { at: b.last_item_at, id: b.id });

export function isThreaded(feed: TopicFeed): boolean {
	return THREADED_MODES.has(feed.mode);
}

export function topicLayout(feed: TopicFeed): TopicLayout {
	const items = allItems(feed.days);
	const live: Entry[] = [
		...feed.threads
			.filter((t) => t.state === 'active')
			.map((t): Entry => ({ kind: 'thread', id: t.id, at: t.last_item_at, thread: t })),
		...items
			.filter((i) => !i.collapsed)
			.map((i): Entry => ({ kind: 'item', id: i.id, at: i.published_at, item: i }))
	].sort(newestFirst);
	return {
		live,
		moreItems: items.filter((i) => i.collapsed).sort((a, b) => b.importance - a.importance),
		cooling: feed.threads.filter((t) => t.state === 'cooling').sort(byUpdate),
		dormant: feed.threads.filter((t) => t.state === 'dormant').sort(byUpdate)
	};
}

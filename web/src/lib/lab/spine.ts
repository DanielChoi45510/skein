// Static mock of the "spine and branches" thread view (UI overhaul step 1).
// The export has no branch structure yet, so it's invented from a real thread:
// the spine is the thread's items in time order, every BRANCH_EVERY-th item
// hangs off the spine node before it as a "side development", and the topic's
// other threads are the related-thread spokes. Layout only, not a data model.

import { allItems } from '$lib/group';
import type { ExportItem, ThreadFeed, ThreadState, TopicFeed } from '$lib/types';

export const BRANCH_EVERY = 3;

export interface SpineNode {
	item: ExportItem;
	branches: ExportItem[];
}

export interface RelatedThread {
	id: string;
	title: string;
	itemCount: number;
	state: ThreadState;
	lastItemAt: string;
}

export interface Spine {
	id: string;
	topicId: string;
	title: string;
	state: ThreadState;
	createdAt: string;
	lastItemAt: string;
	nodes: SpineNode[]; // oldest first
	branchCount: number;
	related: RelatedThread[]; // newest update first
}

const byTime = (a: ExportItem, b: ExportItem) =>
	Date.parse(a.published_at) - Date.parse(b.published_at) || (a.id < b.id ? -1 : 1);

export function buildSpine(thread: ThreadFeed, topic: TopicFeed | null, maxRelated = 6): Spine {
	const items = allItems(thread.days).sort(byTime);
	const nodes: SpineNode[] = [];
	let branchCount = 0;
	items.forEach((item, i) => {
		const last = nodes.at(-1);
		if (last && i % BRANCH_EVERY === BRANCH_EVERY - 1) {
			last.branches.push(item);
			branchCount++;
		} else {
			nodes.push({ item, branches: [] });
		}
	});
	const related = (topic?.threads ?? [])
		.filter((t) => t.id !== thread.id)
		.sort((a, b) => Date.parse(b.last_item_at) - Date.parse(a.last_item_at))
		.slice(0, maxRelated)
		.map((t) => ({
			id: t.id,
			title: t.title,
			itemCount: t.item_count,
			state: t.state,
			lastItemAt: t.last_item_at
		}));
	return {
		id: thread.id,
		topicId: thread.topic_id,
		title: thread.title,
		state: thread.state,
		createdAt: thread.created_at,
		lastItemAt: thread.last_item_at,
		nodes,
		branchCount,
		related
	};
}

/**
 * The thread to show: the requested one if its topic lists it, else the
 * biggest thread of the requested topic, else the biggest thread anywhere.
 */
export function pickThread(
	topics: TopicFeed[],
	topicId: string | null,
	threadId: string | null
): { topicId: string; threadId: string } | null {
	const listed = topics.flatMap((t) => t.threads.map((th) => ({ topicId: t.id, th })));
	const exact = listed.find((x) => x.th.id === threadId);
	if (exact) return { topicId: exact.topicId, threadId: exact.th.id };
	const pool = listed.some((x) => x.topicId === topicId)
		? listed.filter((x) => x.topicId === topicId)
		: listed;
	const best = pool.sort((a, b) => b.th.item_count - a.th.item_count)[0];
	return best ? { topicId: best.topicId, threadId: best.th.id } : null;
}

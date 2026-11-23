// Tiny builders for the lab's unit tests (not a test file itself).
import type { ExportItem, FeedIndex, ThreadFeed, ThreadSummary, TopicFeed } from '$lib/types';

export function item(id: string, at: string, opts: Partial<ExportItem> = {}): ExportItem {
	return {
		id,
		title: id,
		url: `https://example.com/${id}`,
		source_id: 's',
		published_at: at,
		first_seen_at: at,
		excerpt: null,
		importance: 0.5,
		also_covered_by: [],
		collapsed: false,
		...opts
	};
}

export function threadSummary(
	id: string,
	last: string,
	opts: Partial<ThreadSummary> = {}
): ThreadSummary {
	return {
		id,
		title: id,
		kind: 'story',
		state: 'active',
		last_item_at: last,
		item_count: 2,
		collapsed_count: 0,
		latest_first_seen_at: last,
		first_seen: [last, last],
		latest: item(`${id}-latest`, last),
		...opts
	};
}

export function topic(
	id: string,
	mode: string,
	threads: ThreadSummary[],
	items: ExportItem[]
): TopicFeed {
	return {
		schema_version: 2,
		id,
		name: id,
		group: 'news',
		mode,
		threads,
		days: items.length ? [{ date: '2026-11-21', items }] : []
	};
}

export function threadFeed(id: string, topicId: string, items: ExportItem[]): ThreadFeed {
	return {
		schema_version: 2,
		id,
		topic_id: topicId,
		title: id,
		kind: 'story',
		state: 'active',
		created_at: items[0]?.published_at ?? '2026-11-20T00:00:00Z',
		last_item_at: items.at(-1)?.published_at ?? '2026-11-21T00:00:00Z',
		days: [{ date: '2026-11-21', items }]
	};
}

export function index(topics: { id: string; has_sources?: boolean }[]): FeedIndex {
	return {
		schema_version: 2,
		generated_at: '2026-11-21T12:00:00Z',
		groups: [
			{
				id: 'news',
				name: 'News',
				topics: topics.map((t) => ({
					id: t.id,
					name: t.id,
					mode: 'threaded',
					has_sources: t.has_sources ?? true,
					visible_count: 0,
					collapsed_count: 0,
					latest_first_seen_at: null
				}))
			}
		],
		sources: []
	};
}

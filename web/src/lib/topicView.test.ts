import { describe, expect, it } from 'vitest';
import { isThreaded, topicLayout } from './topicView';
import type { ExportItem, ThreadSummary, TopicFeed } from './types';

function item(id: string, published_at: string, importance = 0.5, collapsed = false): ExportItem {
	return {
		id,
		title: id,
		url: `https://example.com/${id}`,
		source_id: 's',
		published_at,
		first_seen_at: published_at,
		excerpt: null,
		importance,
		also_covered_by: [],
		collapsed
	};
}

function thread(id: string, state: ThreadSummary['state'], last_item_at: string): ThreadSummary {
	return {
		id,
		title: id,
		kind: 'story',
		state,
		last_item_at,
		item_count: 2,
		collapsed_count: 0,
		latest_first_seen_at: last_item_at,
		first_seen: [last_item_at],
		latest: item(`${id}-latest`, last_item_at)
	};
}

function feed(mode: string, threads: ThreadSummary[], items: ExportItem[]): TopicFeed {
	return {
		schema_version: 2,
		id: 'world',
		name: 'World',
		group: 'news',
		mode,
		threads,
		days: [{ date: '2026-11-21', items }]
	};
}

describe('topicLayout', () => {
	const f = feed(
		'threaded',
		[
			thread('active-old', 'active', '2026-11-21T08:00:00Z'),
			thread('dormant-new', 'dormant', '2026-11-05T00:00:00Z'),
			thread('active-new', 'active', '2026-11-21T11:00:00Z'),
			thread('cooling-a', 'cooling', '2026-11-17T00:00:00Z'),
			thread('cooling-b', 'cooling', '2026-11-18T00:00:00Z'),
			thread('dormant-old', 'dormant', '2026-11-01T00:00:00Z')
		],
		[
			item('single', '2026-11-21T09:00:00Z'),
			item('capped-low', '2026-11-21T10:00:00Z', 0.2, true),
			item('capped-high', '2026-11-21T07:00:00Z', 0.9, true)
		]
	);
	const layout = topicLayout(f);

	it('interleaves active threads and single items by last update', () => {
		expect(layout.live.map((e) => e.id)).toEqual(['active-new', 'single', 'active-old']);
		expect(layout.live.map((e) => e.kind)).toEqual(['thread', 'item', 'thread']);
	});

	it('puts cooling threads below, then dormant ones, each newest first', () => {
		expect(layout.cooling.map((t) => t.id)).toEqual(['cooling-b', 'cooling-a']);
		expect(layout.dormant.map((t) => t.id)).toEqual(['dormant-new', 'dormant-old']);
	});

	it('keeps capped single items behind "+N more", by importance', () => {
		expect(layout.moreItems.map((i) => i.id)).toEqual(['capped-high', 'capped-low']);
	});

	it('puts pinned threads first, whatever their state', () => {
		const pinned = (t: ThreadSummary): ThreadSummary => ({ ...t, pinned: true });
		const f2 = feed(
			'threaded',
			[
				pinned(thread('pin-dormant', 'dormant', '2026-11-01T00:00:00Z')),
				pinned(thread('pin-active', 'active', '2026-11-21T06:00:00Z')),
				thread('active', 'active', '2026-11-21T11:00:00Z')
			],
			[]
		);
		const l = topicLayout(f2);
		expect(l.pinned.map((t) => t.id)).toEqual(['pin-active', 'pin-dormant']);
		expect(l.live.map((e) => e.id)).toEqual(['active']);
		expect(l.dormant).toEqual([]);
	});

	it('handles a topic with nothing in it', () => {
		expect(topicLayout(feed('threaded', [], []))).toEqual({
			pinned: [],
			live: [],
			moreItems: [],
			cooling: [],
			dormant: []
		});
	});
});

describe('isThreaded', () => {
	it.each([
		['threaded', true],
		['question', true],
		['tracker', true],
		['fixed', true],
		['flat', false],
		['listings', false],
		['reading_list', false]
	])('%s → %s', (mode, expected) => {
		expect(isThreaded(feed(mode, [], []))).toBe(expected);
	});
});
